import argparse

import csv

import os

from pathlib import Path

from typing import Any



import pandas as pd

import psycopg2

from dotenv import load_dotenv

from psycopg2.extras import execute_values



from detect_shrinkflation_supabase import load_snapshots, read_sql_file

from price_change import FiyatDegisimEsikleri, detect_price_changes_series

from sok_weekly_supabase_sync import filter_rows_by_timestamp_window, parse_timestamp_bound



VARSAYILAN_VERITABANI_ADRES_ENV = "SUPABASE_DB_URL"

YEDEK_VERITABANI_ADRES_ENV = "DATABASE_URL"

ZAMLI_FIELDNAMES = [

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

    "zam_orani_pct",

    "severity",

    "reason",

]

INDIRIMLI_FIELDNAMES = [

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

    "indirim_orani_pct",

    "severity",

    "reason",

]





def argumanlari_ayristir() -> argparse.Namespace:

    komut_ayristirici = argparse.ArgumentParser(

        description="Supabase fiyat gecmisinde zamli ve indirimli urun snapshot'larini tespit eder."

    )

    komut_ayristirici.add_argument(

        "--migration-sql",

        type=Path,

        default=Path("migrations/006_price_change_tables.sql"),

    )

    komut_ayristirici.add_argument(

        "--zamli-audit-csv",

        type=Path,

        default=Path("outputs/zamli_urunler_findings.csv"),

    )

    komut_ayristirici.add_argument(

        "--indirimli-audit-csv",

        type=Path,

        default=Path("outputs/indirimli_urunler_findings.csv"),

    )

    komut_ayristirici.add_argument("--min-price-increase-pct", type=float, default=0.0)

    komut_ayristirici.add_argument("--min-price-decrease-pct", type=float, default=0.0)

    komut_ayristirici.add_argument("--start-date", default=None, help="Opsiyonel tespit başlangıç tarihi")

    komut_ayristirici.add_argument("--end-date", default=None, help="Opsiyonel tespit bitiş tarihi")

    komut_ayristirici.add_argument("--skip-migration", action="store_true")

    komut_ayristirici.add_argument("--apply", action="store_true")

    return komut_ayristirici.argumanlari_ayristir()





def load_database_url(ortam_adi: str) -> str:

    env_value = os.getenv(ortam_adi)

    if env_value:

        return env_value



    fallback_env_value = os.getenv(YEDEK_VERITABANI_ADRES_ENV)

    if fallback_env_value:

        return fallback_env_value



    raise RuntimeError(

        f"Supabase bağlantı bilgisi bulunamadı. {env_name}/{FALLBACK_DB_URL_ENV} ortam değişkenini ayarla."

    )





def write_csv(yol: Path, alan_adlari: list[str], satirlar: list[dict[str, Any]]) -> None:

    yol.parent.mkdir(parents=True, exist_ok=True)

    with yol.open("w", encoding="utf-8", newline="") as handle:

        yazici = csv.DictWriter(handle, fieldnames=alan_adlari)

        yazici.writeheader()

        if satirlar:

            yazici.writerows(satirlar)





def finding_to_price_increase_row(bulgu) -> dict[str, Any]:

    return {

        "urun_id": bulgu.urun_id,

        "urun_ad": bulgu.urun_ad,

        "onceki_kayit_tarihi": bulgu.onceki_kayit_tarihi.isoformat(),

        "yeni_kayit_tarihi": bulgu.yeni_kayit_tarihi.isoformat(),

        "onceki_fiyat": bulgu.onceki_fiyat,

        "yeni_fiyat": bulgu.yeni_fiyat,

        "onceki_gramaj_degeri": bulgu.onceki_gramaj_degeri,

        "yeni_gramaj_degeri": bulgu.yeni_gramaj_degeri,

        "gramaj_birimi": bulgu.gramaj_birimi,

        "onceki_birim_fiyat": bulgu.onceki_birim_fiyat,

        "yeni_birim_fiyat": bulgu.yeni_birim_fiyat,

        "gramaj_degisim_pct": round(bulgu.gramaj_degisim_pct, 4) if bulgu.gramaj_degisim_pct is not None else None,

        "fiyat_degisim_pct": round(bulgu.fiyat_degisim_pct, 4),

        "birim_fiyat_degisim_pct": round(bulgu.birim_fiyat_degisim_pct, 4) if bulgu.birim_fiyat_degisim_pct is not None else None,

        "zam_orani_pct": round(bulgu.change_ratio_pct, 4),

        "severity": bulgu.severity,

        "reason": bulgu.reason,

    }





