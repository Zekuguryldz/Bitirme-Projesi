from __future__ import annotations



import argparse

import importlib

import random

import re

import time

import unicodedata

from dataclasses import dataclass

from datetime import datetime

from pathlib import Path

from typing import Any

from urllib.parse import urljoin, urlparse

from zoneinfo import ZoneInfo



import pandas as pd

from bs4 import BeautifulSoup

from tqdm.auto import tqdm



try:

    _playwright_sync_api = importlib.import_module("playwright.sync_api")

except ModuleNotFoundError as exc:                                         

    sync_playwright = None

    _PLAYWRIGHT_IMPORT_ERROR = exc

else:

    sync_playwright = _playwright_sync_api.sync_playwright

    _PLAYWRIGHT_IMPORT_ERROR = None



BASE_DIR = Path(__file__).resolve().parent

BASE_URL = "https://www.migros.com.tr"

TIMEZONE = ZoneInfo("Europe/Istanbul")

DEFAULT_EXISTING_OUTPUTS_DIR = BASE_DIR / "outputs"

DEFAULT_OUTPUT_DIR = BASE_DIR / "migros_outputs"

DEFAULT_SNAPSHOT_DIR = BASE_DIR / "migros_debug_snapshots"

DEFAULT_HEADERS = {

    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",

    "User-Agent": (

        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "

        "AppleWebKit/537.36 (KHTML, like Gecko) "

        "Chrome/135.0.0.0 Safari/537.36"

    ),

}

ALWAYS_EXCLUDED_BRANDS = {"Reyondan"}

HOUSEHOLD_CATEGORY_NAMES = {"Deterjan ve Temizlik", "Kağıt ve Islak Mendil"}

NON_PACKAGED_HOUSEHOLD_SUBCATEGORY_PATTERNS = (

    "banyo set ve aksesuarlari",

    "temizlik seti",

    "temizlik fircasi",

    "mop paspas ve yedekleri",

    "plastik kovalar",

    "elbise askisi",

    "yapiskanli aski",

    "utu masasi",

    "utu masasi kilifi ve askisi",

    "camasir kurutmalik",

    "camasir ve kirli sepeti",

    "cam silecegi",

    "camasir ipi",

    "mandal",

)

NON_PACKAGED_HOUSEHOLD_NAME_PATTERNS = (

    "mop",

    "paspas",

    "firca",

    "faras",

    "supurge",

    "klozet fircasi",

    "cop kutusu",

    "kova",

    "aski",

    "kurutmalik",

    "utu masasi",

    "sepet",

    "silecek",

)



COUNT_PATTERN = re.compile(

    r"(\d+)\s*(?:['’`-]?\s*)?(adet|ad\.?|li|lı|lu|lü|pk|paket|rulo|tablet|yaprak)",

    re.IGNORECASE,

)

MULTIPLY_PATTERN = re.compile(

    r"(?P<count>\d+)\s*(?:x|\*)\s*(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|gr|gram|g|mg|ml|cl|lt|l)",

    re.IGNORECASE,

)

AMOUNT_PATTERN = re.compile(

    r"(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|gr|gram|g|mg|ml|cl|lt|l)",

    re.IGNORECASE,

)

UNIT_PRICE_PATTERN = re.compile(

    r"\(?\s*(\d{1,3}(?:\.\d{3})*,\d{2})\s*TL\s*/\s*([A-Za-zÇĞİÖŞÜçğıöşü]+)\s*\)?"

)

UNIT_ALIASES = {

    "gr": "g",

    "gram": "g",

    "g": "g",

    "kg": "kg",

    "mg": "mg",

    "ml": "ml",

    "cl": "cl",

    "lt": "l",

    "l": "l",

    "adet": "adet",

}

REQUIRED_RAW_COLUMNS = (

    "site_main_category",

    "product_name",

    "product_url",

    "scrape_timestamp",

    "brand",

    "site_product_code",

    "url_key",

    "current_price",

    "package_total_value",

    "package_unit",

    "unit_price_numeric",

    "item_count",

)





@dataclass(frozen=True)

class KategoriHedefi:

    display_name: str

    reference_name: str

    adres: str

    expected_count: int | None = None





KATEGORI_HEDEFLERI: list[KategoriHedefi] = [

    KategoriHedefi(

        display_name="Atıştırmalık",

        reference_name="Atistirmaliklar",

        adres="https://www.migros.com.tr/atistirmalik-c-113fb",

        expected_count=1888,

    ),

    KategoriHedefi(

        display_name="Temel Gıda",

        reference_name="Temel Gida",

        adres="https://www.migros.com.tr/temel-gida-c-5",

        expected_count=1398,

    ),

    KategoriHedefi(

        display_name="Et, Tavuk ve Balık",

        reference_name="Et Tavuk Balik",

        adres="https://www.migros.com.tr/et-tavuk-balik-c-3",

        expected_count=534,

    ),

    KategoriHedefi(

        display_name="Süt ve Kahvaltılık",

        reference_name="Sut Kahvaltilik",

        adres="https://www.migros.com.tr/sut-kahvaltilik-c-4",

        expected_count=1317,

    ),

    KategoriHedefi(

        display_name="İçecek",

        reference_name="Icecekler",

        adres="https://www.migros.com.tr/icecek-c-6",

        expected_count=1246,

    ),

    KategoriHedefi(

        display_name="Meze, Hazır Yemek, Donuk",

        reference_name="Donmus Urunler",

        adres="https://www.migros.com.tr/meze-hazir-yemek-donuk-c-7d",

        expected_count=460,

    ),

    KategoriHedefi(

        display_name="Dondurma",

        reference_name="Dondurma",

        adres="https://www.migros.com.tr/dondurma-c-41b",

        expected_count=205,

    ),

    KategoriHedefi(

        display_name="Deterjan ve Temizlik",

        reference_name="Temizlik",

        adres="https://www.migros.com.tr/deterjan-temizlik-c-7",

        expected_count=1073,

    ),

    KategoriHedefi(

        display_name="Kağıt ve Islak Mendil",

        reference_name="Kagit Urunleri",

        adres="https://www.migros.com.tr/kagit-islak-mendil-c-8d",

        expected_count=133,

    ),

]





