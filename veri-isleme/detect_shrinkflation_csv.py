import argparse

import csv

import json

from collections import defaultdict

from dataclasses import dataclass

from pathlib import Path

from typing import Any, Optional



from normalize_fiyat_zaman_serisi import choose_candidate, compute_unit_price, extract_candidate

from shrinkflation import TespitEsikleri, FiyatKaydi, classify_severity, is_tartimli_kg_urun, pct_change



AUDIT_FIELDNAMES = [

    "identity_key",

    "urun_id",

    "urun_ad",

    "onceki_kayit_tarihi",

    "yeni_kayit_tarihi",

    "onceki_fiyat",

    "yeni_fiyat",

    "onceki_gramaj_degeri",

    "yeni_gramaj_degeri",

    "gramaj_birimi",

    "onceki_birim_fiyat",

    "yeni_birim_fiyat",

    "gramaj_degisim_pct",

    "fiyat_degisim_pct",

    "birim_fiyat_degisim_pct",

    "shrinkflation_orani_pct",

    "severity",

    "reason",

    "strong_case",

    "current_urun_url",

]

KARSILASTIRILABILIR_BIRIMLER = {"g", "ml", "adet"}

FIYAT_EPSILON = 1e-9





@dataclass(frozen=True)

class AnlikKayit:

    snapshot: FiyatKaydi

    urun_url: Optional[str]





def argumanlari_ayristir() -> argparse.Namespace:

    komut_ayristirici = argparse.ArgumentParser(

        description="Iki CSV output klasoru arasinda 4. hafta shrinkflation tespiti yapar."

    )

    komut_ayristirici.add_argument("previous_dir", type=Path)

    komut_ayristirici.add_argument("current_dir", type=Path)

    komut_ayristirici.add_argument("--audit-csv", type=Path, required=True)

    komut_ayristirici.add_argument("--summary-json", type=Path, required=True)

    komut_ayristirici.add_argument("--min-size-drop-pct", type=float, default=3.0)

    komut_ayristirici.add_argument("--max-size-drop-pct", type=float, default=70.0)

    komut_ayristirici.add_argument("--min-unit-price-increase-pct", type=float, default=3.0)

    komut_ayristirici.add_argument("--stable-price-floor-pct", type=float, default=0.0)

    return komut_ayristirici.argumanlari_ayristir()





def read_csv(yol: Path) -> list[dict[str, str]]:

    with yol.open("r", encoding="utf-8-sig", newline="") as handle:

        return list(csv.DictReader(handle))





def write_csv(yol: Path, satirlar: list[dict[str, object]]) -> None:

    yol.parent.mkdir(parents=True, exist_ok=True)

    with yol.open("w", encoding="utf-8", newline="") as handle:

        yazici = csv.DictWriter(handle, fieldnames=AUDIT_FIELDNAMES)

        yazici.writeheader()

        if satirlar:

            yazici.writerows(satirlar)





def format_measure_text(gramaj_degeri, gramaj_birimi: Optional[str]) -> str:

    if gramaj_degeri is None or gramaj_degeri == "" or not gramaj_birimi:

        return ""

    value = float(gramaj_degeri)

    if value.is_integer():

        value_text = str(int(value))

    else:

        value_text = f"{value:.4f}".rstrip("0").rstrip(".")

    return f"{value_text} {gramaj_birimi}"





def parse_float(value: Optional[str]) -> Optional[float]:

    if value is None:

        return None

    text = str(value).strip()

    if not text:

        return None

    return float(text.replace(",", "."))





def canonicalize_snapshot_measure(

    *,

    urun_ad: str,

    urun_fiyat,

    gramaj_degeri,

    gramaj_birimi: Optional[str],

    birim_fiyat,

) -> tuple[Optional[float], Optional[str], Optional[float]]:

    ham_aday = extract_candidate(

        format_measure_text(gramaj_degeri, gramaj_birimi),

        "raw_field",

    )

    ad_adayi = extract_candidate(urun_ad or "", "product_name")

    chosen, _ = choose_candidate(ham_aday, ad_adayi)

    if chosen is None:

        return (

            parse_float(gramaj_degeri),

            gramaj_birimi,

            parse_float(birim_fiyat),

        )

    return (

        float(chosen.total_base),

        chosen.temel_birim,

        compute_unit_price(

            parse_float(urun_fiyat),

            chosen.total_base,

            chosen.taban_birim,

        ),

    )





