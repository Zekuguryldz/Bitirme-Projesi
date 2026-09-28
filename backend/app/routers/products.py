from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Annotated, Optional
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.models import PriceTimeSeries, Product
from app.schemas import CategoryListResponse, DateListResponse, ProductsListResponse
from app.services.shrinkflation import list_latest_product_comparisons


router = APIRouter(prefix="/products", tags=["Products"])
UNIT_PRICE_QUANTIZER = Decimal("0.0001")

CATEGORY_CANONICAL_KEYS = {
    "atistirmalik": "atistirmaliklar",
    "atistirmaliklar": "atistirmaliklar",
    "deterjan temizlik": "deterjan temizlik",
    "dondurma": "dondurma",
    "dondurulmus urunler": "dondurulmus urunler",
    "et tavuk balik": "et tavuk balik",
    "et tavuk sarkuteri": "et tavuk sarkuteri",
    "hazir yemek donuk": "hazir yemek donuk",
    "icecek": "icecekler",
    "icecekler": "icecekler",
    "kagit islak mendil": "kagit islak mendil",
    "kahvaltilik": "kahvaltilik",
    "kagit urunleri": "kagit urunleri",
    "meze hazir yemek donuk": "meze hazir yemek donuk",
    "sut kahvaltilik": "sut kahvaltilik",
    "temizlik": "temizlik",
    "yemeklik malzemeler": "yemeklik malzemeler",
}

CATEGORY_CANONICAL_LABELS = {
    "atistirmaliklar": "Atıştırmalıklar",
    "deterjan temizlik": "Deterjan ve Temizlik",
    "dondurma": "Dondurma",
    "dondurulmus urunler": "Dondurulmuş Ürünler",
    "et tavuk balik": "Et Tavuk Balık",
    "et tavuk sarkuteri": "Et Tavuk Şarküteri",
    "hazir yemek donuk": "Hazır Yemek ve Donuk",
    "icecekler": "İçecekler",
    "kagit islak mendil": "Kağıt ve Islak Mendil",
    "kahvaltilik": "Kahvaltılık",
    "kagit urunleri": "Kağıt Ürünleri",
    "meze hazir yemek donuk": "Meze, Hazır Yemek, Donuk",
    "sut kahvaltilik": "Süt ve Kahvaltılık",
    "temizlik": "Temizlik",
    "yemeklik malzemeler": "Yemeklik Malzemeler",
}

URUN_DURUMU_ZAMLANMIS = "zamlanmis_urunler"
URUN_DURUMU_INDIRIMDEKI = "indirimdeki_urunler"
URUN_DURUMU_SHRINKFLATION = "shrinkflation_riskli_urunler"
URUN_DURUMU_ESLESTIRMELERI = {
    "zamlanmis": URUN_DURUMU_ZAMLANMIS,
    "zamlanan": URUN_DURUMU_ZAMLANMIS,
    "zamlanan_urunler": URUN_DURUMU_ZAMLANMIS,
    "zamlanmis_urunler": URUN_DURUMU_ZAMLANMIS,
    "indirimdeki": URUN_DURUMU_INDIRIMDEKI,
    "indirimli": URUN_DURUMU_INDIRIMDEKI,
    "indirimdeki_urunler": URUN_DURUMU_INDIRIMDEKI,
    "indirimli_urunler": URUN_DURUMU_INDIRIMDEKI,
    "shrinkflation": URUN_DURUMU_SHRINKFLATION,
    "shrinkflation_riskli": URUN_DURUMU_SHRINKFLATION,
    "shrinkflation_riskli_urunler": URUN_DURUMU_SHRINKFLATION,
}


def normalize_text_expression(value):
    return func.lower(
        func.translate(
            value,
            "CGIOSUcgiosuÇĞİIÖŞÜçğıöşü",
            "cgiosucgiosucgiiosucgiosu",
        )
    )


def normalize_market_expression(value):
    normalized = normalize_text_expression(value)
    return case(
        (normalized.like("sok%"), "sok"),
        (normalized.like("migros%"), "migros"),
        else_=normalized,
    )


def normalize_market_value(value: str) -> str:
    lowered = fold_text(value)
    if lowered.startswith("sok"):
        return "sok"
    if lowered.startswith("migros"):
        return "migros"
    return lowered