def clean_text(value: Any) -> str | None:

    if value is None:

        return None

    try:

        if bool(pd.isna(value)):

            return None

    except Exception:

        pass

    text = str(value).replace("\xa0", " ")

    text = re.sub(r"\s+", " ", text).strip()

    return text or None





def normalize_for_match(value: Any) -> str:

    text = clean_text(value) or ""

    text = unicodedata.normalize("NFKD", text)

    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    text = text.lower().replace("ı", "i")

    text = re.sub(r"[^a-z0-9]+", " ", text)

    return re.sub(r"\s+", " ", text).strip()





def cents_to_float(value: Any) -> float | None:

    if value is None:

        return None

    try:

        return round(float(value) / 100.0, 2)

    except (TypeError, ValueError):

        return None





def parse_price_text(value: str | None) -> float | None:

    text = clean_text(value)

    if not text:

        return None

    eslesme = re.search(r"\d{1,3}(?:\.\d{3})*,\d{2}", text)

    if eslesme:

        text = eslesme.group(0)

    normalize_edilmis = text.replace(".", "").replace(",", ".")

    try:

        return float(normalize_edilmis)

    except ValueError:

        return None





def parse_unit_price_text(value: str | None) -> tuple[float | None, str | None]:

    text = clean_text(value)

    if not text:

        return None, None

    eslesme = UNIT_PRICE_PATTERN.search(text)

    if not eslesme:

        return None, None

    fiyat = parse_price_text(eslesme.group(1))

    basis = normalize_for_match(eslesme.group(2))

    basis_map = {

        "adet": "adet",

        "kg": "kg",

        "g": "g",

        "gr": "g",

        "l": "l",

        "lt": "l",

        "ml": "ml",

    }

    return fiyat, basis_map.get(basis, basis)





def parse_measurements(

    urun_adi: str | None,

    net_miktar_degeri: str | None = None,

    birim_fiyat_tabani: str | None = None,

) -> dict[str, Any]:

    sonuc: dict[str, Any] = {

        "package_value_text": None,

        "package_total_value": None,

        "package_unit": None,

        "item_count": None,

    }

    text = clean_text(urun_adi) or ""

    text_lower = text.lower().replace("×", "x")



    multiply_match = MULTIPLY_PATTERN.search(text_lower)

    if multiply_match:

        count = int(multiply_match.group("count"))

        miktar = float(multiply_match.group("amount").replace(",", "."))

        birim = UNIT_ALIASES[multiply_match.group("unit").lower()]

        sonuc["package_value_text"] = clean_text(multiply_match.group(0))

        sonuc["package_total_value"] = round(count * miktar, 4)

        sonuc["package_unit"] = birim

        sonuc["item_count"] = count

        return sonuc



    amount_match = AMOUNT_PATTERN.search(text_lower)

    if amount_match:

        miktar = float(amount_match.group("amount").replace(",", "."))

        birim = UNIT_ALIASES[amount_match.group("unit").lower()]

        sonuc["package_value_text"] = clean_text(amount_match.group(0))

        sonuc["package_total_value"] = round(miktar, 4)

        sonuc["package_unit"] = birim



    count_match = COUNT_PATTERN.search(text_lower)

    if count_match:

        sonuc["item_count"] = int(count_match.group(1))



    if net_miktar_degeri and sonuc["package_total_value"] is None:

        try:

            numeric_value = float(str(net_miktar_degeri).replace(",", "."))

        except ValueError:

            numeric_value = None

        if numeric_value is not None:

            inferred_unit = None

            if sonuc["package_unit"]:

                inferred_unit = sonuc["package_unit"]

            elif birim_fiyat_tabani in {"kg", "g"}:

                inferred_unit = "g" if numeric_value >= 1 else "kg"

            elif birim_fiyat_tabani in {"l", "ml"}:

                inferred_unit = "ml" if numeric_value >= 1 else "l"



            sonuc["package_total_value"] = round(numeric_value, 4)

            sonuc["package_unit"] = inferred_unit

            if inferred_unit:

                sonuc["package_value_text"] = f"{numeric_value:g} {inferred_unit}"



    if sonuc["item_count"] is None and sonuc["package_total_value"] is not None:

        sonuc["item_count"] = 1



    return sonuc





def clean_html_to_text(html: str | None) -> str | None:

    if not html:

        return None

    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)

    return clean_text(text)





def build_category_rest_url(kategori_adresi: str, sayfa: int = 1) -> str:

    slug = urlparse(kategori_adresi).path.lstrip("/")

    if sayfa <= 1:

        return f"{BASE_URL}/rest/search/screens/{slug}"

    return f"{BASE_URL}/rest/search/screens/{slug}?sayfa={page}"





def build_category_page_url(kategori_adresi: str, sayfa: int = 1) -> str:

    if sayfa <= 1:

        return kategori_adresi

    separator = "&" if "?" in kategori_adresi else "?"

    return f"{category_url}{separator}sayfa={page}"





