from datetime import date, datetime, timedelta, timezone
import unicodedata
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import bindparam, func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PriceTimeSeries, Product
from app.routers.products import normalize_category_value
from app.schemas import (
    CategoryDistributionResponse,
    CategoryPriceChangeResponse,
    DashboardSummaryResponse,
    PriceChangeListResponse,
    ProductPriceComparisonResponse,
    RiskyProductListResponse,
    TopProductsResponse,
)
from app.services.shrinkflation import (
    count_market_date_shrinkflation_findings,
    count_shrinkflation_risk_findings,
    DetectionThresholds,
    list_market_date_comparison_findings,
    list_latest_product_comparisons,
    list_shrinkflation_risk_findings,
)
from app.sql_helpers import build_canonical_product_identity_sql


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

MARKET_TRANSLATION_SOURCE = "CGIOSUcgiosuÇĞİIÖŞÜçğıöşü"
MARKET_TRANSLATION_TARGET = "cgiosucgiosucgiiosucgiosu"
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


LATEST_PRICE_CTE = """
with latest_prices as (
    select
        fzs.urun_id,
        fzs.urun_fiyat,
        fzs.kazima_tarihi,
        row_number() over (
            partition by fzs.urun_id
            order by fzs.kazima_tarihi desc nulls last, fzs.kayit_id desc
        ) as rn
    from fiyat_zaman_serisi fzs
    where fzs.urun_fiyat is not null
)
"""

PRICE_COMPARISON_CTE = """
with ranked_prices as (
    select
        fzs.urun_id,
        fzs.urun_fiyat,
        fzs.gramaj_degeri,
        fzs.gramaj_birimi,
        fzs.birim_fiyat,
        fzs.kazima_tarihi,
        row_number() over (
            partition by fzs.urun_id
            order by fzs.kazima_tarihi desc nulls last, fzs.kayit_id desc
        ) as rn
    from fiyat_zaman_serisi fzs
),
latest_prices as (
    select * from ranked_prices where rn = 1
),
previous_prices as (
    select * from ranked_prices where rn = 2
),
comparisons as (
    select
        p.id as urun_id,
        p.urun_ad,
        p.market_adi,
        coalesce(p.urun_kategori, 'Bilinmiyor') as urun_kategori,
        latest.urun_fiyat as yeni_fiyat,
        previous.urun_fiyat as eski_fiyat,
        latest.gramaj_degeri as yeni_gramaj,
        previous.gramaj_degeri as eski_gramaj,
        latest.gramaj_birimi as gramaj_birimi,
        latest.birim_fiyat as yeni_birim_fiyat,
        previous.birim_fiyat as eski_birim_fiyat,
        latest.kazima_tarihi as kazima_tarihi,
        previous.kazima_tarihi as onceki_kazima_tarihi,
        case
            when previous.urun_fiyat is null or previous.urun_fiyat = 0 or latest.urun_fiyat is null then null
            else round(((latest.urun_fiyat - previous.urun_fiyat) / previous.urun_fiyat) * 100, 2)
        end as degisim_yuzdesi,
        case
            when previous.birim_fiyat is null or previous.birim_fiyat = 0 or latest.birim_fiyat is null then null
            else round(((latest.birim_fiyat - previous.birim_fiyat) / previous.birim_fiyat) * 100, 2)
        end as birim_fiyat_degisim_yuzdesi
    from urunler p
    join latest_prices latest on latest.urun_id = p.id
    left join previous_prices previous on previous.urun_id = p.id
)
"""


def fold_market_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return without_marks.translate(str.maketrans("çğıöşü", "cgiosu"))


def parse_dashboard_market_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    normalized = fold_market_text(value)
    if normalized.startswith("sok"):
        return "sok"
    if normalized.startswith("migros"):
        return "migros"

    raise HTTPException(
        status_code=422,
        detail="Gecersiz market secimi. SOK veya MIGROS kullanin.",
    )


def parse_urun_durumu(value: Optional[str]) -> str:
    if not value:
        return URUN_DURUMU_ZAMLANMIS

    normalized = (
        fold_market_text(value)
        .replace("-", "_")
        .replace(" ", "_")
    )
    if normalized in URUN_DURUMU_ESLESTIRMELERI:
        return URUN_DURUMU_ESLESTIRMELERI[normalized]

    raise HTTPException(
        status_code=422,
        detail=(
            "Gecersiz urun durumu secimi. "
            "zamlanmis_urunler, indirimdeki_urunler veya shrinkflation_riskli_urunler kullanin."
        ),
    )


def build_urun_durumu_servis_ayarlari(urun_durumu: str) -> dict[str, bool]:
    if urun_durumu == URUN_DURUMU_INDIRIMDEKI:
        return {
            "increases_only": False,
            "decreases_only": True,
            "shrinkflation_only": False,
            "sort_by_unit_price": False,
            "sort_by_unit_price_decrease": True,
            "sort_by_shrinkflation_risk": False,
        }
    if urun_durumu == URUN_DURUMU_SHRINKFLATION:
        return {
            "increases_only": False,
            "decreases_only": False,
            "shrinkflation_only": True,
            "sort_by_unit_price": False,
            "sort_by_unit_price_decrease": False,
            "sort_by_shrinkflation_risk": True,
        }
    return {
        "increases_only": True,
        "decreases_only": False,
        "shrinkflation_only": False,
        "sort_by_unit_price": True,
        "sort_by_unit_price_decrease": False,
        "sort_by_shrinkflation_risk": False,
    }


