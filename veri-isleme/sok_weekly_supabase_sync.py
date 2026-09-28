from __future__ import annotations



import argparse

import importlib

import importlib.util

import logging

import os

import re

import unicodedata

from dataclasses import dataclass, field

from datetime import datetime, timedelta, timezone

from pathlib import Path

from typing import Any, Callable

from urllib.parse import urlparse



import pandas as pd

import psycopg2

from psycopg2.extras import RealDictCursor, execute_values

from psycopg2.extensions import STATUS_READY

from dotenv import load_dotenv



from normalize_fiyat_zaman_serisi import choose_candidate, compute_unit_price, extract_candidate

from price_change import FiyatDegisimEsikleri, detect_price_decrease, detect_price_increase

from shrinkflation import TespitEsikleri, FiyatKaydi, detect_shrinkflation

from zscore import ZScoreThresholds, detect_unit_price_zscore_anomaly



BASE_DIR = Path(__file__).resolve().parent

DEFAULT_OUTPUT_ROOT = BASE_DIR / "scheduled_outputs"

VARSAYILAN_MARKET_ADI = "ŞOK"

VARSAYILAN_VERITABANI_ADRES_ENV = "SUPABASE_DB_URL"

YEDEK_VERITABANI_ADRES_ENV = "DATABASE_URL"

DEFAULT_SCHEDULE_CRON = "0 19 * * 6"

FALLBACK_REFERENCE_CSV = BASE_DIR / "reference.csv"

PRICE_CHANGE_MIGRATION_SQL = BASE_DIR / "migrations/006_price_change_tables.sql"

ANOMALY_ZSCORE_MIGRATION_SQL = BASE_DIR / "migrations/007_anomali_zscore.sql"

SITE_PRODUCT_CODE_PATTERN = re.compile(r"-p-(\d+)$")



MARKET_NAME_MAP = {

    "sok": VARSAYILAN_MARKET_ADI,

    "sok market": VARSAYILAN_MARKET_ADI,

    "sokmarket": VARSAYILAN_MARKET_ADI,

    "sok marketleri": VARSAYILAN_MARKET_ADI,

    "sok market tr": VARSAYILAN_MARKET_ADI,

}



AUDIT_COLUMNS = [

    "market_id",

    "urun_ad",

    "urun_url",

    "site_product_code",

    "url_key",

    "legacy_signature",

    "resolved_by",

    "resolved_product_id",

    "hard_conflict",

    "conflict_details",

]

ANOMALY_COLUMNS = [

    "ilgili_urun_id",

    "urun_ad",

    "eski_degeri",

    "yeni_degeri",

    "anomali_tespit_tarihi",

    "anomali_turu",

    "onceki_fiyat",

    "yeni_fiyat_detay",

    "onceki_gramaj_degeri",

    "yeni_gramaj_degeri_detay",

    "gramaj_birimi",

    "onceki_birim_fiyat",

    "yeni_birim_fiyat_detay",

    "gramaj_degisim_pct",

    "fiyat_degisim_pct",

    "birim_fiyat_degisim_pct",

    "shrinkflation_orani_pct",

    "severity",

    "reason",

    "z_score",

    "history_sample_count",

    "onceki_kayit_tarihi",

    "yeni_kayit_tarihi",

]

ZAMLI_URUN_COLUMNS = [

    "ilgili_urun_id",

    "urun_ad",

    "eski_degeri",

    "yeni_degeri",

    "zam_tespit_tarihi",

    "onceki_fiyat",

    "yeni_fiyat_detay",

    "onceki_gramaj_degeri",

    "yeni_gramaj_degeri_detay",

    "gramaj_birimi",

    "onceki_birim_fiyat",

    "yeni_birim_fiyat_detay",

    "gramaj_degisim_pct",

    "fiyat_degisim_pct",

    "birim_fiyat_degisim_pct",

    "zam_orani_pct",

    "severity",

    "reason",

    "onceki_kayit_tarihi",

    "yeni_kayit_tarihi",

]

INDIRIMLI_URUN_COLUMNS = [

    "ilgili_urun_id",

    "urun_ad",

    "eski_degeri",

    "yeni_degeri",

    "indirim_tespit_tarihi",

    "onceki_fiyat",

    "yeni_fiyat_detay",

    "onceki_gramaj_degeri",

    "yeni_gramaj_degeri_detay",

    "gramaj_birimi",

    "onceki_birim_fiyat",

    "yeni_birim_fiyat_detay",

    "gramaj_degisim_pct",

    "fiyat_degisim_pct",

    "birim_fiyat_degisim_pct",

    "indirim_orani_pct",

    "severity",

    "reason",

    "onceki_kayit_tarihi",

    "yeni_kayit_tarihi",

]





def _fallback_clean_text(value: Any) -> str | None:

    if value is None:

        return None

    try:

        if bool(pd.isna(value)):

            return None

    except Exception:

        pass



    text = str(value).replace("\xa0", " ").strip()

    if not text or text.lower() == "nan":

        return None

    return text





def _fallback_normalize_for_match(value: Any) -> str:

    text = _fallback_clean_text(value) or ""

    normalize_edilmis = unicodedata.normalize("NFKD", text.casefold())

    normalize_edilmis = "".join(char for char in normalize_edilmis if not unicodedata.combining(char))

    normalize_edilmis = (

        normalize_edilmis.replace("ı", "i")

        .replace("ş", "s")

        .replace("ğ", "g")

        .replace("ç", "c")

        .replace("ö", "o")

        .replace("ü", "u")

    )

    return re.sub(r"[^a-z0-9]+", " ", normalize_edilmis).strip()





def _fallback_parse_scrape_datetime_input(value: str) -> datetime:

    cleaned = clean_text(value)

    if cleaned is None:

        raise argparse.ArgumentTypeError("Çekim zamanı boş bırakılamaz.")



    normalized_value = cleaned.replace("Z", "+00:00")

    try:

        ayristirilmis = datetime.fromisoformat(normalized_value)

    except ValueError as exc:

        raise argparse.ArgumentTypeError(

            "Geçersiz --scrape-datetime değeri. Örnek: 2026-05-09 veya 2026-05-09T19:00:00+03:00"

        ) from exc



    if "T" not in normalized_value and " " not in normalized_value:

        ayristirilmis = ayristirilmis.replace(hour=19, minute=0, second=0, microsecond=0)

    if ayristirilmis.tzinfo is None:

        ayristirilmis = ayristirilmis.replace(tzinfo=TIMEZONE)

    else:

        ayristirilmis = ayristirilmis.astimezone(TIMEZONE)

    return ayristirilmis.replace(microsecond=0)





def _load_sok_scraper_module():

    try:

        return importlib.import_module("sok_scraper")

    except ModuleNotFoundError:

        return None





_SOK_SCRAPER = _load_sok_scraper_module()

KATEGORI_HEDEFLERI = getattr(_SOK_SCRAPER, "CATEGORY_TARGETS", ())

DEFAULT_REFERENCE_CSV = Path(getattr(_SOK_SCRAPER, "DEFAULT_REFERENCE_CSV", FALLBACK_REFERENCE_CSV))

TIMEZONE = getattr(_SOK_SCRAPER, "TIMEZONE", timezone(timedelta(hours=3)))

clean_text = getattr(_SOK_SCRAPER, "clean_text", _fallback_clean_text)

normalize_for_match = getattr(_SOK_SCRAPER, "normalize_for_match", _fallback_normalize_for_match)