def build_product_rest_url(site_urun_kodu: str) -> str:

    return f"{BASE_URL}/rest/products/screens/{site_urun_kodu}?reid={int(time.time() * 1000)}"





def slugify_filename(value: str | None, fallback: str = "snapshot") -> str:

    cleaned = normalize_for_match(value)

    if not cleaned:

        return fallback

    slug = re.sub(r"[^a-z0-9]+", "_", cleaned).strip("_")

    return slug[:100] or fallback





def flatten_property_infos(property_infos_map: dict[str, list[dict[str, Any]]] | None) -> list[dict[str, Any]]:

    satirlar: list[dict[str, Any]] = []

    if not property_infos_map:

        return satirlar

    for group_name, items in property_infos_map.items():

        for item in items or []:

            satir = dict(item)

            satir["group_name"] = group_name

            satirlar.append(satir)

    return satirlar





def get_property_value(

    properties: list[dict[str, Any]],

    *,

    custom_id: str | None = None,

    ad: str | None = None,

) -> str | None:

    for satir in properties:

        if custom_id and satir.get("customId") == custom_id:

            return clean_text(satir.get("value"))

        if ad and clean_text(satir.get("name")) == ad:

            return clean_text(satir.get("value"))

    return None





def load_existing_table(mevcut_cikti_dizini: str | Path | None, filename: str) -> pd.DataFrame:

    if not mevcut_cikti_dizini:

        return pd.DataFrame()

    yol = Path(mevcut_cikti_dizini) / filename

    if not yol.exists():

        return pd.DataFrame()

    return pd.read_csv(yol)





def resolve_market_id(existing_market_df: pd.DataFrame) -> int:

    if not existing_market_df.empty and "market_adi" in existing_market_df.columns:

        existing_match = existing_market_df[

            existing_market_df["market_adi"].astype(str).str.lower() == "migros"

        ]

        if not existing_match.empty:

            return int(existing_match.iloc[0]["market_id"])

        return int(existing_market_df["market_id"].max()) + 1

    return 2





def resolve_start_id(existing_df: pd.DataFrame, column: str, default_value: int) -> int:

    if existing_df.empty or column not in existing_df.columns:

        return default_value

    return int(existing_df[column].max()) + 1





def ensure_raw_columns(raw_df: pd.DataFrame) -> pd.DataFrame:

    normalize_edilmis = raw_df.copy()

    for column in REQUIRED_RAW_COLUMNS:

        if column not in normalize_edilmis.columns:

            normalize_edilmis[column] = pd.NA

    return normalize_edilmis





def _combine_unique_text(values: pd.Series) -> str | None:

    seen: set[str] = set()

    ordered: list[str] = []

    for value in values:

        text = clean_text(value)

        if not text:

            continue

        for part in text.split("|"):

            cleaned_part = clean_text(part)

            if not cleaned_part or cleaned_part in seen:

                continue

            seen.add(cleaned_part)

            ordered.append(cleaned_part)

    if not ordered:

        return None

    return " | ".join(ordered)





def deduplicate_relisted_products(raw_df: pd.DataFrame) -> pd.DataFrame:

    if raw_df.empty:

        return raw_df.copy()



    deduped = ensure_raw_columns(raw_df)

    for column in [

        "source_categories",

        "source_page_urls",

        "category_page_url",

        "product_description",

        "first_reference_date",

    ]:

        if column not in deduped.columns:

            deduped[column] = pd.NA



    deduped["_name_key"] = deduped["product_name"].map(normalize_for_match)

    deduped["_brand_key"] = deduped["brand"].map(normalize_for_match)

    deduped["_price_key"] = deduped["current_price"].map(clean_text)

    deduped["_measure_key"] = deduped["package_total_value"].map(clean_text)

    deduped["_unit_key"] = deduped["package_unit"].map(normalize_for_match)

    deduped["_unit_price_key"] = deduped["unit_price_numeric"].map(clean_text)

    deduped["_item_count_key"] = deduped["item_count"].map(clean_text)

    deduped["_scrape_ts_key"] = deduped["scrape_timestamp"].map(clean_text)



    deduped = deduped.sort_values(

        [

            "_brand_key",

            "_name_key",

            "_scrape_ts_key",

            "first_reference_date",

            "site_main_category",

            "site_product_code",

            "product_url",

        ],

        na_position="last",

    ).reset_index(drop=True)



    duplicate_subset = [

        "_brand_key",

        "_name_key",

        "_price_key",

        "_measure_key",

        "_unit_key",

        "_unit_price_key",

        "_item_count_key",

        "_scrape_ts_key",

    ]

    eligible_mask = deduped["_name_key"].ne("")

    grouped = deduped.groupby(duplicate_subset, dropna=False)



    combined_categories = grouped["source_categories"].transform(_combine_unique_text)

    fallback_categories = deduped["site_main_category"].map(clean_text)

    deduped["source_categories"] = combined_categories.where(combined_categories.notna(), fallback_categories)



    combined_page_urls = grouped["source_page_urls"].transform(_combine_unique_text)

    fallback_page_urls = deduped["category_page_url"].map(clean_text)

    deduped["source_page_urls"] = combined_page_urls.where(combined_page_urls.notna(), fallback_page_urls)



    deduped["source_product_urls"] = grouped["product_url"].transform(_combine_unique_text)

    deduped["source_site_product_codes"] = grouped["site_product_code"].transform(_combine_unique_text)

    deduped["source_url_keys"] = grouped["url_key"].transform(_combine_unique_text)



    keep_mask = ~(eligible_mask & deduped.duplicated(subset=duplicate_subset, keep="first"))

    helper_columns = [

        "_name_key",

        "_brand_key",

        "_price_key",

        "_measure_key",

        "_unit_key",

        "_unit_price_key",

        "_item_count_key",

        "_scrape_ts_key",

    ]

    return deduped.loc[keep_mask].drop(columns=helper_columns).reset_index(drop=True)





