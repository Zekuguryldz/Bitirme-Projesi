import argparse

import csv

import re

from dataclasses import dataclass, field

from pathlib import Path

from typing import Dict, Iterable, Optional





PACK_RE = re.compile(

    r"(?P<a>\d+(?:[.,]\d+)?)\s*[*xX]\s*(?P<b>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|gr|g|ml|lt|l)\b",

    re.IGNORECASE,

)

TRAILING_COUNT_PACK_RE = re.compile(

    r"(?P<b>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|gr|g|ml|lt|l)\s*(?:[*xX]\s*)?(?P<a>\d+)\s*(?:['’]?\s*(?:li|lı|lu|lü)|\s*(?:adet|ad|paket|pk|yikama|tablet|yaprak))\b",

    re.IGNORECASE,

)

SIMPLE_RE = re.compile(

    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|gr|g|ml|lt|l)\b",

    re.IGNORECASE,

)

BARE_UNIT_RE = re.compile(r"\b(?P<unit>kg|lt|l)\b", re.IGNORECASE)

COUNT_MARKER_RE = re.compile(

    r"\d+\s*(?:['’]?\s*(?:li|lı|lu|lü)|\s*(?:adet|ad|paket|pk|yikama|tablet|yaprak))",

    re.IGNORECASE,

)

