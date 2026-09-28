from __future__ import annotations



import argparse

import logging

import time

from datetime import datetime

from pathlib import Path

from typing import Any

from urllib.parse import urlparse



import pandas as pd

from psycopg2 import OperationalError

from dotenv import load_dotenv



from migros_scraper import (

    KATEGORI_HEDEFLERI,

    TIMEZONE,

    clean_text,

    deduplicate_relisted_products,

    filter_packaged_product_rows,

    run_pipeline,

)

from shrinkflation import TespitEsikleri

from sok_weekly_supabase_sync import (

    ANOMALY_COLUMNS,

    INDIRIMLI_URUN_COLUMNS,

    SyncContext,

    ZAMLI_URUN_COLUMNS,

    build_default_anomaly_detector,

    canonicalize_measure,

    connect_db,

    load_anomaly_detector,

    load_database_url,

    load_raw_products_from_outputs,

    parse_timestamp_bound,

    save_sync_audit,

    sync_to_database,

)

from zscore import ZScoreThresholds



BASE_DIR = Path(__file__).resolve().parent

DEFAULT_OUTPUT_ROOT = BASE_DIR / "scheduled_outputs"

VARSAYILAN_MARKET_ADI = "MİGROS"

VARSAYILAN_VERITABANI_ADRES_ENV = "SUPABASE_DB_URL"

DEFAULT_SCHEDULE_CRON = "0 19 * * 1"

DEFAULT_DB_SYNC_MAX_ATTEMPTS = 3

DEFAULT_DB_SYNC_RETRY_DELAY_SECONDS = 5.0



MARKET_NAME_MAP = {

    "migros": VARSAYILAN_MARKET_ADI,

    "migros sanal market": VARSAYILAN_MARKET_ADI,

    "m gross": VARSAYILAN_MARKET_ADI,

}





def normalize_for_match(value: Any) -> str:

    text = clean_text(value) or ""

    normalize_edilmis = (

        text.casefold()

        .replace("ı", "i")

        .replace("ş", "s")

        .replace("ğ", "g")

        .replace("ç", "c")

        .replace("ö", "o")

        .replace("ü", "u")

    )

    collapsed = "".join(char if char.isalnum() else " " for char in normalize_edilmis)

    return " ".join(collapsed.split())





def canonicalize_market_name(value: str | None) -> str:

    normalize_edilmis = normalize_for_match(value or VARSAYILAN_MARKET_ADI)

    return MARKET_NAME_MAP.get(normalize_edilmis, VARSAYILAN_MARKET_ADI)





def derive_migros_url_key(adres: str | None) -> str | None:

    cleaned = clean_text(adres)

    if not cleaned:

        return None

    return clean_text(urlparse(cleaned).path.strip("/"))





def derive_migros_site_product_code(urun_kodu: Any) -> str | None:

    return clean_text(urun_kodu)





def build_legacy_signature(urun_adi: Any, marka: Any, kategori: Any) -> str | None:

    parts = [

        normalize_for_match(marka),

        normalize_for_match(urun_adi),

        normalize_for_match(kategori),

    ]

    signature = "|".join(part for part in parts if part)

    return signature or None





def _series_or_default(df: pd.DataFrame, column: str, default: Any = None) -> pd.Series:

    if column in df:

        return df[column]

    if isinstance(default, pd.Series):

        return default.reindex(df.index)

    return pd.Series([default] * len(df), index=df.index)





def filter_reyondan_raw_df(raw_df: pd.DataFrame) -> pd.DataFrame:

    return filter_packaged_product_rows(raw_df)





