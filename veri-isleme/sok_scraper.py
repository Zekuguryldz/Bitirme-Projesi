from __future__ import annotations



import argparse

import json

import logging

import math

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

import requests

from bs4 import BeautifulSoup

from tqdm.auto import tqdm



LOGGER = logging.getLogger(__name__)



BASE_URL = "https://www.sokmarket.com.tr"

TIMEZONE = ZoneInfo("Europe/Istanbul")

DEFAULT_REFERENCE_CSV = Path("/Users/uguryildiz/Desktop/bitirme/sokdata.csv")

DEFAULT_HEADERS = {

    "User-Agent": (

        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "

        "AppleWebKit/537.36 (KHTML, like Gecko) "

        "Chrome/135.0.0.0 Safari/537.36"

    ),

    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",

}

DEFAULT_MANUAL_SCRAPE_HOUR = 19



MASS_UNITS = {"mg", "g", "kg"}

VOLUME_UNITS = {"ml", "cl", "l"}

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

}



PRICE_PATTERN = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*₺")

TOTAL_COUNT_PATTERN = re.compile(r"(\d+)\s+adet ürün listelendi", re.IGNORECASE)

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

NEXT_F_PUSH_PATTERN = re.compile(

    r'self\.__next_f\.push\(\[\d+,"((?:\\.|[^"\\])*)"\]\)',

    re.DOTALL,

)

PRODUCT_CODE_PATTERN = re.compile(r"-p-(\d+)$")

REFERENCE_URL_KEYS = (

    "product_url",

    "urun_url",

    "url",

    "product link",

)

REFERENCE_NAME_KEYS = (

    "product_name",

    "urun_ad",

    "urun adi",

    "product title",

)

REFERENCE_CATEGORY_KEYS = (

    "site_main_category",

    "urun_kategori",

    "kategori",

    "category",

    "site kategori",

)

REFERENCE_BRAND_KEYS = ("brand", "urun_marka", "marka")

REFERENCE_DATE_KEYS = (

    "first_reference_date",

    "ilk referans tarihi",

    "eklenme_tarihi",

    "cekim_tarihi",

    "scrape_timestamp",

)

REFERENCE_CODE_KEYS = ("product_code", "site_product_code", "urun_kodu")





@dataclass(frozen=True)

class KategoriHedefi:

    display_name: str

    reference_name: str

    adres: str

    expected_count: int | None = None





