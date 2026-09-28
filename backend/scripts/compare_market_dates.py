import argparse
import csv
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from difflib import SequenceMatcher
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal
from app.services.shrinkflation import (  # noqa: E402
    DetectionThresholds,
    compare_snapshots,
    PriceSnapshot,
    load_legacy_product_names,
)


EXPORT_DIR = PROJECT_ROOT / "exports"
MEASURE_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(kg|gr|g|ml|lt|l)\b|"
    r"(\d+)\s*(?:['’]?\s*(?:li|lı|lu|lü)|adet|ad|paket|pk|yikama|tablet|yaprak)\b",
    re.IGNORECASE,
)
NAME_MEASURE_RE = re.compile(r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|gr|g|ml|lt|l)\b", re.IGNORECASE)
PUNCT_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class FamilySnapshot:
    urun_id: int
    display_name: str
    family_key: str
    market: Optional[str]
    category: Optional[str]
    url: Optional[str]
    snapshot: PriceSnapshot


def fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return without_marks.translate(str.maketrans("çğıöşü", "cgiosu"))


def family_key_for_name(value: str) -> str:
    cleaned = MEASURE_RE.sub(" ", fold_text(value))
    cleaned = PUNCT_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\b(x|ve|ile|adet|ad|paket|pk|li|lı|lu|lü)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def coerce_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def parse_turkish_number(value: str, *, assume_thousands_for_small_units: bool = False) -> Optional[Decimal]:
    candidate = value.strip()
    if not candidate:
        return None

    if "," in candidate:
        candidate = candidate.replace(".", "").replace(",", ".")
    elif candidate.count(".") > 1:
        candidate = candidate.replace(".", "")
    elif assume_thousands_for_small_units and "." in candidate and len(candidate.split(".")[-1]) == 3:
        candidate = candidate.replace(".", "")

    try:
        return Decimal(candidate)
    except InvalidOperation:
        return None


def normalize_unit_value(value: Decimal, unit: str) -> tuple[Decimal, str]:
    lowered = unit.strip().lower()
    if lowered in {"gr", "g"}:
        return value, "g"
    if lowered == "kg":
        return value * Decimal("1000"), "g"
    if lowered == "ml":
        return value, "ml"
    if lowered in {"l", "lt"}:
        return value * Decimal("1000"), "ml"
    return value, lowered


def extract_name_measure(name: str) -> tuple[Optional[Decimal], Optional[str]]:
    matches = list(NAME_MEASURE_RE.finditer(name))
    if not matches:
        return None, None

    match = matches[-1]
    unit = match.group("unit")
    numeric = parse_turkish_number(
        match.group("value"),
        assume_thousands_for_small_units=unit.strip().lower() in {"g", "gr", "ml"},
    )
    if numeric is None:
        return None, None
    return normalize_unit_value(numeric, unit)