deduplicate_relisted_products = getattr(_SOK_SCRAPER, "deduplicate_relisted_products", lambda df: df.copy())

run_pipeline = getattr(_SOK_SCRAPER, "run_pipeline", None)

parse_scrape_datetime_input = getattr(

    _SOK_SCRAPER,

    "parse_scrape_datetime_input",

    _fallback_parse_scrape_datetime_input,

)





@dataclass

class SyncStats:

    eklenen_urunler: int = 0

    guncellenen_urunler: int = 0

    eklenen_fiyatlar: int = 0

    updated_prices: int = 0

    inserted_anomalies: int = 0

    inserted_price_increases: int = 0

    inserted_price_decreases: int = 0

    hard_conflicts: int = 0

    skipped_rows: int = 0





@dataclass

class SyncContext:

    market_kimligi: int

    stats: SyncStats = field(default_factory=SyncStats)

    denetim_satirlari: list[dict[str, Any]] = field(default_factory=list)





def canonicalize_market_name(value: str | None) -> str:

    normalize_edilmis = normalize_for_match(value or VARSAYILAN_MARKET_ADI)

    return MARKET_NAME_MAP.get(normalize_edilmis, VARSAYILAN_MARKET_ADI)





def derive_sok_url_key(adres: str | None) -> str | None:

    cleaned = clean_text(adres)

    if not cleaned:

        return None

    yol = urlparse(cleaned).path.strip("/")

    eslesme = SITE_PRODUCT_CODE_PATTERN.search(yol)

    if eslesme:

        return eslesme.group(1)

    return clean_text(yol)





def derive_sok_site_product_code(urun_adresi: str | None, urun_kodu: Any) -> str | None:

    direct_code = clean_text(urun_kodu)

    if direct_code:

        return direct_code

    cleaned_url = clean_text(urun_adresi)

    if not cleaned_url:

        return None

    yol = urlparse(cleaned_url).path.strip("/")

    eslesme = SITE_PRODUCT_CODE_PATTERN.search(yol)

    return eslesme.group(1) if eslesme else None





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

    return pd.Series([default] * len(df), index=df.index)





def _parse_optional_float(value: Any) -> float | None:

    cleaned = clean_text(value)

    if cleaned is None:

        return None

    return float(str(cleaned).replace(",", "."))





def _format_measure_text(gramaj_degeri: Any, gramaj_birimi: Any) -> str:

    numeric_value = _parse_optional_float(gramaj_degeri)

    birim = clean_text(gramaj_birimi)

    if numeric_value is None or birim is None:

        return ""

    if float(numeric_value).is_integer():

        value_text = str(int(numeric_value))

    else:

        value_text = f"{numeric_value:.4f}".rstrip("0").rstrip(".")

    return f"{value_text} {birim}"





def canonicalize_measure(

    *,

    urun_adi: Any,

    fiyat: Any,

    gramaj_degeri: Any,

    gramaj_birimi: Any,

    birim_fiyat: Any,

) -> tuple[float | None, str | None, float | None]:

    ham_aday = extract_candidate(_format_measure_text(gramaj_degeri, gramaj_birimi), "raw_field")

    ad_adayi = extract_candidate(clean_text(urun_adi) or "", "product_name")

    chosen, _ = choose_candidate(ham_aday, ad_adayi)

    if chosen is None:

        return (

            _parse_optional_float(gramaj_degeri),

            clean_text(gramaj_birimi),

            _parse_optional_float(birim_fiyat),

        )



    normalized_price = _parse_optional_float(fiyat)

    return (

        float(chosen.total_base),

        chosen.temel_birim,

        compute_unit_price(normalized_price, chosen.total_base, chosen.taban_birim),

    )





def load_raw_products_from_outputs(cikti_dizini: Path) -> pd.DataFrame:

    raw_path = cikti_dizini / "raw_products.csv"

    if not raw_path.exists():

        raise FileNotFoundError(f"raw_products.csv bulunamadı: {raw_path}")

    return pd.read_csv(raw_path)





def prepare_sync_rows(raw_df: pd.DataFrame) -> pd.DataFrame:

    df = deduplicate_relisted_products(raw_df)

    if df.empty:

        return df



    urun_adresi = _series_or_default(df, "product_url")

    urun_kodu = _series_or_default(df, "product_code")

    urun_adi = _series_or_default(df, "product_name")

    urun_markasi = _series_or_default(df, "brand")

    urun_kategorisi = _series_or_default(df, "site_main_category")

    current_price = _series_or_default(df, "current_price")

    package_total_value = _series_or_default(df, "package_total_value")

    package_unit = _series_or_default(df, "package_unit")

    birim_fiyat = _series_or_default(df, "unit_price")

    item_count = _series_or_default(df, "item_count")

    kazima_zaman_damgasi = _series_or_default(df, "scrape_timestamp")

    first_reference_date = _series_or_default(df, "first_reference_date")



    df["market_adi"] = VARSAYILAN_MARKET_ADI

    df["site_product_code"] = [

        derive_sok_site_product_code(url_value, code_value)

        for url_value, code_value in zip(urun_adresi, urun_kodu)

    ]

    df["url_key"] = urun_adresi.map(derive_sok_url_key)

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

                birim_fiyat=satir.get("unit_price"),

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





def load_anomaly_detector(tespit_edici_tanimi: str | None) -> Callable[[pd.DataFrame, pd.DataFrame], pd.DataFrame] | None:

    if not tespit_edici_tanimi:

        return None



    if ":" in tespit_edici_tanimi and not tespit_edici_tanimi.endswith(".py"):

        module_name, func_name = tespit_edici_tanimi.split(":", 1)

        module = importlib.import_module(module_name)

        return getattr(module, func_name)



    detector_path = Path(tespit_edici_tanimi)

    if not detector_path.exists():

        raise FileNotFoundError(f"Anomali dosyası bulunamadı: {detector_path}")



    spec = importlib.util.spec_from_file_location(detector_path.stem, detector_path)

    if spec is None or spec.loader is None:

        raise ImportError(f"Anomali modülü yüklenemedi: {detector_path}")

    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    if not hasattr(module, "detect_anomalies"):

        raise AttributeError("Anomali modülünde detect_anomalies fonksiyonu bulunamadı.")

    return getattr(module, "detect_anomalies")