def deduplicate_listings(listing_df: pd.DataFrame) -> pd.DataFrame:

    grouped_categories = listing_df.groupby("product_url")["site_main_category"].agg(

        lambda items: " | ".join(sorted({item for item in items if clean_text(item)}))

    )

    grouped_pages = listing_df.groupby("product_url")["category_page_url"].agg(

        lambda items: " | ".join(sorted({item for item in items if clean_text(item)}))

    )

    deduped = listing_df.drop_duplicates(subset="product_url", keep="first").copy()

    deduped["source_categories"] = deduped["product_url"].map(grouped_categories)

    deduped["source_page_urls"] = deduped["product_url"].map(grouped_pages)

    return deduped.reset_index(drop=True)





def filter_listing_rows_by_brand(

    listing_df: pd.DataFrame,

    *,

    excluded_brands: set[str] | None = None,

) -> pd.DataFrame:

    if listing_df.empty:

        return listing_df.copy()



    excluded_brands = excluded_brands or set()

    normalized_excluded = {normalize_for_match(marka) for marka in excluded_brands if clean_text(marka)}

    if not normalized_excluded:

        return listing_df.copy()



    marka_sutunu = "listing_brand" if "listing_brand" in listing_df.columns else "brand"

    if marka_sutunu not in listing_df.columns:

        return listing_df.copy()



    normalized_brand = listing_df[marka_sutunu].map(normalize_for_match)

    return listing_df.loc[~normalized_brand.isin(normalized_excluded)].reset_index(drop=True)





def _normalized_text_series(df: pd.DataFrame, columns: list[str]) -> pd.Series:

    available_columns = [column for column in columns if column in df.columns]

    if not available_columns:

        return pd.Series([""] * len(df), index=df.index, dtype="object")



    series_parts = [df[column].map(normalize_for_match).fillna("") for column in available_columns]

    combined = pd.Series([""] * len(df), index=df.index, dtype="object")

    for part in series_parts:

        combined = (combined + " " + part).str.strip()

    return combined.str.replace(r"\s+", " ", regex=True).str.strip()





def filter_packaged_product_rows(df: pd.DataFrame) -> pd.DataFrame:

    if df.empty:

        return df.copy()



    blocked_brands = {normalize_for_match(marka) for marka in ALWAYS_EXCLUDED_BRANDS}

    reyondan_mask = pd.Series(False, index=df.index)

    for column in ["brand", "listing_brand"]:

        if column in df.columns:

            reyondan_mask = reyondan_mask | df[column].map(normalize_for_match).isin(blocked_brands)



    household_categories = {normalize_for_match(ad) for ad in HOUSEHOLD_CATEGORY_NAMES}

    household_mask = pd.Series(False, index=df.index)

    for column in ["site_main_category", "reference_category_name"]:

        if column in df.columns:

            household_mask = household_mask | df[column].map(normalize_for_match).isin(household_categories)



    detail_text = _normalized_text_series(

        df,

        ["listing_subcategory", "site_subcategory", "listing_category_tree", "breadcrumb_path"],

    )

    name_text = _normalized_text_series(df, ["product_name", "product_name_from_listing"])



    non_packaged_household_mask = pd.Series(False, index=df.index)

    for pattern in NON_PACKAGED_HOUSEHOLD_SUBCATEGORY_PATTERNS:

        non_packaged_household_mask = non_packaged_household_mask | detail_text.str.contains(pattern, regex=False)

    for pattern in NON_PACKAGED_HOUSEHOLD_NAME_PATTERNS:

        non_packaged_household_mask = non_packaged_household_mask | name_text.str.contains(pattern, regex=False)



    blocked_mask = reyondan_mask | (household_mask & non_packaged_household_mask)

    return df.loc[~blocked_mask].reset_index(drop=True)





def build_market_table(market_kimligi: int) -> pd.DataFrame:

    return pd.DataFrame([{"market_id": market_kimligi, "market_adi": "Migros"}])





def build_products_table(

    raw_df: pd.DataFrame,

    *,

    market_kimligi: int,

    start_product_id: int,

    start_sira_no: int,

) -> pd.DataFrame:

    urunler = raw_df.sort_values(["site_main_category", "product_name"]).drop_duplicates("product_url").copy()

    urunler = urunler.reset_index(drop=True)

    urunler["id"] = range(start_product_id, start_product_id + len(urunler))

    urunler["sira_no"] = range(start_sira_no, start_sira_no + len(urunler))

    urunler["market_id"] = market_kimligi

    urunler["market_adi"] = "Migros"

    urunler["urun_ad"] = urunler["product_name"]

    urunler["urun_url"] = urunler["product_url"]

    urunler["urun_kategori"] = urunler["site_main_category"]

    urunler["eklenme_tarihi"] = urunler["scrape_timestamp"]

    urunler["urun_marka"] = urunler["brand"]

    urunler["site_product_code"] = urunler["site_product_code"]

    urunler["url_key"] = urunler["url_key"]

    return urunler[

        [

            "id",

            "market_id",

            "urun_ad",

            "urun_url",

            "urun_kategori",

            "eklenme_tarihi",

            "market_adi",

            "urun_marka",

            "sira_no",

            "site_product_code",

            "url_key",

        ]

    ]