def normalize_market_column_expression(column):
    return func.lower(
        func.translate(
            func.coalesce(column, ""),
            MARKET_TRANSLATION_SOURCE,
            MARKET_TRANSLATION_TARGET,
        )
    )


def build_market_filter_expression(column, market: Optional[str]):
    normalized_column = normalize_market_column_expression(column)
    if market == "sok":
        return normalized_column.like("sok%")
    if market == "migros":
        return normalized_column.like("migros%")
    return None


def build_normalized_market_sql(column_name: str) -> str:
    return (
        f"lower(translate(coalesce({column_name}, ''), "
        f"'{MARKET_TRANSLATION_SOURCE}', '{MARKET_TRANSLATION_TARGET}'))"
    )


def build_market_filter_sql(column_name: str, market: Optional[str]) -> tuple[str, dict[str, str]]:
    normalized_column_name = build_normalized_market_sql(column_name)
    if market == "sok":
        return (
            f" and {normalized_column_name} like :market_pattern_1",
            {"market_pattern_1": "sok%"},
        )
    if market == "migros":
        return (
            f" and {normalized_column_name} like :market_pattern_1",
            {"market_pattern_1": "migros%"},
        )
    return "", {}


def filter_dashboard_rows_by_category(
    rows: list[dict[str, object]],
    kategori: Optional[str],
) -> list[dict[str, object]]:
    if not kategori:
        return rows

    normalized_category = normalize_category_value(kategori)
    filtered_rows: list[dict[str, object]] = []
    for row in rows:
        row_category = row.get("urun_kategori")
        if not row_category:
            continue
        if normalize_category_value(str(row_category)) == normalized_category:
            filtered_rows.append(row)
    return filtered_rows


