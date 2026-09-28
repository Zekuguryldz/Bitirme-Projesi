from __future__ import annotations



import argparse

import csv

import os

from datetime import datetime

from pathlib import Path

from typing import Any



import psycopg2

from dotenv import load_dotenv

from psycopg2.extras import execute_values



VARSAYILAN_VERITABANI_ADRES_ENV = "SUPABASE_DB_URL"

YEDEK_VERITABANI_ADRES_ENV = "DATABASE_URL"





def argumanlari_ayristir() -> argparse.Namespace:

    komut_ayristirici = argparse.ArgumentParser(

        description="Shrinkflation CSV bulgularini anomali tablosuna aktarir."

    )

    komut_ayristirici.add_argument(

        "--input-csv",

        type=Path,

        default=Path("outputs/migros_mart_nisan_2026_shrinkflation.csv"),

    )

    komut_ayristirici.add_argument(

        "--resolved-products-csv",

        type=Path,

        default=Path("outputs/migros_nisan_import_apply.csv"),

    )

    komut_ayristirici.add_argument(

        "--migration-sql",

        type=Path,

        default=Path("migrations/004_anomali_week4.sql"),

    )

    komut_ayristirici.add_argument("--database-url", type=str, default=None)

    komut_ayristirici.add_argument("--database-url-env", type=str, default=VARSAYILAN_VERITABANI_ADRES_ENV)

    komut_ayristirici.add_argument("--skip-migration", action="store_true")

    komut_ayristirici.add_argument("--apply", action="store_true")

    return komut_ayristirici.argumanlari_ayristir()





def clean_text(value: Any) -> str | None:

    if value is None:

        return None

    text = str(value).replace("\xa0", " ").strip()

    if not text or text.lower() == "nan":

        return None

    return text





def parse_float(value: Any) -> float | None:

    text = clean_text(value)

    if text is None:

        return None

    return float(text.replace(",", "."))





def parse_datetime(value: Any) -> datetime | None:

    text = clean_text(value)

    if text is None:

        return None

    return datetime.fromisoformat(text)





def format_numeric_text(value: Any) -> str | None:

    ayristirilmis = parse_float(value)

    if ayristirilmis is None:

        return None

    rounded = round(ayristirilmis, 4)

    if float(rounded).is_integer():

        return str(int(rounded))

    return f"{rounded:.4f}".rstrip("0").rstrip(".")





def read_csv(yol: Path) -> list[dict[str, str]]:

    with yol.open("r", encoding="utf-8-sig", newline="") as handle:

        return list(csv.DictReader(handle))





def read_sql_file(yol: Path) -> str:

    return yol.read_text(encoding="utf-8")





def build_resolved_product_lookup(satirlar: list[dict[str, str]]) -> dict[str, int]:

    lookup: dict[str, int] = {}

    for satir in satirlar:

        resolved_id = clean_text(satir.get("resolved_urun_id"))

        urun_adresi = clean_text(satir.get("urun_url"))

        if not resolved_id or not urun_adresi:

            continue

        lookup[urun_adresi] = int(resolved_id)

    return lookup





def resolve_related_product_id(

    satir: dict[str, str],

    adres_sozlugu: dict[str, int],

    imlec=None,

) -> int | None:

    guncel_adres = clean_text(satir.get("current_urun_url"))

    if guncel_adres and guncel_adres in adres_sozlugu:

        return adres_sozlugu[guncel_adres]



    if imlec is not None and guncel_adres:

        imlec.execute(

            "SELECT id FROM urunler WHERE urun_url = %s ORDER BY id DESC LIMIT 1",

            (guncel_adres,),

        )

        veritabani_satiri = imlec.fetchone()

        if veritabani_satiri:

            return int(veritabani_satiri[0] if not isinstance(veritabani_satiri, dict) else veritabani_satiri["id"])



    return None





def build_anomaly_record(satir: dict[str, str], ilgili_urun_kimligi: int) -> dict[str, Any]:

    return {

        "ilgili_urun_id": ilgili_urun_kimligi,

        "eski_degeri": format_numeric_text(satir.get("onceki_birim_fiyat")),

        "yeni_degeri": format_numeric_text(satir.get("yeni_birim_fiyat")),

        "anomali_tespit_tarihi": parse_datetime(satir.get("yeni_kayit_tarihi")),

        "anomali_turu": "shrinkflation",

        "onceki_fiyat": parse_float(satir.get("onceki_fiyat")),

        "yeni_fiyat_detay": parse_float(satir.get("yeni_fiyat")),

        "onceki_gramaj_degeri": parse_float(satir.get("onceki_gramaj_degeri")),

        "yeni_gramaj_degeri_detay": parse_float(satir.get("yeni_gramaj_degeri")),

        "gramaj_birimi": clean_text(satir.get("gramaj_birimi")),

        "onceki_birim_fiyat": parse_float(satir.get("onceki_birim_fiyat")),

        "yeni_birim_fiyat_detay": parse_float(satir.get("yeni_birim_fiyat")),

        "gramaj_degisim_pct": parse_float(satir.get("gramaj_degisim_pct")),

        "fiyat_degisim_pct": parse_float(satir.get("fiyat_degisim_pct")),

        "birim_fiyat_degisim_pct": parse_float(satir.get("birim_fiyat_degisim_pct")),

        "shrinkflation_orani_pct": parse_float(satir.get("shrinkflation_orani_pct")),

        "severity": clean_text(satir.get("severity")),

        "reason": clean_text(satir.get("reason")),

        "onceki_kayit_tarihi": parse_datetime(satir.get("onceki_kayit_tarihi")),

        "yeni_kayit_tarihi": parse_datetime(satir.get("yeni_kayit_tarihi")),

    }