def prepare_sync_rows(raw_df: pd.DataFrame) -> pd.DataFrame:

    df = deduplicate_relisted_products(filter_packaged_product_rows(raw_df))

    if df.empty:

        return df



    urun_adresi = _series_or_default(df, "product_url")

    urun_adi = _series_or_default(df, "product_name")

    urun_markasi = _series_or_default(df, "brand", _series_or_default(df, "listing_brand"))

    urun_kategorisi = _series_or_default(df, "site_main_category")

    current_price = _series_or_default(df, "current_price")

    package_total_value = _series_or_default(df, "package_total_value")

    package_unit = _series_or_default(df, "package_unit")

    birim_fiyat = _series_or_default(df, "unit_price_numeric", _series_or_default(df, "unit_price"))

    item_count = _series_or_default(df, "item_count")

    kazima_zaman_damgasi = _series_or_default(df, "scrape_timestamp")

    first_reference_date = _series_or_default(df, "first_reference_date", _series_or_default(df, "eklenme_tarihi"))



    df["market_adi"] = VARSAYILAN_MARKET_ADI

    df["site_product_code"] = _series_or_default(df, "site_product_code").map(derive_migros_site_product_code)

    df["url_key"] = _series_or_default(df, "url_key").combine_first(urun_adresi.map(derive_migros_url_key))

    df["legacy_signature"] = [

        build_legacy_signature(name_value, brand_value, category_value)

        for name_value, brand_value, category_value in zip(urun_adi, urun_markasi, urun_kategorisi)

    ]

    df["urun_ad"] = urun_adi.map(clean_text)

    df["urun_url"] = urun_adresi.map(clean_text)

    df["urun_kategori"] = urun_kategorisi.map(clean_text)

    df["urun_marka"] = urun_markasi.map(clean_text)



    kazima_zamani = pd.to_datetime(kazima_zaman_damgasi, errors="coerce", utc=True)

    first_ref_ts = pd.to_datetime(first_reference_date, errors="coerce", utc=True)

    df["kazima_tarihi"] = kazima_zamani

    df["eklenme_tarihi"] = first_ref_ts.combine_first(kazima_zamani)

    df["son_gorulme_tarihi"] = kazima_zamani

    df["urun_fiyat"] = pd.to_numeric(current_price, errors="coerce")



    normalized_measure_df = pd.DataFrame(

        [

            canonicalize_measure(

                urun_adi=satir.get("product_name"),

                fiyat=satir.get("current_price"),

                gramaj_degeri=satir.get("package_total_value"),

                gramaj_birimi=satir.get("package_unit"),

                birim_fiyat=satir.get("unit_price_numeric") if satir.get("unit_price_numeric") is not None else satir.get("unit_price"),

            )

            for satir in df.to_dict("records")

        ],

        columns=["gramaj_degeri", "gramaj_birimi", "birim_fiyat"],

        index=df.index,

    )

    df[["gramaj_degeri", "gramaj_birimi", "birim_fiyat"]] = normalized_measure_df



    df["adet_sayisi"] = pd.to_numeric(item_count, errors="coerce")

    adet_mask = df["adet_sayisi"].isna() & (df["gramaj_birimi"] == "adet")

    df.loc[adet_mask, "adet_sayisi"] = df.loc[adet_mask, "gramaj_degeri"]



    df = df.sort_values(["urun_kategori", "urun_marka", "urun_ad", "urun_url"]).reset_index(drop=True)

    df["sira_no"] = df.index + 1

    df["market_adi"] = df["market_adi"].map(canonicalize_market_name)

    return df.where(pd.notna(df), None)





def run_scrape(cikti_koku: Path, limit: int | None, *, exclude_reyondan: bool = False) -> tuple[Path, pd.DataFrame]:

    run_id = datetime.now(TIMEZONE).strftime("%Y%m%d_%H%M%S")

    cikti_dizini = cikti_koku / f"migros_sync_{run_id}"

    ciktilar = run_pipeline(

        cikti_dizini=cikti_dizini,

        categories=KATEGORI_HEDEFLERI,

        urun_siniri=limit,

        snapshot_dir=cikti_dizini / "_snapshots",

        exclude_reyondan=exclude_reyondan,

    )

    return cikti_dizini, ciktilar["raw_products"]