def select_identity_key(urun_satiri: dict[str, str]) -> Optional[str]:

    site_urun_kodu = (urun_satiri.get("site_product_code") or "").strip()

    if site_urun_kodu:

        return f"site_product_code:{site_urun_kodu}"



    adres_anahtari = (urun_satiri.get("url_key") or "").strip()

    if adres_anahtari:

        return f"url_key:{adres_anahtari}"



    urun_url = (urun_satiri.get("urun_url") or "").strip()

    if urun_url:

        return f"urun_url:{urun_url}"

    return None





def load_grouped_snapshot_records(month_dir: Path) -> dict[str, list[AnlikKayit]]:

    urun_satirlari = read_csv(month_dir / "urunler.csv")

    fiyat_satirlari = read_csv(month_dir / "fiyat_zaman_serisi.csv")

    kimlige_gore_urun = {satir["id"]: satir for satir in urun_satirlari}



    grouped: dict[str, list[AnlikKayit]] = defaultdict(list)

    for fiyat_satiri in fiyat_satirlari:

        urun_satiri = kimlige_gore_urun.get(fiyat_satiri["urun_id"])

        if urun_satiri is None:

            continue



        identity_key = select_identity_key(urun_satiri)

        if not identity_key:

            continue



        normalize_olcu, normalize_birim, normalize_birim_fiyat = canonicalize_snapshot_measure(

            urun_ad=urun_satiri["urun_ad"],

            urun_fiyat=fiyat_satiri.get("urun_fiyat"),

            gramaj_degeri=fiyat_satiri.get("gramaj_degeri"),

            gramaj_birimi=urun_satiri.get("gramaj_birimi") or fiyat_satiri.get("gramaj_birimi"),

            birim_fiyat=fiyat_satiri.get("birim_fiyat"),

        )

        if fiyat_satiri.get("kazima_tarihi") is None:

            continue

        snapshot = FiyatKaydi(

            urun_id=int(fiyat_satiri["urun_id"]),

            urun_ad=urun_satiri["urun_ad"],

            kazima_tarihi=parse_datetime(fiyat_satiri["kazima_tarihi"]),

            urun_fiyat=parse_float(fiyat_satiri.get("urun_fiyat")) or 0.0,

            gramaj_degeri=normalize_olcu,

            gramaj_birimi=normalize_birim,

            birim_fiyat=normalize_birim_fiyat,

        )

        grouped[identity_key].append(

            AnlikKayit(

                snapshot=snapshot,

                urun_url=(urun_satiri.get("urun_url") or "").strip() or None,

            )

        )

    return grouped





def load_grouped_snapshots(month_dir: Path) -> dict[str, list[FiyatKaydi]]:

    records_by_identity = load_grouped_snapshot_records(month_dir)

    return {

        identity_key: [kayit.snapshot for kayit in kayitlar]

        for identity_key, kayitlar in records_by_identity.items()

    }





def parse_datetime(value: str):

    from datetime import datetime



    return datetime.fromisoformat(value)





