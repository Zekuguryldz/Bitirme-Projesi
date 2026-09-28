from __future__ import annotations

import csv
import os
import re
import unicodedata
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.sql_helpers import build_canonical_product_identity_sql


COMPARABLE_UNITS = {"g", "ml", "adet"}
PRICE_EPSILON = 1e-9
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACK_RE = re.compile(
    r"(?P<a>\d+(?:[.,]\d+)?)\s*[*xX]\s*(?P<b>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|gr|g|ml|lt|l)\b",
    re.IGNORECASE,
)
TRAILING_COUNT_PACK_RE = re.compile(
    r"(?P<b>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|gr|g|ml|lt|l)\s*(?:[*xX]\s*)?(?P<a>\d+)\s*(?:['’]?\s*(?:li|lı|lu|lü)|\s*(?:adet|ad|paket|pk|yikama|tablet|yaprak))\b",
    re.IGNORECASE,
)
LEADING_COUNT_PACK_RE = re.compile(
    r"(?P<a>\d+)\s*(?:['’]?\s*(?:li|lı|lu|lü)|\s*(?:adet|ad|paket|pk|yikama|tablet|yaprak))\s*(?P<b>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|gr|g|ml|lt|l)\b",
    re.IGNORECASE,
)
SIMPLE_RE = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|gr|g|ml|lt|l)\b",
    re.IGNORECASE,
)
COUNT_MARKER_RE = re.compile(
    r"\d+\s*(?:['’]?\s*(?:li|lı|lu|lü)|\s*(?:adet|ad|paket|pk|yikama|tablet|yaprak))",
    re.IGNORECASE,
)
FAMILY_MEASURE_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(kg|gr|g|ml|lt|l)\b|"
    r"(\d+)\s*(?:['’]?\s*(?:li|lı|lu|lü)|adet|ad|paket|pk|yikama|tablet|yaprak)\b",
    re.IGNORECASE,
)
FAMILY_PUNCT_RE = re.compile(r"[^a-z0-9]+")


def fold_market_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return without_marks.translate(str.maketrans("çğıöşü", "cgiosu"))


@lru_cache(maxsize=8192)
def family_key_for_name(value: str) -> str:
    cleaned = FAMILY_MEASURE_RE.sub(" ", fold_market_text(value))
    cleaned = FAMILY_PUNCT_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\b(x|ve|ile|adet|ad|paket|pk|li|lı|lu|lü)\b", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_market_value(value: str) -> str:
    lowered = fold_market_text(value)
    if lowered.startswith("sok"):
        return "sok"
    if lowered.startswith("migros"):
        return "migros"
    return lowered


def market_matches(value: Optional[str], market: Optional[str]) -> bool:
    if not market:
        return True
    if not value:
        return False
    return normalize_market_value(value) == market


@dataclass(frozen=True)
class Candidate:
    total_base: float
    base_unit: str
    basis_unit: str
    unit_base: float
    pack_count: Optional[float]
    source: str
    parse_kind: str
    confidence: int
    raw_text: str
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SnapshotMeasure:
    total_base: Optional[float]
    base_unit: Optional[str]
    unit_base: Optional[float]
    pack_count: Optional[float]
    unit_price: Optional[float]


@dataclass(frozen=True)
class PriceSnapshot:
    urun_id: int
    urun_ad: str
    kaynak_urun_ad: str
    market_adi: Optional[str]
    urun_kategori: Optional[str]
    kazima_tarihi: datetime
    urun_fiyat: Optional[float]
    toplam_icerik_degeri: Optional[float]
    icerik_birimi: Optional[str]
    birim_icerik_degeri: Optional[float]
    adet_sayisi: Optional[float]
    birim_fiyat: Optional[float]


@dataclass(frozen=True)
class FamilySnapshot:
    urun_id: int
    display_name: str
    family_key: str
    market: Optional[str]
    category: Optional[str]
    snapshot: PriceSnapshot


@dataclass(frozen=True)
class DetectionThresholds:
    min_size_drop_pct: float = 3.0
    min_unit_price_increase_pct: float = 3.0
    stable_price_floor_pct: float = -1.0


@dataclass(frozen=True)
class ProductChangeFinding:
    urun_id: int
    urun_ad: str
    market_adi: Optional[str]
    urun_kategori: Optional[str]
    onceki_kayit_tarihi: datetime
    yeni_kayit_tarihi: datetime
    onceki_fiyat: Optional[float]
    yeni_fiyat: Optional[float]
    onceki_toplam_icerik: Optional[float]
    yeni_toplam_icerik: Optional[float]
    icerik_birimi: Optional[str]
    onceki_birim_icerik: Optional[float]
    yeni_birim_icerik: Optional[float]
    onceki_birim_fiyat: Optional[float]
    yeni_birim_fiyat: Optional[float]
    onceki_adet_sayisi: Optional[float]
    yeni_adet_sayisi: Optional[float]
    gramaj_degisim_yuzdesi: Optional[float]
    adet_degisim_yuzdesi: Optional[float]
    birim_icerik_degisim_yuzdesi: Optional[float]
    fiyat_degisim_yuzdesi: Optional[float]
    birim_fiyat_degisim_yuzdesi: Optional[float]
    shrinkflation_orani_yuzdesi: Optional[float]
    severity: str
    direction: str
    reason: str
    is_shrinkflation: bool

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["eski_fiyat"] = payload.pop("onceki_fiyat")
        payload["yeni_fiyat"] = payload.pop("yeni_fiyat")
        payload["eski_gramaj"] = payload.pop("onceki_toplam_icerik")
        payload["yeni_gramaj"] = payload.pop("yeni_toplam_icerik")
        payload["gramaj_birimi"] = payload.pop("icerik_birimi")
        payload["eski_birim_gramaj"] = payload.pop("onceki_birim_icerik")
        payload["yeni_birim_gramaj"] = payload.pop("yeni_birim_icerik")
        payload["eski_birim_fiyat"] = payload.pop("onceki_birim_fiyat")
        payload["yeni_birim_fiyat"] = payload.pop("yeni_birim_fiyat")
        payload["eski_adet_sayisi"] = payload.pop("onceki_adet_sayisi")
        payload["yeni_adet_sayisi"] = payload.pop("yeni_adet_sayisi")
        payload["eski_tarih"] = payload.pop("onceki_kayit_tarihi")
        payload["yeni_tarih"] = payload.pop("yeni_kayit_tarihi")
        payload["kazima_tarihi"] = payload["yeni_tarih"]
        return payload


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def parse_number(value: str) -> float:
    return float(value.replace(",", "."))


