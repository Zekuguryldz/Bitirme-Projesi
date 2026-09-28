import argparse

import csv

import os

from collections import defaultdict

from pathlib import Path

from statistics import StatisticsError, mean, stdev

from typing import Optional



import pandas as pd

import psycopg2

from psycopg2.extras import execute_values

from dotenv import load_dotenv



from normalize_fiyat_zaman_serisi import choose_candidate, compute_unit_price, extract_candidate

from shrinkflation import TespitEsikleri, FiyatKaydi, detect_shrinkflation_series

from sok_weekly_supabase_sync import filter_rows_by_timestamp_window, parse_timestamp_bound



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

    "gramaj_degisim_pct",

    "fiyat_degisim_pct",

    "birim_fiyat_degisim_pct",

    "shrinkflation_orani_pct",

    "z_score",

    "history_sample_count",

    "severity",

    "reason",

]





def argumanlari_ayristir() -> argparse.Namespace:

    komut_ayristirici = argparse.ArgumentParser(

        description="Supabase fiyat gecmisinde shrinkflation anomalisini tespit eder."

    )

    komut_ayristirici.add_argument(

        "--migration-sql",

        type=Path,

        default=Path("migrations/004_anomali_week4.sql"),

    )

    komut_ayristirici.add_argument(

        "--audit-csv",

        type=Path,

        default=Path("outputs/shrinkflation_findings.csv"),

    )

    komut_ayristirici.add_argument("--min-size-drop-pct", type=float, default=3.0)

    komut_ayristirici.add_argument("--max-size-drop-pct", type=float, default=70.0)

    komut_ayristirici.add_argument("--min-unit-price-increase-pct", type=float, default=3.0)

    komut_ayristirici.add_argument("--stable-price-floor-pct", type=float, default=0.0)

    komut_ayristirici.add_argument("--start-date", default=None, help="Opsiyonel tespit başlangıç tarihi")

    komut_ayristirici.add_argument("--end-date", default=None, help="Opsiyonel tespit bitiş tarihi")

    komut_ayristirici.add_argument("--skip-migration", action="store_true")

    komut_ayristirici.add_argument("--apply", action="store_true")

    return komut_ayristirici.parse_args()





def read_sql_file(yol: Path) -> str:

    return yol.read_text(encoding="utf-8")





def write_csv(yol: Path, satirlar: list[dict[str, object]]) -> None:

    yol.parent.mkdir(parents=True, exist_ok=True)

    with yol.open("w", encoding="utf-8", newline="") as handle:

        yazici = csv.DictWriter(handle, fieldnames=AUDIT_FIELDNAMES)

        yazici.writeheader()

        if satirlar:

            yazici.writerows(satirlar)





def format_measure_text(gramaj_degeri, gramaj_birimi: Optional[str]) -> str:

    if gramaj_degeri is None or not gramaj_birimi:

        return ""

    value = float(gramaj_degeri)

    if value.is_integer():

        value_text = str(int(value))

    else:

        value_text = f"{value:.4f}".rstrip("0").rstrip(".")

    return f"{value_text} {gramaj_birimi}"





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

            float(gramaj_degeri) if gramaj_degeri is not None else None,

            gramaj_birimi,

            float(birim_fiyat) if birim_fiyat is not None else None,

        )

    return (

        float(chosen.total_base),

        chosen.temel_birim,

        compute_unit_price(

            float(urun_fiyat) if urun_fiyat is not None else None,

            chosen.total_base,

            chosen.taban_birim,

        ),

    )





def build_snapshot_identity_key(satir) -> str:

    market_kimligi = satir[7]

    adres_anahtari = satir[10]

    urun_url = satir[9]

    site_urun_kodu = satir[8]

    if adres_anahtari:

        return f"market:{market_kimligi}:url_key:{adres_anahtari}"

    if urun_url:

        return f"market:{market_kimligi}:urun_url:{urun_url}"

    return f"market:{market_kimligi}:site_product_code:{site_urun_kodu or satir[0]}"


def load_snapshots(cur) -> dict[str, list[FiyatKaydi]]:

    cur.execute(

        """
        SELECT
            u.id,
            u.urun_ad,
            f.kazima_tarihi,
            f.urun_fiyat,
            f.gramaj_degeri,
            f.gramaj_birimi,
            f.birim_fiyat,
            u.market_id,
            u.site_product_code,
            u.urun_url,
            u.url_key
        FROM urunler AS u
        JOIN fiyat_zaman_serisi AS f
          ON f.urun_id = u.id
        ORDER BY u.market_id, u.url_key, u.urun_url, u.id, f.kazima_tarihi
        """

    )



    grouped: dict[str, list[FiyatKaydi]] = defaultdict(list)

    for satir in cur.fetchall():

        normalize_olcu, normalize_birim, normalize_birim_fiyat = canonicalize_snapshot_measure(

            urun_ad=satir[1],

            urun_fiyat=satir[3],

            gramaj_degeri=satir[4],

            gramaj_birimi=satir[5],

            birim_fiyat=satir[6],

        )

        snapshot = FiyatKaydi(

            urun_id=satir[0],

            urun_ad=satir[1],

            kazima_tarihi=satir[2],

            urun_fiyat=float(satir[3]) if satir[3] is not None else None,

            gramaj_degeri=normalize_olcu,

            gramaj_birimi=normalize_birim,

            birim_fiyat=normalize_birim_fiyat,

        )

        grouped[build_snapshot_identity_key(satir)].append(snapshot)

    return grouped