def _assess_transition(

    onceki_kayit: FiyatKaydi,

    guncel_kayit: FiyatKaydi,

) -> Optional[dict[str, Any]]:

    if is_tartimli_kg_urun(onceki_kayit.urun_ad) or is_tartimli_kg_urun(guncel_kayit.urun_ad):

        return None

    if onceki_kayit.gramaj_birimi is None or guncel_kayit.gramaj_birimi is None:

        return None

    if onceki_kayit.gramaj_birimi not in KARSILASTIRILABILIR_BIRIMLER:

        return None

    if guncel_kayit.gramaj_birimi not in KARSILASTIRILABILIR_BIRIMLER:

        return None

    if onceki_kayit.gramaj_birimi != guncel_kayit.gramaj_birimi:

        return None

    if onceki_kayit.gramaj_degeri is None or guncel_kayit.gramaj_degeri is None:

        return None

    if onceki_kayit.birim_fiyat is None or guncel_kayit.birim_fiyat is None:

        return None

    if onceki_kayit.gramaj_degeri <= 0 or guncel_kayit.gramaj_degeri <= 0:

        return None



    gramaj_degisim_pct = pct_change(onceki_kayit.gramaj_degeri, guncel_kayit.gramaj_degeri)

    fiyat_degisim_pct = pct_change(onceki_kayit.urun_fiyat, guncel_kayit.urun_fiyat)

    birim_fiyat_degisim_pct = pct_change(onceki_kayit.birim_fiyat, guncel_kayit.birim_fiyat)

    if gramaj_degisim_pct is None or fiyat_degisim_pct is None or birim_fiyat_degisim_pct is None:

        return None



    size_drop_pct = -gramaj_degisim_pct

    if guncel_kayit.urun_fiyat > onceki_kayit.urun_fiyat + FIYAT_EPSILON:

        reason = "price_increased_while_quantity_dropped"

    elif guncel_kayit.urun_fiyat < onceki_kayit.urun_fiyat - FIYAT_EPSILON:

        reason = "price_dropped_but_not_enough_after_quantity_drop"

    else:

        reason = "price_stable_while_quantity_dropped"



    return {

        "onceki_snapshot": onceki_kayit,

        "yeni_snapshot": guncel_kayit,

        "gramaj_degisim_pct": gramaj_degisim_pct,

        "fiyat_degisim_pct": fiyat_degisim_pct,

        "birim_fiyat_degisim_pct": birim_fiyat_degisim_pct,

        "size_drop_pct": size_drop_pct,

        "severity": classify_severity(size_drop_pct, birim_fiyat_degisim_pct),

        "reason": reason,

    }





def build_candidate_row(

    identity_key: str,

    assessment: dict[str, Any],

    guncel_urun_url: Optional[str],

) -> dict[str, object]:

    onceki_kayit = assessment["onceki_snapshot"]

    guncel_kayit = assessment["yeni_snapshot"]

    return {

        "identity_key": identity_key,

        "urun_id": guncel_kayit.urun_id,

        "urun_ad": onceki_kayit.urun_ad,

        "onceki_kayit_tarihi": onceki_kayit.kazima_tarihi.isoformat(),

        "yeni_kayit_tarihi": guncel_kayit.kazima_tarihi.isoformat(),

        "onceki_fiyat": onceki_kayit.urun_fiyat,

        "yeni_fiyat": guncel_kayit.urun_fiyat,

        "onceki_gramaj_degeri": onceki_kayit.gramaj_degeri,

        "yeni_gramaj_degeri": guncel_kayit.gramaj_degeri,

        "gramaj_birimi": guncel_kayit.gramaj_birimi,

        "onceki_birim_fiyat": onceki_kayit.birim_fiyat,

        "yeni_birim_fiyat": guncel_kayit.birim_fiyat,

        "gramaj_degisim_pct": round(assessment["gramaj_degisim_pct"], 4),

        "fiyat_degisim_pct": round(assessment["fiyat_degisim_pct"], 4),

        "birim_fiyat_degisim_pct": round(assessment["birim_fiyat_degisim_pct"], 4),

        "shrinkflation_orani_pct": round(assessment["birim_fiyat_degisim_pct"], 4),

        "severity": assessment["severity"],

        "reason": assessment["reason"],

        "strong_case": assessment["fiyat_degisim_pct"] >= 0,

        "current_urun_url": guncel_urun_url,

    }