def build_price_series_table(

    raw_df: pd.DataFrame,

    urunler_df: pd.DataFrame,

    *,

    start_price_id: int,

) -> pd.DataFrame:

    if raw_df.empty or urunler_df.empty:

        return pd.DataFrame(

            columns=[

                "kayit_id",

                "urun_id",

                "urun_fiyat",

                "gramaj_degeri",

                "gramaj_birimi",

                "birim_fiyat",

                "kazima_tarihi",

                "adet_sayisi",

            ]

        )



    merged = raw_df.merge(

        urunler_df[["id", "urun_url"]],

        left_on="product_url",

        right_on="urun_url",

        how="left",

    )

    merged = merged.sort_values(["id", "scrape_timestamp"]).drop_duplicates(["id", "scrape_timestamp"])

    merged = merged.reset_index(drop=True)

    merged["kayit_id"] = range(start_price_id, start_price_id + len(merged))

    return merged[

        [

            "kayit_id",

            "id",

            "current_price",

            "package_total_value",

            "package_unit",

            "unit_price_numeric",

            "scrape_timestamp",

            "item_count",

        ]

    ].rename(

        columns={

            "id": "urun_id",

            "current_price": "urun_fiyat",

            "package_total_value": "gramaj_degeri",

            "package_unit": "gramaj_birimi",

            "unit_price_numeric": "birim_fiyat",

            "scrape_timestamp": "kazima_tarihi",

            "item_count": "adet_sayisi",

        }

    )





def build_audit_table(listing_df: pd.DataFrame) -> pd.DataFrame:

    required_columns = {"site_main_category", "input_expected_count", "live_total_count", "product_url"}

    if listing_df.empty or not required_columns.issubset(listing_df.columns):

        return pd.DataFrame(

            columns=[

                "kategori",

                "input_expected_count",

                "live_total_count",

                "collected_product_urls",

                "sayim_durumu",

            ]

        )



    audit_df = (

        listing_df.groupby(["site_main_category", "input_expected_count"], as_index=False)

        .agg(

            live_total_count=("live_total_count", "max"),

            collected_product_urls=("product_url", "nunique"),

        )

        .rename(columns={"site_main_category": "kategori"})

    )

    audit_df["sayim_durumu"] = audit_df.apply(

        lambda satir: "uyumlu"

        if pd.notna(satir["input_expected_count"]) and int(satir["input_expected_count"]) == int(satir["live_total_count"])

        else "canli_sayim_degismis",

        axis=1,

    )

    return audit_df





def export_outputs(cikti_dizini: str | Path, ciktilar: dict[str, pd.DataFrame]) -> None:

    cikti_dizini = Path(cikti_dizini)

    cikti_dizini.mkdir(parents=True, exist_ok=True)

    for ad, df in ciktilar.items():

        df.to_csv(cikti_dizini / f"{name}.csv", index=False, encoding="utf-8-sig")