def load_database_url(cli_value: str | None, ortam_adi: str) -> str:

    if cli_value:

        return cli_value



    env_value = os.getenv(ortam_adi)

    if env_value:

        return env_value



    fallback_env_value = os.getenv(YEDEK_VERITABANI_ADRES_ENV)

    if fallback_env_value:

        return fallback_env_value



    raise RuntimeError(

        f"Supabase bağlantı bilgisi bulunamadı. --database-url ver veya {env_name}/{FALLBACK_DB_URL_ENV} ortam değişkenini ayarla."

    )





def insert_anomaly_records(cur, kayitlar: list[dict[str, Any]]) -> int:

    if not kayitlar:

        return 0



    yuk = [

        (

            kayit["ilgili_urun_id"],

            kayit["eski_degeri"],

            kayit["yeni_degeri"],

            kayit["anomali_tespit_tarihi"],

            kayit["anomali_turu"],

            kayit["onceki_fiyat"],

            kayit["yeni_fiyat_detay"],

            kayit["onceki_gramaj_degeri"],

            kayit["yeni_gramaj_degeri_detay"],

            kayit["gramaj_birimi"],

            kayit["onceki_birim_fiyat"],

            kayit["yeni_birim_fiyat_detay"],

            kayit["gramaj_degisim_pct"],

            kayit["fiyat_degisim_pct"],

            kayit["birim_fiyat_degisim_pct"],

            kayit["shrinkflation_orani_pct"],

            kayit["severity"],

            kayit["reason"],

            kayit["onceki_kayit_tarihi"],

            kayit["yeni_kayit_tarihi"],

        )

        for kayit in kayitlar

    ]



    execute_values(

        cur,

        """
        INSERT INTO anomali (
            ilgili_urun_id,
            eski_degeri,
            yeni_degeri,
            anomali_tespit_tarihi,
            anomali_turu,
            onceki_fiyat,
            yeni_fiyat_detay,
            onceki_gramaj_degeri,
            yeni_gramaj_degeri_detay,
            gramaj_birimi,
            onceki_birim_fiyat,
            yeni_birim_fiyat_detay,
            gramaj_degisim_pct,
            fiyat_degisim_pct,
            birim_fiyat_degisim_pct,
            shrinkflation_orani_pct,
            severity,
            reason,
            onceki_kayit_tarihi,
            yeni_kayit_tarihi
        ) VALUES %s
        ON CONFLICT DO NOTHING
        """,

        yuk,

        page_size=200,

    )

    return cur.rowcount





def main() -> None:

    args = argumanlari_ayristir()

    input_rows = read_csv(args.girdi_csv)

    resolved_rows = read_csv(args.resolved_products_csv)

    adres_sozlugu = build_resolved_product_lookup(resolved_rows)



    load_dotenv(".env")



    baglanti = None

    imlec = None

    try:

        if args.apply:

            veritabani_adresi = load_database_url(args.veritabani_adresi, args.database_url_env)

            baglanti = psycopg2.connect(veritabani_adresi)

            baglanti.autocommit = False

            imlec = baglanti.imlec()



            if not args.skip_migration:

                migration_sql = read_sql_file(args.migration_sql).strip()

                if migration_sql:

                    imlec.execute(migration_sql)

                    baglanti.commit()



        kayitlar: list[dict[str, Any]] = []

        unresolved: list[str] = []

        for satir in input_rows:

            ilgili_urun_kimligi = resolve_related_product_id(satir, adres_sozlugu, imlec=imlec)

            if ilgili_urun_kimligi is None:

                unresolved.append(clean_text(satir.get("urun_ad")) or "<isimsiz>")

                continue

            kayitlar.append(build_anomaly_record(satir, ilgili_urun_kimligi))



        if unresolved:

            raise ValueError(f"DB ürün ID çözümlenemeyen kayıtlar: {unresolved}")



        if args.apply:

            inserted = insert_anomaly_records(imlec, kayitlar)

            baglanti.commit()

            print(f"Inserted anomaly rows: {inserted}")

        else:

            print(f"Dry run only. Prepared anomaly rows: {len(records)}")

    finally:

        if imlec is not None:

            imlec.close()

        if baglanti is not None:

            baglanti.close()





if __name__ == "__main__":

    main()