def canonical_unit(unit: str) -> str:
    lowered = unit.lower()
    if lowered in {"gr", "g"}:
        return "g"
    if lowered == "kg":
        return "kg"
    if lowered == "ml":
        return "ml"
    if lowered in {"l", "lt"}:
        return "l"
    raise ValueError(f"Unsupported unit: {unit}")


def convert_to_base(total_value: float, unit: str) -> tuple[float, str, str]:
    canonical = canonical_unit(unit)
    if canonical == "kg":
        return total_value * 1000.0, "g", "kg"
    if canonical == "g":
        return total_value, "g", "kg"
    if canonical == "l":
        return total_value * 1000.0, "ml", "l"
    if canonical == "ml":
        return total_value, "ml", "l"
    raise ValueError(f"Unsupported canonical unit: {canonical}")


def maybe_fix_decimal_ml(value: float, unit: str) -> tuple[float, str, Optional[str]]:
    canonical = canonical_unit(unit)
    if canonical == "ml" and value < 10 and value != int(value):
        return value, "l", "decimal_ml_assumed_liter"
    return value, canonical, None


def confidence_for_name_simple(text: str, match_start: int, match_end: int) -> int:
    before = False
    after = False
    for marker in COUNT_MARKER_RE.finditer(text):
        if marker.start() < match_start:
            before = True
        if marker.start() > match_end:
            after = True

    if before and not after:
        return 25
    if after and not before:
        return -20
    if before and after:
        return -5
    return 0


def build_pack_candidate(
    *,
    pack_count: float,
    unit_value: float,
    unit: str,
    source: str,
    parse_kind: str,
    raw_text: str,
    base_bonus: int = 20,
) -> Candidate:
    unit_value, unit, note = maybe_fix_decimal_ml(unit_value, unit)
    unit_base, base_unit, basis_unit = convert_to_base(unit_value, unit)
    total_base = unit_base * pack_count
    notes = [note] if note else []
    confidence = 100 + (10 if source == "product_name" else 0) + base_bonus
    if parse_kind == "leading_pack":
        confidence -= 5
    return Candidate(
        total_base=total_base,
        base_unit=base_unit,
        basis_unit=basis_unit,
        unit_base=unit_base,
        pack_count=pack_count,
        source=source,
        parse_kind=parse_kind,
        confidence=confidence,
        raw_text=raw_text,
        notes=notes,
    )


@lru_cache(maxsize=8192)
def extract_candidate(text_value: str, source: str) -> Optional[Candidate]:
    normalized = normalize_spaces(text_value)
    if not normalized:
        return None

    for pattern, parse_kind in (
        (PACK_RE, "pack"),
        (TRAILING_COUNT_PACK_RE, "trailing_pack"),
        (LEADING_COUNT_PACK_RE, "leading_pack"),
    ):
        matches = list(pattern.finditer(normalized))
        if not matches:
            continue
        match = matches[-1]
        pack_count = parse_number(match.group("a"))
        unit_value = parse_number(match.group("b"))
        unit = match.group("unit")
        return build_pack_candidate(
            pack_count=pack_count,
            unit_value=unit_value,
            unit=unit,
            source=source,
            parse_kind=parse_kind,
            raw_text=normalized,
        )

    simple_matches = list(SIMPLE_RE.finditer(normalized))
    if simple_matches:
        match = simple_matches[-1]
        value = parse_number(match.group("value"))
        unit = match.group("unit")
        value, unit, note = maybe_fix_decimal_ml(value, unit)
        total_base, base_unit, basis_unit = convert_to_base(value, unit)
        notes = [note] if note else []
        confidence = 100 + (10 if source == "product_name" else 0) + 10
        if source == "product_name":
            confidence += confidence_for_name_simple(normalized, match.start(), match.end())
        return Candidate(
            total_base=total_base,
            base_unit=base_unit,
            basis_unit=basis_unit,
            unit_base=total_base,
            pack_count=None,
            source=source,
            parse_kind="simple",
            confidence=confidence,
            raw_text=normalized,
            notes=notes,
        )

    return None


def choose_candidate(
    raw_candidate: Optional[Candidate],
    name_candidate: Optional[Candidate],
) -> tuple[Optional[Candidate], list[str]]:
    notes: list[str] = []

    if raw_candidate and name_candidate:
        if raw_candidate.base_unit != name_candidate.base_unit:
            notes.append("raw_name_unit_conflict")
            notes.extend(name_candidate.notes)
            return name_candidate, notes

        if abs(raw_candidate.total_base - name_candidate.total_base) <= 0.001:
            if name_candidate.pack_count and not raw_candidate.pack_count:
                notes.extend(name_candidate.notes)
                return name_candidate, notes
            notes.extend(raw_candidate.notes)
            return raw_candidate, notes

        notes.append("raw_name_value_conflict")
        if name_candidate.pack_count and not raw_candidate.pack_count:
            notes.extend(name_candidate.notes)
            return name_candidate, notes
        if name_candidate.confidence > raw_candidate.confidence:
            notes.extend(name_candidate.notes)
            return name_candidate, notes

        notes.extend(raw_candidate.notes)
        return raw_candidate, notes

    chosen = name_candidate or raw_candidate
    if chosen:
        notes.extend(chosen.notes)
    return chosen, notes