def finding_to_price_decrease_row(bulgu) -> dict[str, Any]:

    return {

        "urun_id": bulgu.urun_id,

        "urun_ad": bulgu.urun_ad,

        "onceki_kayit_tarihi": bulgu.onceki_kayit_tarihi.isoformat(),

        "yeni_kayit_tarihi": bulgu.yeni_kayit_tarihi.isoformat(),

        "onceki_fiyat": bulgu.onceki_fiyat,

        "yeni_fiyat": bulgu.yeni_fiyat,

        "onceki_gramaj_degeri": bulgu.onceki_gramaj_degeri,

        "yeni_gramaj_degeri": bulgu.yeni_gramaj_degeri,

        "gramaj_birimi": bulgu.gramaj_birimi,

        "onceki_birim_fiyat": bulgu.onceki_birim_fiyat,

        "yeni_birim_fiyat": bulgu.yeni_birim_fiyat,

        "gramaj_degisim_pct": round(bulgu.gramaj_degisim_pct, 4) if bulgu.gramaj_degisim_pct is not None else None,

        "fiyat_degisim_pct": round(bulgu.fiyat_degisim_pct, 4),

        "birim_fiyat_degisim_pct": round(bulgu.birim_fiyat_degisim_pct, 4) if bulgu.birim_fiyat_degisim_pct is not None else None,

        "indirim_orani_pct": round(bulgu.change_ratio_pct, 4),

        "severity": bulgu.severity,

        "reason": bulgu.reason,

    }





def insert_price_increase_rows(cur, satirlar: list[dict[str, Any]]) -> int:

    if not satirlar:

        return 0



    cur.execute("SELECT COUNT(*) FROM zamli_urunler")

    before_count = int(cur.fetchone()[0])

    yuk = [

        (

            satir["urun_id"],

            satir["onceki_fiyat"],

            satir["yeni_fiyat"],

            satir["yeni_kayit_tarihi"],

            satir["onceki_fiyat"],

            satir["yeni_fiyat"],

            satir["onceki_gramaj_degeri"],

            satir["yeni_gramaj_degeri"],

            satir["gramaj_birimi"],

            satir["onceki_birim_fiyat"],

            satir["yeni_birim_fiyat"],

            satir["gramaj_degisim_pct"],

            satir["fiyat_degisim_pct"],

            satir["birim_fiyat_degisim_pct"],

            satir["zam_orani_pct"],

            satir["severity"],

            satir["reason"],

            satir["onceki_kayit_tarihi"],

            satir["yeni_kayit_tarihi"],

        )

        for satir in satirlar

    ]

    execute_values(

        cur,

        """
        INSERT INTO zamli_urunler (
            ilgili_urun_id,
            eski_degeri,
            yeni_degeri,
            zam_tespit_tarihi,
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
            zam_orani_pct,
            severity,
            reason,
            onceki_kayit_tarihi,
            yeni_kayit_tarihi
        ) VALUES %s
        ON CONFLICT DO NOTHING
        """,

        yuk,

        page_size=500,

    )

    cur.execute("SELECT COUNT(*) FROM zamli_urunler")

    after_count = int(cur.fetchone()[0])

    return after_count - before_count





def insert_price_decrease_rows(cur, satirlar: list[dict[str, Any]]) -> int:

    if not satirlar:

        return 0



    cur.execute("SELECT COUNT(*) FROM indirimli_urunler")

    before_count = int(cur.fetchone()[0])

    yuk = [

        (

            satir["urun_id"],

            satir["onceki_fiyat"],

            satir["yeni_fiyat"],

            satir["yeni_kayit_tarihi"],

            satir["onceki_fiyat"],

            satir["yeni_fiyat"],

            satir["onceki_gramaj_degeri"],

            satir["yeni_gramaj_degeri"],

            satir["gramaj_birimi"],

            satir["onceki_birim_fiyat"],

            satir["yeni_birim_fiyat"],

            satir["gramaj_degisim_pct"],

            satir["fiyat_degisim_pct"],

            satir["birim_fiyat_degisim_pct"],

            satir["indirim_orani_pct"],

            satir["severity"],

            satir["reason"],

            satir["onceki_kayit_tarihi"],

            satir["yeni_kayit_tarihi"],

        )

        for satir in satirlar

    ]

    execute_values(

        cur,

        """
        INSERT INTO indirimli_urunler (
            ilgili_urun_id,
            eski_degeri,
            yeni_degeri,
            indirim_tespit_tarihi,
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
            indirim_orani_pct,
            severity,
            reason,
            onceki_kayit_tarihi,
            yeni_kayit_tarihi
        ) VALUES %s
        ON CONFLICT DO NOTHING
        """,

        yuk,

        page_size=500,

    )

    cur.execute("SELECT COUNT(*) FROM indirimli_urunler")

    after_count = int(cur.fetchone()[0])

    return after_count - before_count





