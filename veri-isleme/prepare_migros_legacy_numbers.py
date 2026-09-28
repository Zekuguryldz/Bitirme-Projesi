import argparse

import csv

import importlib

import json

from datetime import datetime, timedelta, timezone

from pathlib import Path



from backfill_product_urls import backfill_rows, build_reference_indexes

from normalize_fiyat_zaman_serisi import normalize_rows



try:

    _numbers_parser = importlib.import_module("numbers_parser")

except ModuleNotFoundError as exc:                                         

    Document = None

    _NUMBERS_PARSER_IMPORT_ERROR = exc

else:

    Document = _numbers_parser.Document

    _NUMBERS_PARSER_IMPORT_ERROR = None





TR_TIMEZONE = timezone(timedelta(hours=3))





def argumanlari_ayristir() -> argparse.Namespace:

    komut_ayristirici = argparse.ArgumentParser(

        description="Migros legacy .numbers dosyasini duzeltilmis CSV ciktilarina donusturur."

    )

    komut_ayristirici.add_argument("input_numbers", type=Path)

    komut_ayristirici.add_argument("reference_raw_products_csv", type=Path)

    komut_ayristirici.add_argument("--output-dir", type=Path, required=True)

    komut_ayristirici.add_argument("--market-id", default="2")

    komut_ayristirici.add_argument("--market-name", default="Migros")

    return komut_ayristirici.argumanlari_ayristir()





def clean_text(value: object) -> str:

    if value is None:

        return ""

    text = str(value).replace("\xa0", " ").strip()

    if not text or text.lower() == "nan":

        return ""

    return text





def is_numeric_text(value: str) -> bool:

    try:

        float(value.replace(",", "."))

    except (AttributeError, ValueError):

        return False

    return True





def parse_local_timestamp(value: str) -> str:

    ayristirilmis = datetime.strptime(value, "%d.%m.%Y %H:%M:%S")

    return ayristirilmis.replace(tzinfo=TR_TIMEZONE).isoformat(sep=" ")





def load_numbers_rows(yol: Path) -> list[dict[str, str]]:

    if Document is None:                                         

        raise SystemExit(

            "numbers-parser paketi gerekli. Ornek: python3 -m pip install numbers-parser"

        ) from _NUMBERS_PARSER_IMPORT_ERROR



    document = Document(str(yol))

    if not document.sheets or not document.sheets[0].tables:

        raise ValueError(f"Tablo bulunamadi: {yol}")



    table = document.sheets[0].tables[0]

    satirlar = list(table.rows(values_only=True))

    if not satirlar:

        return []



    header = [clean_text(value) for value in satirlar[0]]

    veri_satirlari: list[dict[str, str]] = []

    for satir in satirlar[1:]:

        kayit = {

            header[index]: clean_text(value)

            for index, value in enumerate(satir[: len(header)])

        }

        if any(kayit.values()) and is_numeric_text(kayit.get("fiyat_tl", "")):

            veri_satirlari.append(kayit)

    return veri_satirlari





def read_csv(yol: Path) -> list[dict[str, str]]:

    with yol.open("r", encoding="utf-8-sig", newline="") as handle:

        return list(csv.DictReader(handle))





def write_csv(yol: Path, satirlar: list[dict[str, object]]) -> None:

    if not satirlar:

        return

    yol.parent.mkdir(parents=True, exist_ok=True)

    with yol.open("w", encoding="utf-8", newline="") as handle:

        yazici = csv.DictWriter(handle, fieldnames=list(satirlar[0].keys()))

        yazici.writeheader()

        yazici.writerows(satirlar)





def build_product_rows(

    sayi_satirlari: list[dict[str, str]],

    market_kimligi: str,

    market_adi: str,

) -> list[dict[str, str]]:

    urun_satirlari: list[dict[str, str]] = []

    for index, satir in enumerate(sayi_satirlari, start=1):

        kazima_zaman_damgasi = parse_local_timestamp(satir["cekim_tarihi"])

        urun_satirlari.append(

            {

                "id": str(index),

                "market_id": market_kimligi,

                "urun_ad": satir["urun_adi"],

                "urun_url": "",

                "urun_kategori": satir["kategori"],

                "eklenme_tarihi": kazima_zaman_damgasi,

                "market_adi": satir.get("market") or market_adi,

                "urun_marka": satir["marka"],

                "sira_no": satir.get("sira") or str(index),

                "site_product_code": "",

                "url_key": "",

            }

        )

    return urun_satirlari