def compute_unit_price(
    price: Optional[float],
    total_base: Optional[float],
    base_unit: Optional[str],
) -> Optional[float]:
    if price is None or total_base is None or total_base <= 0 or not base_unit:
        return None

    if base_unit in {"g", "ml", "adet"}:
        return round(price / total_base, 4)

    return None


def compute_price_per_count(
    price: Optional[float],
    pack_count: Optional[float],
) -> Optional[float]:
    if price is None or pack_count is None or pack_count <= 0:
        return None
    return round(price / pack_count, 4)


def format_measure_text(gramaj_degeri: Optional[float], gramaj_birimi: Optional[str]) -> str:
    if gramaj_degeri is None or not gramaj_birimi:
        return ""
    if float(gramaj_degeri).is_integer():
        value_text = str(int(gramaj_degeri))
    else:
        value_text = f"{float(gramaj_degeri):.4f}".rstrip("0").rstrip(".")
    return f"{value_text} {gramaj_birimi}"


def coerce_count(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if value <= 0:
        return None
    return float(value)


def canonicalize_snapshot_measure(
    *,
    product_name: str,
    urun_fiyat: Optional[float],
    gramaj_degeri: Optional[float],
    gramaj_birimi: Optional[str],
    birim_fiyat: Optional[float],
    adet_sayisi: Optional[float],
) -> SnapshotMeasure:
    raw_candidate = extract_candidate(
        format_measure_text(gramaj_degeri, gramaj_birimi),
        "raw_field",
    )
    name_candidate = extract_candidate(product_name or "", "product_name")
    chosen, _ = choose_candidate(raw_candidate, name_candidate)

    db_count = coerce_count(adet_sayisi)
    if chosen is None:
        unit_price = (
            compute_unit_price(urun_fiyat, gramaj_degeri, gramaj_birimi)
            if gramaj_birimi in COMPARABLE_UNITS
            else birim_fiyat
        )
        if unit_price is None and db_count is not None:
            unit_price = compute_price_per_count(urun_fiyat, db_count)
        unit_base = None
        if gramaj_degeri is not None:
            if db_count and db_count > 1:
                unit_base = float(gramaj_degeri) / db_count
            else:
                unit_base = float(gramaj_degeri)
        return SnapshotMeasure(
            total_base=float(gramaj_degeri) if gramaj_degeri is not None else None,
            base_unit=gramaj_birimi,
            unit_base=unit_base,
            pack_count=db_count,
            unit_price=unit_price,
        )

    pack_count = db_count if db_count is not None else chosen.pack_count
    return SnapshotMeasure(
        total_base=float(chosen.total_base),
        base_unit=chosen.base_unit,
        unit_base=float(chosen.unit_base),
        pack_count=pack_count,
        unit_price=compute_unit_price(urun_fiyat, chosen.total_base, chosen.base_unit),
    )


def pct_change(old_value: Optional[float], new_value: Optional[float]) -> Optional[float]:
    if old_value is None or new_value is None or old_value == 0:
        return None
    return ((new_value - old_value) / old_value) * 100.0


def material_change_detected(*changes: Optional[float]) -> bool:
    for change in changes:
        if change is not None and abs(change) >= 0.01:
            return True
    return False


def classify_severity(signal_drop_pct: float) -> str:
    if signal_drop_pct >= 20.0:
        return "high"
    if signal_drop_pct >= 10.0:
        return "medium"
    return "low"


def classify_change_reason(
    total_change_pct: Optional[float],
    count_change_pct: Optional[float],
    unit_size_change_pct: Optional[float],
) -> tuple[str, str]:
    total_drop = total_change_pct is not None and total_change_pct < 0
    total_gain = total_change_pct is not None and total_change_pct > 0
    count_drop = count_change_pct is not None and count_change_pct < 0
    count_gain = count_change_pct is not None and count_change_pct > 0
    unit_drop = unit_size_change_pct is not None and unit_size_change_pct < 0
    unit_gain = unit_size_change_pct is not None and unit_size_change_pct > 0

    if total_drop:
        if count_drop and unit_drop:
            return "decrease", "pack_count_and_unit_size_reduced"
        if count_drop:
            return "decrease", "pack_count_reduced"
        if unit_drop:
            return "decrease", "unit_size_reduced"
        return "decrease", "total_content_reduced"

    if total_gain:
        if count_gain and unit_gain:
            return "increase", "pack_count_and_unit_size_increased"
        if count_gain:
            return "increase", "pack_count_increased"
        if unit_gain:
            return "increase", "unit_size_increased"
        return "increase", "total_content_increased"

    if count_drop:
        return "decrease", "pack_count_reduced"
    if count_gain:
        return "increase", "pack_count_increased"
    if unit_drop:
        return "decrease", "unit_size_reduced"
    if unit_gain:
        return "increase", "unit_size_increased"
    return "stable", "content_unchanged"


def compare_snapshots(
    previous_snapshot: PriceSnapshot,
    current_snapshot: PriceSnapshot,
    thresholds: DetectionThresholds,
    require_material_change: bool = True,
) -> Optional[ProductChangeFinding]:
    comparable_content_units = (
        previous_snapshot.icerik_birimi is not None
        and current_snapshot.icerik_birimi is not None
        and previous_snapshot.icerik_birimi in COMPARABLE_UNITS
        and current_snapshot.icerik_birimi in COMPARABLE_UNITS
        and previous_snapshot.icerik_birimi == current_snapshot.icerik_birimi
    )

    toplam_icerik_degisim_yuzdesi = None
    birim_icerik_degisim_yuzdesi = None
    if comparable_content_units:
        toplam_icerik_degisim_yuzdesi = pct_change(
            previous_snapshot.toplam_icerik_degeri,
            current_snapshot.toplam_icerik_degeri,
        )
        birim_icerik_degisim_yuzdesi = pct_change(
            previous_snapshot.birim_icerik_degeri,
            current_snapshot.birim_icerik_degeri,
        )

    adet_degisim_yuzdesi = pct_change(
        previous_snapshot.adet_sayisi,
        current_snapshot.adet_sayisi,
    )
    fiyat_degisim_yuzdesi = pct_change(previous_snapshot.urun_fiyat, current_snapshot.urun_fiyat)
    birim_fiyat_degisim_yuzdesi = pct_change(previous_snapshot.birim_fiyat, current_snapshot.birim_fiyat)

    has_material_change = material_change_detected(
        toplam_icerik_degisim_yuzdesi,
        adet_degisim_yuzdesi,
        birim_icerik_degisim_yuzdesi,
    )
    if require_material_change and not has_material_change:
        return None

    direction, reason = classify_change_reason(
        toplam_icerik_degisim_yuzdesi,
        adet_degisim_yuzdesi,
        birim_icerik_degisim_yuzdesi,
    )

    drop_signal_pct = max(
        [
            -change
            for change in (
                toplam_icerik_degisim_yuzdesi,
                adet_degisim_yuzdesi,
                birim_icerik_degisim_yuzdesi,
            )
            if change is not None and change < 0
        ]
        or [0.0]
    )

    is_shrinkflation = (
        direction == "decrease"
        and drop_signal_pct >= thresholds.min_size_drop_pct
        and birim_fiyat_degisim_yuzdesi is not None
        and birim_fiyat_degisim_yuzdesi >= thresholds.min_unit_price_increase_pct
    )
    severity = classify_severity(drop_signal_pct) if direction == "decrease" else "info"

    return ProductChangeFinding(
        urun_id=current_snapshot.urun_id,
        urun_ad=current_snapshot.urun_ad,
        market_adi=current_snapshot.market_adi,
        urun_kategori=current_snapshot.urun_kategori,
        onceki_kayit_tarihi=previous_snapshot.kazima_tarihi,
        yeni_kayit_tarihi=current_snapshot.kazima_tarihi,
        onceki_fiyat=previous_snapshot.urun_fiyat,
        yeni_fiyat=current_snapshot.urun_fiyat,
        onceki_toplam_icerik=previous_snapshot.toplam_icerik_degeri,
        yeni_toplam_icerik=current_snapshot.toplam_icerik_degeri,
        icerik_birimi=current_snapshot.icerik_birimi,
        onceki_birim_icerik=previous_snapshot.birim_icerik_degeri,
        yeni_birim_icerik=current_snapshot.birim_icerik_degeri,
        onceki_birim_fiyat=previous_snapshot.birim_fiyat,
        yeni_birim_fiyat=current_snapshot.birim_fiyat,
        onceki_adet_sayisi=previous_snapshot.adet_sayisi,
        yeni_adet_sayisi=current_snapshot.adet_sayisi,
        gramaj_degisim_yuzdesi=toplam_icerik_degisim_yuzdesi,
        adet_degisim_yuzdesi=adet_degisim_yuzdesi,
        birim_icerik_degisim_yuzdesi=birim_icerik_degisim_yuzdesi,
        fiyat_degisim_yuzdesi=fiyat_degisim_yuzdesi,
        birim_fiyat_degisim_yuzdesi=birim_fiyat_degisim_yuzdesi,
        shrinkflation_orani_yuzdesi=birim_fiyat_degisim_yuzdesi if is_shrinkflation else None,
        severity=severity,
        direction=direction,
        reason=reason,
        is_shrinkflation=is_shrinkflation,
    )


def detect_change_series(
    snapshots: Iterable[PriceSnapshot],
    thresholds: DetectionThresholds,
) -> list[ProductChangeFinding]:
    ordered = sorted(snapshots, key=lambda item: item.kazima_tarihi)
    findings: list[ProductChangeFinding] = []
    for previous_snapshot, current_snapshot in zip(ordered, ordered[1:]):
        finding = compare_snapshots(previous_snapshot, current_snapshot, thresholds)
        if finding is not None:
            findings.append(finding)
    return findings


@lru_cache(maxsize=1)
def load_legacy_product_names() -> dict[int, str]:
    candidate_paths: list[Path] = []
    env_path = os.getenv("LEGACY_PRODUCT_SNAPSHOT_CSV")
    if env_path:
        candidate_paths.append(Path(env_path).expanduser())
    candidate_paths.append(PROJECT_ROOT / "data" / "supabase_urunler_before_repair.csv")
    candidate_paths.append(Path("/Users/uguryildiz/Desktop/bitirme/bitirme-/outputs/supabase_urunler_before_repair.csv"))

    for path in candidate_paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return {
                int(row["id"]): row["urun_ad"]
                for row in csv.DictReader(handle)
                if row.get("id") and row.get("urun_ad")
            }
    return {}


def load_price_snapshots(db: Session) -> dict[str, list[PriceSnapshot]]:
    product_identity_sql = build_canonical_product_identity_sql("u.urun_url", "u.urun_ad")
    query = text(
        """
        SELECT
            """
        + product_identity_sql
        + """ AS urun_kimligi,
            u.id AS urun_id,
            u.urun_ad,
            u.market_adi,
            u.urun_kategori,
            f.kazima_tarihi,
            f.urun_fiyat,
            f.gramaj_degeri,
            f.gramaj_birimi,
            f.birim_fiyat,
            f.adet_sayisi
        FROM urunler u
        JOIN fiyat_zaman_serisi f ON f.urun_id = u.id
        ORDER BY u.id, f.kazima_tarihi ASC, f.kayit_id ASC
        """
    )
    legacy_names = load_legacy_product_names()
    grouped: dict[str, list[PriceSnapshot]] = {}

    for row in db.execute(query).mappings():
        current_name = row["urun_ad"]
        product_key = row.get("urun_kimligi") or str(row["urun_id"])
        product_snapshots = grouped.setdefault(str(product_key), [])
        effective_name = legacy_names.get(row["urun_id"], current_name) if not product_snapshots else current_name

        normalized = canonicalize_snapshot_measure(
            product_name=effective_name,
            urun_fiyat=float(row["urun_fiyat"]) if row["urun_fiyat"] is not None else None,
            gramaj_degeri=float(row["gramaj_degeri"]) if row["gramaj_degeri"] is not None else None,
            gramaj_birimi=row["gramaj_birimi"],
            birim_fiyat=float(row["birim_fiyat"]) if row["birim_fiyat"] is not None else None,
            adet_sayisi=float(row["adet_sayisi"]) if row["adet_sayisi"] is not None else None,
        )

        product_snapshots.append(
            PriceSnapshot(
                urun_id=row["urun_id"],
                urun_ad=current_name,
                kaynak_urun_ad=effective_name,
                market_adi=row["market_adi"],
                urun_kategori=row["urun_kategori"],
                kazima_tarihi=row["kazima_tarihi"],
                urun_fiyat=float(row["urun_fiyat"]) if row["urun_fiyat"] is not None else None,
                toplam_icerik_degeri=normalized.total_base,
                icerik_birimi=normalized.base_unit,
                birim_icerik_degeri=normalized.unit_base,
                adet_sayisi=normalized.pack_count,
                birim_fiyat=normalized.unit_price,
            )
        )
    return grouped


def build_change_findings(
    db: Session,
    thresholds: Optional[DetectionThresholds] = None,
) -> list[ProductChangeFinding]:
    effective_thresholds = thresholds or DetectionThresholds()
    findings: list[ProductChangeFinding] = []
    for snapshots in load_price_snapshots(db).values():
        findings.extend(detect_change_series(snapshots, effective_thresholds))
    return findings


def build_latest_product_comparisons(
    db: Session,
    thresholds: Optional[DetectionThresholds] = None,
) -> list[ProductChangeFinding]:
    effective_thresholds = thresholds or DetectionThresholds()
    findings: list[ProductChangeFinding] = []
    for snapshots in load_price_snapshots(db).values():
        ordered = sorted(snapshots, key=lambda item: item.kazima_tarihi)
        if len(ordered) < 2:
            continue
        finding = compare_snapshots(
            ordered[-2],
            ordered[-1],
            effective_thresholds,
            require_material_change=False,
        )
        if finding is not None:
            findings.append(finding)
    return findings


def build_family_snapshot(
    row: Any,
    *,
    target_date: date,
    legacy_names: dict[int, str],
) -> FamilySnapshot:
    current_name = row["urun_ad"]
    effective_name = legacy_names.get(row["urun_id"], current_name)
    reference_name = effective_name if target_date <= date(2026, 3, 22) else current_name
    normalized = canonicalize_snapshot_measure(
        product_name=reference_name,
        urun_fiyat=float(row["urun_fiyat"]) if row["urun_fiyat"] is not None else None,
        gramaj_degeri=float(row["gramaj_degeri"]) if row["gramaj_degeri"] is not None else None,
        gramaj_birimi=row["gramaj_birimi"],
        birim_fiyat=float(row["birim_fiyat"]) if row["birim_fiyat"] is not None else None,
        adet_sayisi=float(row["adet_sayisi"]) if row["adet_sayisi"] is not None else None,
    )
    snapshot = PriceSnapshot(
        urun_id=row["urun_id"],
        urun_ad=current_name,
        kaynak_urun_ad=reference_name,
        market_adi=row["market_adi"],
        urun_kategori=row["urun_kategori"],
        kazima_tarihi=row["kazima_tarihi"],
        urun_fiyat=float(row["urun_fiyat"]) if row["urun_fiyat"] is not None else None,
        toplam_icerik_degeri=normalized.total_base,
        icerik_birimi=normalized.base_unit,
        birim_icerik_degeri=normalized.unit_base,
        adet_sayisi=normalized.pack_count,
        birim_fiyat=normalized.unit_price,
    )
    return FamilySnapshot(
        urun_id=row["urun_id"],
        display_name=current_name,
        family_key=family_key_for_name(reference_name),
        market=row["market_adi"],
        category=row["urun_kategori"],
        snapshot=snapshot,
    )


def load_family_snapshots_for_date(
    db: Session,
    *,
    target_date: date,
    market: str,
) -> list[FamilySnapshot]:
    market_pattern = "sok%" if market == "sok" else "migros%"
    query = text(
        """
        with ranked_snapshots as (
            select
                u.id as urun_id,
                u.urun_ad,
                u.market_adi,
                u.urun_kategori,
                f.kazima_tarihi,
                f.urun_fiyat,
                f.gramaj_degeri,
                f.gramaj_birimi,
                f.birim_fiyat,
                f.adet_sayisi,
                row_number() over (
                    partition by u.id
                    order by f.kazima_tarihi desc nulls last, f.kayit_id desc
                ) as rn
            from urunler u
            join fiyat_zaman_serisi f on f.urun_id = u.id
            where f.kazima_tarihi >= :date_start and f.kazima_tarihi < :date_end
              and lower(
                    translate(
                        coalesce(u.market_adi, ''),
                        'CGIOSUcgiosuÇĞİIÖŞÜçğıöşü',
                        'cgiosucgiosucgiiosucgiosu'
                    )
                ) like :market_pattern
        )
        select
            urun_id,
            urun_ad,
            market_adi,
            urun_kategori,
            kazima_tarihi,
            urun_fiyat,
            gramaj_degeri,
            gramaj_birimi,
            birim_fiyat,
            adet_sayisi
        from ranked_snapshots
        where rn = 1
        order by urun_id asc
        """
    )
    legacy_names = load_legacy_product_names()
    rows = db.execute(
        query,
        {
            "date_start": target_date.isoformat(),
            "date_end": (target_date + timedelta(days=1)).isoformat(),
            "market_pattern": market_pattern,
        },
    ).mappings()
    return [
        build_family_snapshot(
            row,
            target_date=target_date,
            legacy_names=legacy_names,
        )
        for row in rows
    ]


def pair_family_snapshots(
    previous_rows: list[FamilySnapshot],
    current_rows: list[FamilySnapshot],
) -> list[tuple[FamilySnapshot, FamilySnapshot, float]]:
    current_by_key: dict[str, list[FamilySnapshot]] = {}
    for current in current_rows:
        if current.family_key:
            current_by_key.setdefault(current.family_key, []).append(current)

    candidates: list[tuple[float, int, int, FamilySnapshot, FamilySnapshot]] = []
    for previous in previous_rows:
        if not previous.family_key:
            continue
        for current in current_by_key.get(previous.family_key, []):
            if previous.snapshot.icerik_birimi != current.snapshot.icerik_birimi:
                continue

            quantity_ratio = 0.0
            if (
                previous.snapshot.toplam_icerik_degeri is not None
                and current.snapshot.toplam_icerik_degeri is not None
                and previous.snapshot.toplam_icerik_degeri > 0
                and current.snapshot.toplam_icerik_degeri > 0
            ):
                quantity_ratio = min(
                    previous.snapshot.toplam_icerik_degeri,
                    current.snapshot.toplam_icerik_degeri,
                ) / max(
                    previous.snapshot.toplam_icerik_degeri,
                    current.snapshot.toplam_icerik_degeri,
                )
                if quantity_ratio < 0.2:
                    continue

            category_bonus = 0.1 if previous.category and previous.category == current.category else 0.0
            score = 1.0 + category_bonus + quantity_ratio
            candidates.append((score, previous.urun_id, current.urun_id, previous, current))

    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    used_previous: set[int] = set()
    used_current: set[int] = set()
    pairs: list[tuple[FamilySnapshot, FamilySnapshot, float]] = []
    for score, _, _, previous, current in candidates:
        if previous.urun_id in used_previous or current.urun_id in used_current:
            continue
        used_previous.add(previous.urun_id)
        used_current.add(current.urun_id)
        pairs.append((previous, current, score))
    return pairs


def build_market_date_comparison_findings(
    db: Session,
    *,
    market: str,
    old_date: date,
    new_date: date,
    thresholds: Optional[DetectionThresholds] = None,
) -> list[ProductChangeFinding]:
    effective_thresholds = thresholds or DetectionThresholds()
    previous_rows = load_family_snapshots_for_date(db, target_date=old_date, market=market)
    current_rows = load_family_snapshots_for_date(db, target_date=new_date, market=market)
    findings: list[ProductChangeFinding] = []
    for previous, current, _ in pair_family_snapshots(previous_rows, current_rows):
        finding = compare_snapshots(
            previous.snapshot,
            current.snapshot,
            effective_thresholds,
            require_material_change=False,
        )
        if finding is not None:
            findings.append(finding)
    return findings


def list_market_date_comparison_findings(
    db: Session,
    *,
    market: str,
    old_date: date,
    new_date: date,
    thresholds: Optional[DetectionThresholds] = None,
    limit: Optional[int] = None,
    increases_only: bool = False,
    decreases_only: bool = False,
    shrinkflation_only: bool = False,
    sort_by_unit_price: bool = False,
    sort_by_unit_price_decrease: bool = False,
    sort_by_shrinkflation_risk: bool = False,
) -> list[dict[str, object]]:
    findings = build_market_date_comparison_findings(
        db,
        market=market,
        old_date=old_date,
        new_date=new_date,
        thresholds=thresholds,
    )
    findings = filter_product_comparison_findings(
        findings,
        market=market,
        increases_only=increases_only,
        decreases_only=decreases_only,
        shrinkflation_only=shrinkflation_only,
    )
    if sort_by_shrinkflation_risk:
        findings.sort(key=sort_key_for_shrinkflation_risk, reverse=True)
    elif sort_by_unit_price_decrease:
        findings.sort(key=sort_key_for_unit_price_drop, reverse=True)
    else:
        findings.sort(
            key=sort_key_for_unit_price_gain if sort_by_unit_price else sort_key_for_latest_product_comparison,
            reverse=True,
        )
    rows = [finding.to_dict() for finding in findings]
    if limit is not None:
        return rows[:limit]
    return rows


def count_market_date_shrinkflation_findings(
    db: Session,
    *,
    market: str,
    old_date: date,
    new_date: date,
    thresholds: Optional[DetectionThresholds] = None,
) -> int:
    findings = build_market_date_comparison_findings(
        db,
        market=market,
        old_date=old_date,
        new_date=new_date,
        thresholds=thresholds,
    )
    findings = filter_findings(
        findings,
        market=market,
        decreases_only=True,
        shrinkflation_only=True,
        content_decrease_only=True,
        unit_price_increase_only=True,
    )
    return len(findings)


def sort_key_for_content_change(item: ProductChangeFinding) -> tuple[float, datetime, int]:
    magnitude = max(
        abs(item.gramaj_degisim_yuzdesi or 0.0),
        abs(item.adet_degisim_yuzdesi or 0.0),
        abs(item.birim_icerik_degisim_yuzdesi or 0.0),
    )
    return (magnitude, item.yeni_kayit_tarihi, item.urun_id)


def filter_findings(
    findings: list[ProductChangeFinding],
    *,
    market: Optional[str] = None,
    latest_day_only: bool = False,
    decreases_only: bool = False,
    shrinkflation_only: bool = False,
    content_decrease_only: bool = False,
    unit_price_increase_only: bool = False,
    date_start: Optional[datetime] = None,
    date_end: Optional[datetime] = None,
) -> list[ProductChangeFinding]:
    filtered = findings
    if market:
        filtered = [item for item in filtered if market_matches(item.market_adi, market)]
    if decreases_only:
        filtered = [item for item in filtered if item.direction == "decrease"]
    if shrinkflation_only:
        filtered = [item for item in filtered if item.is_shrinkflation]
    if content_decrease_only:
        filtered = [
            item
            for item in filtered
            if item.gramaj_degisim_yuzdesi is not None
            and item.gramaj_degisim_yuzdesi < 0
        ]
    if unit_price_increase_only:
        filtered = [
            item
            for item in filtered
            if item.birim_fiyat_degisim_yuzdesi is not None
            and item.birim_fiyat_degisim_yuzdesi > 0
        ]
    if date_start:
        filtered = [item for item in filtered if item.yeni_kayit_tarihi >= date_start]
    if date_end:
        filtered = [item for item in filtered if item.yeni_kayit_tarihi < date_end]
    if latest_day_only and filtered:
        latest_date = max(item.yeni_kayit_tarihi.date() for item in filtered)
        filtered = [item for item in filtered if item.yeni_kayit_tarihi.date() == latest_date]
    return filtered


def sort_key_for_daily_anomaly(item: ProductChangeFinding) -> tuple[int, float, datetime, int]:
    return (
        1 if item.is_shrinkflation else 0,
        max(
            abs(item.gramaj_degisim_yuzdesi or 0.0),
            abs(item.adet_degisim_yuzdesi or 0.0),
            abs(item.birim_icerik_degisim_yuzdesi or 0.0),
        ),
        item.yeni_kayit_tarihi,
        item.urun_id,
    )


def list_content_change_findings(
    db: Session,
    thresholds: Optional[DetectionThresholds] = None,
    limit: Optional[int] = None,
) -> list[dict[str, object]]:
    findings = build_change_findings(db, thresholds)
    findings.sort(key=sort_key_for_content_change, reverse=True)
    rows = [finding.to_dict() for finding in findings]
    if limit is not None:
        return rows[:limit]
    return rows


def sort_key_for_latest_product_comparison(
    item: ProductChangeFinding,
) -> tuple[datetime, float, int]:
    magnitude = max(
        abs(item.gramaj_degisim_yuzdesi or 0.0),
        abs(item.adet_degisim_yuzdesi or 0.0),
        abs(item.birim_icerik_degisim_yuzdesi or 0.0),
        abs(item.birim_fiyat_degisim_yuzdesi or 0.0),
        abs(item.fiyat_degisim_yuzdesi or 0.0),
    )
    return (item.yeni_kayit_tarihi, magnitude, item.urun_id)


def sort_key_for_unit_price_gain(
    item: ProductChangeFinding,
) -> tuple[float, datetime, int]:
    return (
        item.birim_fiyat_degisim_yuzdesi or float("-inf"),
        item.yeni_kayit_tarihi,
        item.urun_id,
    )


def sort_key_for_unit_price_drop(
    item: ProductChangeFinding,
) -> tuple[float, datetime, int]:
    degisim = item.birim_fiyat_degisim_yuzdesi
    return (
        abs(degisim) if degisim is not None and degisim < 0 else float("-inf"),
        item.yeni_kayit_tarihi,
        item.urun_id,
    )


def filter_product_comparison_findings(
    findings: list[ProductChangeFinding],
    *,
    market: Optional[str] = None,
    increases_only: bool = False,
    decreases_only: bool = False,
    shrinkflation_only: bool = False,
    date_start: Optional[datetime] = None,
    date_end: Optional[datetime] = None,
) -> list[ProductChangeFinding]:
    filtered = findings
    if market:
        filtered = [item for item in filtered if market_matches(item.market_adi, market)]
    if increases_only:
        filtered = [
            item
            for item in filtered
            if item.birim_fiyat_degisim_yuzdesi is not None
            and item.birim_fiyat_degisim_yuzdesi > 0
        ]
    if decreases_only:
        filtered = [
            item
            for item in filtered
            if item.birim_fiyat_degisim_yuzdesi is not None
            and item.birim_fiyat_degisim_yuzdesi < 0
        ]
    if shrinkflation_only:
        filtered = [item for item in filtered if item.is_shrinkflation]
    if date_start:
        filtered = [item for item in filtered if item.yeni_kayit_tarihi >= date_start]
    if date_end:
        filtered = [item for item in filtered if item.yeni_kayit_tarihi < date_end]
    return filtered


def list_latest_product_comparisons(
    db: Session,
    thresholds: Optional[DetectionThresholds] = None,
    limit: Optional[int] = None,
    market: Optional[str] = None,
    increases_only: bool = False,
    decreases_only: bool = False,
    shrinkflation_only: bool = False,
    date_start: Optional[datetime] = None,
    date_end: Optional[datetime] = None,
    sort_by_unit_price: bool = False,
    sort_by_unit_price_decrease: bool = False,
    sort_by_shrinkflation_risk: bool = False,
) -> list[dict[str, object]]:
    findings = build_latest_product_comparisons(db, thresholds)
    findings = filter_product_comparison_findings(
        findings,
        market=market,
        increases_only=increases_only,
        decreases_only=decreases_only,
        shrinkflation_only=shrinkflation_only,
        date_start=date_start,
        date_end=date_end,
    )
    if sort_by_shrinkflation_risk:
        findings.sort(key=sort_key_for_shrinkflation_risk, reverse=True)
    elif sort_by_unit_price_decrease:
        findings.sort(key=sort_key_for_unit_price_drop, reverse=True)
    else:
        findings.sort(
            key=sort_key_for_unit_price_gain if sort_by_unit_price else sort_key_for_latest_product_comparison,
            reverse=True,
        )
    rows = [finding.to_dict() for finding in findings]
    if limit is not None:
        return rows[:limit]
    return rows


def list_top_unit_price_increase_findings(
    db: Session,
    thresholds: Optional[DetectionThresholds] = None,
    limit: Optional[int] = None,
    market: Optional[str] = None,
    days: int = 30,
) -> list[dict[str, object]]:
    findings = filter_product_comparison_findings(
        build_change_findings(db, thresholds),
        market=market,
        increases_only=True,
        date_start=datetime.now(timezone.utc) - timedelta(days=days),
    )
    best_findings_by_product: dict[int, ProductChangeFinding] = {}
    for finding in findings:
        current_best = best_findings_by_product.get(finding.urun_id)
        if current_best is None or sort_key_for_unit_price_gain(finding) > sort_key_for_unit_price_gain(current_best):
            best_findings_by_product[finding.urun_id] = finding

    findings = list(best_findings_by_product.values())
    findings.sort(key=sort_key_for_unit_price_gain, reverse=True)
    rows: list[dict[str, object]] = []
    for finding in findings:
        payload = finding.to_dict()
        payload["degisim_yuzdesi"] = payload.get("birim_fiyat_degisim_yuzdesi")
        rows.append(payload)
    if limit is not None:
        return rows[:limit]
    return rows


def list_daily_anomaly_findings(
    db: Session,
    thresholds: Optional[DetectionThresholds] = None,
    limit: Optional[int] = None,
    market: Optional[str] = None,
) -> list[dict[str, object]]:
    findings = filter_findings(
        build_change_findings(db, thresholds),
        market=market,
        latest_day_only=True,
        decreases_only=True,
    )
    findings.sort(key=sort_key_for_daily_anomaly, reverse=True)
    rows = [finding.to_dict() for finding in findings]
    if limit is not None:
        return rows[:limit]
    return rows


def sort_key_for_shrinkflation_risk(item: ProductChangeFinding) -> tuple[float, float, datetime, int]:
    return (
        item.birim_fiyat_degisim_yuzdesi or float("-inf"),
        abs(item.gramaj_degisim_yuzdesi or 0.0),
        item.yeni_kayit_tarihi,
        item.urun_id,
    )


def list_shrinkflation_risk_findings(
    db: Session,
    thresholds: Optional[DetectionThresholds] = None,
    limit: Optional[int] = None,
    market: Optional[str] = None,
    date_start: Optional[datetime] = None,
    date_end: Optional[datetime] = None,
) -> list[dict[str, object]]:
    findings = filter_findings(
        build_change_findings(db, thresholds),
        market=market,
        decreases_only=True,
        shrinkflation_only=True,
        content_decrease_only=True,
        unit_price_increase_only=True,
        date_start=date_start,
        date_end=date_end,
    )
    findings.sort(key=sort_key_for_shrinkflation_risk, reverse=True)
    rows = [finding.to_dict() for finding in findings]
    if limit is not None:
        return rows[:limit]
    return rows


def count_shrinkflation_risk_findings(
    db: Session,
    thresholds: Optional[DetectionThresholds] = None,
    market: Optional[str] = None,
    date_start: Optional[datetime] = None,
    date_end: Optional[datetime] = None,
) -> int:
    findings = filter_findings(
        build_change_findings(db, thresholds),
        market=market,
        decreases_only=True,
        shrinkflation_only=True,
        content_decrease_only=True,
        unit_price_increase_only=True,
        date_start=date_start,
        date_end=date_end,
    )
    return len(findings)


def count_daily_anomaly_findings(
    db: Session,
    thresholds: Optional[DetectionThresholds] = None,
    market: Optional[str] = None,
) -> int:
    findings = filter_findings(
        build_change_findings(db, thresholds),
        market=market,
        latest_day_only=True,
        decreases_only=True,
    )
    return len(findings)


def list_shrinkflation_findings(
    db: Session,
    thresholds: Optional[DetectionThresholds] = None,
    limit: Optional[int] = None,
) -> list[dict[str, object]]:
    findings = [item for item in build_change_findings(db, thresholds) if item.is_shrinkflation]
    findings.sort(
        key=lambda item: (
            item.shrinkflation_orani_yuzdesi or 0.0,
            sort_key_for_content_change(item),
        ),
        reverse=True,
    )
    rows = [finding.to_dict() for finding in findings]
    if limit is not None:
        return rows[:limit]
    return rows