def build_cli_parser() -> argparse.ArgumentParser:

    komut_ayristirici = argparse.ArgumentParser(description="Migros haftalik scrape + Supabase senkronizasyonu")

    komut_ayristirici.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)

    komut_ayristirici.add_argument("--existing-output-dir", type=Path, default=None)

    komut_ayristirici.add_argument("--database-url", default=None, help="Opsiyonel Postgres baglanti cumlesi")

    komut_ayristirici.add_argument("--database-url-env", default=VARSAYILAN_VERITABANI_ADRES_ENV)

    komut_ayristirici.add_argument("--anomaly-detector", default=None, help="module:function veya /path/to/file.py")

    komut_ayristirici.add_argument("--strict-identity", action="store_true", help="Kimlik cakismasinda islemi durdur")

    komut_ayristirici.add_argument("--dry-run", action="store_true", help="DB yazmadan sadece normalize et ve audit uret")

    komut_ayristirici.add_argument("--exclude-reyondan", action="store_true", help="Reyondan markali urunleri haric tut")

    komut_ayristirici.add_argument("--limit", type=int, default=None)

    komut_ayristirici.add_argument("--min-size-drop-pct", type=float, default=3.0)

    komut_ayristirici.add_argument("--max-size-drop-pct", type=float, default=70.0)

    komut_ayristirici.add_argument("--min-unit-price-increase-pct", type=float, default=3.0)

    komut_ayristirici.add_argument("--stable-price-floor-pct", type=float, default=0.0)

    komut_ayristirici.add_argument("--zscore-threshold", type=float, default=2.5)

    komut_ayristirici.add_argument("--zscore-min-history", type=int, default=3)

    komut_ayristirici.add_argument("--zscore-min-unit-price-change-pct", type=float, default=3.0)

    komut_ayristirici.add_argument("--detection-start-date", default=None, help="Opsiyonel tespit başlangıç tarihi")

    komut_ayristirici.add_argument("--detection-end-date", default=None, help="Opsiyonel tespit bitiş tarihi")

    return komut_ayristirici





def sync_to_database_with_retry(

    *,

    veritabani_adresi: str,

    esitleme_satirlari: pd.DataFrame,

    market_adi: str,

    tespit_edici,

    strict_identity: bool,

    denetim_cikti_dizini: Path,

    tespit_baslangici: datetime | None = None,

    tespit_sonu: datetime | None = None,

    max_attempts: int = DEFAULT_DB_SYNC_MAX_ATTEMPTS,

    retry_delay_seconds: float = DEFAULT_DB_SYNC_RETRY_DELAY_SECONDS,

    baglanma_fonksiyonu=connect_db,

    esitleme_fonksiyonu=sync_to_database,

    sleep_fn=time.sleep,

    logger: logging.Logger | None = None,

) -> SyncContext:

    if max_attempts < 1:

        raise ValueError("max_attempts en az 1 olmalı")



    last_error: OperationalError | None = None

    for attempt in range(1, max_attempts + 1):

        baglanti = baglanma_fonksiyonu(veritabani_adresi)

        try:

            return esitleme_fonksiyonu(

                baglanti=baglanti,

                esitleme_satirlari=esitleme_satirlari,

                market_adi=market_adi,

                tespit_edici=tespit_edici,

                strict_identity=strict_identity,

                denetim_cikti_dizini=denetim_cikti_dizini,

                tespit_baslangici=tespit_baslangici,

                tespit_sonu=tespit_sonu,

            )

        except OperationalError as exc:

            last_error = exc

            try:

                baglanti.rollback()

            except Exception:

                pass

            if attempt >= max_attempts:

                raise

            if logger is not None:

                logger.warning(

                    "Veritabanı senkronu deneme %s/%s sırasında koptu; %ss sonra tekrar denenecek.",

                    attempt,

                    max_attempts,

                    retry_delay_seconds,

                )

            sleep_fn(retry_delay_seconds)

        finally:

            try:

                baglanti.close()

            except Exception:

                pass



    if last_error is not None:

        raise last_error

    raise RuntimeError("Veritabanı senkronu başlatılamadı")