def normalize_quantity(
    gramaj_degeri: Any,
    gramaj_birimi: Optional[str],
    adet_sayisi: Any,
    reference_name: str,
) -> tuple[Optional[float], Optional[str], Optional[float]]:
    quantity = coerce_decimal(gramaj_degeri)
    count = coerce_decimal(adet_sayisi)
    name_quantity, name_unit = extract_name_measure(reference_name)
    if quantity is not None and gramaj_birimi:
        unit = gramaj_birimi.strip().lower()
        if unit in {"gr", "g"}:
            base_value = quantity
            base_unit = "g"
        elif unit == "kg":
            base_value = quantity * Decimal("1000")
            base_unit = "g"
        elif unit == "ml":
            base_value = quantity
            base_unit = "ml"
        elif unit in {"l", "lt"}:
            base_value = quantity * Decimal("1000")
            base_unit = "ml"
        else:
            base_value = None
            base_unit = None

        if base_value is not None:
            if (
                name_quantity is not None
                and name_unit == base_unit
                and (
                    base_value <= 0
                    or (base_value < Decimal("10") and name_quantity >= base_value * Decimal("10"))
                )
            ):
                base_value = name_quantity
            unit_content = None
            if count is not None and count > 0:
                unit_content = float((base_value / count).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
            return float(base_value), base_unit, unit_content

    if name_quantity is not None and name_unit is not None:
        unit_content = None
        if count is not None and count > 0:
            unit_content = float((name_quantity / count).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
        return float(name_quantity), name_unit, unit_content

    if count is not None and count > 0:
        return float(count), "adet", 1.0

    return None, None, None


def compute_unit_price(price: Any, total_quantity: Optional[float]) -> Optional[float]:
    numeric_price = coerce_decimal(price)
    numeric_total = coerce_decimal(total_quantity)
    if numeric_price is None or numeric_total is None or numeric_total <= 0:
        return None
    return float((numeric_price / numeric_total).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def fetch_snapshots_for_day(target_date: date, market: str) -> list[FamilySnapshot]:
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                select
                    u.id as urun_id,
                    u.urun_ad,
                    u.urun_url,
                    u.market_adi,
                    u.urun_kategori,
                    f.kazima_tarihi,
                    f.urun_fiyat,
                    f.gramaj_degeri,
                    f.gramaj_birimi,
                    f.birim_fiyat,
                    f.adet_sayisi
                from urunler u
                join fiyat_zaman_serisi f on f.urun_id = u.id
                where date(f.kazima_tarihi) = :target_date
                  and lower(translate(coalesce(u.market_adi, ''), 'CGIOSUcgiosuÇĞİIÖŞÜçğıöşü', 'cgiosucgiosucgiiosucgiosu')) like :market_pattern
                order by u.id asc, f.kazima_tarihi desc, f.kayit_id desc
                """
            ),
            {
                "target_date": target_date.isoformat(),
                "market_pattern": f"{market}%",
            },
        ).mappings().all()
    finally:
        db.close()

    legacy_names = load_legacy_product_names()
    snapshots: list[FamilySnapshot] = []
    for row in rows:
        current_name = row["urun_ad"]
        effective_name = legacy_names.get(row["urun_id"], current_name)
        reference_name = effective_name if target_date <= date(2026, 3, 22) else current_name
        total_quantity, base_unit, unit_content = normalize_quantity(
            row["gramaj_degeri"],
            row["gramaj_birimi"],
            row["adet_sayisi"],
            reference_name,
        )
        snapshots.append(
            FamilySnapshot(
                urun_id=row["urun_id"],
                display_name=current_name,
                family_key=family_key_for_name(reference_name),
                market=row["market_adi"],
                category=row["urun_kategori"],
                url=row["urun_url"],
                snapshot=PriceSnapshot(
                    urun_id=row["urun_id"],
                    urun_ad=current_name,
                    kaynak_urun_ad=reference_name,
                    market_adi=row["market_adi"],
                    urun_kategori=row["urun_kategori"],
                    kazima_tarihi=row["kazima_tarihi"],
                    urun_fiyat=float(row["urun_fiyat"]) if row["urun_fiyat"] is not None else None,
                    toplam_icerik_degeri=total_quantity,
                    icerik_birimi=base_unit,
                    birim_icerik_degeri=unit_content,
                    adet_sayisi=float(row["adet_sayisi"]) if row["adet_sayisi"] is not None else None,
                    birim_fiyat=compute_unit_price(row["urun_fiyat"], total_quantity),
                ),
            )
        )
    return snapshots


def pair_snapshots(old_rows: list[FamilySnapshot], new_rows: list[FamilySnapshot]) -> list[tuple[FamilySnapshot, FamilySnapshot, float]]:
    candidates: list[tuple[float, int, int, FamilySnapshot, FamilySnapshot]] = []
    for old in old_rows:
        for new in new_rows:
            if old.family_key != new.family_key:
                continue
            if old.snapshot.icerik_birimi != new.snapshot.icerik_birimi:
                continue
            similarity = SequenceMatcher(None, old.family_key, new.family_key).ratio()
            category_bonus = 0.1 if old.category and new.category and old.category == new.category else 0.0
            quantity_ratio = 0.0
            if (
                old.snapshot.toplam_icerik_degeri is not None
                and new.snapshot.toplam_icerik_degeri is not None
                and old.snapshot.toplam_icerik_degeri > 0
                and new.snapshot.toplam_icerik_degeri > 0
            ):
                quantity_ratio = min(old.snapshot.toplam_icerik_degeri, new.snapshot.toplam_icerik_degeri) / max(
                    old.snapshot.toplam_icerik_degeri,
                    new.snapshot.toplam_icerik_degeri,
                )
                if quantity_ratio < 0.2:
                    continue
            score = similarity + category_bonus + quantity_ratio
            candidates.append((score, old.urun_id, new.urun_id, old, new))

    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    used_old: set[int] = set()
    used_new: set[int] = set()
    pairs: list[tuple[FamilySnapshot, FamilySnapshot, float]] = []
    for score, _, _, old, new in candidates:
        if old.urun_id in used_old or new.urun_id in used_new:
            continue
        used_old.add(old.urun_id)
        used_new.add(new.urun_id)
        pairs.append((old, new, score))
    return pairs


def compare_market_dates(
    market: str,
    old_date: date,
    new_date: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    old_snapshots = fetch_snapshots_for_day(old_date, market)
    new_snapshots = fetch_snapshots_for_day(new_date, market)

    old_by_family: dict[str, list[FamilySnapshot]] = {}
    new_by_family: dict[str, list[FamilySnapshot]] = {}
    for row in old_snapshots:
        if row.family_key:
            old_by_family.setdefault(row.family_key, []).append(row)
    for row in new_snapshots:
        if row.family_key:
            new_by_family.setdefault(row.family_key, []).append(row)

    matched_pairs: list[tuple[FamilySnapshot, FamilySnapshot, float]] = []
    for family_key in sorted(set(old_by_family) & set(new_by_family)):
        matched_pairs.extend(pair_snapshots(old_by_family[family_key], new_by_family[family_key]))

    summary_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    thresholds = DetectionThresholds(
        min_size_drop_pct=3.0,
        min_unit_price_increase_pct=3.0,
        stable_price_floor_pct=0.0,
    )

    for old, new, score in matched_pairs:
        finding = compare_snapshots(old.snapshot, new.snapshot, thresholds, require_material_change=False)
        if finding is None:
            continue

        row = {
            "market": market,
            "urun_ailesi": old.family_key,
            "eski_urun_id": old.urun_id,
            "yeni_urun_id": new.urun_id,
            "eski_urun_ad": old.display_name,
            "yeni_urun_ad": new.display_name,
            "eski_url": old.url,
            "yeni_url": new.url,
            "kategori": new.category or old.category,
            "eski_tarih": old.snapshot.kazima_tarihi.isoformat(),
            "yeni_tarih": new.snapshot.kazima_tarihi.isoformat(),
            "eski_fiyat": old.snapshot.urun_fiyat,
            "yeni_fiyat": new.snapshot.urun_fiyat,
            "eski_gramaj": old.snapshot.toplam_icerik_degeri,
            "yeni_gramaj": new.snapshot.toplam_icerik_degeri,
            "gramaj_birimi": new.snapshot.icerik_birimi or old.snapshot.icerik_birimi,
            "eski_birim_fiyat": old.snapshot.birim_fiyat,
            "yeni_birim_fiyat": new.snapshot.birim_fiyat,
            "gramaj_degisim_yuzdesi": finding.gramaj_degisim_yuzdesi,
            "birim_fiyat_degisim_yuzdesi": finding.birim_fiyat_degisim_yuzdesi,
            "fiyat_degisim_yuzdesi": finding.fiyat_degisim_yuzdesi,
            "is_content_decrease": bool(finding.gramaj_degisim_yuzdesi is not None and finding.gramaj_degisim_yuzdesi < 0),
            "is_unit_price_increase": bool(
                finding.birim_fiyat_degisim_yuzdesi is not None and finding.birim_fiyat_degisim_yuzdesi > 0
            ),
            "is_shrinkflation_risk": bool(finding.is_shrinkflation),
            "match_score": round(score, 4),
        }
        summary_rows.append(row)
        if row["is_content_decrease"] and row["is_unit_price_increase"]:
            candidate_rows.append(row)

    summary_rows.sort(
        key=lambda row: (
            row["is_shrinkflation_risk"],
            row["birim_fiyat_degisim_yuzdesi"] or float("-inf"),
            -(row["gramaj_degisim_yuzdesi"] or 0.0),
        ),
        reverse=True,
    )
    candidate_rows.sort(
        key=lambda row: (
            row["is_shrinkflation_risk"],
            row["birim_fiyat_degisim_yuzdesi"] or float("-inf"),
        ),
        reverse=True,
    )

    summary = {
        "market": market,
        "matched_families": len(summary_rows),
        "content_decrease_count": sum(1 for row in summary_rows if row["is_content_decrease"]),
        "unit_price_increase_candidates": sum(
            1 for row in summary_rows if row["is_content_decrease"] and row["is_unit_price_increase"]
        ),
        "strong_cases_same_or_up_price": sum(
            1
            for row in summary_rows
            if row["is_content_decrease"]
            and row["is_unit_price_increase"]
            and row["fiyat_degisim_yuzdesi"] is not None
            and row["fiyat_degisim_yuzdesi"] >= 0
        ),
        "risk_count": sum(1 for row in summary_rows if row["is_shrinkflation_risk"]),
    }
    return summary_rows, candidate_rows, summary


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            handle.write("")
        return
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Belirli iki tarih icin market bazinda shrinkflation adaylarini karsilastir.")
    parser.add_argument("--old-date", required=True)
    parser.add_argument("--new-date", required=True)
    parser.add_argument("--market", choices=["migros", "sok", "all"], default="all")
    args = parser.parse_args()

    old_date = datetime.strptime(args.old_date, "%Y-%m-%d").date()
    new_date = datetime.strptime(args.new_date, "%Y-%m-%d").date()
    markets = ["migros", "sok"] if args.market == "all" else [args.market]

    for market in markets:
        summary_rows, candidate_rows, summary = compare_market_dates(market, old_date, new_date)
        suffix = f"{old_date.strftime('%Y%m%d')}_vs_{new_date.strftime('%Y%m%d')}"
        summary_path = EXPORT_DIR / f"{market}_shrinkflation_summary_{suffix}.csv"
        candidate_path = EXPORT_DIR / f"{market}_shrinkflation_candidates_{suffix}.csv"
        write_csv(summary_rows, summary_path)
        write_csv(candidate_rows, candidate_path)

        print(f"[{market.upper()}]")
        print(f"Eslesen benzersiz urun ailesi: {summary['matched_families']}")
        print(f"Icerigi kuculen urun: {summary['content_decrease_count']}")
        print(f"Birim fiyati artan shrinkflation adayi: {summary['unit_price_increase_candidates']}")
        print(f"Nominal fiyati ayni kalip ya da artip kuculen guclu vaka: {summary['strong_cases_same_or_up_price']}")
        print(f"Risk olarak isaretlenen aday: {summary['risk_count']}")
        print(f"Ozet CSV: {summary_path}")
        print(f"Aday CSV: {candidate_path}")
        print("Ilk 5 aday:")
        for row in candidate_rows[:5]:
            print(
                f"- {row['eski_urun_ad']} -> {row['yeni_urun_ad']}, "
                f"{row['eski_gramaj']} {row['gramaj_birimi']} -> {row['yeni_gramaj']} {row['gramaj_birimi']}, "
                f"fiyat {row['eski_fiyat']} TL -> {row['yeni_fiyat']} TL, "
                f"birim fiyat %{row['birim_fiyat_degisim_yuzdesi']}, risk={row['is_shrinkflation_risk']}, "
                f"URL={row['yeni_url'] or '-'}"
            )
        if not candidate_rows:
            print("- Aday bulunamadi.")
        print("")


if __name__ == "__main__":
    main()