def compact_text_expression(value):
    return func.trim(
        func.regexp_replace(
            func.regexp_replace(
                func.regexp_replace(
                    func.replace(normalize_text_expression(value), "&", " ve "),
                    r"[,/()\\-]+",
                    " ",
                    "g",
                ),
                r"\mve\M",
                " ",
                "g",
            ),
            r"\s+",
            " ",
            "g",
        )
    )


def normalize_category_expression(value):
    normalized = compact_text_expression(value)
    return case(
        *[
            (normalized == alias, canonical_key)
            for alias, canonical_key in CATEGORY_CANONICAL_KEYS.items()
        ],
        else_=normalized,
    )


def normalize_category_value(value: str) -> str:
    lowered = fold_text(value).replace("&", " ve ")
    for separator in [",", "/", "(", ")", "-"]:
        lowered = lowered.replace(separator, " ")
    lowered = lowered.replace("\\", " ")
    lowered = " ".join(token for token in lowered.split() if token != "ve")
    compacted = " ".join(lowered.split())
    return CATEGORY_CANONICAL_KEYS.get(compacted, compacted)


def canonical_category_label(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    stripped_value = value.strip()
    return CATEGORY_CANONICAL_LABELS.get(
        normalize_category_value(stripped_value),
        stripped_value,
    )


def deduplicate_category_labels(values: list[Optional[str]]) -> list[str]:
    unique_labels: dict[str, str] = {}
    for value in values:
        if not value:
            continue

        normalized_value = normalize_category_value(value)
        unique_labels.setdefault(
            normalized_value,
            canonical_category_label(value) or value.strip(),
        )

    return sorted(
        unique_labels.values(),
        key=lambda value: normalize_category_value(value),
    )


def fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return without_marks.translate(str.maketrans("çğıöşü", "cgiosu"))


def coerce_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return decimal_value if decimal_value.is_finite() else None


def normalize_measure_value(
    value,
    unit: Optional[str],
) -> tuple[Optional[Decimal], Optional[str]]:
    numeric_value = coerce_decimal(value)
    if numeric_value is None or not unit:
        return numeric_value, unit

    normalized_unit = unit.strip().lower()
    if normalized_unit in {"gr", "g"}:
        return numeric_value, "g"
    if normalized_unit == "kg":
        return numeric_value * Decimal("1000"), "g"
    if normalized_unit == "ml":
        return numeric_value, "ml"
    if normalized_unit in {"l", "lt"}:
        return numeric_value * Decimal("1000"), "ml"
    if normalized_unit in {"adet", "ad"}:
        return numeric_value, "adet"

    return numeric_value, unit


def compute_normalized_unit_price(
    price,
    normalized_measure_value,
    normalized_measure_unit: Optional[str],
) -> Optional[Decimal]:
    numeric_price = coerce_decimal(price)
    numeric_measure = coerce_decimal(normalized_measure_value)
    if (
        numeric_price is None
        or numeric_measure is None
        or numeric_measure <= 0
        or normalized_measure_unit not in {"g", "ml", "adet"}
    ):
        return None

    return (numeric_price / numeric_measure).quantize(
        UNIT_PRICE_QUANTIZER,
        rounding=ROUND_HALF_UP,
    )


def parse_product_datetime_range(value: str) -> tuple[datetime, datetime]:
    candidate = value.strip()

    try:
        normalized_candidate = candidate.replace("Z", "+00:00")
        parsed_datetime = datetime.fromisoformat(normalized_candidate)
        if parsed_datetime.tzinfo is None:
            parsed_datetime = parsed_datetime.replace(tzinfo=timezone.utc)
        if "T" in candidate:
            return parsed_datetime, parsed_datetime + timedelta(minutes=1)
        return parsed_datetime, parsed_datetime + timedelta(days=1)
    except ValueError:
        pass

    for date_format in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            parsed_date = datetime.strptime(candidate, date_format).replace(tzinfo=timezone.utc)
            return parsed_date, parsed_date + timedelta(days=1)
        except ValueError:
            continue

    raise HTTPException(
        status_code=422,
        detail="Gecersiz tarih formati. ISO tarih-saat, YYYY-MM-DD veya DD.MM.YYYY kullanin.",
    )


def parse_product_datetime_start(value: str) -> datetime:
    return parse_product_datetime_range(value)[0]


def parse_product_datetime_end(value: str) -> datetime:
    return parse_product_datetime_range(value)[1]


def normalize_urun_durumu_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    stripped_value = value.strip()
    if not stripped_value:
        return None

    normalized = fold_text(stripped_value).replace("-", "_").replace(" ", "_")
    if normalized in URUN_DURUMU_ESLESTIRMELERI:
        return URUN_DURUMU_ESLESTIRMELERI[normalized]

    raise HTTPException(
        status_code=422,
        detail=(
            "Gecersiz urun_durumu. "
            "zamlanmis_urunler, indirimdeki_urunler veya shrinkflation_riskli_urunler kullanin."
        ),
    )


def classify_product_status(comparison_row: dict[str, object]) -> Optional[str]:
    if comparison_row.get("is_shrinkflation"):
        return URUN_DURUMU_SHRINKFLATION

    unit_price_change = coerce_decimal(comparison_row.get("birim_fiyat_degisim_yuzdesi"))
    if unit_price_change is None:
        return None
    if unit_price_change > 0:
        return URUN_DURUMU_ZAMLANMIS
    if unit_price_change < 0:
        return URUN_DURUMU_INDIRIMDEKI
    return None


def resolve_effective_datetime_range(
    *,
    tarih: Optional[str],
    tarih_baslangic: Optional[str],
    tarih_bitis: Optional[str],
) -> tuple[Optional[datetime], Optional[datetime]]:
    start_candidates: list[datetime] = []
    end_candidates: list[datetime] = []

    if tarih:
        start_datetime, end_datetime = parse_product_datetime_range(tarih)
        start_candidates.append(start_datetime)
        end_candidates.append(end_datetime)

    if tarih_baslangic:
        start_candidates.append(parse_product_datetime_start(tarih_baslangic))

    if tarih_bitis:
        end_candidates.append(parse_product_datetime_end(tarih_bitis))

    effective_start = max(start_candidates) if start_candidates else None
    effective_end = min(end_candidates) if end_candidates else None
    return effective_start, effective_end


def build_product_status_lookup(
    db: Session,
    *,
    urun_durumu: str,
    market: Optional[str],
    kategori: Optional[str],
    date_start: Optional[datetime],
    date_end: Optional[datetime],
) -> dict[int, str]:
    normalized_category = normalize_category_value(kategori) if kategori else None
    if urun_durumu == URUN_DURUMU_SHRINKFLATION and (date_start or date_end):
        anomali_lookup = build_shrinkflation_status_lookup_from_anomali(
            db,
            date_start=date_start,
            date_end=date_end,
        )
        if anomali_lookup is not None:
            return anomali_lookup

    comparison_rows = list_latest_product_comparisons(
        db,
        market=market,
        date_start=date_start,
        date_end=date_end,
    )
    status_lookup: dict[int, str] = {}

    for row in comparison_rows:
        product_id = row.get("urun_id")
        if product_id is None:
            continue

        if normalized_category:
            row_category = row.get("urun_kategori")
            if not row_category:
                continue
            if normalize_category_value(str(row_category)) != normalized_category:
                continue

        current_status = classify_product_status(row)
        if current_status != urun_durumu:
            continue

        status_lookup[int(product_id)] = current_status

    return status_lookup


def build_shrinkflation_status_lookup_from_anomali(
    db: Session,
    *,
    date_start: Optional[datetime],
    date_end: Optional[datetime],
) -> Optional[dict[int, str]]:
    query = """
        select distinct a.ilgili_urun_id as urun_id
        from public.anomali a
        where a.anomali_turu = 'shrinkflation'
          and a.yeni_kayit_tarihi is not null
    """
    params: dict[str, object] = {}

    if date_start and date_end:
        normalized_start = min(date_start.date(), date_end.date())
        normalized_end = max(date_start.date(), date_end.date())
        query += """
          and date(a.yeni_kayit_tarihi) between :anomali_start_date and :anomali_end_date
        """
        params["anomali_start_date"] = normalized_start
        params["anomali_end_date"] = normalized_end
    elif date_start or date_end:
        query += " and date(a.yeni_kayit_tarihi) = :anomali_new_date"
        params["anomali_new_date"] = (date_start or date_end).date()

    try:
        rows = db.execute(text(query), params).mappings().all()
    except SQLAlchemyError:
        return None

    return {
        int(row["urun_id"]): URUN_DURUMU_SHRINKFLATION
        for row in rows
        if row.get("urun_id") is not None
    }


def build_latest_price_snapshots_subquery():
    return (
        select(
            PriceTimeSeries.urun_id.label("urun_id"),
            PriceTimeSeries.urun_fiyat.label("urun_fiyat"),
            PriceTimeSeries.gramaj_degeri.label("gramaj_degeri"),
            PriceTimeSeries.gramaj_birimi.label("gramaj_birimi"),
            PriceTimeSeries.birim_fiyat.label("birim_fiyat"),
            PriceTimeSeries.kazima_tarihi.label("kazima_tarihi"),
            func.row_number().over(
                partition_by=PriceTimeSeries.urun_id,
                order_by=(
                    PriceTimeSeries.kazima_tarihi.desc(),
                    PriceTimeSeries.kayit_id.desc(),
                ),
            ).label("rn"),
        ).subquery("latest_price_snapshots")
    )


@router.get(
    "",
    response_model=ProductsListResponse,
    summary="Urun listesini getir",
)
def get_products(
    kategori: Annotated[
        Optional[str], Query(description="Kategoriye gore filtreleme")
    ] = None,
    market: Annotated[
        Optional[str], Query(description="Markete gore filtreleme")
    ] = None,
    tarih: Annotated[
        Optional[str], Query(description="Kayit gunune gore filtreleme")
    ] = None,
    tarih_baslangic: Annotated[
        Optional[str], Query(description="Kayit baslangic tarih-saat filtreleme")
    ] = None,
    tarih_bitis: Annotated[
        Optional[str], Query(description="Kayit bitis tarih-saat filtreleme")
    ] = None,
    search: Annotated[
        Optional[str], Query(description="Urun adinda arama")
    ] = None,
    urun_durumu: Annotated[
        Optional[str], Query(description="Urun durumuna gore filtreleme")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
):
    has_snapshot_date_filter = bool(tarih or tarih_baslangic or tarih_bitis)
    effective_date_start, effective_date_end = resolve_effective_datetime_range(
        tarih=tarih,
        tarih_baslangic=tarih_baslangic,
        tarih_bitis=tarih_bitis,
    )

    if has_snapshot_date_filter:
        statement = select(
            Product.id,
            Product.urun_ad,
            Product.urun_url,
            Product.urun_kategori,
            Product.market_adi,
            PriceTimeSeries.urun_fiyat.label("urun_fiyat"),
            PriceTimeSeries.gramaj_degeri.label("gramaj_degeri"),
            PriceTimeSeries.gramaj_birimi.label("gramaj_birimi"),
            PriceTimeSeries.birim_fiyat.label("birim_fiyat"),
            Product.urun_marka,
            PriceTimeSeries.kazima_tarihi.label("eklenme_tarihi"),
            PriceTimeSeries.kayit_id.label("kayit_id"),
            func.count().over().label("total_count"),
        ).select_from(Product).join(PriceTimeSeries, PriceTimeSeries.urun_id == Product.id)
    else:
        latest_price_snapshots = build_latest_price_snapshots_subquery()
        statement = select(
            Product.id,
            Product.urun_ad,
            Product.urun_url,
            Product.urun_kategori,
            Product.market_adi,
            latest_price_snapshots.c.urun_fiyat,
            latest_price_snapshots.c.gramaj_degeri,
            latest_price_snapshots.c.gramaj_birimi,
            latest_price_snapshots.c.birim_fiyat,
            Product.urun_marka,
            latest_price_snapshots.c.kazima_tarihi.label("eklenme_tarihi"),
            func.count().over().label("total_count"),
        ).select_from(Product).outerjoin(
            latest_price_snapshots,
            (latest_price_snapshots.c.urun_id == Product.id)
            & (latest_price_snapshots.c.rn == 1),
        )

    market_value = normalize_market_value(market) if market else None
    urun_durumu_value = normalize_urun_durumu_value(urun_durumu)

    if kategori:
        statement = statement.where(
            normalize_category_expression(Product.urun_kategori)
            == normalize_category_value(kategori)
        )

    if market_value:
        statement = statement.where(
            normalize_market_expression(Product.market_adi)
            == market_value
        )

    if tarih:
        statement = statement.where(
            PriceTimeSeries.kazima_tarihi >= parse_product_datetime_start(tarih),
            PriceTimeSeries.kazima_tarihi < parse_product_datetime_end(tarih),
        )

    if tarih_baslangic:
        statement = statement.where(
            PriceTimeSeries.kazima_tarihi >= parse_product_datetime_start(tarih_baslangic)
        )

    if tarih_bitis:
        statement = statement.where(
            PriceTimeSeries.kazima_tarihi < parse_product_datetime_end(tarih_bitis)
        )

    if search:
        normalized_search = normalize_text_expression(search)
        statement = statement.where(
            normalize_text_expression(Product.urun_ad).contains(normalized_search)
        )

    product_status_lookup: dict[int, str] = {}
    if urun_durumu_value:
        product_status_lookup = build_product_status_lookup(
            db,
            urun_durumu=urun_durumu_value,
            market=market_value,
            kategori=kategori,
            date_start=effective_date_start,
            date_end=effective_date_end,
        )
        if not product_status_lookup:
            return {"total": 0, "items": []}
        statement = statement.where(Product.id.in_(sorted(product_status_lookup)))

    if has_snapshot_date_filter:
        statement = statement.order_by(
            PriceTimeSeries.kazima_tarihi.asc(),
            PriceTimeSeries.kayit_id.asc(),
            Product.id.asc(),
        )
    else:
        statement = statement.order_by(Product.id.asc())

    rows = db.execute(
        statement.offset(offset).limit(limit)
    ).mappings().all()

    total = rows[0]["total_count"] if rows else 0
    items = []
    for row in rows:
        normalized_measure_value, normalized_measure_unit = normalize_measure_value(
            row["gramaj_degeri"],
            row["gramaj_birimi"],
        )
        items.append(
            {
                "id": row["id"],
                "urun_ad": row["urun_ad"],
                "urun_url": row["urun_url"],
                "urun_kategori": canonical_category_label(row["urun_kategori"]),
                "market_adi": row["market_adi"],
                "urun_fiyat": row["urun_fiyat"],
                "gramaj_degeri": normalized_measure_value,
                "gramaj_birimi": normalized_measure_unit,
                "birim_fiyat": compute_normalized_unit_price(
                    row["urun_fiyat"],
                    normalized_measure_value,
                    normalized_measure_unit,
                ),
                "urun_marka": row["urun_marka"],
                "eklenme_tarihi": row["eklenme_tarihi"],
                "urun_durumu": product_status_lookup.get(row["id"]),
            }
        )
    return {"total": total, "items": items}


@router.get(
    "/categories",
    response_model=CategoryListResponse,
    summary="Tum urun kategorilerini getir",
)
def get_product_categories(
    market: Annotated[
        Optional[str], Query(description="Markete gore kategori filtreleme")
    ] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Product.urun_kategori).filter(Product.urun_kategori.isnot(None))

    market_value = normalize_market_value(market) if market else None
    if market_value:
        query = query.filter(
            normalize_market_expression(Product.market_adi) == market_value
        )

    rows = (
        query.distinct()
        .order_by(Product.urun_kategori.asc())
        .all()
    )
    items = deduplicate_category_labels([row.urun_kategori for row in rows])
    return {"total": len(items), "items": items}


@router.get(
    "/dates",
    response_model=DateListResponse,
    summary="Tum urun kayit tarihlerini getir",
)
def get_product_dates(
    market: Annotated[
        Optional[str], Query(description="Markete gore tarih filtreleme")
    ] = None,
    db: Session = Depends(get_db),
):
    date_expression = func.date(PriceTimeSeries.kazima_tarihi)
    query = (
        db.query(date_expression.label("tarih"))
        .select_from(PriceTimeSeries)
        .filter(PriceTimeSeries.kazima_tarihi.isnot(None))
    )

    market_value = normalize_market_value(market) if market else None
    if market_value:
        query = query.join(Product, Product.id == PriceTimeSeries.urun_id).filter(
            normalize_market_expression(Product.market_adi) == market_value
        )

    rows = (
        query.distinct()
        .order_by(date_expression.desc())
        .all()
    )
    items = [row.tarih for row in rows if row.tarih is not None]
    return {"total": len(items), "items": items}