def finding_to_row(bulgu) -> dict[str, object]:

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

        "gramaj_degisim_pct": round(bulgu.gramaj_degisim_pct, 4),

        "fiyat_degisim_pct": round(bulgu.fiyat_degisim_pct, 4),

        "birim_fiyat_degisim_pct": round(bulgu.birim_fiyat_degisim_pct, 4),

        "shrinkflation_orani_pct": round(bulgu.shrinkflation_orani_pct, 4),

        "z_score": None,

        "history_sample_count": 0,

        "severity": bulgu.severity,

        "reason": bulgu.reason,

    }


def calculate_unit_price_zscore(

    history_snapshots: list[FiyatKaydi],

    guncel_kayit_tarihi: str,

    guncel_birim_fiyat: float,

) -> tuple[Optional[float], int]:

    current_time = pd.Timestamp(guncel_kayit_tarihi).to_pydatetime()

    history_values = [
        float(item.birim_fiyat)
        for item in history_snapshots
        if item.birim_fiyat is not None and item.kazima_tarihi < current_time
    ]

    if len(history_values) < 3:

        return None, len(history_values)

    try:

        history_std = stdev(history_values)

    except StatisticsError:

        return None, len(history_values)

    if history_std == 0:

        return None, len(history_values)

    z_score_value = (float(guncel_birim_fiyat) - mean(history_values)) / history_std

    return round(float(z_score_value), 4), len(history_values)


def enrich_rows_with_zscore(

    bulgu_satirlari: list[dict[str, object]],

    grouped: dict[str, list[FiyatKaydi]],

) -> list[dict[str, object]]:

    snapshots_by_product_id: dict[int, list[FiyatKaydi]] = {}

    for snapshots in grouped.values():

        for snapshot in snapshots:

            snapshots_by_product_id.setdefault(snapshot.urun_id, snapshots)

    for satir in bulgu_satirlari:

        snapshots = snapshots_by_product_id.get(int(satir["urun_id"]), [])

        z_score_value, history_count = calculate_unit_price_zscore(

            snapshots,

            str(satir["yeni_kayit_tarihi"]),

            float(satir["yeni_birim_fiyat"]),

        )

        satir["z_score"] = z_score_value

        satir["history_sample_count"] = history_count

    return bulgu_satirlari





def insert_findings(cur, bulgu_satirlari: list[dict[str, object]]) -> int:

    if not bulgu_satirlari:

        return 0



    yuk = [

        (

            satir["urun_id"],

            satir["onceki_birim_fiyat"],

            satir["yeni_birim_fiyat"],

            satir["yeni_kayit_tarihi"],

            "shrinkflation",

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

            satir["shrinkflation_orani_pct"],

            satir["severity"],

            satir["reason"],

            satir["z_score"],

            satir["history_sample_count"],

            satir["onceki_kayit_tarihi"],

            satir["yeni_kayit_tarihi"],

        )

        for satir in bulgu_satirlari

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

    return len(yuk)





def main() -> None:

    args = argumanlari_ayristir()

    thresholds = TespitEsikleri(

        min_size_drop_pct=args.min_size_drop_pct,

        max_size_drop_pct=args.max_size_drop_pct,

        min_birim_fiyat_artis_yuzdesi=args.min_unit_price_increase_pct,

        sabit_fiyat_alt_yuzdesi=args.stable_price_floor_pct,

    )

    start_bound = parse_timestamp_bound(args.start_date) if args.start_date else None

    end_bound = parse_timestamp_bound(args.end_date, end_of_day=True) if args.end_date else None



    load_dotenv(".env")

    baglanti = psycopg2.connect(os.environ["DATABASE_URL"])

    cur = baglanti.cursor()

    try:

        if not args.skip_migration:

            sql = read_sql_file(args.migration_sql).strip()

            if sql:

                cur.execute(sql)

                baglanti.commit()



        grouped = load_snapshots(cur)

        bulgular = []

        for snapshots in grouped.values():

            bulgular.extend(detect_shrinkflation_series(snapshots, thresholds))



        bulgu_satirlari = [finding_to_row(item) for item in bulgular]

        bulgu_satirlari = enrich_rows_with_zscore(bulgu_satirlari, grouped)

        findings_df = pd.DataFrame(bulgu_satirlari)

        if not findings_df.empty:

            findings_df = filter_rows_by_timestamp_window(

                findings_df,

                "yeni_kayit_tarihi",

                start_bound,

                end_bound,

            )

        bulgu_satirlari = findings_df.to_dict("records") if not findings_df.empty else []

        bulgu_satirlari.sort(key=lambda satir: satir["shrinkflation_orani_pct"], reverse=True)

        write_csv(args.audit_csv, bulgu_satirlari)



        if args.apply:

            inserted = insert_findings(cur, bulgu_satirlari)

            baglanti.commit()

            print(f"Applied findings={inserted}")

        else:

            print("Dry run only; no anomaly rows inserted.")



        severity_counts: dict[str, int] = defaultdict(int)

        for satir in bulgu_satirlari:

            severity_counts[satir["severity"]] += 1



        print(f"Toplam finding: {len(bulgu_satirlari)}")

        print(f"Severity counts: {dict(severity_counts)}")

        print(f"Audit CSV: {args.audit_csv}")

    finally:

        cur.close()

        baglanti.close()





if __name__ == "__main__":

    main()