def satirlara_urun_url_ekle(
    db: Session,
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not rows or not hasattr(db, "execute"):
        return rows

    urun_idleri = sorted(
        {
            int(urun_id)
            for urun_id in (row.get("urun_id") for row in rows)
            if urun_id is not None
        }
    )
    if not urun_idleri:
        return rows

    sorgu = text(
        """
        select id, urun_url
        from urunler
        where id in :urun_idleri
        """
    ).bindparams(bindparam("urun_idleri", expanding=True))

    try:
        url_haritasi = {
            int(row["id"]): row["urun_url"]
            for row in db.execute(sorgu, {"urun_idleri": urun_idleri}).mappings().all()
        }
    except SQLAlchemyError:
        return rows

    for row in rows:
        urun_id = row.get("urun_id")
        if urun_id is None:
            continue
        row["urun_url"] = url_haritasi.get(int(urun_id))
    return rows


def get_snapshot_record_count(
    db: Session,
    market: Optional[str],
    *,
    snapshot_date: Optional[date] = None,
) -> int:
    product_identity_sql = build_canonical_product_identity_sql("p.urun_url", "p.urun_ad")

    if snapshot_date is not None:
        snapshot_market_sql, snapshot_market_params = build_market_filter_sql(
            "p.market_adi",
            market,
        )
        snapshot_count_query = text(
            f"""
            select count(distinct {product_identity_sql}) as snapshot_count
            from fiyat_zaman_serisi f
            join urunler p on p.id = f.urun_id
            where date(f.kazima_tarihi) = :snapshot_date
            """
            + snapshot_market_sql
        )
        snapshot_row = db.execute(
            snapshot_count_query,
            {
                **snapshot_market_params,
                "snapshot_date": snapshot_date,
            },
        ).mappings().one()
        return snapshot_row["snapshot_count"] or 0

    latest_snapshot_market_sql, latest_snapshot_market_params = build_market_filter_sql(
        "p.market_adi",
        market,
    )
    latest_snapshot_count_query = text(
        f"""
        with latest_snapshot as (
            select max(date(f.kazima_tarihi)) as latest_snapshot_date
            from fiyat_zaman_serisi f
            join urunler p on p.id = f.urun_id
            where f.kazima_tarihi is not null
        """
        + latest_snapshot_market_sql
        + f"""
        )
        select count(distinct {product_identity_sql}) as snapshot_count
        from fiyat_zaman_serisi f
        join urunler p on p.id = f.urun_id
        cross join latest_snapshot ls
        where ls.latest_snapshot_date is not null
          and date(f.kazima_tarihi) = ls.latest_snapshot_date
        """
        + latest_snapshot_market_sql
    )
    latest_snapshot_row = db.execute(
        latest_snapshot_count_query,
        latest_snapshot_market_params,
    ).mappings().one()
    return latest_snapshot_row["snapshot_count"] or 0


def build_thresholds(
    min_size_drop_pct: float,
    min_unit_price_increase_pct: float,
    stable_price_floor_pct: float,
) -> DetectionThresholds:
    return DetectionThresholds(
        min_size_drop_pct=min_size_drop_pct,
        min_unit_price_increase_pct=min_unit_price_increase_pct,
        stable_price_floor_pct=stable_price_floor_pct,
    )


def parse_dashboard_datetime_range(value: str) -> tuple[datetime, datetime]:
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


def parse_dashboard_datetime_start(value: str) -> datetime:
    return parse_dashboard_datetime_range(value)[0]


def parse_dashboard_datetime_end(value: str) -> datetime:
    return parse_dashboard_datetime_range(value)[1]


def parse_dashboard_selected_date(value: str) -> date:
    return parse_dashboard_datetime_start(value).date()


def resolve_dashboard_selected_dates(
    tarih_baslangic: Optional[str],
    tarih_bitis: Optional[str],
) -> tuple[Optional[date], Optional[date]]:
    start_date = parse_dashboard_selected_date(tarih_baslangic) if tarih_baslangic else None
    end_date = parse_dashboard_selected_date(tarih_bitis) if tarih_bitis else None

    if start_date and end_date:
        if start_date <= end_date:
            return start_date, end_date
        return end_date, start_date

    single_date = start_date or end_date
    if single_date is not None:
        return single_date, single_date

    return None, None


def get_previous_market_snapshot_date(
    db: Session,
    *,
    market: Optional[str],
    selected_date: date,
) -> Optional[date]:
    date_expression = func.date(PriceTimeSeries.kazima_tarihi)
    query = (
        db.query(date_expression.label("tarih"))
        .select_from(PriceTimeSeries)
        .join(Product, Product.id == PriceTimeSeries.urun_id)
        .filter(PriceTimeSeries.kazima_tarihi.isnot(None))
        .filter(date_expression < selected_date)
    )
    market_expression = build_market_filter_expression(Product.market_adi, market)
    if market_expression is not None:
        query = query.filter(market_expression)

    row = (
        query.distinct()
        .order_by(date_expression.desc())
        .first()
    )
    return row.tarih if row and row.tarih is not None else None


def get_latest_market_snapshot_date_on_or_before(
    db: Session,
    *,
    market: Optional[str],
    selected_date: date,
) -> Optional[date]:
    date_expression = func.date(PriceTimeSeries.kazima_tarihi)
    query = (
        db.query(date_expression.label("tarih"))
        .select_from(PriceTimeSeries)
        .join(Product, Product.id == PriceTimeSeries.urun_id)
        .filter(PriceTimeSeries.kazima_tarihi.isnot(None))
        .filter(date_expression <= selected_date)
    )
    market_expression = build_market_filter_expression(Product.market_adi, market)
    if market_expression is not None:
        query = query.filter(market_expression)

    row = (
        query.distinct()
        .order_by(date_expression.desc())
        .first()
    )
    return row.tarih if row and row.tarih is not None else None


def get_first_market_snapshot_date_on_or_after(
    db: Session,
    *,
    market: Optional[str],
    selected_date: date,
    max_date: Optional[date] = None,
) -> Optional[date]:
    date_expression = func.date(PriceTimeSeries.kazima_tarihi)
    query = (
        db.query(date_expression.label("tarih"))
        .select_from(PriceTimeSeries)
        .join(Product, Product.id == PriceTimeSeries.urun_id)
        .filter(PriceTimeSeries.kazima_tarihi.isnot(None))
        .filter(date_expression >= selected_date)
    )
    if max_date is not None:
        query = query.filter(date_expression <= max_date)

    market_expression = build_market_filter_expression(Product.market_adi, market)
    if market_expression is not None:
        query = query.filter(market_expression)

    row = (
        query.distinct()
        .order_by(date_expression.asc())
        .first()
    )
    return row.tarih if row and row.tarih is not None else None


def resolve_dashboard_comparison_dates(
    db: Session,
    *,
    market: Optional[str],
    tarih_baslangic: Optional[str],
    tarih_bitis: Optional[str],
) -> tuple[Optional[date], Optional[date], bool]:
    selected_start_date, selected_end_date = resolve_dashboard_selected_dates(
        tarih_baslangic,
        tarih_bitis,
    )
    has_date_selection = bool(selected_start_date and selected_end_date)

    if not has_date_selection:
        return None, None, False

    if selected_start_date != selected_end_date:
        resolved_end_date = get_latest_market_snapshot_date_on_or_before(
            db,
            market=market,
            selected_date=selected_end_date,
        )
        if resolved_end_date is None:
            return None, None, True

        resolved_start_date = get_first_market_snapshot_date_on_or_after(
            db,
            market=market,
            selected_date=selected_start_date,
            max_date=resolved_end_date,
        )
        if resolved_start_date is None or resolved_start_date > resolved_end_date:
            return None, None, True

        return resolved_start_date, resolved_end_date, True

    resolved_selected_date = get_latest_market_snapshot_date_on_or_before(
        db,
        market=market,
        selected_date=selected_start_date,
    )
    if resolved_selected_date is None:
        return None, None, True

    previous_date = get_previous_market_snapshot_date(
        db,
        market=market,
        selected_date=resolved_selected_date,
    )
    if previous_date is None:
        return None, None, True

    return previous_date, resolved_selected_date, True


def has_effective_market_date_comparison(
    old_date: Optional[date],
    new_date: Optional[date],
) -> bool:
    return old_date is not None and new_date is not None and old_date < new_date


def listele_secili_urun_durumu_satirlari(
    db: Session,
    *,
    market: Optional[str],
    urun_durumu: str,
    thresholds: DetectionThresholds,
    comparison_old_date: Optional[date],
    comparison_new_date: Optional[date],
    has_date_selection: bool,
    selected_start_date: Optional[date] = None,
    selected_end_date: Optional[date] = None,
    date_start: Optional[datetime] = None,
    date_end: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> list[dict[str, object]]:
    if urun_durumu == URUN_DURUMU_SHRINKFLATION:
        anomali_scope_start_date = None
        anomali_scope_end_date = None
        if has_date_selection:
            if (
                selected_start_date
                and selected_end_date
                and selected_start_date != selected_end_date
            ):
                anomali_scope_start_date = selected_start_date
                anomali_scope_end_date = selected_end_date
            else:
                anomali_scope_start_date = comparison_new_date
                anomali_scope_end_date = comparison_new_date

        anomali_rows = list_anomali_findings(
            db,
            market=market,
            selected_start_date=anomali_scope_start_date,
            selected_end_date=anomali_scope_end_date,
            limit=limit,
        )
        if anomali_rows is not None:
            return satirlara_urun_url_ekle(db, anomali_rows)
        if not has_date_selection:
            return satirlara_urun_url_ekle(db, list_shrinkflation_risk_findings(
                db,
                thresholds=thresholds,
                limit=limit,
                market=market,
                date_start=date_start,
                date_end=date_end,
            ))

    has_effective_date_comparison = has_effective_market_date_comparison(
        comparison_old_date,
        comparison_new_date,
    )
    servis_ayarlari = build_urun_durumu_servis_ayarlari(urun_durumu)

    if market and has_effective_date_comparison:
        return satirlara_urun_url_ekle(db, list_market_date_comparison_findings(
            db,
            thresholds=thresholds,
            limit=limit,
            market=market,
            old_date=comparison_old_date,
            new_date=comparison_new_date,
            **servis_ayarlari,
        ))

    if has_date_selection:
        return []

    return satirlara_urun_url_ekle(db, list_latest_product_comparisons(
        db,
        thresholds=thresholds,
        limit=limit,
        market=market,
        date_start=date_start,
        date_end=date_end,
        **servis_ayarlari,
    ))


def build_anomali_scope_sql(
    *,
    market: Optional[str],
    selected_start_date: Optional[date],
    selected_end_date: Optional[date],
) -> tuple[str, dict[str, object]]:
    market_sql, market_params = build_market_filter_sql("u.market_adi", market)
    params: dict[str, object] = dict(market_params)

    if selected_start_date and selected_end_date and selected_start_date != selected_end_date:
        scope_sql = """
          and date(a.yeni_kayit_tarihi) > :anomali_start_date
          and date(a.yeni_kayit_tarihi) <= :anomali_end_date
        """
        params["anomali_start_date"] = selected_start_date
        params["anomali_end_date"] = selected_end_date
        return market_sql + scope_sql, params

    if selected_start_date or selected_end_date:
        scope_sql = " and date(a.yeni_kayit_tarihi) = :anomali_new_date"
        params["anomali_new_date"] = selected_end_date or selected_start_date
        return market_sql + scope_sql, params

    latest_market_sql, latest_market_params = build_market_filter_sql("sub_u.market_adi", market)
    scope_sql = (
        """
        and date(a.yeni_kayit_tarihi) = (
            select max(date(sub.yeni_kayit_tarihi))
            from public.anomali sub
            left join urunler sub_u on sub_u.id = sub.ilgili_urun_id
            where sub.yeni_kayit_tarihi is not null
        """
        + latest_market_sql
        + """
        )
        """
    )
    params.update(latest_market_params)
    return market_sql + scope_sql, params


def count_anomali_findings(
    db: Session,
    *,
    market: Optional[str],
    selected_start_date: Optional[date],
    selected_end_date: Optional[date],
) -> Optional[int]:
    if not hasattr(db, "execute"):
        return None

    scope_sql, params = build_anomali_scope_sql(
        market=market,
        selected_start_date=selected_start_date,
        selected_end_date=selected_end_date,
    )
    query = text(
        """
        select count(*) as toplam
        from public.anomali a
        left join urunler u on u.id = a.ilgili_urun_id
        where a.anomali_turu = 'shrinkflation'
          and a.yeni_kayit_tarihi is not null
        """
        + scope_sql
    )
    try:
        row = db.execute(query, params).mappings().one()
    except SQLAlchemyError:
        return None
    return row["toplam"] or 0


def list_anomali_findings(
    db: Session,
    *,
    market: Optional[str],
    selected_start_date: Optional[date],
    selected_end_date: Optional[date],
    limit: Optional[int],
) -> Optional[list[dict[str, object]]]:
    if not hasattr(db, "execute"):
        return None

    scope_sql, params = build_anomali_scope_sql(
        market=market,
        selected_start_date=selected_start_date,
        selected_end_date=selected_end_date,
    )
    limit_sql = ""
    if limit is not None:
        limit_sql = " limit :limit"
        params["limit"] = limit

    query = text(
        """
        select
            a.ilgili_urun_id as urun_id,
            coalesce(u.urun_ad, 'Bilinmeyen Ürün') as urun_ad,
            u.market_adi,
            u.urun_kategori,
            u.urun_url,
            a.onceki_fiyat as eski_fiyat,
            a.yeni_fiyat_detay as yeni_fiyat,
            a.onceki_gramaj_degeri as eski_gramaj,
            a.yeni_gramaj_degeri_detay as yeni_gramaj,
            a.gramaj_birimi,
            a.onceki_birim_fiyat as eski_birim_fiyat,
            a.yeni_birim_fiyat_detay as yeni_birim_fiyat,
            a.birim_fiyat_degisim_pct as birim_fiyat_degisim_yuzdesi,
            a.gramaj_degisim_pct as gramaj_degisim_yuzdesi,
            a.onceki_gramaj_degeri as eski_birim_gramaj,
            a.yeni_gramaj_degeri_detay as yeni_birim_gramaj,
            null::numeric as eski_adet_sayisi,
            null::numeric as yeni_adet_sayisi,
            null::numeric as adet_degisim_yuzdesi,
            a.gramaj_degisim_pct as birim_icerik_degisim_yuzdesi,
            a.fiyat_degisim_pct as fiyat_degisim_yuzdesi,
            a.shrinkflation_orani_pct as shrinkflation_orani_yuzdesi,
            a.severity,
            'decrease'::text as direction,
            a.reason,
            true as is_shrinkflation,
            a.onceki_kayit_tarihi as eski_tarih,
            a.yeni_kayit_tarihi as yeni_tarih,
            a.anomali_tespit_tarihi as kazima_tarihi
        from public.anomali a
        left join urunler u on u.id = a.ilgili_urun_id
        where a.anomali_turu = 'shrinkflation'
          and a.yeni_kayit_tarihi is not null
        """
        + scope_sql
        + """
        order by
            coalesce(a.shrinkflation_orani_pct, a.birim_fiyat_degisim_pct, 0) desc,
            abs(coalesce(a.gramaj_degisim_pct, 0)) desc,
            a.yeni_kayit_tarihi desc,
            a.ilgili_urun_id asc
        """
        + limit_sql
    )
    try:
        return [dict(row) for row in db.execute(query, params).mappings().all()]
    except SQLAlchemyError:
        return None


@router.get("/summary", response_model=DashboardSummaryResponse, summary="Dashboard ozet verileri")
def get_dashboard_summary(
    market: Annotated[
        Optional[str], Query(description="Markete gore filtreleme")
    ] = None,
    urun_durumu: Annotated[
        Optional[str], Query(description="Secilen urun durumu")
    ] = None,
    tarih_baslangic: Annotated[
        Optional[str], Query(description="Karsilastirma icin secilen ilk tarih")
    ] = None,
    tarih_bitis: Annotated[
        Optional[str], Query(description="Karsilastirma icin secilen ikinci tarih")
    ] = None,
    db: Session = Depends(get_db),
):
    thresholds = build_thresholds(
        min_size_drop_pct=3.0,
        min_unit_price_increase_pct=3.0,
        stable_price_floor_pct=0.0,
    )
    market_value = parse_dashboard_market_value(market)
    secili_urun_durumu = (
        URUN_DURUMU_SHRINKFLATION
        if urun_durumu is None
        else parse_urun_durumu(urun_durumu)
    )
    market_expression = build_market_filter_expression(Product.market_adi, market_value)

    toplam_kategori_query = (
        db.query(func.count(func.distinct(Product.urun_kategori)))
        .filter(Product.urun_kategori.isnot(None))
    )
    if market_expression is not None:
        toplam_kategori_query = toplam_kategori_query.filter(market_expression)

    comparison_old_date, comparison_new_date, has_date_selection = resolve_dashboard_comparison_dates(
        db,
        market=market_value,
        tarih_baslangic=tarih_baslangic,
        tarih_bitis=tarih_bitis,
    )
    selected_start_date, selected_end_date = resolve_dashboard_selected_dates(
        tarih_baslangic,
        tarih_bitis,
    )
    date_start = parse_dashboard_datetime_start(tarih_baslangic) if tarih_baslangic else None
    date_end = parse_dashboard_datetime_end(tarih_bitis) if tarih_bitis else None
    has_effective_date_comparison = has_effective_market_date_comparison(
        comparison_old_date,
        comparison_new_date,
    )
    summary_snapshot_date = comparison_new_date if has_date_selection else None
    if has_date_selection and summary_snapshot_date is None:
        toplam_urun = 0
    else:
        toplam_urun = get_snapshot_record_count(
            db,
            market_value,
            snapshot_date=summary_snapshot_date,
        )
    toplam_kategori = toplam_kategori_query.scalar() or 0

    summary_market_sql, summary_market_params = build_market_filter_sql("p.market_adi", market_value)

    istatistik_sorgusu = text(
        LATEST_PRICE_CTE
        + """
        select
            avg(lp.urun_fiyat) as ortalama_fiyat,
            min(lp.urun_fiyat) as minimum_fiyat,
            max(lp.urun_fiyat) as maksimum_fiyat
        from latest_prices lp
        join urunler p on p.id = lp.urun_id
        where lp.rn = 1
        """
        + summary_market_sql
    )
    fiyat_istatistikleri = db.execute(istatistik_sorgusu, summary_market_params).mappings().one()

    anomali_scope_start_date = None
    anomali_scope_end_date = None
    if has_date_selection:
        if selected_start_date and selected_end_date and selected_start_date != selected_end_date:
            anomali_scope_start_date = selected_start_date
            anomali_scope_end_date = selected_end_date
        else:
            anomali_scope_start_date = comparison_new_date
            anomali_scope_end_date = comparison_new_date

    if secili_urun_durumu == URUN_DURUMU_SHRINKFLATION:
        anomali_count = count_anomali_findings(
            db,
            market=market_value,
            selected_start_date=anomali_scope_start_date,
            selected_end_date=anomali_scope_end_date,
        )
        if anomali_count is not None:
            secili_urun_sayisi = anomali_count
        elif market_value and has_effective_date_comparison:
            secili_urun_sayisi = count_market_date_shrinkflation_findings(
                db,
                market=market_value,
                old_date=comparison_old_date,
                new_date=comparison_new_date,
                thresholds=thresholds,
            )
        elif has_date_selection:
            secili_urun_sayisi = 0
        else:
            secili_urun_sayisi = count_shrinkflation_risk_findings(
                db,
                thresholds=thresholds,
                market=market_value,
            )
    else:
        secili_urun_sayisi = len(
            listele_secili_urun_durumu_satirlari(
                db,
                market=market_value,
                urun_durumu=secili_urun_durumu,
                thresholds=thresholds,
                comparison_old_date=comparison_old_date,
                comparison_new_date=comparison_new_date,
                has_date_selection=has_date_selection,
                selected_start_date=selected_start_date,
                selected_end_date=selected_end_date,
                date_start=date_start,
                date_end=date_end,
                limit=None,
            )
        )

    top_category_market_sql, top_category_market_params = build_market_filter_sql("market_adi", market_value)

    top_category_row = db.execute(
        text(
            PRICE_COMPARISON_CTE
            + """
            select
                urun_kategori,
                count(*) as kayit_sayisi
            from comparisons
            where kazima_tarihi >= now() - interval '24 hours'
              and degisim_yuzdesi is not null
            """
            + top_category_market_sql
            + """
            group by urun_kategori
            order by kayit_sayisi desc, urun_kategori asc
            limit 1
            """
        ),
        top_category_market_params,
    ).mappings().first()

    return {
        "toplam_urun": toplam_urun,
        "toplam_urun_tarihi": summary_snapshot_date,
        "toplam_kategori": toplam_kategori,
        "bugun_guncellenen_kayit": secili_urun_sayisi,
        "karsilastirma_baslangic_tarihi": comparison_old_date,
        "karsilastirma_bitis_tarihi": comparison_new_date,
        "en_cok_hareket_gosteren_kategori": (
            top_category_row["urun_kategori"] if top_category_row else None
        ),
        "ortalama_fiyat": fiyat_istatistikleri["ortalama_fiyat"],
        "minimum_fiyat": fiyat_istatistikleri["minimum_fiyat"],
        "maksimum_fiyat": fiyat_istatistikleri["maksimum_fiyat"],
    }


@router.get(
    "/category-distribution",
    response_model=CategoryDistributionResponse,
    summary="Kategori bazli urun dagilimi",
)
def get_category_distribution(db: Session = Depends(get_db)):
    rows = (
        db.query(
            func.coalesce(Product.urun_kategori, "Bilinmiyor").label("kategori"),
            func.count(Product.id).label("urun_sayisi"),
        )
        .group_by(func.coalesce(Product.urun_kategori, "Bilinmiyor"))
        .order_by(func.count(Product.id).desc())
        .all()
    )
    items = [{"kategori": row.kategori, "urun_sayisi": row.urun_sayisi} for row in rows]
    return {"total_categories": len(items), "items": items}


@router.get("/top-cheapest", response_model=TopProductsResponse, summary="En ucuz 5 urun")
def get_top_cheapest(db: Session = Depends(get_db)):
    query = text(
        LATEST_PRICE_CTE
        + """
        select
            p.id as urun_id,
            p.urun_ad,
            p.market_adi,
            p.urun_kategori,
            p.urun_marka,
            lp.urun_fiyat,
            lp.kazima_tarihi
        from latest_prices lp
        join urunler p on p.id = lp.urun_id
        where lp.rn = 1
        order by lp.urun_fiyat asc, p.id asc
        limit 5
        """
    )
    rows = [dict(row._mapping) for row in db.execute(query)]
    return {"total": len(rows), "items": rows}


@router.get("/top-expensive", response_model=TopProductsResponse, summary="En pahali 5 urun")
def get_top_expensive(db: Session = Depends(get_db)):
    query = text(
        LATEST_PRICE_CTE
        + """
        select
            p.id as urun_id,
            p.urun_ad,
            p.market_adi,
            p.urun_kategori,
            p.urun_marka,
            lp.urun_fiyat,
            lp.kazima_tarihi
        from latest_prices lp
        join urunler p on p.id = lp.urun_id
        where lp.rn = 1
        order by lp.urun_fiyat desc, p.id asc
        limit 5
        """
    )
    rows = [dict(row._mapping) for row in db.execute(query)]
    return {"total": len(rows), "items": rows}


@router.get(
    "/top-price-changes",
    response_model=PriceChangeListResponse,
    summary="Secilen urun durumuna gore ilk 5 urun",
)
def get_top_price_changes(
    market: Annotated[
        Optional[str], Query(description="Markete gore filtreleme")
    ] = None,
    urun_durumu: Annotated[
        Optional[str], Query(description="Secilen urun durumu")
    ] = None,
    tarih_baslangic: Annotated[
        Optional[str], Query(description="Karsilastirma icin secilen ilk tarih")
    ] = None,
    tarih_bitis: Annotated[
        Optional[str], Query(description="Karsilastirma icin secilen ikinci tarih")
    ] = None,
    db: Session = Depends(get_db),
):
    market_value = parse_dashboard_market_value(market)
    secili_urun_durumu = parse_urun_durumu(urun_durumu)
    thresholds = build_thresholds(
        min_size_drop_pct=3.0,
        min_unit_price_increase_pct=3.0,
        stable_price_floor_pct=0.0,
    )
    comparison_old_date, comparison_new_date, has_date_selection = resolve_dashboard_comparison_dates(
        db,
        market=market_value,
        tarih_baslangic=tarih_baslangic,
        tarih_bitis=tarih_bitis,
    )
    selected_start_date, selected_end_date = resolve_dashboard_selected_dates(
        tarih_baslangic,
        tarih_bitis,
    )
    date_start = parse_dashboard_datetime_start(tarih_baslangic) if tarih_baslangic else None
    date_end = parse_dashboard_datetime_end(tarih_bitis) if tarih_bitis else None
    rows = listele_secili_urun_durumu_satirlari(
        db,
        market=market_value,
        urun_durumu=secili_urun_durumu,
        thresholds=thresholds,
        comparison_old_date=comparison_old_date,
        comparison_new_date=comparison_new_date,
        has_date_selection=has_date_selection,
        selected_start_date=selected_start_date,
        selected_end_date=selected_end_date,
        date_start=date_start,
        date_end=date_end,
        limit=5,
    )
    for row in rows:
        if secili_urun_durumu == URUN_DURUMU_SHRINKFLATION:
            row["degisim_yuzdesi"] = (
                row.get("shrinkflation_orani_yuzdesi")
                or row.get("birim_fiyat_degisim_yuzdesi")
            )
        else:
            row["degisim_yuzdesi"] = row.get("birim_fiyat_degisim_yuzdesi")
    return {"total": len(rows), "items": rows}


@router.get(
    "/category-price-changes",
    response_model=CategoryPriceChangeResponse,
    summary="Kategori bazli ortalama fiyat degisimi",
)
def get_category_price_changes(db: Session = Depends(get_db)):
    query = text(
        PRICE_COMPARISON_CTE
        + """
        select
            urun_kategori as kategori,
            round(avg(degisim_yuzdesi), 2) as ortalama_degisim_yuzdesi,
            count(*) as urun_sayisi
        from comparisons
        where kazima_tarihi >= now() - interval '24 hours'
          and degisim_yuzdesi is not null
        group by urun_kategori
        order by abs(avg(degisim_yuzdesi)) desc, urun_kategori asc
        limit 8
        """
    )
    rows = [dict(row._mapping) for row in db.execute(query)]
    return {"total": len(rows), "items": rows}


@router.get(
    "/product-price-comparisons",
    response_model=ProductPriceComparisonResponse,
    summary="Ayni urunun son iki tarih kaydini karsilastir",
)
def get_product_price_comparisons(
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
    offset: Annotated[int, Query(ge=0)] = 0,
    market: Annotated[
        Optional[str], Query(description="Markete gore filtreleme")
    ] = None,
    urun_durumu: Annotated[
        Optional[str], Query(description="Secilen urun durumu")
    ] = None,
    kategori: Annotated[
        Optional[str], Query(description="Kategoriye gore filtreleme")
    ] = None,
    tarih_baslangic: Annotated[
        Optional[str], Query(description="Yeni tarih baslangic filtreleme")
    ] = None,
    tarih_bitis: Annotated[
        Optional[str], Query(description="Yeni tarih bitis filtreleme")
    ] = None,
    artanlar: bool = False,
    min_size_drop_pct: Annotated[float, Query(ge=0)] = 3.0,
    min_unit_price_increase_pct: Annotated[float, Query(ge=0)] = 3.0,
    stable_price_floor_pct: float = 0.0,
    db: Session = Depends(get_db),
):
    market_value = parse_dashboard_market_value(market)
    secili_urun_durumu = parse_urun_durumu(urun_durumu)
    if urun_durumu is None and artanlar:
        secili_urun_durumu = URUN_DURUMU_ZAMLANMIS
    date_start = parse_dashboard_datetime_start(tarih_baslangic) if tarih_baslangic else None
    date_end = parse_dashboard_datetime_end(tarih_bitis) if tarih_bitis else None
    thresholds = build_thresholds(
        min_size_drop_pct=min_size_drop_pct,
        min_unit_price_increase_pct=min_unit_price_increase_pct,
        stable_price_floor_pct=stable_price_floor_pct,
    )
    selected_start_date, selected_end_date = resolve_dashboard_selected_dates(
        tarih_baslangic,
        tarih_bitis,
    )
    comparison_old_date, comparison_new_date, has_date_selection = resolve_dashboard_comparison_dates(
        db,
        market=market_value,
        tarih_baslangic=tarih_baslangic,
        tarih_bitis=tarih_bitis,
    )
    all_rows = listele_secili_urun_durumu_satirlari(
        db,
        market=market_value,
        urun_durumu=secili_urun_durumu,
        thresholds=thresholds,
        comparison_old_date=comparison_old_date,
        comparison_new_date=comparison_new_date,
        has_date_selection=has_date_selection,
        selected_start_date=selected_start_date,
        selected_end_date=selected_end_date,
        date_start=date_start,
        date_end=date_end,
        limit=None,
    )
    all_rows = filter_dashboard_rows_by_category(all_rows, kategori)
    rows = all_rows[offset:offset + limit]
    return {"total": len(all_rows), "items": rows}


@router.get(
    "/risky-products",
    response_model=RiskyProductListResponse,
    summary="Günlük tespit edilen riskli urunler ve anomaliler",
)
def get_risky_products(
    limit: Annotated[Optional[int], Query(ge=1, le=1000)] = None,
    market: Annotated[
        Optional[str], Query(description="Markete gore filtreleme")
    ] = None,
    tarih_baslangic: Annotated[
        Optional[str], Query(description="Karsilastirma icin secilen ilk tarih")
    ] = None,
    tarih_bitis: Annotated[
        Optional[str], Query(description="Karsilastirma icin secilen ikinci tarih")
    ] = None,
    min_size_drop_pct: Annotated[float, Query(ge=0)] = 3.0,
    min_unit_price_increase_pct: Annotated[float, Query(ge=0)] = 3.0,
    stable_price_floor_pct: float = 0.0,
    db: Session = Depends(get_db),
):
    market_value = parse_dashboard_market_value(market)
    thresholds = build_thresholds(
        min_size_drop_pct=min_size_drop_pct,
        min_unit_price_increase_pct=min_unit_price_increase_pct,
        stable_price_floor_pct=stable_price_floor_pct,
    )
    comparison_old_date, comparison_new_date, has_date_selection = resolve_dashboard_comparison_dates(
        db,
        market=market_value,
        tarih_baslangic=tarih_baslangic,
        tarih_bitis=tarih_bitis,
    )
    selected_start_date, selected_end_date = resolve_dashboard_selected_dates(
        tarih_baslangic,
        tarih_bitis,
    )
    has_effective_date_comparison = has_effective_market_date_comparison(
        comparison_old_date,
        comparison_new_date,
    )

    anomali_scope_start_date = None
    anomali_scope_end_date = None
    if has_date_selection:
        if selected_start_date and selected_end_date and selected_start_date != selected_end_date:
            anomali_scope_start_date = selected_start_date
            anomali_scope_end_date = selected_end_date
        else:
            anomali_scope_start_date = comparison_new_date
            anomali_scope_end_date = comparison_new_date

    anomali_rows = list_anomali_findings(
        db,
        market=market_value,
        selected_start_date=anomali_scope_start_date,
        selected_end_date=anomali_scope_end_date,
        limit=limit,
    )
    if anomali_rows is not None:
        anomali_total = count_anomali_findings(
            db,
            market=market_value,
            selected_start_date=anomali_scope_start_date,
            selected_end_date=anomali_scope_end_date,
        )
        return {"total": anomali_total or 0, "items": satirlara_urun_url_ekle(db, anomali_rows)}

    if market_value and has_effective_date_comparison:
        all_rows = list_market_date_comparison_findings(
            db,
            thresholds=thresholds,
            limit=None,
            market=market_value,
            old_date=comparison_old_date,
            new_date=comparison_new_date,
            shrinkflation_only=True,
            sort_by_shrinkflation_risk=True,
        )
    elif has_date_selection:
        all_rows = []
    else:
        all_rows = list_shrinkflation_risk_findings(
            db,
            thresholds=thresholds,
            limit=None,
            market=market_value,
        )
    rows = all_rows[:limit] if limit is not None else all_rows
    return {"total": len(all_rows), "items": satirlara_urun_url_ekle(db, rows)}