class MigrosApiClient:

    def __init__(

        self,

        *,

        headless: bool = True,

        pause_range: tuple[float, float] = (0.1, 0.25),

        timeout_ms: int = 120_000,

        snapshot_dir: str | Path | None = None,

    ) -> None:

        self.headless = headless

        self.pause_range = pause_range

        self.timeout_ms = timeout_ms

        self.snapshot_dir = Path(snapshot_dir) if snapshot_dir else None

        self.playwright: Any | None = None

        self.browser: Any | None = None

        self.context: Any | None = None

        self.sayfa: Any | None = None



    def __enter__(self) -> "MigrosApiClient":

        if sync_playwright is None:                                         

            raise ModuleNotFoundError(

                "playwright paketi gerekli. Ornek: python3 -m pip install playwright && playwright install chromium"

            ) from _PLAYWRIGHT_IMPORT_ERROR



        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(headless=self.headless)

        self.context = self.browser.new_context(

            locale="tr-TR",

            extra_http_headers=DEFAULT_HEADERS,

            viewport={"width": 1440, "height": 2400},

        )

        self.sayfa = self.context.new_page()

        self.sayfa.goto(KATEGORI_HEDEFLERI[0].adres, wait_until="networkidle", timeout=self.timeout_ms)

        return self



    def __exit__(self, exc_type, exc, tb) -> None:

        if self.context is not None:

            self.context.close()

        if self.browser is not None:

            self.browser.close()

        if self.playwright is not None:

            self.playwright.stop()



    def _sleep(self) -> None:

        time.sleep(random.uniform(*self.pause_range))



    def save_snapshot(self, ad: str, content: str) -> None:

        if self.snapshot_dir is None:

            return

        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        snapshot_name = slugify_filename(ad, fallback="snapshot")

        snapshot_path = self.snapshot_dir / f"{snapshot_name}.html"

        snapshot_path.write_text(content, encoding="utf-8")



    def fetch_json(self, adres: str, retries: int = 3) -> dict[str, Any]:

        assert self.context is not None

        last_error: Exception | None = None

        for attempt in range(1, retries + 1):

            try:

                response = self.context.request.get(adres, timeout=self.timeout_ms)

                if response.status >= 400:

                    raise RuntimeError(f"HTTP {response.status} for {url}")

                veri = response.json()

                if isinstance(veri, dict) and veri.get("successful", True):

                    return veri

                raise ValueError(f"Beklenmeyen API cevabı: {url}")

            except Exception as exc:  

                last_error = exc

                if self.sayfa is not None:

                    try:

                        self.save_snapshot(

                            f"direct_request_failure_{attempt}_{urlparse(url).path}",

                            self.sayfa.content(),

                        )

                    except Exception: 

                        pass

                time.sleep(min(attempt, 3))

        raise RuntimeError(f"JSON alınamadı: {url}") from last_error



    def fetch_json_via_page(

        self,

        *,

        sayfa_adresi: str,

        response_matcher,

        snapshot_name: str,

        retries: int = 2,

    ) -> dict[str, Any]:

        assert self.sayfa is not None

        last_error: Exception | None = None

        for attempt in range(1, retries + 1):

            try:

                with self.sayfa.expect_response(response_matcher, timeout=self.timeout_ms) as response_info:

                    self.sayfa.goto(sayfa_adresi, wait_until="networkidle", timeout=self.timeout_ms)

                response = response_info.value

                if response.status >= 400:

                    raise RuntimeError(f"HTTP {response.status} for {response.url}")

                veri = response.json()

                if isinstance(veri, dict) and veri.get("successful", True):

                    return veri

                raise ValueError(f"Beklenmeyen sayfa içi API cevabı: {page_url}")

            except Exception as exc:                

                last_error = exc

                try:

                    self.save_snapshot(f"{snapshot_name}_attempt_{attempt}", self.sayfa.content())

                except Exception:                

                    pass

                time.sleep(min(attempt, 3))

        raise RuntimeError(f"Sayfa üzerinden JSON alınamadı: {page_url}") from last_error



    def get_category_page(self, kategori: KategoriHedefi, sayfa: int = 1) -> dict[str, Any]:

        self._sleep()

        rest_url = build_category_rest_url(kategori.adres, sayfa)

        try:

            return self.fetch_json(rest_url)

        except Exception:                

            slug = urlparse(kategori.adres).path.lstrip("/")

            sayfa_adresi = build_category_page_url(kategori.adres, sayfa)

            return self.fetch_json_via_page(

                sayfa_adresi=sayfa_adresi,

                response_matcher=lambda response: (

                    "/rest/search/screens/" in response.adres

                    and slug in response.adres

                    and response.request.method == "GET"

                ),

                snapshot_name=f"category_{slug}_page_{page}",

            )



    def get_product_detail(self, site_urun_kodu: str | None, urun_adresi: str | None = None) -> dict[str, Any]:

        self._sleep()

        if site_urun_kodu:

            try:

                return self.fetch_json(build_product_rest_url(site_urun_kodu))

            except Exception:                

                pass



        if not urun_adresi:

            raise RuntimeError("Ürün detayı için ne site_product_code ne de product_url sağlandı.")



        code_hint = clean_text(site_urun_kodu)

        return self.fetch_json_via_page(

            sayfa_adresi=urun_adresi,

            response_matcher=lambda response: (

                "/rest/products/screens/" in response.adres

                and response.request.method == "GET"

                and (code_hint in response.adres if code_hint else True)

            ),

            snapshot_name=f"product_{slugify_filename(product_url, fallback='detail')}",

        )





def parse_category_listing_response(

    yuk: dict[str, Any],

    kategori: KategoriHedefi,

    sayfa_numarasi: int,

) -> tuple[int, int, list[dict[str, Any]]]:

    search_info = yuk["data"]["searchInfo"]

    live_total_count = int(search_info["hitCount"])

    page_count = int(search_info["pageCount"])

    satirlar: list[dict[str, Any]] = []

    kategori_sayfa_adresi = kategori.adres if sayfa_numarasi == 1 else f"{kategori.adres}?sayfa={sayfa_numarasi}"



    for item in search_info.get("storeProductInfos", []):

        unit_price_numeric, birim_fiyat_tabani = parse_unit_price_text(item.get("unitPrice"))

        measurements = parse_measurements(item.get("name"), birim_fiyat_tabani=birim_fiyat_tabani)

        satirlar.append(

            {

                "site_main_category": kategori.display_name,

                "reference_category_name": kategori.reference_name,

                "category_url": kategori.adres,

                "category_page_url": kategori_sayfa_adresi,

                "input_expected_count": kategori.expected_count,

                "live_total_count": live_total_count,

                "product_name_from_listing": clean_text(item.get("name")),

                "product_url": urljoin(BASE_URL, f"/{item.get('prettyName')}"),

                "url_key": clean_text(item.get("prettyName")),

                "site_product_code": clean_text(item.get("sku")),

                "listing_brand": clean_text((item.get("brand") or {}).get("name")),

                "listing_subcategory": clean_text((item.get("category") or {}).get("name")),

                "listing_category_tree": " > ".join(

                    [

                        clean_text(node.get("name"))

                        for node in item.get("categoryAscendants", [])

                        if clean_text(node.get("name"))

                    ]

                    + [clean_text((item.get("category") or {}).get("name"))]

                ),

                "current_price": cents_to_float(item.get("shownPrice")),

                "original_price": (

                    cents_to_float(item.get("regularPrice"))

                    if item.get("regularPrice") != item.get("shownPrice")

                    else None

                ),

                "unit_price_text": clean_text(item.get("unitPrice")),

                "unit_price_numeric": unit_price_numeric,

                "unit_price_basis": birim_fiyat_tabani,

                **measurements,

            }

        )



    return live_total_count, page_count, satirlar





