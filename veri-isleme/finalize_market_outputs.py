import argparse

import csv

import json

from pathlib import Path



from normalize_fiyat_zaman_serisi import normalize_rows





def argumanlari_ayristir() -> argparse.Namespace:

    komut_ayristirici = argparse.ArgumentParser(

        description="Mevcut market output klasorunu 3. hafta kurallarina gore finalize eder."

    )

    komut_ayristirici.add_argument("input_dir", type=Path)

    komut_ayristirici.add_argument("--output-dir", type=Path, required=True)

    return komut_ayristirici.argumanlari_ayristir()





def read_csv(yol: Path) -> list[dict[str, str]]:

    with yol.open("r", encoding="utf-8-sig", newline="") as handle:

        return list(csv.DictReader(handle))





def clean_text(value: object) -> str:

    if value is None:

        return ""

    text = str(value).replace("\xa0", " ").strip()

    if not text or text.lower() == "nan":

        return ""

    return text





def write_csv(yol: Path, satirlar: list[dict[str, object]]) -> None:

    if not satirlar:

        return

    yol.parent.mkdir(parents=True, exist_ok=True)

    with yol.open("w", encoding="utf-8", newline="") as handle:

        yazici = csv.DictWriter(handle, fieldnames=list(satirlar[0].keys()))

        yazici.writeheader()

        yazici.writerows(satirlar)





def adrese_gore_ham_oge_sayisi(ham_satirlar: list[dict[str, str]]) -> dict[str, str]:

    mapping: dict[str, str] = {}

    for satir in ham_satirlar:

        urun_adresi = clean_text(satir.get("product_url"))

        if not urun_adresi:

            continue

        item_count = clean_text(satir.get("item_count"))

        if item_count:

            mapping[urun_adresi] = item_count

    return mapping





def coalesce_item_count(

    existing_row: dict[str, str],

    urun_satiri: dict[str, str],

    adrese_gore_oge_sayisi: dict[str, str],

) -> str:

    existing = clean_text(existing_row.get("adet_sayisi"))

    if existing:

        return existing



    urun_adresi = clean_text(urun_satiri.get("urun_url"))

    if urun_adresi and urun_adresi in adrese_gore_oge_sayisi:

        return adrese_gore_oge_sayisi[urun_adresi]

    return "1.0"





def build_final_price_rows(

    existing_price_rows: list[dict[str, str]],

    normalize_satirlar: list[dict[str, str]],

    urun_satirlari: list[dict[str, str]],

    ham_satirlar: list[dict[str, str]],

) -> list[dict[str, str]]:

    kimlige_gore_urun = {satir["id"]: satir for satir in urun_satirlari}

    item_count_lookup = adrese_gore_ham_oge_sayisi(ham_satirlar)

    son_satirlar: list[dict[str, str]] = []

    for existing_row, normalize_satir in zip(existing_price_rows, normalize_satirlar):

        urun_satiri = kimlige_gore_urun[normalize_satir["urun_id"]]

        son_satirlar.append(

            {

                "kayit_id": normalize_satir["kayit_id"],

                "urun_id": normalize_satir["urun_id"],

                "urun_fiyat": normalize_satir["urun_fiyat"],

                "gramaj_degeri": normalize_satir["gramaj_degeri"],

                "gramaj_birimi": normalize_satir["gramaj_birimi"],

                "birim_fiyat": normalize_satir["unit_price"],

                "kazima_tarihi": normalize_satir["kazima_tarihi"],

                "adet_sayisi": coalesce_item_count(existing_row, urun_satiri, item_count_lookup),

            }

        )

    return son_satirlar





def write_summary(

    yol: Path,

    *,

    girdi_dizini: Path,

    urun_satirlari: list[dict[str, str]],

    existing_price_rows: list[dict[str, str]],

    normalize_fiyat_satirlari: list[dict[str, str]],

    normalization_stats: dict[str, int],

) -> None:

    missing_before = sum(

        1

        for satir in existing_price_rows

        if not clean_text(satir.get("gramaj_degeri"))

        or not clean_text(satir.get("gramaj_birimi"))

        or not clean_text(satir.get("birim_fiyat"))

    )

    missing_after = sum(

        1

        for satir in normalize_fiyat_satirlari

        if not clean_text(satir.get("gramaj_degeri"))

        or not clean_text(satir.get("gramaj_birimi"))

        or not clean_text(satir.get("birim_fiyat"))

    )

    ozet = {

        "input_dir": str(girdi_dizini),

        "total_products": len(urun_satirlari),

        "total_prices": len(existing_price_rows),

        "missing_before": missing_before,

        "missing_after": missing_after,

        "normalization": normalization_stats,

    }

    yol.write_text(json.dumps(ozet, ensure_ascii=False, indent=2), encoding="utf-8")





def main() -> None:

    args = argumanlari_ayristir()

    girdi_dizini = args.girdi_dizini

    cikti_dizini = args.cikti_dizini



    market_rows = read_csv(girdi_dizini / "market.csv")

    urun_satirlari = read_csv(girdi_dizini / "urunler.csv")

    fiyat_satirlari = read_csv(girdi_dizini / "fiyat_zaman_serisi.csv")

    ham_satirlar = read_csv(girdi_dizini / "raw_products.csv") if (girdi_dizini / "raw_products.csv").exists() else []



    urun_adlari = {satir["id"]: satir["urun_ad"] for satir in urun_satirlari}

    normalize_satirlar, denetim_satirlari, stats = normalize_rows(fiyat_satirlari, urun_adlari)

    son_fiyat_satirlari = build_final_price_rows(fiyat_satirlari, normalize_satirlar, urun_satirlari, ham_satirlar)



    cikti_dizini.mkdir(parents=True, exist_ok=True)

    write_csv(cikti_dizini / "market.csv", market_rows)

    write_csv(cikti_dizini / "urunler.csv", urun_satirlari)

    write_csv(cikti_dizini / "fiyat_zaman_serisi.csv", son_fiyat_satirlari)

    write_csv(cikti_dizini / "fiyat_normalization_audit.csv", denetim_satirlari)

    write_summary(

        cikti_dizini / "summary.json",

        girdi_dizini=girdi_dizini,

        urun_satirlari=urun_satirlari,

        existing_price_rows=fiyat_satirlari,

        normalize_fiyat_satirlari=son_fiyat_satirlari,

        normalization_stats=stats,

    )



    print(f"Output dir: {cikti_dizini}")

    print(f"Toplam urun: {len(product_rows)}")

    print(f"Toplam fiyat satiri: {len(final_price_rows)}")

    print(f"Normalize edilen satir: {stats['normalized']}")





if __name__ == "__main__":

    main()