def analyze_market_pairs(

    onceki_dizin: Path,

    guncel_dizin: Path,

    thresholds: TespitEsikleri,

) -> tuple[int, int, int, int, list[dict[str, object]]]:

    previous_grouped = load_grouped_snapshot_records(onceki_dizin)

    current_grouped = load_grouped_snapshot_records(guncel_dizin)

    shared_keys = sorted(set(previous_grouped) & set(current_grouped))



    content_shrunk_identities = 0

    candidate_identities = 0

    strong_case_identities = 0

    bulgu_satirlari: list[dict[str, object]] = []



    for identity_key in shared_keys:

        kayitlar = previous_grouped[identity_key] + current_grouped[identity_key]

        ordered_records = sorted(kayitlar, key=lambda item: item.snapshot.kazima_tarihi)



        has_size_drop = False

        kimlik_icin_aday_satirlar: list[dict[str, object]] = []

        for previous_record, current_record in zip(ordered_records, ordered_records[1:]):

            assessment = _assess_transition(previous_record.snapshot, current_record.snapshot)

            if assessment is None:

                continue

            if assessment["size_drop_pct"] < thresholds.min_size_drop_pct:

                continue

            if assessment["size_drop_pct"] > thresholds.max_size_drop_pct:

                continue



            has_size_drop = True

            if assessment["birim_fiyat_degisim_pct"] < thresholds.min_birim_fiyat_artis_yuzdesi:

                continue



            kimlik_icin_aday_satirlar.append(

                build_candidate_row(

                    identity_key,

                    assessment,

                    current_record.urun_url,

                )

            )



        if has_size_drop:

            content_shrunk_identities += 1

        if not kimlik_icin_aday_satirlar:

            continue



        candidate_identities += 1

        best_candidate = max(

            kimlik_icin_aday_satirlar,

            key=lambda satir: (float(satir["shrinkflation_orani_pct"]), float(satir["gramaj_degisim_pct"])),

        )

        bulgu_satirlari.append(best_candidate)

        if any(bool(satir["strong_case"]) for satir in kimlik_icin_aday_satirlar):

            strong_case_identities += 1



    bulgu_satirlari.sort(key=lambda satir: float(satir["shrinkflation_orani_pct"]), reverse=True)

    return len(shared_keys), content_shrunk_identities, candidate_identities, strong_case_identities, bulgu_satirlari





def format_currency(value: float) -> str:

    return f"{value:.2f} TL"





def format_percentage(value: float) -> str:

    rounded = round(value, 1)

    if float(rounded).is_integer():

        return str(int(rounded))

    return f"{rounded:.1f}"





def format_human_measure(value: object, birim: Optional[str]) -> str:

    if value in (None, "") or not birim:

        return "?"



    numeric_value = float(value)

    normalize_birim = birim.lower()

    if normalize_birim == "ml" and numeric_value >= 1000:

        liters = numeric_value / 1000

        if liters.is_integer():

            return f"{int(liters)} L"

        return f"{liters:.1f}".rstrip("0").rstrip(".") + " L"

    if normalize_birim == "g" and numeric_value >= 1000:

        kilograms = numeric_value / 1000

        if kilograms.is_integer():

            return f"{int(kilograms)} kg"

        return f"{kilograms:.1f}".rstrip("0").rstrip(".") + " kg"

    if numeric_value.is_integer():

        return f"{int(numeric_value)} {birim}"

    return f"{numeric_value:.1f}".rstrip("0").rstrip(".") + f" {birim}"





def normalize_text_for_compare(value: object) -> str:

    return " ".join(str(value).casefold().split())





def format_candidate_title(urun_adi: str, onceki_olcu: str, guncel_olcu: str) -> str:

    normalize_ad = normalize_text_for_compare(urun_adi)

    normalized_previous_measure = normalize_text_for_compare(onceki_olcu)

    if normalized_previous_measure and normalize_ad.endswith(normalized_previous_measure):

        return f"{urun_adi} -> {guncel_olcu}"

    return f"{urun_adi} {onceki_olcu} -> {guncel_olcu}"





def format_summary_text(

    *,

    compared_identities: int,

    content_shrunk_count: int,

    aday_sayisi: int,

    strong_case_count: int,

    bulgu_satirlari: list[dict[str, object]],

) -> str:

    lines = [

        "Özet:",

        "",

        f"Eşleştirilen benzersiz ürün ailesi: {compared_identities}",

        f"İçeriği küçülen ürün: {content_shrunk_count}",

        f"Birim fiyatı artan shrinkflation adayı: {aday_sayisi}",

        f'Nominal fiyatı aynı kalıp ya da artıp küçülen "güçlü" vaka: {strong_case_count}',

        "",

        "Adaylar:",

    ]

    if not bulgu_satirlari:

        lines.append("Yok.")

        return "\n".join(lines)



    for satir in bulgu_satirlari:

        onceki_olcu = format_human_measure(satir["onceki_gramaj_degeri"], satir["gramaj_birimi"])

        guncel_olcu = format_human_measure(satir["yeni_gramaj_degeri"], satir["gramaj_birimi"])

        guncel_adres = satir.get("current_urun_url") or "URL yok"

        title = format_candidate_title(str(satir["urun_ad"]), onceki_olcu, guncel_olcu)

        lines.append(

            (

                f"{title}, "

                f'fiyat {format_currency(float(satir["onceki_fiyat"]))} -> '

                f'{format_currency(float(satir["yeni_fiyat"]))}, '

                f'birim fiyat yaklaşık %{format_percentage(float(satir["birim_fiyat_degisim_pct"]))} arttı. '

                f"Güncel ürün: {guncel_adres}"

            )

        )

    return "\n".join(lines)