def build_default_anomaly_detector(

    thresholds: TespitEsikleri,

    zscore_thresholds: ZScoreThresholds | None = None,

) -> Callable[[pd.DataFrame, pd.DataFrame], pd.DataFrame]:

    zscore_thresholds = zscore_thresholds or ZScoreThresholds()



    def detect_anomalies(guncel_df: pd.DataFrame, history_df: pd.DataFrame) -> pd.DataFrame:

        if guncel_df.empty or history_df.empty:

            return pd.DataFrame(columns=ANOMALY_COLUMNS)



        history_by_product: dict[int, list[dict[str, Any]]] = {}

        for satir in history_df.to_dict("records"):

            urun_id = satir.get("urun_id")

            if urun_id is None:

                continue

            history_by_product.setdefault(int(urun_id), []).append(satir)



        bulgu_satirlari: list[dict[str, Any]] = []

        for guncel_satir in guncel_df.to_dict("records"):

            urun_id = guncel_satir.get("urun_id")

            if urun_id is None:

                continue

            urun_id = int(urun_id)

            product_history_rows = history_by_product.get(urun_id, [])

            if not product_history_rows:

                continue

            product_history_rows = sorted(

                product_history_rows,

                key=lambda item: pd.to_datetime(item.get("kazima_tarihi"), errors="coerce", utc=True),

            )

            previous_row = product_history_rows[-1]



            previous_name = clean_text(previous_row.get("urun_ad")) or clean_text(guncel_satir.get("urun_ad")) or ""

            current_name = clean_text(guncel_satir.get("urun_ad")) or previous_name

            onceki_kayit = build_price_snapshot(previous_row, previous_name)

            guncel_kayit = build_price_snapshot(guncel_satir, current_name)

            if onceki_kayit is None or guncel_kayit is None:

                continue



            shrinkflation_bulgusu = detect_shrinkflation(onceki_kayit, guncel_kayit, thresholds)

            if shrinkflation_bulgusu is not None:

                bulgu_satirlari.append(

                    {

                        "ilgili_urun_id": shrinkflation_bulgusu.urun_id,

                        "urun_ad": shrinkflation_bulgusu.urun_ad,

                        "eski_degeri": _format_numeric_text(shrinkflation_bulgusu.onceki_birim_fiyat),

                        "yeni_degeri": _format_numeric_text(shrinkflation_bulgusu.yeni_birim_fiyat),

                        "anomali_tespit_tarihi": guncel_kayit.kazima_tarihi,

                        "anomali_turu": "shrinkflation",

                        "onceki_fiyat": shrinkflation_bulgusu.onceki_fiyat,

                        "yeni_fiyat_detay": shrinkflation_bulgusu.yeni_fiyat,

                        "onceki_gramaj_degeri": shrinkflation_bulgusu.onceki_gramaj_degeri,

                        "yeni_gramaj_degeri_detay": shrinkflation_bulgusu.yeni_gramaj_degeri,

                        "gramaj_birimi": shrinkflation_bulgusu.gramaj_birimi,

                        "onceki_birim_fiyat": shrinkflation_bulgusu.onceki_birim_fiyat,

                        "yeni_birim_fiyat_detay": shrinkflation_bulgusu.yeni_birim_fiyat,

                        "gramaj_degisim_pct": shrinkflation_bulgusu.gramaj_degisim_pct,

                        "fiyat_degisim_pct": shrinkflation_bulgusu.fiyat_degisim_pct,

                        "birim_fiyat_degisim_pct": shrinkflation_bulgusu.birim_fiyat_degisim_pct,

                        "shrinkflation_orani_pct": shrinkflation_bulgusu.shrinkflation_orani_pct,

                        "severity": shrinkflation_bulgusu.severity,

                        "reason": shrinkflation_bulgusu.reason,

                        "z_score": None,

                        "history_sample_count": None,

                        "onceki_kayit_tarihi": shrinkflation_bulgusu.onceki_kayit_tarihi,

                        "yeni_kayit_tarihi": shrinkflation_bulgusu.yeni_kayit_tarihi,

                    }

                )



            history_snapshots = [

                snapshot

                for snapshot in (

                    build_price_snapshot(

                        history_row,

                        clean_text(history_row.get("urun_ad")) or previous_name,

                    )

                    for history_row in product_history_rows

                )

                if snapshot is not None

            ]

            zscore_bulgusu = detect_unit_price_zscore_anomaly(

                history_snapshots,

                guncel_kayit,

                zscore_thresholds,

            )

            if zscore_bulgusu is not None:

                bulgu_satirlari.append(

                    {

                        "ilgili_urun_id": zscore_bulgusu.urun_id,

                        "urun_ad": zscore_bulgusu.urun_ad,

                        "eski_degeri": _format_numeric_text(zscore_bulgusu.gecmis_ortalama_birim_fiyat),

                        "yeni_degeri": _format_numeric_text(zscore_bulgusu.yeni_birim_fiyat),

                        "anomali_tespit_tarihi": guncel_kayit.kazima_tarihi,

                        "anomali_turu": "unit_price_zscore",

                        "onceki_fiyat": zscore_bulgusu.onceki_fiyat,

                        "yeni_fiyat_detay": zscore_bulgusu.yeni_fiyat,

                        "onceki_gramaj_degeri": zscore_bulgusu.onceki_gramaj_degeri,

                        "yeni_gramaj_degeri_detay": zscore_bulgusu.yeni_gramaj_degeri,

                        "gramaj_birimi": zscore_bulgusu.gramaj_birimi,

                        "onceki_birim_fiyat": zscore_bulgusu.onceki_birim_fiyat,

                        "yeni_birim_fiyat_detay": zscore_bulgusu.yeni_birim_fiyat,

                        "gramaj_degisim_pct": zscore_bulgusu.gramaj_degisim_pct,

                        "fiyat_degisim_pct": zscore_bulgusu.fiyat_degisim_pct,

                        "birim_fiyat_degisim_pct": zscore_bulgusu.birim_fiyat_degisim_pct,

                        "shrinkflation_orani_pct": None,

                        "severity": zscore_bulgusu.severity,

                        "reason": zscore_bulgusu.reason,

                        "z_score": zscore_bulgusu.z_score,

                        "history_sample_count": zscore_bulgusu.history_sample_count,

                        "onceki_kayit_tarihi": zscore_bulgusu.onceki_kayit_tarihi,

                        "yeni_kayit_tarihi": zscore_bulgusu.yeni_kayit_tarihi,

                    }

                )



        anomalies_df = pd.DataFrame(bulgu_satirlari, columns=ANOMALY_COLUMNS)

        if anomalies_df.empty:

            return anomalies_df



        anomalies_df["_sort_score"] = anomalies_df.apply(

            lambda satir: abs(float(satir["z_score"]))

            if pd.notna(satir.get("z_score"))

            else abs(float(satir["shrinkflation_orani_pct"]))

            if pd.notna(satir.get("shrinkflation_orani_pct"))

            else 0.0,

            axis=1,

        )

        anomalies_df = anomalies_df.sort_values("_sort_score", ascending=False).drop(columns="_sort_score")

        return anomalies_df.reset_index(drop=True)



    return detect_anomalies





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





def connect_db(veritabani_adresi: str):

    baglanti = psycopg2.connect(veritabani_adresi)

    baglanti.autocommit = False

    with baglanti.imlec() as cur:

        cur.execute("SET statement_timeout = 0")

        cur.execute("SET idle_in_transaction_session_timeout = 0")

    return baglanti





def fetch_market_id(imlec, market_adi: str) -> int:

    imlec.execute("SELECT market_id FROM market WHERE market_adi = %s ORDER BY market_id LIMIT 1", (market_adi,))

    satir = imlec.fetchone()

    if satir:

        return int(satir["market_id"])



    imlec.execute(

        "INSERT INTO market (market_adi) VALUES (%s) RETURNING market_id",

        (market_adi,),

    )

    return int(imlec.fetchone()["market_id"])





def fetch_existing_products(imlec, market_kimligi: int) -> list[dict[str, Any]]:

    imlec.execute(

        """
        SELECT
            id,
            market_id,
            urun_ad,
            urun_url,
            urun_kategori,
            eklenme_tarihi,
            son_gorulme_tarihi,
            market_adi,
            urun_marka,
            sira_no,
            site_product_code,
            url_key
        FROM urunler
        WHERE market_id = %s
        """,

        (market_kimligi,),

    )

    return list(imlec.fetchall())