def main(argv: list[str] | None = None) -> None:

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    load_dotenv(BASE_DIR / ".env")

    komut_ayristirici = build_cli_parser()

    args, _unknown = komut_ayristirici.parse_known_args(argv)



    thresholds = TespitEsikleri(

        min_size_drop_pct=args.min_size_drop_pct,

        max_size_drop_pct=args.max_size_drop_pct,

        min_birim_fiyat_artis_yuzdesi=args.min_birim_fiyat_artis_yuzdesi,

        sabit_fiyat_alt_yuzdesi=args.sabit_fiyat_alt_yuzdesi,

    )

    zscore_thresholds = ZScoreThresholds(

        z_score_threshold=args.zscore_threshold,

        min_history_count=args.zscore_min_history,

        min_mutlak_birim_fiyat_degisim_yuzdesi=args.zscore_min_unit_price_change_pct,

    )

    tespit_baslangici = parse_timestamp_bound(args.detection_start_date) if args.detection_start_date else None

    tespit_sonu = (

        parse_timestamp_bound(args.detection_end_date, end_of_day=True) if args.detection_end_date else None

    )

    tespit_edici = load_anomaly_detector(args.anomaly_detector) or build_default_anomaly_detector(

        thresholds,

        zscore_thresholds,

    )



    if args.existing_output_dir:

        cikti_dizini = args.existing_output_dir

        raw_df = load_raw_products_from_outputs(cikti_dizini)

    else:

        cikti_dizini, raw_df = run_scrape(

            cikti_koku=args.cikti_koku,

            limit=args.limit,

            exclude_reyondan=args.exclude_reyondan,

        )



    raw_df = filter_packaged_product_rows(raw_df)



    esitleme_satirlari = prepare_sync_rows(raw_df)

    cikti_dizini.mkdir(parents=True, exist_ok=True)

    esitleme_satirlari.to_csv(cikti_dizini / "db_sync_input.csv", index=False, encoding="utf-8-sig")



    if args.dry_run:

        dry_context = SyncContext(market_kimligi=2)

        save_sync_audit(

            cikti_dizini,

            dry_context,

            pd.DataFrame(columns=ANOMALY_COLUMNS),

            pd.DataFrame(columns=ZAMLI_URUN_COLUMNS),

            pd.DataFrame(columns=INDIRIMLI_URUN_COLUMNS),

        )

        print(f"Dry run tamamlandi. Hazir satir sayisi: {len(esitleme_satirlari)}")

        print(f"Girdi dosyasi: {cikti_dizini / 'db_sync_input.csv'}")

        print(f"Onerilen cron: {DEFAULT_SCHEDULE_CRON}")

        return



    veritabani_adresi = load_database_url(args.veritabani_adresi, args.database_url_env)

    context = sync_to_database_with_retry(

        veritabani_adresi=veritabani_adresi,

        esitleme_satirlari=esitleme_satirlari,

        market_adi=VARSAYILAN_MARKET_ADI,

        tespit_edici=tespit_edici,

        strict_identity=args.strict_identity,

        denetim_cikti_dizini=cikti_dizini,

        tespit_baslangici=tespit_baslangici,

        tespit_sonu=tespit_sonu,

        logger=logging.getLogger(__name__),

    )



    print("\nSenkronizasyon tamamlandi:")

    print(f"- market_id: {context.market_id}")

    print(f"- yeni urun: {context.stats.inserted_products}")

    print(f"- guncellenen urun: {context.stats.updated_products}")

    print(f"- yeni fiyat kaydi: {context.stats.inserted_prices}")

    print(f"- guncellenen fiyat kaydi: {context.stats.updated_prices}")

    print(f"- eklenen anomali: {context.stats.inserted_anomalies}")

    print(f"- eklenen zamli urun kaydi: {context.stats.inserted_price_increases}")

    print(f"- eklenen indirimli urun kaydi: {context.stats.inserted_price_decreases}")

    print(f"- hard conflict: {context.stats.hard_conflicts}")

    print(f"- atlanan satir: {context.stats.skipped_rows}")

    print(f"- audit dosyasi: {cikti_dizini / 'db_sync_audit.csv'}")

    print(f"- onerilen cron: {DEFAULT_SCHEDULE_CRON}")





if __name__ == "__main__":

    main()