def write_summary(

    yol: Path,

    *,

    onceki_dizin: Path,

    guncel_dizin: Path,

    compared_identities: int,

    content_shrunk_count: int,

    aday_sayisi: int,

    strong_case_count: int,

    bulgu_satirlari: list[dict[str, object]],

) -> None:

    severity_counts: dict[str, int] = defaultdict(int)

    for satir in bulgu_satirlari:

        severity_counts[satir["severity"]] += 1



    ozet_metni = format_summary_text(

        compared_identities=compared_identities,

        content_shrunk_count=content_shrunk_count,

        aday_sayisi=aday_sayisi,

        strong_case_count=strong_case_count,

        bulgu_satirlari=bulgu_satirlari,

    )

    ozet = {

        "previous_dir": str(onceki_dizin),

        "current_dir": str(guncel_dizin),

        "compared_identities": compared_identities,

        "content_shrunk_count": content_shrunk_count,

        "candidate_count": aday_sayisi,

        "strong_case_count": strong_case_count,

        "findings_count": len(bulgu_satirlari),

        "severity_counts": dict(severity_counts),

        "summary_text": ozet_metni,

        "candidates": [

            {

                "identity_key": satir["identity_key"],

                "urun_id": satir["urun_id"],

                "urun_ad": satir["urun_ad"],

                "onceki_olcu": format_human_measure(satir["onceki_gramaj_degeri"], satir["gramaj_birimi"]),

                "yeni_olcu": format_human_measure(satir["yeni_gramaj_degeri"], satir["gramaj_birimi"]),

                "onceki_fiyat": satir["onceki_fiyat"],

                "yeni_fiyat": satir["yeni_fiyat"],

                "birim_fiyat_degisim_pct": satir["birim_fiyat_degisim_pct"],

                "strong_case": satir["strong_case"],

                "current_urun_url": satir["current_urun_url"],

            }

            for satir in bulgu_satirlari

        ],

    }

    yol.write_text(json.dumps(ozet, ensure_ascii=False, indent=2), encoding="utf-8")





def main() -> None:

    args = argumanlari_ayristir()

    thresholds = TespitEsikleri(

        min_size_drop_pct=args.min_size_drop_pct,

        max_size_drop_pct=args.max_size_drop_pct,

        min_birim_fiyat_artis_yuzdesi=args.min_birim_fiyat_artis_yuzdesi,

        sabit_fiyat_alt_yuzdesi=args.sabit_fiyat_alt_yuzdesi,

    )

    (

        compared_identities,

        content_shrunk_count,

        aday_sayisi,

        strong_case_count,

        bulgu_satirlari,

    ) = analyze_market_pairs(

        args.onceki_dizin,

        args.guncel_dizin,

        thresholds,

    )

    write_csv(args.denetim_csv, bulgu_satirlari)

    write_summary(

        args.summary_json,

        onceki_dizin=args.onceki_dizin,

        guncel_dizin=args.guncel_dizin,

        compared_identities=compared_identities,

        content_shrunk_count=content_shrunk_count,

        aday_sayisi=aday_sayisi,

        strong_case_count=strong_case_count,

        bulgu_satirlari=bulgu_satirlari,

    )



    print(

        format_summary_text(

            compared_identities=compared_identities,

            content_shrunk_count=content_shrunk_count,

            aday_sayisi=aday_sayisi,

            strong_case_count=strong_case_count,

            bulgu_satirlari=bulgu_satirlari,

        )

    )

    print()

    print(f"Audit CSV: {args.audit_csv}")

    print(f"Summary JSON: {args.summary_json}")





if __name__ == "__main__":

    main()