def build_existing_maps(satirlar: list[dict[str, Any]]) -> dict[str, dict[str, int]]:

    maps = {

        "site_product_code": {},

        "url_key": {},

        "urun_url": {},

        "legacy_signature": {},

    }

    for satir in satirlar:

        urun_kimligi = int(satir["id"])

        site_urun_kodu = clean_text(satir.get("site_product_code"))

        adres_anahtari = clean_text(satir.get("url_key"))

        urun_url = clean_text(satir.get("urun_url"))

        legacy_signature = build_legacy_signature(

            satir.get("urun_ad"),

            satir.get("urun_marka"),

            satir.get("urun_kategori"),

        )

        if site_urun_kodu:

            maps["site_product_code"][site_urun_kodu] = urun_kimligi

        if adres_anahtari:

            maps["url_key"][adres_anahtari] = urun_kimligi

        if urun_url:

            maps["urun_url"][urun_url] = urun_kimligi

        if legacy_signature:

            maps["legacy_signature"][legacy_signature] = urun_kimligi

    return maps





def resolve_product_id(

    satir: pd.Series,

    lookup_maps: dict[str, dict[str, int]],

) -> tuple[int | None, str | None, list[str]]:

    adaylar: dict[int, list[str]] = {}

    for field in ["site_product_code", "url_key", "urun_url", "legacy_signature"]:

        value = clean_text(satir.get(field))

        if not value:

            continue

        urun_kimligi = lookup_maps[field].get(value)

        if urun_kimligi is not None:

            adaylar.setdefault(urun_kimligi, []).append(field)



    if not adaylar:

        return None, None, []



    if len(adaylar) > 1:

        conflict_fields = [f"{product_id}:{','.join(fields)}" for urun_kimligi, fields in sorted(adaylar.items())]

        return None, None, conflict_fields



    urun_kimligi, matched_fields = next(iter(adaylar.items()))

    return urun_kimligi, matched_fields[0], []





def find_existing_product_id(imlec, market_kimligi: int, satir: pd.Series) -> int | None:

    lookup_specs = [

        ("site_product_code", "site_product_code"),

        ("url_key", "url_key"),

        ("urun_url", "urun_url"),

    ]

    for field_name, column_name in lookup_specs:

        value = clean_text(satir.get(field_name))

        if not value:

            continue

        imlec.execute(

            f"""
            SELECT id
            FROM urunler
            WHERE market_id = %s AND {column_name} = %s
            ORDER BY id
            LIMIT 1
            """,

            (market_kimligi, value),

        )

        existing = imlec.fetchone()

        if existing:

            return int(existing["id"])

    return None





def _int_or_none(value: Any) -> int | None:

    if value is None:

        return None

    try:

        if bool(pd.isna(value)):

            return None

    except Exception:

        pass

    return int(value)





def _latest_seen_at(satir: pd.Series) -> datetime | None:

    for field_name in ["kazima_tarihi", "son_gorulme_tarihi", "eklenme_tarihi"]:

        value = satir.get(field_name)

        if pd.notna(value):

            return value.to_pydatetime()

    return None





def parse_timestamp_bound(value: str | None, *, end_of_day: bool = False) -> datetime | None:

    if value is None:

        return None



    raw_text = str(value).strip()

    if not raw_text:

        return None



    iso_date_match = re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", raw_text)

    dotted_date_match = re.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-]\d{4}", raw_text)

    if iso_date_match:

        ayristirilmis = pd.Timestamp(raw_text)

    elif dotted_date_match:

        ayristirilmis = pd.to_datetime(raw_text, errors="coerce", dayfirst=True)

    else:

        ayristirilmis = pd.to_datetime(raw_text, errors="coerce")

    if pd.isna(ayristirilmis):

        raise ValueError(f"Geçersiz tarih değeri: {value!r}")



    is_date_only = bool(iso_date_match or dotted_date_match)

    if end_of_day and is_date_only:

        ayristirilmis = ayristirilmis.normalize() + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)



    if ayristirilmis.tzinfo is None:

        ayristirilmis = ayristirilmis.tz_localize(TIMEZONE)



    return ayristirilmis.tz_convert(timezone.utc).to_pydatetime()





def filter_rows_by_timestamp_window(

    df: pd.DataFrame,

    timestamp_column: str,

    start_bound: datetime | None,

    end_bound: datetime | None,

) -> pd.DataFrame:

    if df.empty or (start_bound is None and end_bound is None):

        return df



    timestamps = pd.to_datetime(df[timestamp_column], errors="coerce", utc=True)

    mask = timestamps.notna()

    if start_bound is not None:

        start_ts = pd.Timestamp(start_bound)

        if start_ts.tzinfo is None:

            start_ts = start_ts.tz_localize("UTC")

        else:

            start_ts = start_ts.tz_convert("UTC")

        mask &= timestamps >= start_ts

    if end_bound is not None:

        end_ts = pd.Timestamp(end_bound)

        if end_ts.tzinfo is None:

            end_ts = end_ts.tz_localize("UTC")

        else:

            end_ts = end_ts.tz_convert("UTC")

        mask &= timestamps <= end_ts

    return df.loc[mask].reset_index(drop=True)





def _update_existing_product(

    imlec,

    satir: pd.Series,

    urun_kimligi: int,

    sira_no: int | None,

) -> None:

    latest_seen_at = _latest_seen_at(satir)

    son_gorulme_tarihi = latest_seen_at

    imlec.execute(

        """
        UPDATE urunler
        SET
            urun_ad = %s,
            urun_url = %s,
            urun_kategori = %s,
            eklenme_tarihi = COALESCE(GREATEST(eklenme_tarihi, %s), eklenme_tarihi, %s),
            son_gorulme_tarihi = COALESCE(GREATEST(son_gorulme_tarihi, %s), son_gorulme_tarihi, %s),
            market_adi = %s,
            urun_marka = %s,
            sira_no = %s,
            site_product_code = COALESCE(site_product_code, %s),
            url_key = COALESCE(url_key, %s)
        WHERE id = %s
        """,

        (

            satir["urun_ad"],

            satir["urun_url"],

            satir["urun_kategori"],

            latest_seen_at,

            latest_seen_at,

            son_gorulme_tarihi,

            son_gorulme_tarihi,

            satir["market_adi"],

            satir["urun_marka"],

            sira_no,

            satir["site_product_code"],

            satir["url_key"],

            urun_kimligi,

        ),

    )





def ensure_transaction(imlec) -> None:

    connection = getattr(imlec, "connection", None)

    if connection is not None and getattr(connection, "status", None) == STATUS_READY:

        imlec.execute("BEGIN")