def build_price_rows(sayi_satirlari: list[dict[str, str]], urun_satirlari: list[dict[str, str]]) -> list[dict[str, str]]:

    fiyat_satirlari: list[dict[str, str]] = []

    for urun_satiri, kaynak_satir in zip(urun_satirlari, sayi_satirlari):

        fiyat_satirlari.append(

            {

                "kayit_id": urun_satiri["id"],

                "urun_id": urun_satiri["id"],

                "urun_fiyat": kaynak_satir["fiyat_tl"].replace(",", "."),

                "gramaj_degeri": kaynak_satir["gramaj"],

                "gramaj_birimi": "",

                "unit_price": "",

                "kazima_tarihi": urun_satiri["eklenme_tarihi"],

            }

        )

    return fiyat_satirlari





def coalesce_item_count(urun_satiri: dict[str, str], adrese_gore_ham: dict[str, dict[str, str]]) -> str:

    ham_satir = adrese_gore_ham.get(urun_satiri["urun_url"])

    item_count = clean_text(ham_satir.get("item_count")) if ham_satir else ""

    return item_count or "1.0"





def build_final_price_rows(

    normalize_satirlar: list[dict[str, str]],

    urun_satirlari: list[dict[str, str]],

    ham_satirlar: list[dict[str, str]],

) -> list[dict[str, str]]:

    adrese_gore_ham = {

        satir["product_url"]: satir

        for satir in ham_satirlar

        if clean_text(satir.get("product_url"))

    }

    kimlige_gore_urun = {satir["id"]: satir for satir in urun_satirlari}

    son_satirlar: list[dict[str, str]] = []

    for satir in normalize_satirlar:

        urun_satiri = kimlige_gore_urun[satir["urun_id"]]

        son_satirlar.append(

            {

                "kayit_id": satir["kayit_id"],

                "urun_id": satir["urun_id"],

                "urun_fiyat": satir["urun_fiyat"],

                "gramaj_degeri": satir["gramaj_degeri"],

                "gramaj_birimi": satir["gramaj_birimi"],

                "birim_fiyat": satir["unit_price"],

                "kazima_tarihi": satir["kazima_tarihi"],

                "adet_sayisi": coalesce_item_count(urun_satiri, adrese_gore_ham),

            }

        )

    return son_satirlar





def write_summary(

    yol: Path,

    eslesme_istatistikleri: dict[str, int],

    normalization_stats: dict[str, int],

    urun_satirlari: list[dict[str, str]],

) -> None:

    matched_products = sum(1 for satir in urun_satirlari if satir["urun_url"])

    ozet = {

        "total_products": len(urun_satirlari),

        "matched_products": matched_products,

        "unmatched_products": len(urun_satirlari) - matched_products,

        "url_backfill": eslesme_istatistikleri,

        "normalization": normalization_stats,

    }

    yol.write_text(json.dumps(ozet, ensure_ascii=False, indent=2), encoding="utf-8")





def main() -> None:

    args = argumanlari_ayristir()

    sayi_satirlari = load_numbers_rows(args.input_numbers)

    ham_satirlar = read_csv(args.reference_raw_products_csv)



    urun_satirlari = build_product_rows(sayi_satirlari, args.market_kimligi, args.market_adi)

    indexes = build_reference_indexes(ham_satirlar)

    guncellenen_urun_satirlari, backfill_audit_rows, eslesme_istatistikleri = backfill_rows(urun_satirlari, indexes)



    raw_price_rows = build_price_rows(sayi_satirlari, guncellenen_urun_satirlari)

    urun_adlari = {satir["id"]: satir["urun_ad"] for satir in guncellenen_urun_satirlari}

    normalize_fiyat_satirlari, normalization_audit_rows, normalization_stats = normalize_rows(

        raw_price_rows,

        urun_adlari,

    )

    son_fiyat_satirlari = build_final_price_rows(normalize_fiyat_satirlari, guncellenen_urun_satirlari, ham_satirlar)



    cikti_dizini = args.cikti_dizini

    cikti_dizini.mkdir(parents=True, exist_ok=True)

    write_csv(cikti_dizini / "market.csv", [{"market_id": args.market_kimligi, "market_adi": args.market_adi}])

    write_csv(cikti_dizini / "urunler.csv", guncellenen_urun_satirlari)

    write_csv(cikti_dizini / "fiyat_zaman_serisi.csv", son_fiyat_satirlari)

    write_csv(cikti_dizini / "urun_url_backfill_audit.csv", backfill_audit_rows)

    write_csv(cikti_dizini / "fiyat_normalization_audit.csv", normalization_audit_rows)

    write_summary(cikti_dizini / "summary.json", eslesme_istatistikleri, normalization_stats, guncellenen_urun_satirlari)



    print(f"Output dir: {cikti_dizini}")

    print(f"Toplam urun: {len(guncellenen_urun_satirlari)}")

    print(f"URL eslesen urun: {sum(1 for satir in guncellenen_urun_satirlari if satir['urun_url'])}")

    print(f"Normalize edilen fiyat satiri: {normalization_stats['normalized']}")





if __name__ == "__main__":

    main()
