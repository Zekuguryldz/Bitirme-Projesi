import argparse

import csv

import os

from pathlib import Path

from typing import Any



import psycopg2

from dotenv import load_dotenv

from psycopg2.extras import execute_values



from detect_shrinkflation_supabase import load_snapshots, read_sql_file

from zscore import ZScoreThresholds, detect_unit_price_zscore_anomaly



VARSAYILAN_VERITABANI_ADRES_ENV = "SUPABASE_DB_URL"

YEDEK_VERITABANI_ADRES_ENV = "DATABASE_URL"

AUDIT_FIELDNAMES = [

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

    "fiyat_degisim_pct",

    "birim_fiyat_degisim_pct",

    "history_mean_unit_price",

    "history_std_unit_price",

    "history_sample_count",

    "z_score",

    "severity",

    "reason",

]





def argumanlari_ayristir() -> argparse.Namespace:

    komut_ayristirici = argparse.ArgumentParser(

        description="Supabase fiyat gecmisinde unit price Z-score anomalilerini tespit eder."

    )

    komut_ayristirici.add_argument(

        "--migration-sql",

        type=Path,

        default=Path("migrations/007_anomali_zscore.sql"),

    )

    komut_ayristirici.add_argument(

        "--audit-csv",

        type=Path,

        default=Path("outputs/zscore_anomalies_findings.csv"),

    )

    komut_ayristirici.add_argument("--zscore-threshold", type=float, default=2.5)

    komut_ayristirici.add_argument("--zscore-min-history", type=int, default=3)

    komut_ayristirici.add_argument("--zscore-min-unit-price-change-pct", type=float, default=3.0)

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





def write_csv(yol: Path, satirlar: list[dict[str, Any]]) -> None:

    yol.parent.mkdir(parents=True, exist_ok=True)

    with yol.open("w", encoding="utf-8", newline="") as handle:

        yazici = csv.DictWriter(handle, fieldnames=AUDIT_FIELDNAMES)

        yazici.writeheader()

        if satirlar:

            yazici.writerows(satirlar)





def finding_to_row(bulgu) -> dict[str, Any]:

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

        "fiyat_degisim_pct": round(bulgu.fiyat_degisim_pct, 4) if bulgu.fiyat_degisim_pct is not None else None,

        "birim_fiyat_degisim_pct": round(bulgu.birim_fiyat_degisim_pct, 4) if bulgu.birim_fiyat_degisim_pct is not None else None,

        "history_mean_unit_price": round(bulgu.gecmis_ortalama_birim_fiyat, 4),

        "history_std_unit_price": round(bulgu.gecmis_std_birim_fiyat, 4),

        "history_sample_count": bulgu.history_sample_count,

        "z_score": round(bulgu.z_score, 4),

        "severity": bulgu.severity,

        "reason": bulgu.reason,

    }





def insert_zscore_rows(cur, satirlar: list[dict[str, Any]]) -> int:

    if not satirlar:

        return 0



    cur.execute("SELECT COUNT(*) FROM anomali WHERE anomali_turu = 'unit_price_zscore'")

    before_count = int(cur.fetchone()[0])

    yuk = [

        (

            satir["urun_id"],

            satir["history_mean_unit_price"],

            satir["yeni_birim_fiyat"],

            satir["yeni_kayit_tarihi"],

            "unit_price_zscore",

            satir["onceki_fiyat"],

            satir["yeni_fiyat"],

            satir["onceki_gramaj_degeri"],

            satir["yeni_gramaj_degeri"],

            satir["gramaj_birimi"],

            satir["onceki_birim_fiyat"],

            satir["yeni_birim_fiyat"],

            None,

            satir["fiyat_degisim_pct"],

            satir["birim_fiyat_degisim_pct"],

            None,

            satir["severity"],

            satir["reason"],

            satir["z_score"],

            satir["history_sample_count"],

            satir["onceki_kayit_tarihi"],

            satir["yeni_kayit_tarihi"],

        )

        for satir in satirlar

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
            z_score,
            history_sample_count,
            onceki_kayit_tarihi,
            yeni_kayit_tarihi
        ) VALUES %s
        ON CONFLICT DO NOTHING
        """,

        yuk,

        page_size=500,

    )

    cur.execute("SELECT COUNT(*) FROM anomali WHERE anomali_turu = 'unit_price_zscore'")

    after_count = int(cur.fetchone()[0])

    return after_count - before_count





def main() -> None:

    args = argumanlari_ayristir()

    thresholds = ZScoreThresholds(

        z_score_threshold=args.zscore_threshold,

        min_history_count=args.zscore_min_history,

        min_mutlak_birim_fiyat_degisim_yuzdesi=args.zscore_min_unit_price_change_pct,

    )



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

        bulgu_satirlari: list[dict[str, Any]] = []

        for snapshots in grouped.values():

            if len(snapshots) <= thresholds.min_history_count:

                continue

            ordered = sorted(snapshots, key=lambda item: item.kazima_tarihi)

            for index in range(thresholds.min_history_count, len(ordered)):

                history_snapshots = ordered[:index]

                guncel_kayit = ordered[index]

                bulgu = detect_unit_price_zscore_anomaly(history_snapshots, guncel_kayit, thresholds)

                if bulgu is not None:

                    bulgu_satirlari.append(finding_to_row(bulgu))



        bulgu_satirlari.sort(key=lambda satir: abs(float(satir["z_score"])), reverse=True)

        write_csv(args.denetim_csv, bulgu_satirlari)



        print(f"Z-score bulgu sayisi: {len(bulgu_satirlari)}")

        print(f"Audit CSV: {args.audit_csv}")



        if args.apply:

            inserted = insert_zscore_rows(cur, bulgu_satirlari)

            baglanti.commit()

            cur.execute("SELECT COUNT(*) FROM anomali WHERE anomali_turu = 'unit_price_zscore'")

            total_rows = int(cur.fetchone()[0])

            print(f"Inserted unit_price_zscore rows: {inserted}")

            print(f"Total unit_price_zscore rows: {total_rows}")

        else:

            print("Dry run only; no anomaly rows inserted.")

    finally:

        cur.close()

        baglanti.close()





if __name__ == "__main__":

    main()