KATEGORI_HEDEFLERI: list[KategoriHedefi] = [

    KategoriHedefi(

        display_name="Atıştırmalıklar",

        reference_name="Atistirmaliklar",

        adres="https://www.sokmarket.com.tr/atistirmaliklar-c-20376",

        expected_count=484,

    ),

    KategoriHedefi(

        display_name="Yemeklik Malzemeler",

        reference_name="Yemeklik Malzemeler",

        adres="https://www.sokmarket.com.tr/yemeklik-malzemeler-c-1770",

        expected_count=257,

    ),

    KategoriHedefi(

        display_name="Et & Tavuk & Şarküteri",

        reference_name="Et Tavuk Sarkuteri",

        adres="https://www.sokmarket.com.tr/et-ve-tavuk-ve-sarkuteri-c-160",

        expected_count=58,

    ),

    KategoriHedefi(

        display_name="Kahvaltılık",

        reference_name="Kahvaltilik",

        adres="https://www.sokmarket.com.tr/kahvaltilik-c-890",

        expected_count=219,

    ),

    KategoriHedefi(

        display_name="İçecek",

        reference_name="Icecek",

        adres="https://www.sokmarket.com.tr/icecek-c-20505",

        expected_count=247,

    ),

    KategoriHedefi(

        display_name="Dondurulmuş Ürünler",

        reference_name="Dondurulmus Urunler",

        adres="https://www.sokmarket.com.tr/dondurulmus-urunler-c-1550",

        expected_count=32,

    ),

    KategoriHedefi(

        display_name="Dondurma",

        reference_name="Dondurma",

        adres="https://www.sokmarket.com.tr/dondurma-c-31102",

        expected_count=87,

    ),

    KategoriHedefi(

        display_name="Temizlik",

        reference_name="Temizlik",

        adres="https://www.sokmarket.com.tr/temizlik-c-20647",

        expected_count=150,

    ),

    KategoriHedefi(

        display_name="Kağıt Ürünleri",

        reference_name="Kagit Urunleri",

        adres="https://www.sokmarket.com.tr/kagit-urunler-c-20875",

        expected_count=46,

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



    text = str(value).replace("\xa0", " ").strip()

    if not text or text.lower() == "nan":

        return None

    return re.sub(r"\s+", " ", text)





def value_present(value: Any) -> bool:

    if value is None:

        return False

    try:

        if bool(pd.isna(value)):

            return False

    except Exception:

        pass

    if isinstance(value, str):

        return clean_text(value) is not None

    return True





def normalize_scrape_timestamp(value: datetime | None) -> datetime:

    if value is None:

        return datetime.now(TIMEZONE).replace(microsecond=0)

    if value.tzinfo is None:

        value = value.replace(tzinfo=TIMEZONE)

    else:

        value = value.astimezone(TIMEZONE)

    return value.replace(microsecond=0)





def parse_scrape_datetime_input(value: str) -> datetime:

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

        ayristirilmis = ayristirilmis.replace(

            hour=DEFAULT_MANUAL_SCRAPE_HOUR,

            minute=0,

            second=0,

            microsecond=0,

        )

    return normalize_scrape_timestamp(ayristirilmis)





def normalize_for_match(value: Any) -> str:

    text = clean_text(value) or ""

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





def first_non_null(series: pd.Series) -> Any:

    for value in series:

        cleaned = clean_text(value)

        if cleaned is not None:

            return value

    return None





def parse_decimal(value: str | None) -> float | None:

    cleaned = clean_text(value)

    if cleaned is None:

        return None

    return float(cleaned.replace(".", "").replace(",", "."))





def parse_price(value: Any) -> float | None:

    cleaned = clean_text(value)

    if cleaned is None:

        return None

    eslesme = PRICE_PATTERN.search(cleaned)

    if eslesme:

        return parse_decimal(eslesme.group(1))



    maybe_number = re.search(r"\d+(?:[.,]\d+)?", cleaned)

    if maybe_number:

        return float(maybe_number.group(0).replace(",", "."))

    return None





def parse_json_script_node(script) -> Any | None:

    raw = script.string if script.string is not None else script.get_text()

    if raw is None:

        return None

    raw = raw.strip()

    if not raw:

        return None

    try:

        return json.loads(raw)

    except json.JSONDecodeError:

        return None





def standart_birim(birim: str | None) -> str | None:

    cleaned = clean_text(birim)

    if cleaned is None:

        return None

    return UNIT_ALIASES.get(cleaned.casefold())





def convert_amount_to_base(miktar: float, birim: str | None) -> tuple[float | None, str | None]:

    canonical = standart_birim(birim)

    if canonical is None:

        return None, None

    if canonical == "kg":

        return miktar * 1000.0, "g"

    if canonical == "mg":

        return miktar / 1000.0, "g"

    if canonical == "g":

        return miktar, "g"

    if canonical == "cl":

        return miktar * 10.0, "ml"

    if canonical == "l":

        return miktar * 1000.0, "ml"

    if canonical == "ml":

        return miktar, "ml"

    return None, None





def compute_unit_price(fiyat: float | None, total_value: float | None, birim: str | None) -> float | None:

    if fiyat is None or total_value is None or total_value <= 0 or birim is None:

        return None

    if birim in {"g", "ml"}:

        return round((fiyat * 1000.0) / total_value, 4)

    if birim == "adet":

        return round(fiyat / total_value, 4)

    return None





def derive_site_product_code(urun_adresi: Any) -> str | None:

    cleaned = clean_text(urun_adresi)

    if cleaned is None:

        return None

    yol = urlparse(cleaned).path.rstrip("/").split("/")[-1]

    eslesme = PRODUCT_CODE_PATTERN.search(yol)

    return eslesme.group(1) if eslesme else None





def derive_url_key(urun_adresi: Any) -> str | None:

    return derive_site_product_code(urun_adresi)





def derive_slug_key(urun_adresi: Any) -> str | None:

    cleaned = clean_text(urun_adresi)

    if cleaned is None:

        return None

    yol = urlparse(cleaned).path.strip("/")

    if not yol:

        return None

    return PRODUCT_CODE_PATTERN.sub("", yol).casefold()





def deduplicate_relisted_products(raw_df: pd.DataFrame) -> pd.DataFrame:

    if raw_df.empty:

        return raw_df.copy()



    deduped = raw_df.copy()

    for column in [

        "site_main_category",

        "product_name",

        "product_url",

        "product_code",

        "brand",

        "current_price",

        "package_total_value",

        "package_unit",

        "unit_price",

        "item_count",

        "first_reference_date",

    ]:

        if column not in deduped:

            deduped[column] = None



    deduped["_slug_key"] = deduped["product_url"].map(derive_slug_key)

    deduped["_name_key"] = deduped["product_name"].map(normalize_for_match)

    deduped["_brand_key"] = deduped["brand"].map(normalize_for_match)

    deduped["_price_key"] = deduped["current_price"].map(clean_text)

    deduped["_measure_key"] = deduped["package_total_value"].map(clean_text)

    deduped["_unit_key"] = deduped["package_unit"].map(normalize_for_match)

    deduped["_unit_price_key"] = deduped["unit_price"].map(clean_text)

    deduped["_item_count_key"] = deduped["item_count"].map(clean_text)



    deduped = deduped.sort_values(

        [

            "site_main_category",

            "_brand_key",

            "_name_key",

            "first_reference_date",

            "product_code",

            "product_url",

        ],

        na_position="last",

    ).reset_index(drop=True)



    duplicate_subset = [

        "site_main_category",

        "_slug_key",

        "_brand_key",

        "_name_key",

        "_price_key",

        "_measure_key",

        "_unit_key",

        "_unit_price_key",

        "_item_count_key",

    ]

    slug_present = deduped["_slug_key"].notna()

    keep_mask = ~(

        slug_present

        & deduped.duplicated(

            subset=duplicate_subset,

            keep="first",

        )

    )



    helper_columns = [

        "_slug_key",

        "_name_key",

        "_brand_key",

        "_price_key",

        "_measure_key",

        "_unit_key",

        "_unit_price_key",

        "_item_count_key",

    ]

    return deduped.loc[keep_mask].drop(columns=helper_columns).reset_index(drop=True)





def normalize_spaces(text: str) -> str:

    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()





def build_page_url(base_url: str, sayfa: int) -> str:

    if sayfa <= 1:

        return base_url

    separator = "&" if "?" in base_url else "?"

    return f"{base_url}{separator}page={page}"





def parse_count_from_text(text: str | None) -> float | None:

    cleaned = clean_text(text)

    if cleaned is None:

        return None

    eslesmeler = COUNT_PATTERN.findall(cleaned)

    if not eslesmeler:

        return None

    return float(eslesmeler[-1][0])





def extract_measure_and_count(*texts: str | None) -> tuple[float | None, str | None, float | None]:

    normalized_texts = [normalize_spaces(text) for text in texts if clean_text(text)]

    count_value: float | None = None



    for text in normalized_texts:

        if count_value is None:

            count_value = parse_count_from_text(text)

        pack_matches = list(MULTIPLY_PATTERN.finditer(text))

        if not pack_matches:

            continue

        eslesme = pack_matches[-1]

        count = float(eslesme.group("count"))

        miktar = float(eslesme.group("amount").replace(",", "."))

        total_base, temel_birim = convert_amount_to_base(miktar * count, eslesme.group("unit"))

        if total_base is not None and temel_birim is not None:

            return round(total_base, 4), temel_birim, count



    for text in normalized_texts:

        if count_value is None:

            count_value = parse_count_from_text(text)

        amount_matches = list(AMOUNT_PATTERN.finditer(text))

        if not amount_matches:

            continue

        eslesme = amount_matches[-1]

        miktar = float(eslesme.group("amount").replace(",", "."))

        total_base, temel_birim = convert_amount_to_base(miktar, eslesme.group("unit"))

        if total_base is not None and temel_birim is not None:

            return round(total_base, 4), temel_birim, count_value



    if count_value is not None:

        return count_value, "adet", count_value

    return None, None, None





def decode_next_payload_chunks(html: str) -> list[str]:

    chunks: list[str] = []

    for raw_chunk in NEXT_F_PUSH_PATTERN.findall(html):

        try:

            decoded = bytes(raw_chunk, "utf-8").decode("unicode_escape")

        except UnicodeDecodeError:

            decoded = raw_chunk.encode("utf-8", "ignore").decode("utf-8", "ignore")

        chunks.append(decoded)

    return chunks





def extract_live_total_count(html: str) -> int | None:

    soup = BeautifulSoup(html, "html.parser")

    whole_text = soup.get_text(" ", strip=True)

    eslesme = TOTAL_COUNT_PATTERN.search(whole_text)

    if eslesme:

        return int(eslesme.group(1))

    for chunk in decode_next_payload_chunks(html):

        eslesme = TOTAL_COUNT_PATTERN.search(chunk)

        if eslesme:

            return int(eslesme.group(1))

    return None





def extract_candidate_url(aday: dict[str, Any]) -> str | None:

    for key in ("url", "@id", "product_url", "productUrl", "href", "link"):

        value = clean_text(aday.get(key))

        if value is None:

            continue

        normalize_edilmis = urljoin(BASE_URL, value)

        normalize_edilmis = normalize_edilmis.split("#", 1)[0]

        return normalize_edilmis.split("?", 1)[0]

    return None





def extract_candidate_name(aday: dict[str, Any]) -> str | None:

    for key in ("name", "title", "product_name", "productName"):

        value = clean_text(aday.get(key))

        if value is not None:

            return value

    return None





def extract_candidate_brand(aday: dict[str, Any]) -> str | None:

    brand_value = aday.get("brand")

    if isinstance(brand_value, dict):

        return clean_text(brand_value.get("name")) or clean_text(brand_value.get("brand"))

    if isinstance(brand_value, list):

        for item in brand_value:

            if isinstance(item, dict):

                brand_name = clean_text(item.get("name"))

                if brand_name is not None:

                    return brand_name

            else:

                brand_name = clean_text(item)

                if brand_name is not None:

                    return brand_name

        return None

    return clean_text(brand_value)





def extract_candidate_description(aday: dict[str, Any]) -> str | None:

    for key in ("description", "shortDescription", "productDescription", "summary"):

        value = clean_text(aday.get(key))

        if value is not None:

            return value

    return None





def extract_candidate_product_code(aday: dict[str, Any]) -> str | None:

    for key in ("sku", "product_code", "productCode", "code"):

        value = clean_text(aday.get(key))

        if value is not None:

            return value

    return None





def extract_offer_price(value: Any) -> float | None:

    if isinstance(value, dict):

        for key in ("price", "lowPrice", "highPrice", "salePrice", "currentPrice", "discountedPrice"):

            fiyat = parse_price(value.get(key))

            if fiyat is not None:

                return fiyat

        return None

    if isinstance(value, list):

        for item in value:

            fiyat = extract_offer_price(item)

            if fiyat is not None:

                return fiyat

        return None

    return parse_price(value)





def extract_candidate_price(aday: dict[str, Any]) -> float | None:

    fiyat = extract_offer_price(aday.get("offers"))

    if fiyat is not None:

        return fiyat

    for key in ("price", "currentPrice", "current_price", "salePrice", "sale_price", "discountedPrice"):

        fiyat = parse_price(aday.get(key))

        if fiyat is not None:

            return fiyat

    return None





def looks_like_product_candidate(aday: dict[str, Any]) -> bool:

    urun_adresi = extract_candidate_url(aday)

    urun_adi = extract_candidate_name(aday)

    if urun_adresi is None or urun_adi is None or "-p-" not in urun_adresi:

        return False



    product_type = clean_text(aday.get("@type") or aday.get("type"))

    if product_type and "product" in product_type.casefold():

        return True



    return any(

        value_present(aday.get(key))

        for key in ("sku", "offers", "brand", "description", "price", "currentPrice", "productCode")

    )





def iter_structured_product_candidates(soup: BeautifulSoup):

    for script in soup.find_all("script"):

        script_type = clean_text(script.get("type"))

        script_id = clean_text(script.get("id"))

        if script_type not in {"application/ld+json", "application/json"} and script_id != "__NEXT_DATA__":

            continue

        yuk = parse_json_script_node(script)

        if yuk is None:

            continue

        for aday in iter_json_objects(yuk):

            if isinstance(aday, dict) and looks_like_product_candidate(aday):

                yield aday





def merge_listing_rows(*row_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:

    merged_by_url: dict[str, dict[str, Any]] = {}

    ordered_urls: list[str] = []

    for satirlar in row_groups:

        for satir in satirlar:

            urun_adresi = clean_text(satir.get("product_url"))

            if urun_adresi is None:

                continue

            if urun_adresi not in merged_by_url:

                merged_by_url[urun_adresi] = dict(satir)

                ordered_urls.append(urun_adresi)

                continue

            guncel = merged_by_url[urun_adresi]

            for key, value in satir.items():

                if not value_present(guncel.get(key)) and value_present(value):

                    guncel[key] = value

    return [merged_by_url[adres] for adres in ordered_urls]





def choose_anchor_name(anchor) -> str | None:

    adaylar: list[str] = []

    for attribute in ("title", "aria-label"):

        value = clean_text(anchor.get(attribute))

        if value:

            adaylar.append(value)



    img = anchor.find("img")

    if img is not None:

        alt = clean_text(img.get("alt"))

        if alt:

            adaylar.append(alt)



    for element in anchor.find_all(["h2", "h3", "span", "p", "div"]):

        text = clean_text(element.get_text(" ", strip=True))

        if text and not PRICE_PATTERN.search(text):

            adaylar.append(text)



    anchor_text = clean_text(anchor.get_text(" ", strip=True))

    if anchor_text and not PRICE_PATTERN.search(anchor_text):

        adaylar.append(anchor_text)



    adaylar = [value for value in adaylar if len(value) > 2]

    if not adaylar:

        return None

    return sorted(adaylar, key=len, reverse=True)[0]





def extract_listing_rows_from_anchors(

    soup: BeautifulSoup,

    kategori: KategoriHedefi,

    sayfa_adresi: str,

    live_total_count: int | None,

) -> list[dict[str, Any]]:

    satirlar: list[dict[str, Any]] = []

    seen_urls: set[str] = set()

    for anchor in soup.find_all("a", href=True):

        href = clean_text(anchor.get("href"))

        if href is None or "-p-" not in href:

            continue

        urun_adresi = urljoin(BASE_URL, href.split("?")[0])

        if urun_adresi in seen_urls:

            continue



        urun_adi = choose_anchor_name(anchor)

        if urun_adi is None:

            continue



        context_text = clean_text(anchor.parent.get_text(" ", strip=True)) or ""

        price_match = PRICE_PATTERN.search(context_text) or PRICE_PATTERN.search(anchor.get_text(" ", strip=True))

        listing_price_text = price_match.group(1) if price_match else None

        satirlar.append(

            {

                "site_main_category": kategori.display_name,

                "reference_category_name": kategori.reference_name,

                "input_expected_count": kategori.expected_count,

                "live_total_count": live_total_count,

                "listing_page_url": sayfa_adresi,

                "product_name": urun_adi,

                "product_url": urun_adresi,

                "listing_price": parse_decimal(listing_price_text),

                "listing_price_text": listing_price_text,

                "product_code": derive_site_product_code(urun_adresi),

            }

        )

        seen_urls.add(urun_adresi)

    return satirlar





def extract_listing_rows_from_structured_data(

    soup: BeautifulSoup,

    kategori: KategoriHedefi,

    sayfa_adresi: str,

    live_total_count: int | None,

) -> list[dict[str, Any]]:

    satirlar: list[dict[str, Any]] = []

    seen_urls: set[str] = set()

    for aday in iter_structured_product_candidates(soup):

        urun_adresi = extract_candidate_url(aday)

        urun_adi = extract_candidate_name(aday)

        if urun_adresi is None or urun_adi is None or urun_adresi in seen_urls:

            continue

        satirlar.append(

            {

                "site_main_category": kategori.display_name,

                "reference_category_name": kategori.reference_name,

                "input_expected_count": kategori.expected_count,

                "live_total_count": live_total_count,

                "listing_page_url": sayfa_adresi,

                "product_name": urun_adi,

                "product_url": urun_adresi,

                "listing_price": extract_candidate_price(aday),

                "listing_price_text": None,

                "product_code": extract_candidate_product_code(aday) or derive_site_product_code(urun_adresi),

            }

        )

        seen_urls.add(urun_adresi)

    return satirlar





def parse_category_listing_page(

    html: str,

    kategori: KategoriHedefi,

    sayfa_adresi: str,

) -> tuple[int | None, list[dict[str, Any]]]:

    live_total_count = extract_live_total_count(html)

    soup = BeautifulSoup(html, "html.parser")

    satirlar = merge_listing_rows(

        extract_listing_rows_from_anchors(soup, kategori, sayfa_adresi, live_total_count),

        extract_listing_rows_from_structured_data(soup, kategori, sayfa_adresi, live_total_count),

    )

    return live_total_count, satirlar





def deduplicate_listings(listing_df: pd.DataFrame) -> pd.DataFrame:

    if listing_df.empty:

        return listing_df.copy()

    sorted_df = listing_df.sort_values(["site_main_category", "product_name", "product_url"]).reset_index(drop=True)

    return sorted_df.drop_duplicates(subset=["product_url", "site_main_category"]).reset_index(drop=True)





def iter_json_objects(value: Any):

    if isinstance(value, dict):

        yield value

        for nested in value.values():

            yield from iter_json_objects(nested)

    elif isinstance(value, list):

        for nested in value:

            yield from iter_json_objects(nested)





def extract_json_ld_product(soup: BeautifulSoup) -> dict[str, Any] | None:

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):

        yuk = parse_json_script_node(script)

        if yuk is None:

            continue

        for aday in iter_json_objects(yuk):

            product_type = clean_text(aday.get("@type")) if isinstance(aday, dict) else None

            if product_type and "product" in product_type.casefold():

                return aday

    return None





def select_best_structured_product_candidate(

    adaylar: list[dict[str, Any]],

    satir: dict[str, Any],

) -> dict[str, Any] | None:

    target_url = extract_candidate_url({"url": satir.get("product_url")})

    target_code = clean_text(satir.get("product_code")) or derive_site_product_code(target_url)

    best_candidate: dict[str, Any] | None = None

    best_score = -1



    for aday in adaylar:

        score = 0

        candidate_url = extract_candidate_url(aday)

        candidate_code = extract_candidate_product_code(aday)



        if target_url and candidate_url == target_url:

            score += 10

        elif target_code and candidate_url and f"-p-{target_code}" in candidate_url:

            score += 6



        if target_code and candidate_code == target_code:

            score += 8

        if extract_candidate_name(aday) is not None:

            score += 2

        if extract_candidate_price(aday) is not None:

            score += 2

        if extract_candidate_description(aday) is not None:

            score += 1



        if score > best_score:

            best_candidate = aday

            best_score = score



    return best_candidate if best_score > 0 else None





def extract_meta_content(soup: BeautifulSoup, *, property_name: str | None = None, meta_name: str | None = None) -> str | None:

    if property_name:

        node = soup.find("meta", attrs={"property": property_name})

        if node is not None:

            return clean_text(node.get("content"))

    if meta_name:

        node = soup.find("meta", attrs={"name": meta_name})

        if node is not None:

            return clean_text(node.get("content"))

    return None





def derive_brand(urun_adi: str | None) -> str | None:

    cleaned = clean_text(urun_adi)

    if cleaned is None:

        return None

    parts = cleaned.split()

    if not parts:

        return None

    return parts[0]





def parse_product_detail_page(html: str, satir: dict[str, Any], kazima_zaman_damgasi: datetime) -> dict[str, Any]:

    soup = BeautifulSoup(html, "html.parser")

    product_json = extract_json_ld_product(soup) or {}

    structured_product = select_best_structured_product_candidate(list(iter_structured_product_candidates(soup)), satir) or {}



    urun_adi = (

        clean_text(product_json.get("name"))

        or extract_candidate_name(structured_product)

        or clean_text(soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else None)

        or clean_text(satir.get("product_name"))

    )

    urun_adresi = clean_text(satir.get("product_url"))

    marka = None

    raw_brand = product_json.get("brand") if value_present(product_json.get("brand")) else structured_product.get("brand")

    if isinstance(raw_brand, dict):

        marka = clean_text(raw_brand.get("name"))

    elif raw_brand is not None:

        marka = clean_text(raw_brand)

    marka = marka or extract_candidate_brand(structured_product) or derive_brand(urun_adi)



    description = (

        clean_text(product_json.get("description"))

        or extract_candidate_description(structured_product)

        or extract_meta_content(soup, property_name="og:description")

        or extract_meta_content(soup, meta_name="description")

    )



    offer_price = extract_offer_price(product_json.get("offers"))

    if offer_price is None:

        offer_price = extract_candidate_price(structured_product)



    page_text = soup.get_text(" ", strip=True)

    current_price = offer_price or parse_price(page_text) or parse_price(satir.get("listing_price"))

    package_total_value, package_unit, item_count = extract_measure_and_count(urun_adi, description, page_text)

    birim_fiyat = compute_unit_price(current_price, package_total_value, package_unit)



    urun_kodu = (

        clean_text(product_json.get("sku"))

        or extract_candidate_product_code(structured_product)

        or clean_text(satir.get("product_code"))

        or derive_site_product_code(urun_adresi)

    )



    return {

        **satir,

        "product_name": urun_adi,

        "product_url": urun_adresi,

        "brand": marka,

        "description": description,

        "product_code": urun_kodu,

        "current_price": current_price,

        "package_total_value": package_total_value,

        "package_unit": package_unit,

        "unit_price": birim_fiyat,

        "item_count": item_count or 1.0,

        "scrape_timestamp": kazima_zaman_damgasi.isoformat(),

    }





def find_reference_column(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:

    normalized_map = {normalize_for_match(column): column for column in df.columns}

    for alias in aliases:

        normalized_alias = normalize_for_match(alias)

        if normalized_alias in normalized_map:

            return normalized_map[normalized_alias]

    return None





def datetime_series_or_nat(df: pd.DataFrame, column: str) -> pd.Series:

    if column not in df:

        return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")

    return pd.to_datetime(df[column], errors="coerce", utc=True)





def load_reference_csv(reference_csv_path: str | Path) -> pd.DataFrame:

    yol = Path(reference_csv_path)

    if not yol.exists():

        raise FileNotFoundError(f"Referans CSV bulunamadı: {path}")



    sample_lines = yol.read_text(encoding="utf-8-sig").splitlines()

    candidate_delimiters = (";", ",", "\t")



    header_index = 0

    delimiter = ","

    best_score = -1

    for index, line in enumerate(sample_lines[:10]):

        scores = {aday: line.count(aday) for aday in candidate_delimiters}

        line_delimiter, score = max(scores.items(), key=lambda item: item[1])

        if score > best_score:

            best_score = score

            header_index = index

            delimiter = line_delimiter



    if best_score <= 0:

        return pd.read_csv(yol, encoding="utf-8-sig")



    referans_df = pd.read_csv(

        yol,

        sep=delimiter,

        skiprows=header_index,

        encoding="utf-8-sig",

    )

    referans_df.columns = [clean_text(column) or str(column) for column in referans_df.columns]

    return referans_df





def enrich_with_reference(raw_df: pd.DataFrame, referans_df: pd.DataFrame) -> pd.DataFrame:

    if raw_df.empty or referans_df.empty:

        enriched = raw_df.copy()

        if "first_reference_date" not in enriched:

            enriched["first_reference_date"] = None

        return enriched



    ref_df = referans_df.copy()

    url_col = find_reference_column(ref_df, REFERENCE_URL_KEYS)

    name_col = find_reference_column(ref_df, REFERENCE_NAME_KEYS)

    kategori_sutunu = find_reference_column(ref_df, REFERENCE_CATEGORY_KEYS)

    marka_sutunu = find_reference_column(ref_df, REFERENCE_BRAND_KEYS)

    tarih_sutunu = find_reference_column(ref_df, REFERENCE_DATE_KEYS)

    code_col = find_reference_column(ref_df, REFERENCE_CODE_KEYS)



    if url_col:

        ref_df["_url_key"] = ref_df[url_col].map(clean_text)

    if name_col:

        ref_df["_name_key"] = ref_df[name_col].map(normalize_for_match)

    if kategori_sutunu:

        ref_df["_category_key"] = ref_df[kategori_sutunu].map(normalize_for_match)



    enriched = raw_df.copy()

    enriched["_url_key"] = enriched["product_url"].map(clean_text)

    enriched["_name_key"] = enriched["product_name"].map(normalize_for_match)

    enriched["_category_key"] = enriched["site_main_category"].map(normalize_for_match)

    enriched["first_reference_date"] = None



    if url_col:

        ref_url = ref_df.drop_duplicates(subset=["_url_key"])

        enriched = enriched.merge(

            ref_url[

                ["_url_key"]

                + [column for column in (tarih_sutunu, marka_sutunu, kategori_sutunu, code_col) if column is not None]

            ],

            on="_url_key",

            how="left",

            suffixes=("", "_ref"),

        )

    else:

        for optional_col in (tarih_sutunu, marka_sutunu, kategori_sutunu, code_col):

            if optional_col:

                enriched[f"{optional_col}_ref"] = None



    if name_col:

        ref_name = ref_df.drop_duplicates(subset=["_name_key", "_category_key"])

        unresolved = (

            enriched[f"{date_col}_ref"].isna() if tarih_sutunu and f"{date_col}_ref" in enriched else pd.Series(True, index=enriched.index)

        )

        fallback_input = enriched.loc[unresolved, ["_name_key", "_category_key"]].copy()

        fallback_input["__row_index"] = fallback_input.index

        fallback_merge = fallback_input.merge(

            ref_name[

                ["_name_key", "_category_key"]

                + [column for column in (tarih_sutunu, marka_sutunu, kategori_sutunu, code_col) if column is not None]

            ],

            on=["_name_key", "_category_key"],

            how="left",

        )

        fallback_merge = fallback_merge.set_index("__row_index")

        for original_col in (tarih_sutunu, marka_sutunu, kategori_sutunu, code_col):

            if original_col is None:

                continue

            fallback_col = original_col

            target_col = f"{original_col}_ref"

            if target_col not in enriched:

                enriched[target_col] = None

            enriched.loc[unresolved, target_col] = enriched.loc[unresolved, target_col].combine_first(

                fallback_merge[fallback_col].reindex(enriched.loc[unresolved].index)

            )



    if tarih_sutunu and f"{date_col}_ref" in enriched:

        enriched["first_reference_date"] = pd.to_datetime(

            enriched[f"{date_col}_ref"],

            errors="coerce",

            utc=True,

            dayfirst=True,

        )



    if marka_sutunu and f"{brand_col}_ref" in enriched:

        enriched["brand"] = enriched["brand"].combine_first(enriched[f"{brand_col}_ref"].map(clean_text))

    if kategori_sutunu and f"{category_col}_ref" in enriched:

        enriched["site_main_category"] = enriched["site_main_category"].combine_first(

            enriched[f"{category_col}_ref"].map(clean_text)

        )

    if code_col and f"{code_col}_ref" in enriched:

        enriched["product_code"] = enriched["product_code"].combine_first(enriched[f"{code_col}_ref"].map(clean_text))



    drop_columns = [column for column in enriched.columns if column.endswith("_ref")]

    drop_columns.extend(["_url_key", "_name_key", "_category_key"])

    return enriched.drop(columns=[column for column in drop_columns if column in enriched.columns])





def build_market_table() -> pd.DataFrame:

    return pd.DataFrame([{"market_id": 1, "market_adi": "ŞOK"}])





def build_products_table(sql_ready: pd.DataFrame) -> pd.DataFrame:

    if sql_ready.empty:

        return pd.DataFrame(

            columns=[

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

        )



    urunler_df = (

        sql_ready.sort_values(["urun_kategori", "urun_ad", "urun_url"])

        .drop_duplicates(subset=["urun_url", "urun_ad"])

        .reset_index(drop=True)

    )

    urunler_df["id"] = urunler_df.index + 1

    urunler_df["site_product_code"] = urunler_df["product_code"].combine_first(

        urunler_df["product_url"].map(derive_site_product_code)

    )

    urunler_df["url_key"] = urunler_df["product_url"].map(derive_url_key)

    urunler_df["sira_no"] = urunler_df.index + 1

    urunler_df["eklenme_tarihi"] = datetime_series_or_nat(urunler_df, "first_reference_date").combine_first(

        datetime_series_or_nat(urunler_df, "scrape_timestamp")

    )

    urunler_df["market_adi"] = "ŞOK"

    urunler_df["urun_marka"] = urunler_df["brand"].map(clean_text)

    return urunler_df[

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





def build_price_series_table(sql_ready: pd.DataFrame, urunler_df: pd.DataFrame) -> pd.DataFrame:

    if sql_ready.empty or urunler_df.empty:

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



    product_id_map = {

        (clean_text(satir["urun_url"]), clean_text(satir["urun_ad"])): int(satir["id"])

        for satir in urunler_df.to_dict("records")

    }

    fiyat_serisi_df = sql_ready.copy()

    fiyat_serisi_df["urun_id"] = [

        product_id_map.get((clean_text(adres), clean_text(ad)))

        for adres, ad in zip(fiyat_serisi_df["urun_url"], fiyat_serisi_df["urun_ad"])

    ]

    fiyat_serisi_df = fiyat_serisi_df[fiyat_serisi_df["urun_id"].notna()].reset_index(drop=True)

    fiyat_serisi_df["kayit_id"] = fiyat_serisi_df.index + 1

    fiyat_serisi_df["urun_fiyat"] = pd.to_numeric(fiyat_serisi_df["current_price"], errors="coerce")

    fiyat_serisi_df["kazima_tarihi"] = pd.to_datetime(fiyat_serisi_df["scrape_timestamp"], errors="coerce", utc=True)

    fiyat_serisi_df["adet_sayisi"] = pd.to_numeric(fiyat_serisi_df["item_count"], errors="coerce").fillna(1.0)

    return fiyat_serisi_df[

        [

            "kayit_id",

            "urun_id",

            "urun_fiyat",

            "package_total_value",

            "package_unit",

            "unit_price",

            "kazima_tarihi",

            "adet_sayisi",

        ]

    ].rename(

        columns={

            "package_total_value": "gramaj_degeri",

            "package_unit": "gramaj_birimi",

            "unit_price": "birim_fiyat",

        }

    )





def build_audit_table(listing_df: pd.DataFrame) -> pd.DataFrame:

    if listing_df.empty:

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

            live_total_count=("live_total_count", first_non_null),

            collected_product_urls=("product_url", "nunique"),

        )

        .rename(columns={"site_main_category": "kategori"})

    )

    audit_df["sayim_durumu"] = audit_df.apply(

        lambda satir: "uyumlu"

        if pd.notna(satir["input_expected_count"]) and satir["input_expected_count"] == satir["live_total_count"]

        else "canli_sayim_degismis",

        axis=1,

    )

    return audit_df





def format_sql_tables(raw_df: pd.DataFrame) -> dict[str, pd.DataFrame]:

    sql_ready = deduplicate_relisted_products(raw_df)

    sql_ready["market_id"] = 1

    sql_ready["urun_ad"] = sql_ready["product_name"]

    sql_ready["urun_url"] = sql_ready["product_url"]

    sql_ready["urun_kategori"] = sql_ready["site_main_category"]



    market_df = build_market_table()

    urunler_df = build_products_table(sql_ready)

    fiyat_serisi_df = build_price_series_table(sql_ready, urunler_df)

    return {

        "market": market_df,

        "urunler": urunler_df,

        "fiyat_zaman_serisi": fiyat_serisi_df,

    }





def export_outputs(cikti_dizini: str | Path, ciktilar: dict[str, pd.DataFrame]) -> None:

    cikti_dizini = Path(cikti_dizini)

    cikti_dizini.mkdir(parents=True, exist_ok=True)

    for ad, df in ciktilar.items():

        df.to_csv(cikti_dizini / f"{name}.csv", index=False, encoding="utf-8-sig")





class SokMarketScraper:

    def __init__(

        self,

        pause_range: tuple[float, float] = (0.2, 0.5),

        timeout: int = 30,

    ) -> None:

        self.pause_range = pause_range

        self.timeout = timeout

        self.session = requests.Session()

        self.session.headers.update(DEFAULT_HEADERS)

        self.failed_product_rows: list[dict[str, Any]] = []



    def _sleep(self) -> None:

        time.sleep(random.uniform(*self.pause_range))



    def fetch_html(self, adres: str) -> str:

        response = self.session.get(adres, timeout=self.timeout)

        response.raise_for_status()

        return response.text



    def collect_category_listings(self, kategori: KategoriHedefi) -> pd.DataFrame:

        first_page_url = build_page_url(kategori.adres, 1)

        first_html = self.fetch_html(first_page_url)

        live_total_count, first_rows = parse_category_listing_page(first_html, kategori, first_page_url)



        tum_satirlar = list(first_rows)

        page_size = len(first_rows) or 20

        total_pages = math.ceil((live_total_count or len(first_rows) or 1) / page_size)



        for sayfa in range(2, total_pages + 1):

            self._sleep()

            sayfa_adresi = build_page_url(kategori.adres, sayfa)

            html = self.fetch_html(sayfa_adresi)

            _, satirlar = parse_category_listing_page(html, kategori, sayfa_adresi)

            if not satirlar:

                break

            tum_satirlar.extend(satirlar)



        listing_df = pd.DataFrame(tum_satirlar)

        return listing_df.drop_duplicates(subset=["product_url", "site_main_category"]).reset_index(drop=True)



    def collect_all_listings(self, categories: list[KategoriHedefi]) -> pd.DataFrame:

        frames: list[pd.DataFrame] = []

        for kategori in tqdm(categories, desc="Kategori sayfaları"):

            frames.append(self.collect_category_listings(kategori))

        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()



    def collect_product_details(

        self,

        listing_df: pd.DataFrame,

        urun_siniri: int | None = None,

        kazima_zaman_damgasi: datetime | None = None,

    ) -> pd.DataFrame:

        satirlar = listing_df.to_dict("records")

        if urun_siniri is not None:

            satirlar = satirlar[:urun_siniri]



        scraped_rows: list[dict[str, Any]] = []

        kazima_zaman_damgasi = normalize_scrape_timestamp(kazima_zaman_damgasi)

        self.failed_product_rows = []



        for satir in tqdm(satirlar, desc="Ürün detayları"):

            try:

                html = self.fetch_html(satir["product_url"])

                scraped_rows.append(parse_product_detail_page(html, satir, kazima_zaman_damgasi))

            except requests.RequestException as exc:

                failed_row = dict(satir)

                failed_row["error_type"] = type(exc).__name__

                failed_row["error_message"] = str(exc)

                failed_row["status_code"] = getattr(getattr(exc, "response", None), "status_code", None)

                failed_row["scrape_timestamp"] = kazima_zaman_damgasi.isoformat()

                self.failed_product_rows.append(failed_row)

                LOGGER.warning("Urun detayi atlandi: %s (%s)", satir["product_url"], exc)

            self._sleep()



        if self.failed_product_rows:

            LOGGER.warning("Urun detay scrape tamamlandi; atlanan urun sayisi: %s", len(self.failed_product_rows))



        return pd.DataFrame(scraped_rows)





def run_pipeline(

    reference_csv_path: str | Path,

    cikti_dizini: str | Path | None = None,

    categories: list[KategoriHedefi] | None = None,

    pause_range: tuple[float, float] = (0.2, 0.5),

    urun_siniri: int | None = None,

    kazima_zaman_damgasi: datetime | None = None,

) -> dict[str, pd.DataFrame]:

    categories = categories or KATEGORI_HEDEFLERI

    scraper = SokMarketScraper(pause_range=pause_range)



    listing_df = scraper.collect_all_listings(categories)

    listing_unique_df = deduplicate_listings(listing_df)

    raw_df = scraper.collect_product_details(

        listing_unique_df,

        urun_siniri=urun_siniri,

        kazima_zaman_damgasi=kazima_zaman_damgasi,

    )



    referans_df = load_reference_csv(reference_csv_path)

    enriched_raw_df = enrich_with_reference(raw_df, referans_df)

    enriched_raw_df = deduplicate_relisted_products(enriched_raw_df)

    enriched_raw_df = enriched_raw_df.sort_values(["site_main_category", "product_name"]).reset_index(drop=True)

    enriched_raw_df["market_id"] = 1



    ciktilar = format_sql_tables(enriched_raw_df)

    ciktilar["raw_products"] = enriched_raw_df

    ciktilar["scrape_audit"] = build_audit_table(listing_df)

    if scraper.failed_product_rows:

        ciktilar["failed_products"] = pd.DataFrame(scraper.failed_product_rows)



    if cikti_dizini is not None:

        export_outputs(cikti_dizini, ciktilar)



    return ciktilar





def build_cli_parser() -> argparse.ArgumentParser:

    komut_ayristirici = argparse.ArgumentParser(description="ŞOK kategori scraper")

    komut_ayristirici.add_argument(

        "--reference-csv",

        default=str(DEFAULT_REFERENCE_CSV),

        help="Referans sokdata.csv yolu",

    )

    komut_ayristirici.add_argument("--output-dir", default="outputs", help="Çıktı klasörü")

    komut_ayristirici.add_argument("--limit", type=int, default=None, help="Test amaçlı ürün limiti")

    komut_ayristirici.add_argument("--min-sleep", type=float, default=0.2, help="İstekler arası minimum bekleme")

    komut_ayristirici.add_argument("--max-sleep", type=float, default=0.5, help="İstekler arası maksimum bekleme")

    komut_ayristirici.add_argument(

        "--scrape-datetime",

        type=parse_scrape_datetime_input,

        default=None,

        help="Çekimi bu tarih/saatle etiketle. Örnek: 2026-05-09 veya 2026-05-09T19:00:00+03:00",

    )

    return komut_ayristirici





def main(argv: list[str] | None = None) -> None:

    komut_ayristirici = build_cli_parser()

    args, _unknown = komut_ayristirici.parse_known_args(argv)



    reference_csv_path = Path(args.reference_csv)

    if not reference_csv_path.exists():

        komut_ayristirici.error(

            "Referans CSV bulunamadı. "

            f"Beklenen yol: {reference_csv_path}. "

            "İstersen --reference-csv ile doğru dosya yolunu ver."

        )



    ciktilar = run_pipeline(

        reference_csv_path=reference_csv_path,

        cikti_dizini=args.cikti_dizini,

        pause_range=(args.min_sleep, args.max_sleep),

        urun_siniri=args.limit,

        kazima_zaman_damgasi=args.scrape_datetime,

    )



    print("\nOluşan tablolar:")

    for ad, df in ciktilar.items():

        print(f"- {name}: {len(df)} satır")





if __name__ == "__main__":

    main()