PURE_COUNT_RE = re.compile(

    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?:['’]?\s*(?:li|lı|lu|lü)|(?P<unit>adet|ad|paket|pk|yikama|yıkama|kullanim|kullanım|tablet|yaprak|kapsul|kapsül|porsiyon|servis|poşet|poset|saşe|sase))\b",

    re.IGNORECASE,

)





@dataclass

class Aday:

    total_base: float

    temel_birim: str

    taban_birim: str

    source: str

    parse_kind: str

    confidence: int

    raw_text: str

    notes: list[str] = field(default_factory=list)





def normalize_spaces(value: str) -> str:

    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()





def parse_number(value: str) -> float:

    return float(value.replace(",", "."))





def standart_birim(birim: str) -> str:

    lowered = birim.lower()

    if lowered in {"gr", "g"}:

        return "g"

    if lowered == "kg":

        return "kg"

    if lowered == "ml":

        return "ml"

    if lowered in {"l", "lt"}:

        return "l"

    if lowered in {

        "adet",

        "ad",

        "paket",

        "pk",

        "yikama",

        "yıkama",

        "kullanim",

        "kullanım",

        "tablet",

        "yaprak",

        "kapsul",

        "kapsül",

        "porsiyon",

        "servis",

        "poşet",

        "poset",

        "saşe",

        "sase",

        "li",

        "lı",

        "lu",

        "lü",

    }:

        return "adet"

    raise ValueError(f"Unsupported unit: {birim}")





def convert_to_base(total_value: float, birim: str) -> tuple[float, str, str]:

    canonical = standart_birim(birim)

    if canonical == "kg":

        return total_value * 1000.0, "g", "kg"

    if canonical == "g":

        return total_value, "g", "kg"

    if canonical == "l":

        return total_value * 1000.0, "ml", "l"

    if canonical == "ml":

        return total_value, "ml", "l"

    if canonical == "adet":

        return total_value, "adet", "adet"

    raise ValueError(f"Unsupported canonical unit: {canonical}")





def maybe_fix_decimal_ml(value: float, birim: str) -> tuple[float, str, Optional[str]]:

    canonical = standart_birim(birim)

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





def extract_candidate(text: str, source: str) -> Optional[Aday]:

    normalize_edilmis = normalize_spaces(text)

    if not normalize_edilmis:

        return None



    pack_matches = list(PACK_RE.finditer(normalize_edilmis))

    if pack_matches:

        eslesme = pack_matches[-1]

        a = parse_number(eslesme.group("a"))

        b = parse_number(eslesme.group("b"))

        birim = eslesme.group("unit")

        total_value = a * b

        total_value, birim, note = maybe_fix_decimal_ml(total_value, birim)

        total_base, temel_birim, taban_birim = convert_to_base(total_value, birim)

        notes = [note] if note else []

        confidence = 100 + (10 if source == "product_name" else 0) + 20

        return Aday(

            total_base=total_base,

            temel_birim=temel_birim,

            taban_birim=taban_birim,

            source=source,

            parse_kind="pack",

            confidence=confidence,

            raw_text=normalize_edilmis,

            notes=notes,

        )



    trailing_pack_matches = list(TRAILING_COUNT_PACK_RE.finditer(normalize_edilmis))

    if trailing_pack_matches:

        eslesme = trailing_pack_matches[-1]

        a = parse_number(eslesme.group("a"))

        b = parse_number(eslesme.group("b"))

        birim = eslesme.group("unit")

        total_value = a * b

        total_value, birim, note = maybe_fix_decimal_ml(total_value, birim)

        total_base, temel_birim, taban_birim = convert_to_base(total_value, birim)

        notes = [note] if note else []

        confidence = 100 + (10 if source == "product_name" else 0) + 20

        return Aday(

            total_base=total_base,

            temel_birim=temel_birim,

            taban_birim=taban_birim,

            source=source,

            parse_kind="trailing_pack",

            confidence=confidence,

            raw_text=normalize_edilmis,

            notes=notes,

        )



    simple_matches = list(SIMPLE_RE.finditer(normalize_edilmis))

    if simple_matches:

        eslesme = simple_matches[-1]

        value = parse_number(eslesme.group("value"))

        birim = eslesme.group("unit")

        value, birim, note = maybe_fix_decimal_ml(value, birim)

        total_base, temel_birim, taban_birim = convert_to_base(value, birim)

        notes = [note] if note else []

        confidence = 100 + (10 if source == "product_name" else 0) + 10

        if source == "product_name":

            confidence += confidence_for_name_simple(normalize_edilmis, eslesme.start(), eslesme.end())

        return Aday(

            total_base=total_base,

            temel_birim=temel_birim,

            taban_birim=taban_birim,

            source=source,

            parse_kind="simple",

            confidence=confidence,

            raw_text=normalize_edilmis,

            notes=notes,

        )



    bare_unit_matches = list(BARE_UNIT_RE.finditer(normalize_edilmis))

    if bare_unit_matches:

        eslesme = bare_unit_matches[-1]

        birim = eslesme.group("unit")

        total_base, temel_birim, taban_birim = convert_to_base(1.0, birim)

        confidence = 35 + (10 if source == "product_name" else 0)

        return Aday(

            total_base=total_base,

            temel_birim=temel_birim,

            taban_birim=taban_birim,

            source=source,

            parse_kind="bare_unit",

            confidence=confidence,

            raw_text=normalize_edilmis,

        )



    pure_count_matches = list(PURE_COUNT_RE.finditer(normalize_edilmis))

    if pure_count_matches:

        eslesme = pure_count_matches[-1]

        value = parse_number(eslesme.group("value"))

        ham_birim = eslesme.group("unit") or "adet"

        total_base, temel_birim, taban_birim = convert_to_base(value, ham_birim)

        confidence = 90 + (10 if source == "product_name" else 0)

        return Aday(

            total_base=total_base,

            temel_birim=temel_birim,

            taban_birim=taban_birim,

            source=source,

            parse_kind="pure_count",

            confidence=confidence,

            raw_text=normalize_edilmis,

        )



    return None





def choose_candidate(

    ham_aday: Optional[Aday],

    ad_adayi: Optional[Aday],

) -> tuple[Optional[Aday], list[str]]:

    notes: list[str] = []



    if ham_aday and ad_adayi:

        if ham_aday.temel_birim != ad_adayi.temel_birim:

            notes.append("raw_name_unit_conflict")

            notes.extend(ad_adayi.notes)

            return ad_adayi, notes



        if abs(ham_aday.total_base - ad_adayi.total_base) <= 0.001:

            notes.extend(ham_aday.notes)

            return ham_aday, notes



        notes.append("raw_name_value_conflict")

        if ad_adayi.confidence > ham_aday.confidence:

            notes.extend(ad_adayi.notes)

            return ad_adayi, notes



        notes.extend(ham_aday.notes)

        return ham_aday, notes



    chosen = ad_adayi or ham_aday

    if chosen:

        notes.extend(chosen.notes)

    return chosen, notes





def compute_unit_price(fiyat: Optional[float], total_base: Optional[float], taban_birim: Optional[str]) -> Optional[float]:

    if fiyat is None or total_base is None or total_base <= 0 or not taban_birim:

        return None

    multiplier = 1.0 if taban_birim == "adet" else 1000.0

    return fiyat * multiplier / total_base





def compute_unit_price_per_100(fiyat: Optional[float], total_base: Optional[float]) -> Optional[float]:

    if fiyat is None or total_base is None or total_base <= 0:

        return None

    return fiyat * 100.0 / total_base





def maybe_parse_float(value: str) -> Optional[float]:

    text = (value or "").strip()

    if not text:

        return None

    return parse_number(text)





def format_number(value: Optional[float]) -> str:

    if value is None:

        return ""

    rounded = round(value, 4)

    if abs(rounded - round(rounded)) < 1e-9:

        return str(int(round(rounded)))

    return f"{rounded:.4f}".rstrip("0").rstrip(".")





def load_product_names(yol: Optional[Path]) -> Dict[str, str]:

    if not yol or not yol.exists():

        return {}



    with yol.open("r", encoding="utf-8-sig", newline="") as handle:

        return {satir["id"]: satir["urun_ad"] for satir in csv.DictReader(handle)}





def default_output_paths(girdi_yolu: Path) -> tuple[Path, Path]:

    normalize_edilmis = girdi_yolu.with_name(f"{input_path.stem}_normalized.csv")

    audit = girdi_yolu.with_name(f"{input_path.stem}_normalization_audit.csv")

    return normalize_edilmis, audit





def normalize_rows(

    satirlar: Iterable[dict[str, str]],

    urun_adlari: Dict[str, str],

) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:

    normalize_satirlar: list[dict[str, str]] = []

    denetim_satirlari: list[dict[str, str]] = []

    stats = {

        "total": 0,

        "normalized": 0,

        "resolved_from_product_name": 0,

        "unresolved": 0,

        "cleared_old_unit_price": 0,

    }



    for satir in satirlar:

        stats["total"] += 1



        urun_adi = urun_adlari.get(satir["urun_id"], "")

        raw_measure = (satir.get("gramaj_degeri") or "").strip()

        ham_birim = (satir.get("gramaj_birimi") or "").strip()

        fiyat = maybe_parse_float(satir.get("urun_fiyat", ""))

        ham_aday = extract_candidate(raw_measure, "raw_field")

        ad_adayi = extract_candidate(urun_adi, "product_name")

        chosen, notes = choose_candidate(ham_aday, ad_adayi)



        normalize_olcu = ""

        normalize_birim = ""

        normalize_birim_fiyat = ""

        taban_birim = ""

        unit_price_per_100 = ""

        source = "unresolved"



        if chosen:

            normalize_olcu = format_number(chosen.total_base)

            normalize_birim = chosen.temel_birim

            taban_birim = chosen.taban_birim

            normalize_birim_fiyat = format_number(

                compute_unit_price(fiyat, chosen.total_base, chosen.taban_birim)

            )

            unit_price_per_100 = format_number(

                compute_unit_price_per_100(fiyat, chosen.total_base)

            )

            source = chosen.source

            stats["normalized"] += 1

            if chosen.source == "product_name":

                stats["resolved_from_product_name"] += 1

        else:

            stats["unresolved"] += 1

            if (satir.get("unit_price") or "").strip():

                stats["cleared_old_unit_price"] += 1



        normalize_satirlar.append(

            {

                "kayit_id": satir["kayit_id"],

                "urun_id": satir["urun_id"],

                "urun_fiyat": satir["urun_fiyat"],

                "gramaj_degeri": normalize_olcu,

                "gramaj_birimi": normalize_birim,

                "unit_price": normalize_birim_fiyat,

                "kazima_tarihi": satir["kazima_tarihi"],

            }

        )



        denetim_satirlari.append(

            {

                "kayit_id": satir["kayit_id"],

                "urun_id": satir["urun_id"],

                "urun_ad": urun_adi,

                "urun_fiyat": satir["urun_fiyat"],

                "gramaj_raw": raw_measure,

                "gramaj_birimi_raw": ham_birim,

                "unit_price_raw": satir.get("unit_price", ""),

                "gramaj_degeri_normalized": normalize_olcu,

                "gramaj_birimi_normalized": normalize_birim,

                "unit_price_normalized": normalize_birim_fiyat,

                "unit_price_basis": taban_birim,

                "unit_price_per_100": unit_price_per_100,

                "normalization_source": source,

                "normalization_notes": ";".join(notes),

                "kazima_tarihi": satir["kazima_tarihi"],

            }

        )



    return normalize_satirlar, denetim_satirlari, stats





def write_csv(yol: Path, satirlar: list[dict[str, str]]) -> None:

    if not satirlar:

        return



    with yol.open("w", encoding="utf-8", newline="") as handle:

        yazici = csv.DictWriter(handle, fieldnames=list(satirlar[0].keys()))

        yazici.writeheader()

        yazici.writerows(satirlar)





def argumanlari_ayristir() -> argparse.Namespace:

    komut_ayristirici = argparse.ArgumentParser(

        description="SOK fiyat_zaman_serisi.csv dosyasini 3. hafta kurallarina gore normalize eder."

    )

    komut_ayristirici.add_argument("input_csv", type=Path)

    komut_ayristirici.add_argument("--urunler-csv", type=Path, default=None)

    komut_ayristirici.add_argument("--output-csv", type=Path, default=None)

    komut_ayristirici.add_argument("--audit-csv", type=Path, default=None)

    return komut_ayristirici.argumanlari_ayristir()





def main() -> None:

    args = argumanlari_ayristir()

    girdi_yolu = args.girdi_csv

    if args.urunler_csv is None:

        args.urunler_csv = girdi_yolu.with_name("urunler.csv")



    cikti_csv, denetim_csv = default_output_paths(girdi_yolu)

    if args.cikti_csv is not None:

        cikti_csv = args.cikti_csv

    if args.denetim_csv is not None:

        denetim_csv = args.denetim_csv



    with girdi_yolu.open("r", encoding="utf-8-sig", newline="") as handle:

        satirlar = list(csv.DictReader(handle))



    urun_adlari = load_product_names(args.urunler_csv)

    normalize_satirlar, denetim_satirlari, stats = normalize_rows(satirlar, urun_adlari)

    write_csv(cikti_csv, normalize_satirlar)

    write_csv(denetim_csv, denetim_satirlari)



    print(f"Normalized CSV: {output_csv}")

    print(f"Audit CSV: {audit_csv}")

    print(f"Toplam satir: {stats['total']}")

    print(f"Normalize edilen satir: {stats['normalized']}")

    print(f"Urun adindan cozuldu: {stats['resolved_from_product_name']}")

    print(f"Cozulemeyen satir: {stats['unresolved']}")

    print(f"Temizlenen eski unit_price: {stats['cleared_old_unit_price']}")





if __name__ == "__main__":

    main()