def upsert_product(

    imlec,

    satir: pd.Series,

    market_kimligi: int,

    urun_kimligi: int | None,

) -> tuple[int, bool]:

    sira_no = _int_or_none(satir.get("sira_no"))

    latest_seen_at = _latest_seen_at(satir)

    son_gorulme_tarihi = latest_seen_at

    if urun_kimligi is None:

        imlec.execute(

            """
            INSERT INTO urunler (
                market_id,
                urun_ad,
                urun_url,
                urun_kategori,
                eklenme_tarihi,
                son_gorulme_tarihi,
                market_adi,
                urun_marka,
                sira_no,
                site_product_code,
                url_key
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,

            (

                market_kimligi,

                satir["urun_ad"],

                satir["urun_url"],

                satir["urun_kategori"],

                latest_seen_at,

                son_gorulme_tarihi,

                satir["market_adi"],

                satir["urun_marka"],

                sira_no,

                satir["site_product_code"],

                satir["url_key"],

            ),

        )

        inserted_row = imlec.fetchone()

        if inserted_row:

            return int(inserted_row["id"]), True



        urun_kimligi = find_existing_product_id(imlec, market_kimligi, satir)

        if urun_kimligi is None:

            raise RuntimeError(f"Mevcut urun bulunamadi: {row.get('urun_ad')}")



    _update_existing_product(imlec, satir, urun_kimligi, sira_no)

    return urun_kimligi, False





def upsert_price_snapshot(imlec, urun_kimligi: int, satir: pd.Series) -> bool:

    if pd.isna(satir["kazima_tarihi"]):

        raise ValueError(f"kazima_tarihi eksik: {row.get('urun_ad')}")



    timestamp = satir["kazima_tarihi"].to_pydatetime()

    imlec.execute(

        """
        SELECT kayit_id
        FROM fiyat_zaman_serisi
        WHERE urun_id = %s AND kazima_tarihi = %s
        """,

        (urun_kimligi, timestamp),

    )

    existing = imlec.fetchone()



    if existing:

        imlec.execute(

            """
            UPDATE fiyat_zaman_serisi
            SET
                urun_fiyat = %s,
                gramaj_degeri = %s,
                gramaj_birimi = %s,
                birim_fiyat = %s,
                adet_sayisi = %s
            WHERE kayit_id = %s
            """,

            (

                satir["urun_fiyat"],

                satir["gramaj_degeri"],

                satir["gramaj_birimi"],

                satir["birim_fiyat"],

                satir["adet_sayisi"],

                existing["kayit_id"],

            ),

        )

        return False



    imlec.execute(

        """
        INSERT INTO fiyat_zaman_serisi (
            urun_id,
            urun_fiyat,
            gramaj_degeri,
            gramaj_birimi,
            birim_fiyat,
            kazima_tarihi,
            adet_sayisi
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (urun_id, kazima_tarihi) DO NOTHING
        RETURNING kayit_id
        """,

        (

            urun_kimligi,

            satir["urun_fiyat"],

            satir["gramaj_degeri"],

            satir["gramaj_birimi"],

            satir["birim_fiyat"],

            timestamp,

            satir["adet_sayisi"],

        ),

    )

    inserted_row = imlec.fetchone()

    if inserted_row:

        return True



    imlec.execute(

        """
        SELECT kayit_id
        FROM fiyat_zaman_serisi
        WHERE urun_id = %s AND kazima_tarihi = %s
        """,

        (urun_kimligi, timestamp),

    )

    existing = imlec.fetchone()

    if not existing:

        raise RuntimeError(f"Mevcut fiyat kaydi bulunamadi: urun_id={product_id} kazima_tarihi={timestamp.isoformat()}")



    imlec.execute(

        """
        UPDATE fiyat_zaman_serisi
        SET
            urun_fiyat = %s,
            gramaj_degeri = %s,
            gramaj_birimi = %s,
            birim_fiyat = %s,
            adet_sayisi = %s
        WHERE kayit_id = %s
        """,

        (

            satir["urun_fiyat"],

            satir["gramaj_degeri"],

            satir["gramaj_birimi"],

            satir["birim_fiyat"],

            satir["adet_sayisi"],

            existing["kayit_id"],

        ),

    )

    return False





def fetch_history_before_current(imlec, guncel_calisma_df: pd.DataFrame) -> pd.DataFrame:

    if guncel_calisma_df.empty:

        return pd.DataFrame(columns=["urun_id", "urun_ad"])



    latest_by_product: dict[int, datetime] = {}

    for satir in guncel_calisma_df.to_dict("records"):

        urun_id = satir.get("urun_id")

        if urun_id is None:

            continue

        parsed_timestamp = pd.to_datetime(satir.get("kazima_tarihi"), errors="coerce", utc=True)

        if pd.isna(parsed_timestamp):

            continue

        urun_id = int(urun_id)

        previous_timestamp = latest_by_product.get(urun_id)

        as_python = parsed_timestamp.to_pydatetime()

        if previous_timestamp is None or as_python > previous_timestamp:

            latest_by_product[urun_id] = as_python



    if not latest_by_product:

        return pd.DataFrame(columns=["urun_id", "urun_ad"])



    history_rows = execute_values(

        imlec,

        """
        WITH current_run_lookup (urun_id, kazima_tarihi) AS (
            VALUES %s
        )
        SELECT
            f.urun_id,
            u.urun_ad,
            f.urun_fiyat,
            f.gramaj_degeri,
            f.gramaj_birimi,
            f.birim_fiyat,
            f.nameet_sayisi,
            f.kazima_tarihi
        FROM fiyat_zaman_serisi AS f
        JOIN current_run_lookup AS c
          ON c.urun_id = f.urun_id
        JOIN urunler AS u
          ON u.id = f.urun_id
        WHERE f.kazima_tarihi < c.kazima_tarihi
        ORDER BY f.urun_id, f.kazima_tarihi
        """,

        [(urun_id, kazima_tarihi) for urun_id, kazima_tarihi in latest_by_product.items()],

        template="(%s::bigint, %s::timestamptz)",

        page_size=500,

        fetch=True,

    )

    return pd.DataFrame(history_rows)





def _format_numeric_text(value: float | None) -> str | None:

    if value is None:

        return None

    rounded = round(float(value), 4)

    if float(rounded).is_integer():

        return str(int(rounded))

    return f"{rounded:.4f}".rstrip("0").rstrip(".")





def build_price_snapshot(satir: dict[str, Any], urun_ad: str) -> FiyatKaydi | None:

    parsed_timestamp = pd.to_datetime(satir.get("kazima_tarihi"), errors="coerce", utc=True)

    if pd.isna(parsed_timestamp):

        return None



    normalize_olcu, normalize_birim, normalize_birim_fiyat = canonicalize_measure(

        urun_adi=urun_ad,

        fiyat=satir.get("urun_fiyat"),

        gramaj_degeri=satir.get("gramaj_degeri"),

        gramaj_birimi=satir.get("gramaj_birimi"),

        birim_fiyat=satir.get("birim_fiyat"),

    )

    fiyat = _parse_optional_float(satir.get("urun_fiyat"))

    urun_id = satir.get("urun_id")

    if fiyat is None or urun_id is None:

        return None



    return FiyatKaydi(

        urun_id=int(urun_id),

        urun_ad=urun_ad,

        kazima_tarihi=parsed_timestamp.to_pydatetime(),

        urun_fiyat=fiyat,

        gramaj_degeri=normalize_olcu,

        gramaj_birimi=normalize_birim,

        birim_fiyat=normalize_birim_fiyat,

    )





def build_price_change_row(

    bulgu,

    *,

    detection_time_column: str,

    change_ratio_column: str,

) -> dict[str, Any]:

    return {

        "ilgili_urun_id": bulgu.urun_id,

        "urun_ad": bulgu.urun_ad,

        "eski_degeri": _format_numeric_text(bulgu.onceki_fiyat),

        "yeni_degeri": _format_numeric_text(bulgu.yeni_fiyat),

        detection_time_column: bulgu.yeni_kayit_tarihi,

        "onceki_fiyat": bulgu.onceki_fiyat,

        "yeni_fiyat_detay": bulgu.yeni_fiyat,

        "onceki_gramaj_degeri": bulgu.onceki_gramaj_degeri,

        "yeni_gramaj_degeri_detay": bulgu.yeni_gramaj_degeri,

        "gramaj_birimi": bulgu.gramaj_birimi,

        "onceki_birim_fiyat": bulgu.onceki_birim_fiyat,

        "yeni_birim_fiyat_detay": bulgu.yeni_birim_fiyat,

        "gramaj_degisim_pct": bulgu.gramaj_degisim_pct,

        "fiyat_degisim_pct": bulgu.fiyat_degisim_pct,

        "birim_fiyat_degisim_pct": bulgu.birim_fiyat_degisim_pct,

        change_ratio_column: bulgu.change_ratio_pct,

        "severity": bulgu.severity,

        "reason": bulgu.reason,

        "onceki_kayit_tarihi": bulgu.onceki_kayit_tarihi,

        "yeni_kayit_tarihi": bulgu.yeni_kayit_tarihi,

    }





def _maybe_python_datetime(value: Any) -> Any:

    if isinstance(value, pd.Timestamp):

        return value.to_pydatetime()

    return value





def _build_empty_price_change_frames() -> tuple[pd.DataFrame, pd.DataFrame]:

    return (

        pd.DataFrame(columns=ZAMLI_URUN_COLUMNS),

        pd.DataFrame(columns=INDIRIMLI_URUN_COLUMNS),

    )





def run_price_change_detection_from_history(

    guncel_calisma_df: pd.DataFrame,

    history_df: pd.DataFrame,

    thresholds: FiyatDegisimEsikleri | None = None,

) -> tuple[pd.DataFrame, pd.DataFrame]:

    if guncel_calisma_df.empty or history_df.empty:

        return _build_empty_price_change_frames()



    thresholds = thresholds or FiyatDegisimEsikleri()

    history_by_product: dict[int, dict[str, Any]] = {}

    for satir in history_df.to_dict("records"):

        urun_id = satir.get("urun_id")

        if urun_id is None:

            continue

        history_by_product[int(urun_id)] = satir



    zamli_rows: list[dict[str, Any]] = []

    indirimli_rows: list[dict[str, Any]] = []

    for guncel_satir in guncel_calisma_df.to_dict("records"):

        urun_id = guncel_satir.get("urun_id")

        if urun_id is None:

            continue

        previous_row = history_by_product.get(int(urun_id))

        if previous_row is None:

            continue



        previous_name = clean_text(previous_row.get("urun_ad")) or clean_text(guncel_satir.get("urun_ad")) or ""

        current_name = clean_text(guncel_satir.get("urun_ad")) or previous_name

        onceki_kayit = build_price_snapshot(previous_row, previous_name)

        guncel_kayit = build_price_snapshot(guncel_satir, current_name)

        if onceki_kayit is None or guncel_kayit is None:

            continue



        artis_bulgusu = detect_price_increase(onceki_kayit, guncel_kayit, thresholds)

        if artis_bulgusu is not None:

            zamli_rows.append(

                build_price_change_row(

                    artis_bulgusu,

                    detection_time_column="zam_tespit_tarihi",

                    change_ratio_column="zam_orani_pct",

                )

            )



        dusus_bulgusu = detect_price_decrease(onceki_kayit, guncel_kayit, thresholds)

        if dusus_bulgusu is not None:

            indirimli_rows.append(

                build_price_change_row(

                    dusus_bulgusu,

                    detection_time_column="indirim_tespit_tarihi",

                    change_ratio_column="indirim_orani_pct",

                )

            )



    zamli_df = pd.DataFrame(zamli_rows, columns=ZAMLI_URUN_COLUMNS)

    if not zamli_df.empty:

        zamli_df = zamli_df.sort_values("zam_orani_pct", ascending=False).reset_index(drop=True)



    indirimli_df = pd.DataFrame(indirimli_rows, columns=INDIRIMLI_URUN_COLUMNS)

    if not indirimli_df.empty:

        indirimli_df = indirimli_df.sort_values("indirim_orani_pct", ascending=False).reset_index(drop=True)



    return zamli_df, indirimli_df





def ensure_price_change_tables(imlec) -> None:

    if not PRICE_CHANGE_MIGRATION_SQL.exists():

        return

    migration_sql = PRICE_CHANGE_MIGRATION_SQL.read_text(encoding="utf-8").strip()

    if migration_sql:

        imlec.execute(migration_sql)





def ensure_zscore_anomaly_columns(imlec) -> None:

    if not ANOMALY_ZSCORE_MIGRATION_SQL.exists():

        return

    migration_sql = ANOMALY_ZSCORE_MIGRATION_SQL.read_text(encoding="utf-8").strip()

    if migration_sql:

        imlec.execute(migration_sql)





def insert_anomalies(imlec, anomalies_df: pd.DataFrame) -> int:

    if anomalies_df.empty:

        return 0



    required_columns = {"ilgili_urun_id", "eski_degeri", "yeni_degeri", "anomali_tespit_tarihi"}

    missing = required_columns.difference(anomalies_df.columns)

    if missing:

        raise ValueError(f"Anomali çıktısında eksik kolon var: {sorted(missing)}")



    insert_count = 0

    for satir in anomalies_df.to_dict("records"):

        detection_time = satir["anomali_tespit_tarihi"]

        previous_time = satir.get("onceki_kayit_tarihi")

        current_time = satir.get("yeni_kayit_tarihi")

        if isinstance(detection_time, pd.Timestamp):

            detection_time = detection_time.to_pydatetime()

        if isinstance(previous_time, pd.Timestamp):

            previous_time = previous_time.to_pydatetime()

        if isinstance(current_time, pd.Timestamp):

            current_time = current_time.to_pydatetime()



        imlec.execute(

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
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,

            (

                int(satir["ilgili_urun_id"]),

                satir["eski_degeri"],

                satir["yeni_degeri"],

                detection_time,

                satir.get("anomali_turu", "shrinkflation"),

                satir.get("onceki_fiyat"),

                satir.get("yeni_fiyat_detay"),

                satir.get("onceki_gramaj_degeri"),

                satir.get("yeni_gramaj_degeri_detay"),

                satir.get("gramaj_birimi"),

                satir.get("onceki_birim_fiyat"),

                satir.get("yeni_birim_fiyat_detay"),

                satir.get("gramaj_degisim_pct"),

                satir.get("fiyat_degisim_pct"),

                satir.get("birim_fiyat_degisim_pct"),

                satir.get("shrinkflation_orani_pct"),

                satir.get("severity"),

                satir.get("reason"),

                satir.get("z_score"),

                satir.get("history_sample_count"),

                previous_time,

                current_time,

            ),

        )

        insert_count += imlec.rowcount

    return insert_count





def insert_price_increases(imlec, zamli_df: pd.DataFrame) -> int:

    if zamli_df.empty:

        return 0



    insert_count = 0

    for satir in zamli_df.to_dict("records"):

        imlec.execute(

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
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,

            (

                int(satir["ilgili_urun_id"]),

                satir.get("eski_degeri"),

                satir.get("yeni_degeri"),

                _maybe_python_datetime(satir.get("zam_tespit_tarihi")),

                satir.get("onceki_fiyat"),

                satir.get("yeni_fiyat_detay"),

                satir.get("onceki_gramaj_degeri"),

                satir.get("yeni_gramaj_degeri_detay"),

                satir.get("gramaj_birimi"),

                satir.get("onceki_birim_fiyat"),

                satir.get("yeni_birim_fiyat_detay"),

                satir.get("gramaj_degisim_pct"),

                satir.get("fiyat_degisim_pct"),

                satir.get("birim_fiyat_degisim_pct"),

                satir.get("zam_orani_pct"),

                satir.get("severity"),

                satir.get("reason"),

                _maybe_python_datetime(satir.get("onceki_kayit_tarihi")),

                _maybe_python_datetime(satir.get("yeni_kayit_tarihi")),

            ),

        )

        insert_count += imlec.rowcount

    return insert_count





def insert_price_decreases(imlec, indirimli_df: pd.DataFrame) -> int:

    if indirimli_df.empty:

        return 0



    insert_count = 0

    for satir in indirimli_df.to_dict("records"):

        imlec.execute(

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
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,

            (

                int(satir["ilgili_urun_id"]),

                satir.get("eski_degeri"),

                satir.get("yeni_degeri"),

                _maybe_python_datetime(satir.get("indirim_tespit_tarihi")),

                satir.get("onceki_fiyat"),

                satir.get("yeni_fiyat_detay"),

                satir.get("onceki_gramaj_degeri"),

                satir.get("yeni_gramaj_degeri_detay"),

                satir.get("gramaj_birimi"),

                satir.get("onceki_birim_fiyat"),

                satir.get("yeni_birim_fiyat_detay"),

                satir.get("gramaj_degisim_pct"),

                satir.get("fiyat_degisim_pct"),

                satir.get("birim_fiyat_degisim_pct"),

                satir.get("indirim_orani_pct"),

                satir.get("severity"),

                satir.get("reason"),

                _maybe_python_datetime(satir.get("onceki_kayit_tarihi")),

                _maybe_python_datetime(satir.get("yeni_kayit_tarihi")),

            ),

        )

        insert_count += imlec.rowcount

    return insert_count





def run_anomaly_detection_from_history(

    tespit_edici: Callable[[pd.DataFrame, pd.DataFrame], pd.DataFrame] | None,

    guncel_calisma_df: pd.DataFrame,

    history_df: pd.DataFrame,

) -> pd.DataFrame:

    if tespit_edici is None or guncel_calisma_df.empty:

        return pd.DataFrame(columns=ANOMALY_COLUMNS)



    anomalies_df = tespit_edici(guncel_calisma_df.copy(), history_df.copy())

    if anomalies_df is None:

        return pd.DataFrame(columns=ANOMALY_COLUMNS)



    anomalies_df = anomalies_df.copy()

    if anomalies_df.empty:

        return pd.DataFrame(columns=ANOMALY_COLUMNS)



    if "anomali_tespit_tarihi" not in anomalies_df.columns:

        latest_timestamp = pd.to_datetime(guncel_calisma_df["kazima_tarihi"], errors="coerce", utc=True).max()

        anomalies_df["anomali_tespit_tarihi"] = latest_timestamp

    return anomalies_df





def save_sync_audit(

    cikti_dizini: Path,

    context: SyncContext,

    anomalies_df: pd.DataFrame | None = None,

    zamli_df: pd.DataFrame | None = None,

    indirimli_df: pd.DataFrame | None = None,

) -> None:

    cikti_dizini.mkdir(parents=True, exist_ok=True)

    audit_df = pd.DataFrame(context.denetim_satirlari, columns=AUDIT_COLUMNS)

    audit_df.to_csv(cikti_dizini / "db_sync_audit.csv", index=False, encoding="utf-8-sig")



    if anomalies_df is None:

        anomalies_df = pd.DataFrame(columns=ANOMALY_COLUMNS)

    anomalies_df.to_csv(cikti_dizini / "anomalies_detected.csv", index=False, encoding="utf-8-sig")



    if zamli_df is None:

        zamli_df = pd.DataFrame(columns=ZAMLI_URUN_COLUMNS)

    zamli_df.to_csv(cikti_dizini / "zamli_urunler_detected.csv", index=False, encoding="utf-8-sig")



    if indirimli_df is None:

        indirimli_df = pd.DataFrame(columns=INDIRIMLI_URUN_COLUMNS)

    indirimli_df.to_csv(cikti_dizini / "indirimli_urunler_detected.csv", index=False, encoding="utf-8-sig")





def sync_to_database(

    baglanti,

    esitleme_satirlari: pd.DataFrame,

    market_adi: str,

    tespit_edici: Callable[[pd.DataFrame, pd.DataFrame], pd.DataFrame] | None,

    strict_identity: bool,

    denetim_cikti_dizini: Path,

    tespit_baslangici: datetime | None = None,

    tespit_sonu: datetime | None = None,

) -> SyncContext:

    context: SyncContext

    with baglanti.imlec(cursor_factory=RealDictCursor) as imlec:

                                                                                             

        ensure_transaction(imlec)

        ensure_price_change_tables(imlec)

        ensure_zscore_anomaly_columns(imlec)

        market_kimligi = fetch_market_id(imlec, market_adi)

        context = SyncContext(market_kimligi=market_kimligi)



        existing_rows = fetch_existing_products(imlec, market_kimligi)

        lookup_maps = build_existing_maps(existing_rows)



        synced_rows: list[dict[str, Any]] = []

        for kayit in esitleme_satirlari.to_dict("records"):

            satir = pd.Series(kayit)

            urun_kimligi, resolved_by, conflicts = resolve_product_id(satir, lookup_maps)

            audit_row = {

                "market_id": market_kimligi,

                "urun_ad": satir["urun_ad"],

                "urun_url": satir["urun_url"],

                "site_product_code": satir["site_product_code"],

                "url_key": satir["url_key"],

                "legacy_signature": satir["legacy_signature"],

                "resolved_by": resolved_by,

                "resolved_product_id": urun_kimligi,

                "hard_conflict": bool(conflicts),

                "conflict_details": " | ".join(conflicts) if conflicts else None,

            }



            if conflicts:

                context.stats.hard_conflicts += 1

                context.stats.skipped_rows += 1

                context.denetim_satirlari.append(audit_row)

                if strict_identity:

                    raise RuntimeError(

                        f"Ürün kimlik çakışması bulundu: {satir['urun_ad']} -> {audit_row['conflict_details']}"

                    )

                continue



            esitlenen_urun_kimligi, inserted = upsert_product(imlec, satir, market_kimligi, urun_kimligi)

            audit_row["resolved_product_id"] = esitlenen_urun_kimligi

            if inserted:

                context.stats.eklenen_urunler += 1

            else:

                context.stats.guncellenen_urunler += 1



            inserted_price = upsert_price_snapshot(imlec, esitlenen_urun_kimligi, satir)

            if inserted_price:

                context.stats.eklenen_fiyatlar += 1

            else:

                context.stats.updated_prices += 1



            urun_url = clean_text(satir.get("urun_url"))

            site_urun_kodu = clean_text(satir.get("site_product_code"))

            adres_anahtari = clean_text(satir.get("url_key"))

            legacy_signature = clean_text(satir.get("legacy_signature"))

            if urun_url:

                lookup_maps["urun_url"][urun_url] = esitlenen_urun_kimligi

            if site_urun_kodu:

                lookup_maps["site_product_code"][site_urun_kodu] = esitlenen_urun_kimligi

            if adres_anahtari:

                lookup_maps["url_key"][adres_anahtari] = esitlenen_urun_kimligi

            if legacy_signature:

                lookup_maps["legacy_signature"][legacy_signature] = esitlenen_urun_kimligi



            synced_rows.append(

                {

                    **kayit,

                    "market_id": market_kimligi,

                    "urun_id": esitlenen_urun_kimligi,

                }

            )

            context.denetim_satirlari.append(audit_row)



        synced_df = pd.DataFrame(synced_rows)

        history_df = fetch_history_before_current(imlec, synced_df)

        anomalies_df = run_anomaly_detection_from_history(tespit_edici, synced_df, history_df)

        zamli_df, indirimli_df = run_price_change_detection_from_history(synced_df, history_df)

        anomalies_df = filter_rows_by_timestamp_window(anomalies_df, "anomali_tespit_tarihi", tespit_baslangici, tespit_sonu)

        zamli_df = filter_rows_by_timestamp_window(zamli_df, "zam_tespit_tarihi", tespit_baslangici, tespit_sonu)

        indirimli_df = filter_rows_by_timestamp_window(indirimli_df, "indirim_tespit_tarihi", tespit_baslangici, tespit_sonu)

        context.stats.inserted_anomalies = insert_anomalies(imlec, anomalies_df)

        context.stats.inserted_price_increases = insert_price_increases(imlec, zamli_df)

        context.stats.inserted_price_decreases = insert_price_decreases(imlec, indirimli_df)

        baglanti.commit()

        save_sync_audit(denetim_cikti_dizini, context, anomalies_df, zamli_df, indirimli_df)

    return context





def run_scrape(

    cikti_koku: Path,

    reference_csv_path: Path,

    limit: int | None,

    kazima_zaman_damgasi: datetime | None = None,

) -> tuple[Path, pd.DataFrame]:

    if run_pipeline is None:

        raise RuntimeError("sok_scraper.py bulunamadı. Scrape çalıştırmak için modülü repo köküne ekle.")



    effective_timestamp = kazima_zaman_damgasi.astimezone(TIMEZONE) if kazima_zaman_damgasi is not None else datetime.now(TIMEZONE)

    run_id = effective_timestamp.replace(microsecond=0).strftime("%Y%m%d_%H%M%S")

    cikti_dizini = cikti_koku / f"sok_sync_{run_id}"

    ciktilar = run_pipeline(

        reference_csv_path=reference_csv_path,

        cikti_dizini=cikti_dizini,

        categories=KATEGORI_HEDEFLERI,

        urun_siniri=limit,

        kazima_zaman_damgasi=kazima_zaman_damgasi,

    )

    return cikti_dizini, ciktilar["raw_products"]





def build_cli_parser() -> argparse.ArgumentParser:

    komut_ayristirici = argparse.ArgumentParser(description="ŞOK haftalık scrape + Supabase senkronizasyonu")

    komut_ayristirici.add_argument("--reference-csv", type=Path, default=DEFAULT_REFERENCE_CSV)

    komut_ayristirici.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)

    komut_ayristirici.add_argument("--existing-output-dir", type=Path, default=None)

    komut_ayristirici.add_argument("--database-url", default=None, help="Opsiyonel Postgres bağlantı cümlesi")

    komut_ayristirici.add_argument("--database-url-env", default=VARSAYILAN_VERITABANI_ADRES_ENV)

    komut_ayristirici.add_argument("--anomaly-detector", default=None, help="module:function veya /path/to/file.py")

    komut_ayristirici.add_argument("--strict-identity", action="store_true", help="Kimlik çakışmasında işlemi durdur")

    komut_ayristirici.add_argument("--dry-run", action="store_true", help="DB yazmadan sadece normalize et ve audit üret")

    komut_ayristirici.add_argument("--limit", type=int, default=None)

    komut_ayristirici.add_argument(

        "--scrape-datetime",

        type=parse_scrape_datetime_input,

        default=None,

        help="Çekimi bu tarih/saatle etiketle. Örnek: 2026-05-09 veya 2026-05-09T19:00:00+03:00",

    )

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





def main() -> None:

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    load_dotenv(BASE_DIR / ".env")

    komut_ayristirici = build_cli_parser()

    args = komut_ayristirici.argumanlari_ayristir()



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



    if args.existing_output_dir and args.scrape_datetime is not None:

        komut_ayristirici.error("--scrape-datetime yalnızca yeni scrape sırasında kullanılabilir.")



    if args.existing_output_dir:

        cikti_dizini = args.existing_output_dir

        raw_df = load_raw_products_from_outputs(cikti_dizini)

    else:

        cikti_dizini, raw_df = run_scrape(

            cikti_koku=args.cikti_koku,

            reference_csv_path=args.reference_csv,

            limit=args.limit,

            kazima_zaman_damgasi=args.scrape_datetime,

        )



    esitleme_satirlari = prepare_sync_rows(raw_df)

    cikti_dizini.mkdir(parents=True, exist_ok=True)

    esitleme_satirlari.to_csv(cikti_dizini / "db_sync_input.csv", index=False, encoding="utf-8-sig")



    if args.dry_run:

        dry_context = SyncContext(market_kimligi=1)

        save_sync_audit(

            cikti_dizini,

            dry_context,

            pd.DataFrame(columns=ANOMALY_COLUMNS),

            pd.DataFrame(columns=ZAMLI_URUN_COLUMNS),

            pd.DataFrame(columns=INDIRIMLI_URUN_COLUMNS),

        )

        print(f"Dry run tamamlandı. Hazır satır sayısı: {len(esitleme_satirlari)}")

        print(f"Girdi dosyası: {cikti_dizini / 'db_sync_input.csv'}")

        print(f"Önerilen cron: {DEFAULT_SCHEDULE_CRON}")

        return



    veritabani_adresi = load_database_url(args.veritabani_adresi, args.database_url_env)

    baglanti = connect_db(veritabani_adresi)

    try:

        context = sync_to_database(

            baglanti=baglanti,

            esitleme_satirlari=esitleme_satirlari,

            market_adi=VARSAYILAN_MARKET_ADI,

            tespit_edici=tespit_edici,

            strict_identity=args.strict_identity,

            denetim_cikti_dizini=cikti_dizini,

            tespit_baslangici=tespit_baslangici,

            tespit_sonu=tespit_sonu,

        )

    finally:

        baglanti.close()



    print("\nSenkronizasyon tamamlandı:")

    print(f"- market_id: {context.market_id}")

    print(f"- yeni ürün: {context.stats.inserted_products}")

    print(f"- güncellenen ürün: {context.stats.updated_products}")

    print(f"- yeni fiyat kaydı: {context.stats.inserted_prices}")

    print(f"- güncellenen fiyat kaydı: {context.stats.updated_prices}")

    print(f"- eklenen anomali: {context.stats.inserted_anomalies}")

    print(f"- eklenen zamlı ürün kaydı: {context.stats.inserted_price_increases}")

    print(f"- eklenen indirimli ürün kaydı: {context.stats.inserted_price_decreases}")

    print(f"- hard conflict: {context.stats.hard_conflicts}")

    print(f"- atlanan satır: {context.stats.skipped_rows}")

    print(f"- audit dosyası: {cikti_dizini / 'db_sync_audit.csv'}")

    print(f"- önerilen cron: {DEFAULT_SCHEDULE_CRON}")





if __name__ == "__main__":

    main()