def parse_product_detail_response(

    yuk: dict[str, Any],

    liste_satiri: dict[str, Any],

    kazima_zaman_damgasi: datetime,

) -> dict[str, Any]:

    dto = yuk["data"]["storeProductInfoDTO"]

    properties = flatten_property_infos(dto.get("propertyInfosMap"))

    breadcrumb_nodes = dto.get("categoryAscendants", []) + ([dto.get("category")] if dto.get("category") else [])

    breadcrumbs = [clean_text(node.get("name")) for node in breadcrumb_nodes if clean_text(node.get("name"))]



    urun_adi = clean_text(dto.get("name")) or liste_satiri["product_name_from_listing"]

    urun_adresi = urljoin(BASE_URL, f"/{dto.get('prettyName')}")

    unit_price_numeric, birim_fiyat_tabani = parse_unit_price_text(dto.get("unitPrice"))

    net_miktar_degeri = get_property_value(properties, custom_id="netKg", ad="Net Miktar (g/ml)")

    measurements = parse_measurements(urun_adi, net_miktar_degeri=net_miktar_degeri, birim_fiyat_tabani=birim_fiyat_tabani)



    for key in ["package_value_text", "package_total_value", "package_unit", "item_count"]:

        if liste_satiri.get(key) and not measurements.get(key):

            measurements[key] = liste_satiri[key]



    return {

        **liste_satiri,

        "scrape_timestamp": pd.Timestamp(kazima_zaman_damgasi),

        "product_name": urun_adi,

        "product_url": urun_adresi,

        "url_key": clean_text(dto.get("prettyName")) or liste_satiri["url_key"],

        "site_product_code": clean_text(dto.get("sku")) or liste_satiri["site_product_code"],

        "brand": clean_text((dto.get("brand") or {}).get("name")) or liste_satiri["listing_brand"],

        "origin": get_property_value(properties, custom_id="country", ad="Menşei"),

        "manufacturer": get_property_value(

            properties,

            custom_id="productSupplier",

            ad="İşletmeci / Üretici / İthalatçı / Dağıtıcı",

        ),

        "manufacturer_address": get_property_value(properties, custom_id="productSupplierAddress"),

        "product_supplier_id": get_property_value(properties, custom_id="productSupplierId"),

        "availability_text": clean_text(dto.get("status")),

        "current_price": cents_to_float(dto.get("shownPrice")) or liste_satiri["current_price"],

        "original_price": (

            cents_to_float(dto.get("regularPrice"))

            if dto.get("regularPrice") != dto.get("shownPrice")

            else liste_satiri["original_price"]

        ),

        "unit_price_text": clean_text(dto.get("unitPrice")) or liste_satiri["unit_price_text"],

        "unit_price_numeric": unit_price_numeric or liste_satiri["unit_price_numeric"],

        "unit_price_basis": birim_fiyat_tabani or liste_satiri["unit_price_basis"],

        "net_amount_text": net_miktar_degeri,

        "breadcrumb_path": " > ".join(breadcrumbs) if breadcrumbs else liste_satiri["listing_category_tree"],

        "site_subcategory": clean_text((dto.get("category") or {}).get("name")) or liste_satiri["listing_subcategory"],

        "product_description": clean_html_to_text(dto.get("description")),

        "information_text": clean_html_to_text(dto.get("information")),

        "general_information": clean_text(dto.get("generalInformation")),

        **measurements,

    }





def collect_all_listings(istemci: MigrosApiClient, categories: list[KategoriHedefi]) -> pd.DataFrame:

    frames: list[pd.DataFrame] = []

    for kategori in tqdm(categories, desc="Kategori sayfaları"):

        first_payload = istemci.get_category_page(kategori, sayfa=1)

        _, page_count, first_rows = parse_category_listing_response(first_payload, kategori, sayfa_numarasi=1)

        tum_satirlar = list(first_rows)



        for sayfa_numarasi in range(2, page_count + 1):

            yuk = istemci.get_category_page(kategori, sayfa=sayfa_numarasi)

            _, _, page_rows = parse_category_listing_response(yuk, kategori, sayfa_numarasi=sayfa_numarasi)

            tum_satirlar.extend(page_rows)



        frames.append(pd.DataFrame(tum_satirlar))



    if not frames:

        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)





def collect_product_details(

    istemci: MigrosApiClient,

    listing_df: pd.DataFrame,

    *,

    urun_siniri: int | None = None,

) -> pd.DataFrame:

    satirlar = listing_df.to_dict("records")

    if urun_siniri is not None:

        satirlar = satirlar[:urun_siniri]



    scraped_rows: list[dict[str, Any]] = []

    kazima_zaman_damgasi = datetime.now(TIMEZONE).replace(microsecond=0)



    for satir in tqdm(satirlar, desc="Ürün detayları"):

        yuk = istemci.get_product_detail(satir["site_product_code"], satir.get("product_url"))

        scraped_rows.append(parse_product_detail_response(yuk, satir, kazima_zaman_damgasi))



    return pd.DataFrame(scraped_rows)