def main() -> None:

    args = argumanlari_ayristir()

    thresholds = FiyatDegisimEsikleri(

        min_fiyat_artis_yuzdesi=args.min_fiyat_artis_yuzdesi,

        min_fiyat_dusus_yuzdesi=args.min_fiyat_dusus_yuzdesi,

    )

    start_bound = parse_timestamp_bound(args.start_date) if args.start_date else None

    end_bound = parse_timestamp_bound(args.end_date, end_of_day=True) if args.end_date else None



    load_dotenv(".env")

    baglanti = psycopg2.connect(load_database_url(VARSAYILAN_VERITABANI_ADRES_ENV))

    cur = baglanti.imlec()

    try:

        if not args.skip_migration:

            sql = read_sql_file(args.migration_sql).strip()

            if sql:

                cur.execute(sql)

                baglanti.commit()



        grouped = load_snapshots(cur)

        artis_satirlari: list[dict[str, Any]] = []

        dusus_satirlari: list[dict[str, Any]] = []

        for snapshots in grouped.values():

            increases, decreases = detect_price_changes_series(snapshots, thresholds)

            artis_satirlari.extend(finding_to_price_increase_row(item) for item in increases)

            dusus_satirlari.extend(finding_to_price_decrease_row(item) for item in decreases)



        increase_df = pd.DataFrame(artis_satirlari)

        decrease_df = pd.DataFrame(dusus_satirlari)

        if not increase_df.empty:

            increase_df = filter_rows_by_timestamp_window(increase_df, "yeni_kayit_tarihi", start_bound, end_bound)

        if not decrease_df.empty:

            decrease_df = filter_rows_by_timestamp_window(decrease_df, "yeni_kayit_tarihi", start_bound, end_bound)

        artis_satirlari = increase_df.to_dict("records") if not increase_df.empty else []

        dusus_satirlari = decrease_df.to_dict("records") if not decrease_df.empty else []



        artis_satirlari.sort(key=lambda satir: float(satir["zam_orani_pct"]), reverse=True)

        dusus_satirlari.sort(key=lambda satir: float(satir["indirim_orani_pct"]), reverse=True)



        write_csv(args.zamli_audit_csv, ZAMLI_FIELDNAMES, artis_satirlari)

        write_csv(args.indirimli_audit_csv, INDIRIMLI_FIELDNAMES, dusus_satirlari)



        print(f"Zamli bulgu sayisi: {len(increase_rows)}")

        print(f"Indirimli bulgu sayisi: {len(decrease_rows)}")

        print(f"Zamli audit CSV: {args.zamli_audit_csv}")

        print(f"Indirimli audit CSV: {args.indirimli_audit_csv}")



        if args.apply:

            inserted_increases = insert_price_increase_rows(cur, artis_satirlari)

            inserted_decreases = insert_price_decrease_rows(cur, dusus_satirlari)

            baglanti.commit()

            cur.execute("SELECT COUNT(*) FROM zamli_urunler")

            total_increases = int(cur.fetchone()[0])

            cur.execute("SELECT COUNT(*) FROM indirimli_urunler")

            total_decreases = int(cur.fetchone()[0])

            print(f"Inserted zamli_urunler rows: {inserted_increases}")

            print(f"Inserted indirimli_urunler rows: {inserted_decreases}")

            print(f"Total zamli_urunler rows: {total_increases}")

            print(f"Total indirimli_urunler rows: {total_decreases}")

        else:

            print("Dry run only; no price change rows inserted.")

    finally:

        cur.close()

        baglanti.close()





if __name__ == "__main__":

    main()