def build_outputs(

    raw_df: pd.DataFrame,

    listing_df: pd.DataFrame,

    *,

    mevcut_cikti_dizini: str | Path | None,

) -> dict[str, pd.DataFrame]:

    raw_df = filter_packaged_product_rows(raw_df)

    listing_df = filter_packaged_product_rows(listing_df)

    raw_df = deduplicate_relisted_products(raw_df)

    existing_market_df = load_existing_table(mevcut_cikti_dizini, "market.csv")

    existing_products_df = load_existing_table(mevcut_cikti_dizini, "urunler.csv")

    existing_prices_df = load_existing_table(mevcut_cikti_dizini, "fiyat_zaman_serisi.csv")



    if not existing_products_df.empty and "urun_url" in existing_products_df.columns:

        raw_df = raw_df[~raw_df["product_url"].isin(existing_products_df["urun_url"])].copy()



    market_kimligi = resolve_market_id(existing_market_df)

    start_product_id = resolve_start_id(existing_products_df, "id", default_value=1)

    start_price_id = resolve_start_id(existing_prices_df, "kayit_id", default_value=1)

    start_sira_no = resolve_start_id(existing_products_df, "sira_no", default_value=1)



    market_df = build_market_table(market_kimligi)

    urunler_df = build_products_table(

        raw_df,

        market_kimligi=market_kimligi,

        start_product_id=start_product_id,

        start_sira_no=start_sira_no,

    )

    fiyat_serisi_df = build_price_series_table(

        raw_df,

        urunler_df,

        start_price_id=start_price_id,

    )

    audit_df = build_audit_table(listing_df)



    raw_df = raw_df.copy()

    raw_df["market_id"] = market_kimligi



    return {

        "market": market_df,

        "urunler": urunler_df,

        "fiyat_zaman_serisi": fiyat_serisi_df,

        "raw_products": raw_df,

        "scrape_audit": audit_df,

    }





def run_pipeline_from_raw_df(

    raw_df: pd.DataFrame,

    *,

    listing_df: pd.DataFrame | None = None,

    cikti_dizini: str | Path | None = None,

    mevcut_cikti_dizini: str | Path | None = None,

) -> dict[str, pd.DataFrame]:

    ciktilar = build_outputs(

        raw_df,

        listing_df if listing_df is not None else pd.DataFrame(),

        mevcut_cikti_dizini=mevcut_cikti_dizini,

    )

    if cikti_dizini is not None:

        export_outputs(cikti_dizini, ciktilar)

    return ciktilar





def run_pipeline(

    *,

    cikti_dizini: str | Path | None = DEFAULT_OUTPUT_DIR,

    mevcut_cikti_dizini: str | Path | None = DEFAULT_EXISTING_OUTPUTS_DIR,

    categories: list[KategoriHedefi] | None = None,

    urun_siniri: int | None = None,

    pause_range: tuple[float, float] = (0.1, 0.25),

    headless: bool = True,

    snapshot_dir: str | Path | None = DEFAULT_SNAPSHOT_DIR,

    exclude_reyondan: bool = False,

) -> dict[str, pd.DataFrame]:

    categories = categories or KATEGORI_HEDEFLERI

    with MigrosApiClient(

        headless=headless,

        pause_range=pause_range,

        snapshot_dir=snapshot_dir,

    ) as istemci:

        listing_df = collect_all_listings(istemci, categories)

        listing_df = deduplicate_listings(listing_df)

        if exclude_reyondan:

            listing_df = filter_listing_rows_by_brand(listing_df, excluded_brands=ALWAYS_EXCLUDED_BRANDS)

        listing_df = filter_packaged_product_rows(listing_df)

        raw_df = collect_product_details(istemci, listing_df, urun_siniri=urun_siniri)



    ciktilar = build_outputs(raw_df, listing_df, mevcut_cikti_dizini=mevcut_cikti_dizini)



    if cikti_dizini is not None:

        export_outputs(cikti_dizini, ciktilar)



    return ciktilar





def build_cli_parser() -> argparse.ArgumentParser:

    komut_ayristirici = argparse.ArgumentParser(description="Migros kategori scraper")

    komut_ayristirici.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Çıktı klasörü")

    komut_ayristirici.add_argument(

        "--existing-outputs-dir",

        default=str(DEFAULT_EXISTING_OUTPUTS_DIR),

        help="Önceki ŞOK çıktılarının bulunduğu klasör",

    )

    komut_ayristirici.add_argument("--limit", type=int, default=None, help="Test amaçlı ürün limiti")

    komut_ayristirici.add_argument("--min-sleep", type=float, default=0.10, help="İstekler arası minimum bekleme")

    komut_ayristirici.add_argument("--max-sleep", type=float, default=0.25, help="İstekler arası maksimum bekleme")

    komut_ayristirici.add_argument("--exclude-reyondan", action="store_true", help="Reyondan markali urunleri detay scrape oncesi haric tut")

    komut_ayristirici.add_argument("--headed", action="store_true", help="Tarayıcıyı görünür aç")

    komut_ayristirici.add_argument(

        "--snapshot-dir",

        default=str(DEFAULT_SNAPSHOT_DIR),

        help="Hata anındaki HTML snapshot klasörü",

    )

    return komut_ayristirici





def main(argv: list[str] | None = None) -> None:

    komut_ayristirici = build_cli_parser()

    args, _unknown = komut_ayristirici.parse_known_args(argv)



    ciktilar = run_pipeline(

        cikti_dizini=Path(args.cikti_dizini),

        mevcut_cikti_dizini=Path(args.mevcut_cikti_dizini) if args.mevcut_cikti_dizini else None,

        urun_siniri=args.limit,

        pause_range=(args.min_sleep, args.max_sleep),

        headless=not args.headed,

        snapshot_dir=Path(args.snapshot_dir) if args.snapshot_dir else None,

        exclude_reyondan=args.exclude_reyondan,

    )



    print("\nOluşan tablolar:")

    for ad, df in ciktilar.items():

        print(f"- {name}: {len(df)} satır")





if __name__ == "__main__":

    main()

