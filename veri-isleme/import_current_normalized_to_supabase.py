import argparse

import csv

import os

import re

import unicodedata

from datetime import datetime

from pathlib import Path

from typing import Optional



import psycopg2

from psycopg2.extras import execute_values

from dotenv import load_dotenv



from product_identity import build_product_identity, clean_optional_text





MARKET_NAME_ALIASES = {

    "migros": "MİGROS",

    "sok": "ŞOK",

    "sokmarket": "ŞOK",

}





def argumanlari_ayristir() -> argparse.Namespace:

    komut_ayristirici = argparse.ArgumentParser(

        description="Guncel normalize edilmis market verisini Supabase'e kalici urun kimligiyle aktarir."

    )

    komut_ayristirici.add_argument("--urunler-csv", type=Path, required=True)

    komut_ayristirici.add_argument("--raw-products-csv", type=Path, required=True)

    komut_ayristirici.add_argument("--normalized-price-csv", type=Path, required=True)

    komut_ayristirici.add_argument(

        "--market-name",

        type=str,

        default=None,

        help="CSV'den otomatik cikmazsa market adini zorla belirt.",

    )

    komut_ayristirici.add_argument(

        "--migration-sql",

        type=Path,

        default=Path("migrations/001_product_identity.sql"),

    )

    komut_ayristirici.add_argument(

        "--skip-migration",

        action="store_true",

        help="Migration SQL calistirmadan import et.",

    )

    komut_ayristirici.add_argument(

        "--audit-csv",

        type=Path,

        default=Path("outputs/current_import_audit.csv"),

    )

    komut_ayristirici.add_argument(

        "--apply",

        action="store_true",

        help="Gercekten veritabanina yaz. Bu bayrak yoksa sadece dry-run calisir.",

    )

    return komut_ayristirici.argumanlari_ayristir()





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





def read_sql_file(yol: Path) -> str:

    return yol.read_text(encoding="utf-8")





def parse_datetime(value: Optional[str]) -> Optional[datetime]:

    text = clean_optional_text(value)

    if not text:

        return None

    try:

        return datetime.fromisoformat(text)

    except ValueError:

        return None





def parse_float(value: Optional[str]) -> Optional[float]:

    text = clean_optional_text(value)

    if not text:

        return None

    return float(text.replace(",", "."))





def pick_first(satir: dict[str, str], *columns: str) -> Optional[str]:

    for column in columns:

        value = clean_optional_text(satir.get(column))

        if value is not None:

            return value

    return None





def normalize_market_alias_key(value: str) -> str:

    text = unicodedata.normalize("NFKD", value.casefold())

    text = "".join(char for char in text if not unicodedata.combining(char))

    text = (

        text.replace("ı", "i")

        .replace("ş", "s")

        .replace("ğ", "g")

        .replace("ç", "c")

        .replace("ö", "o")

        .replace("ü", "u")

    )

    return re.sub(r"[^a-z0-9]+", "", text)





def canonicalize_market_name(value: Optional[str]) -> Optional[str]:

    text = clean_optional_text(value)

    if text is None:

        return None

    return MARKET_NAME_ALIASES.get(normalize_market_alias_key(text), text)





def normalize_signature_text(value: Optional[object]) -> str:

    text = clean_optional_text(value)

    if text is None:

        return ""

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





def build_legacy_signature(

    *,

    urun_ad: Optional[object],

    urun_kategori: Optional[object],

    urun_marka: Optional[object],

    site_urun_kodu: Optional[object],

    adres_anahtari: Optional[object],

    urun_url: Optional[object],

) -> Optional[str]:

    if (

        clean_optional_text(site_urun_kodu)

        or clean_optional_text(adres_anahtari)

        or clean_optional_text(urun_url)

    ):

        return None



    parts = [

        normalize_signature_text(urun_ad),

        normalize_signature_text(urun_kategori),

        normalize_signature_text(urun_marka),

    ]

    if not parts[0]:

        return None

    return " | ".join(parts)





def detect_market_name(

    urunler_rows: list[dict[str, str]],

    ham_satirlar: list[dict[str, str]],

    explicit_market_name: Optional[str],

) -> str:

    canonical_explicit = canonicalize_market_name(explicit_market_name)

    if canonical_explicit:

        return canonical_explicit



    for satir in urunler_rows:

        value = canonicalize_market_name(satir.get("market_adi"))

        if value:

            return value



    for satir in ham_satirlar:

        value = canonicalize_market_name(satir.get("market_adi"))

        if value:

            return value



    raise ValueError("Market adi tespit edilemedi. --market-name ile belirt.")





def load_market_id(cur, market_adi: str) -> int:

    market_adi = canonicalize_market_name(market_adi) or market_adi

    cur.execute("SELECT market_id FROM market WHERE market_adi = %s ORDER BY market_id LIMIT 1", (market_adi,))

    satir = cur.fetchone()

    if satir:

        return satir[0]



    cur.execute(

        "INSERT INTO market (market_adi) VALUES (%s) ON CONFLICT DO NOTHING RETURNING market_id",

        (market_adi,),

    )

    satir = cur.fetchone()

    if satir:

        return satir[0]

    cur.execute("SELECT market_id FROM market WHERE market_adi = %s ORDER BY market_id LIMIT 1", (market_adi,))

    return cur.fetchone()[0]





def build_current_rows(

    urunler_rows: list[dict[str, str]],

    ham_satirlar: list[dict[str, str]],

    fiyat_satirlari: list[dict[str, str]],

) -> list[dict[str, object]]:

    urunler_by_id = {satir["id"]: satir for satir in urunler_rows}

    adrese_gore_ham = {satir["product_url"]: satir for satir in ham_satirlar if satir.get("product_url")}

    raw_by_name = {satir["product_name"]: satir for satir in ham_satirlar if satir.get("product_name")}



    merged_rows: list[dict[str, object]] = []

    for fiyat_satiri in fiyat_satirlari:

        urun_row = urunler_by_id.get(fiyat_satiri["urun_id"])

        if not urun_row:

            continue



        ham_satir = adrese_gore_ham.get(urun_row["urun_url"]) or raw_by_name.get(urun_row["urun_ad"])



        identity = build_product_identity(

            site_urun_kodu=pick_first(ham_satir or {}, "product_code", "site_product_code")

            or pick_first(urun_row, "site_product_code"),

            urun_url=pick_first(ham_satir or {}, "product_url") or pick_first(urun_row, "urun_url"),

        )

        urun_ad = pick_first(urun_row, "urun_ad") or pick_first(ham_satir or {}, "product_name")

        urun_kategori = (

            pick_first(urun_row, "urun_kategori")

            or pick_first(ham_satir or {}, "site_main_category", "reference_category_name")

        )

        urun_marka = (

            pick_first(ham_satir or {}, "brand", "listing_brand")

            or pick_first(urun_row, "urun_marka")

        )

        merged_rows.append(

            {

                "urun_ad": urun_ad,

                "urun_url": identity.urun_url or "",

                "urun_kategori": urun_kategori,

                "urun_marka": urun_marka,

                "site_product_code": identity.site_urun_kodu,

                "url_key": identity.adres_anahtari,

                "legacy_signature": build_legacy_signature(

                    urun_ad=urun_ad,

                    urun_kategori=urun_kategori,

                    urun_marka=urun_marka,

                    site_urun_kodu=identity.site_urun_kodu,

                    adres_anahtari=identity.adres_anahtari,

                    urun_url=identity.urun_url,

                ),

                "urun_fiyat": parse_float(fiyat_satiri.get("urun_fiyat")),

                "gramaj_degeri": parse_float(fiyat_satiri.get("gramaj_degeri")),

                "gramaj_birimi": clean_optional_text(fiyat_satiri.get("gramaj_birimi")),

                "birim_fiyat": parse_float(

                    pick_first(fiyat_satiri, "unit_price", "birim_fiyat")

                ),

                "kazima_tarihi": parse_datetime(fiyat_satiri.get("kazima_tarihi")),

            }

        )



    return merged_rows





def load_existing_product_maps(cur, market_kimligi: int):

    cur.execute(

        """
        SELECT id, market_id, urun_ad, urun_kategori, urun_marka, urun_url, site_product_code, url_key
        FROM urunler
        WHERE market_id = %s
        """,

        (market_kimligi,),

    )

    by_site_code = {}

    by_url_key = {}

    by_url = {}

    by_legacy_signature = {}

    for satir in cur.fetchall():

        urun_id, _, urun_ad, urun_kategori, urun_marka, urun_url, site_urun_kodu, adres_anahtari = satir

        if site_urun_kodu:

            by_site_code[site_urun_kodu] = urun_id

        if adres_anahtari:

            by_url_key[adres_anahtari] = urun_id

        if urun_url:

            by_url[urun_url] = urun_id

        legacy_signature = build_legacy_signature(

            urun_ad=urun_ad,

            urun_kategori=urun_kategori,

            urun_marka=urun_marka,

            site_urun_kodu=site_urun_kodu,

            adres_anahtari=adres_anahtari,

            urun_url=urun_url,

        )

        if legacy_signature:

            by_legacy_signature[legacy_signature] = urun_id

    return by_site_code, by_url_key, by_url, by_legacy_signature





def resolve_existing_product_id(satir: dict[str, object], by_site_code, by_url_key, by_url, by_legacy_signature):

    if satir["site_product_code"] and satir["site_product_code"] in by_site_code:

        return by_site_code[satir["site_product_code"]], "site_product_code"

    if satir["url_key"] and satir["url_key"] in by_url_key:

        return by_url_key[satir["url_key"]], "url_key"

    if satir["urun_url"] and satir["urun_url"] in by_url:

        return by_url[satir["urun_url"]], "urun_url"

    if satir.get("legacy_signature") and satir["legacy_signature"] in by_legacy_signature:

        return by_legacy_signature[satir["legacy_signature"]], "legacy_signature"

    return None, ""





def register_product_identity(satir: dict[str, object], urun_id: int, by_site_code, by_url_key, by_url, by_legacy_signature) -> None:

    if satir["site_product_code"]:

        by_site_code[satir["site_product_code"]] = urun_id

    if satir["url_key"]:

        by_url_key[satir["url_key"]] = urun_id

    if satir["urun_url"]:

        by_url[satir["urun_url"]] = urun_id

    if satir.get("legacy_signature"):

        by_legacy_signature[satir["legacy_signature"]] = urun_id





def insert_product(cur, market_kimligi: int, satir: dict[str, object], market_adi: str) -> int:

    cur.execute(

        """
        INSERT INTO urunler
        (market_id, urun_ad, urun_url, urun_kategori, urun_marka, market_adi, site_product_code, url_key)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,

        (

            market_kimligi,

            satir["urun_ad"],

            satir["urun_url"],

            satir["urun_kategori"],

            satir["urun_marka"],

            market_adi,

            satir["site_product_code"],

            satir["url_key"],

        ),

    )

    return cur.fetchone()[0]





def update_product(cur, urun_id: int, satir: dict[str, object], market_adi: str) -> None:

    cur.execute(

        """
        UPDATE urunler
        SET urun_ad = %s,
            urun_url = %s,
            urun_kategori = %s,
            urun_marka = %s,
            market_adi = %s,
            site_product_code = COALESCE(site_product_code, %s),
            url_key = COALESCE(url_key, %s)
        WHERE id = %s
        """,

        (

            satir["urun_ad"],

            satir["urun_url"],

            satir["urun_kategori"],

            satir["urun_marka"],

            market_adi,

            satir["site_product_code"],

            satir["url_key"],

            urun_id,

        ),

    )





def insert_price(cur, urun_id: int, satir: dict[str, object]) -> int:

    cur.execute(

        """
        INSERT INTO fiyat_zaman_serisi
        (urun_id, urun_fiyat, gramaj_degeri, gramaj_birimi, birim_fiyat, kazima_tarihi)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,

        (

            urun_id,

            satir["urun_fiyat"],

            satir["gramaj_degeri"],

            satir["gramaj_birimi"],

            satir["birim_fiyat"],

            satir["kazima_tarihi"],

        ),

    )

    return cur.rowcount





def split_current_rows_for_apply(

    guncel_satirlar: list[dict[str, object]],

) -> tuple[list[dict[str, object]], list[dict[str, object]]]:

    stable_rows = []

    eski_satirlar = []

    for satir in guncel_satirlar:

        if satir["site_product_code"] or satir["url_key"] or satir["urun_url"]:

            stable_rows.append(satir)

        else:

            eski_satirlar.append(satir)

    return stable_rows, eski_satirlar





def apply_bulk_rows(

    cur,

    market_kimligi: int,

    market_adi: str,

    satirlar: list[dict[str, object]],

    predicted_audit_rows: list[dict[str, object]],

) -> tuple[list[dict[str, object]], int, int, int]:

    if not satirlar:

        return [], 0, 0, 0



    cur.execute(

        """
        CREATE TEMP TABLE _current_import_payload (
            urun_ad TEXT NOT NULL,
            urun_url TEXT NOT NULL,
            urun_kategori TEXT,
            urun_marka TEXT,
            site_product_code TEXT,
            url_key TEXT,
            urun_fiyat NUMERIC,
            gramaj_degeri NUMERIC,
            gramaj_birimi TEXT,
            birim_fiyat NUMERIC,
            kazima_tarihi TIMESTAMPTZ,
            matched_urun_id BIGINT,
            matched_by TEXT
        ) ON COMMIT DROP
        """

    )

    execute_values(

        cur,

        """
        INSERT INTO _current_import_payload
        (urun_ad, urun_url, urun_kategori, urun_marka, site_product_code, url_key,
         urun_fiyat, gramaj_degeri, gramaj_birimi, birim_fiyat, kazima_tarihi)
        VALUES %s
        """,

        [

            (

                satir["urun_ad"],

                satir["urun_url"],

                satir["urun_kategori"],

                satir["urun_marka"],

                satir["site_product_code"],

                satir["url_key"],

                satir["urun_fiyat"],

                satir["gramaj_degeri"],

                satir["gramaj_birimi"],

                satir["birim_fiyat"],

                satir["kazima_tarihi"],

            )

            for satir in satirlar

        ],

        page_size=500,

    )



    for column in ("site_product_code", "url_key", "urun_url"):

        cur.execute(

            f"""
            UPDATE _current_import_payload AS p
            SET matched_urun_id = u.id,
                matched_by = %s
            FROM urunler AS u
            WHERE u.market_id = %s
              AND p.{column} IS NOT NULL
              AND p.{column} <> ''
              AND u.{column} = p.{column}
              AND p.matched_urun_id IS NULL
            """,

            (column, market_kimligi),

        )



    cur.execute(

        """
        UPDATE urunler AS u
        SET urun_ad = p.urun_ad,
            urun_url = p.urun_url,
            urun_kategori = p.urun_kategori,
            urun_marka = p.urun_marka,
            market_adi = %s,
            site_product_code = COALESCE(u.site_product_code, p.site_product_code),
            url_key = COALESCE(u.url_key, p.url_key)
        FROM _current_import_payload AS p
        WHERE u.id = p.matched_urun_id
        """,

        (market_adi,),

    )



    cur.execute(

        """
        INSERT INTO urunler
        (market_id, urun_ad, urun_url, urun_kategori, urun_marka, market_adi, site_product_code, url_key)
        SELECT %s, p.urun_ad, p.urun_url, p.urun_kategori, p.urun_marka, %s, p.site_product_code, p.url_key
        FROM (
            SELECT DISTINCT ON (
                COALESCE(
                    CASE
                        WHEN site_product_code IS NOT NULL AND site_product_code <> '' THEN 'site:' || site_product_code
                    END,
                    CASE
                        WHEN url_key IS NOT NULL AND url_key <> '' THEN 'url_key:' || url_key
                    END,
                    CASE
                        WHEN urun_url IS NOT NULL AND urun_url <> '' THEN 'url:' || urun_url
                    END
                )
            )
                urun_ad,
                urun_url,
                urun_kategori,
                urun_marka,
                site_product_code,
                url_key
            FROM _current_import_payload
            WHERE matched_urun_id IS NULL
            ORDER BY
                COALESCE(
                    CASE
                        WHEN site_product_code IS NOT NULL AND site_product_code <> '' THEN 'site:' || site_product_code
                    END,
                    CASE
                        WHEN url_key IS NOT NULL AND url_key <> '' THEN 'url_key:' || url_key
                    END,
                    CASE
                        WHEN urun_url IS NOT NULL AND urun_url <> '' THEN 'url:' || urun_url
                    END
                ),
                urun_ad
        ) AS p
        """,

        (market_kimligi, market_adi),

    )



    for column in ("site_product_code", "url_key", "urun_url"):

        cur.execute(

            f"""
            UPDATE _current_import_payload AS p
            SET matched_urun_id = u.id,
                matched_by = %s
            FROM urunler AS u
            WHERE u.market_id = %s
              AND p.{column} IS NOT NULL
              AND p.{column} <> ''
              AND u.{column} = p.{column}
              AND p.matched_urun_id IS NULL
            """,

            (column, market_kimligi),

        )



    cur.execute(

        """
        INSERT INTO fiyat_zaman_serisi
        (urun_id, urun_fiyat, gramaj_degeri, gramaj_birimi, birim_fiyat, kazima_tarihi)
        SELECT p.matched_urun_id, p.urun_fiyat, p.gramaj_degeri, p.gramaj_birimi, p.birim_fiyat, p.kazima_tarihi
        FROM _current_import_payload AS p
        WHERE p.matched_urun_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """

    )

    eklenen_fiyatlar = cur.rowcount



    cur.execute(

        """
        SELECT urun_ad, urun_url, COALESCE(site_product_code, ''), COALESCE(url_key, ''),
               COALESCE(matched_by, ''), matched_urun_id, kazima_tarihi
        FROM _current_import_payload
        ORDER BY urun_ad
        """

    )

    resolved_rows = cur.fetchall()



    predicted_lookup = {

        (satir["urun_ad"], satir["urun_url"], satir["site_product_code"] or "", satir["url_key"] or ""): satir

        for satir in predicted_audit_rows

    }

    predicted_by_name = {satir["urun_ad"]: satir for satir in predicted_audit_rows}

    denetim_satirlari = []

    for urun_ad, urun_url, site_urun_kodu, adres_anahtari, eslestiren, matched_urun_id, kazima_tarihi in resolved_rows:

        predicted = predicted_lookup.get((urun_ad, urun_url, site_urun_kodu, adres_anahtari)) or predicted_by_name.get(urun_ad)

        product_action = "insert" if predicted["product_action"] == "insert" else "update"

        denetim_satirlari.append(

            {

                "urun_ad": urun_ad,

                "urun_url": urun_url,

                "site_product_code": site_urun_kodu,

                "url_key": adres_anahtari,

                "matched_by": eslestiren,

                "resolved_urun_id": matched_urun_id,

                "product_action": product_action,

                "price_action": "inserted",

                "kazima_tarihi": kazima_tarihi.isoformat() if kazima_tarihi else "",

            }

        )



    eklenen_urunler = sum(1 for satir in denetim_satirlari if satir["product_action"] == "insert")

    guncellenen_urunler = sum(1 for satir in denetim_satirlari if satir["product_action"] == "update")

    return denetim_satirlari, eklenen_urunler, guncellenen_urunler, eklenen_fiyatlar





def apply_legacy_bulk_rows(

    cur,

    market_kimligi: int,

    market_adi: str,

    satirlar: list[dict[str, object]],

    predicted_audit_rows: list[dict[str, object]],

) -> tuple[list[dict[str, object]], int, int, int]:

    if not satirlar:

        return [], 0, 0, 0



    cur.execute(

        """
        CREATE TEMP TABLE _legacy_import_payload (
            urun_ad TEXT NOT NULL,
            urun_url TEXT NOT NULL,
            urun_kategori TEXT,
            urun_marka TEXT,
            urun_fiyat NUMERIC,
            gramaj_degeri NUMERIC,
            gramaj_birimi TEXT,
            birim_fiyat NUMERIC,
            kazima_tarihi TIMESTAMPTZ,
            matched_urun_id BIGINT,
            matched_by TEXT
        ) ON COMMIT DROP
        """

    )

    execute_values(

        cur,

        """
        INSERT INTO _legacy_import_payload
        (urun_ad, urun_url, urun_kategori, urun_marka, urun_fiyat, gramaj_degeri, gramaj_birimi, birim_fiyat, kazima_tarihi)
        VALUES %s
        """,

        [

            (

                satir["urun_ad"],

                satir["urun_url"],

                satir["urun_kategori"],

                satir["urun_marka"],

                satir["urun_fiyat"],

                satir["gramaj_degeri"],

                satir["gramaj_birimi"],

                satir["birim_fiyat"],

                satir["kazima_tarihi"],

            )

            for satir in satirlar

        ],

        page_size=500,

    )



    cur.execute(

        """
        UPDATE _legacy_import_payload AS p
        SET matched_urun_id = u.id,
            matched_by = 'legacy_signature'
        FROM urunler AS u
        WHERE u.market_id = %s
          AND COALESCE(u.site_product_code, '') = ''
          AND COALESCE(u.url_key, '') = ''
          AND COALESCE(u.urun_url, '') = ''
          AND u.urun_ad = p.urun_ad
          AND COALESCE(u.urun_kategori, '') = COALESCE(p.urun_kategori, '')
          AND COALESCE(u.urun_marka, '') = COALESCE(p.urun_marka, '')
          AND p.matched_urun_id IS NULL
        """,

        (market_kimligi,),

    )



    cur.execute(

        """
        UPDATE urunler AS u
        SET urun_ad = p.urun_ad,
            urun_kategori = p.urun_kategori,
            urun_marka = p.urun_marka,
            market_adi = %s
        FROM _legacy_import_payload AS p
        WHERE u.id = p.matched_urun_id
        """,

        (market_adi,),

    )



    cur.execute(

        """
        INSERT INTO urunler
        (market_id, urun_ad, urun_url, urun_kategori, urun_marka, market_adi, site_product_code, url_key)
        SELECT %s, p.urun_ad, '', p.urun_kategori, p.urun_marka, %s, NULL, NULL
        FROM (
            SELECT DISTINCT ON (urun_ad, COALESCE(urun_kategori, ''), COALESCE(urun_marka, ''))
                urun_ad,
                urun_kategori,
                urun_marka
            FROM _legacy_import_payload
            WHERE matched_urun_id IS NULL
            ORDER BY urun_ad, COALESCE(urun_kategori, ''), COALESCE(urun_marka, '')
        ) AS p
        """,

        (market_kimligi, market_adi),

    )



    cur.execute(

        """
        UPDATE _legacy_import_payload AS p
        SET matched_urun_id = u.id,
            matched_by = 'legacy_signature'
        FROM urunler AS u
        WHERE u.market_id = %s
          AND COALESCE(u.site_product_code, '') = ''
          AND COALESCE(u.url_key, '') = ''
          AND COALESCE(u.urun_url, '') = ''
          AND u.urun_ad = p.urun_ad
          AND COALESCE(u.urun_kategori, '') = COALESCE(p.urun_kategori, '')
          AND COALESCE(u.urun_marka, '') = COALESCE(p.urun_marka, '')
          AND p.matched_urun_id IS NULL
        """,

        (market_kimligi,),

    )



    cur.execute(

        """
        INSERT INTO fiyat_zaman_serisi
        (urun_id, urun_fiyat, gramaj_degeri, gramaj_birimi, birim_fiyat, kazima_tarihi)
        SELECT p.matched_urun_id, p.urun_fiyat, p.gramaj_degeri, p.gramaj_birimi, p.birim_fiyat, p.kazima_tarihi
        FROM _legacy_import_payload AS p
        WHERE p.matched_urun_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """

    )

    eklenen_fiyatlar = cur.rowcount



    cur.execute(

        """
        SELECT urun_ad, urun_url, matched_by, matched_urun_id, kazima_tarihi
        FROM _legacy_import_payload
        ORDER BY urun_ad
        """

    )

    resolved_rows = cur.fetchall()



    predicted_lookup = {

        (satir["urun_ad"], satir["kazima_tarihi"]): satir

        for satir in predicted_audit_rows

    }

    predicted_by_name = {satir["urun_ad"]: satir for satir in predicted_audit_rows}

    denetim_satirlari = []

    for urun_ad, urun_url, eslestiren, matched_urun_id, kazima_tarihi in resolved_rows:

        predicted = (

            predicted_lookup.get((urun_ad, kazima_tarihi.isoformat() if kazima_tarihi else ""))

            or predicted_by_name.get(urun_ad)

            or {"product_action": "insert"}

        )

        product_action = "insert" if predicted["product_action"] == "insert" else "update"

        denetim_satirlari.append(

            {

                "urun_ad": urun_ad,

                "urun_url": urun_url,

                "site_product_code": "",

                "url_key": "",

                "matched_by": eslestiren,

                "resolved_urun_id": matched_urun_id,

                "product_action": product_action,

                "price_action": "inserted",

                "kazima_tarihi": kazima_tarihi.isoformat() if kazima_tarihi else "",

            }

        )



    eklenen_urunler = sum(1 for satir in denetim_satirlari if satir["product_action"] == "insert")

    guncellenen_urunler = sum(1 for satir in denetim_satirlari if satir["product_action"] == "update")

    return denetim_satirlari, eklenen_urunler, guncellenen_urunler, eklenen_fiyatlar





def main() -> None:

    args = argumanlari_ayristir()

    load_dotenv(".env")

    veritabani_adresi = os.environ["DATABASE_URL"]



    urunler_rows = read_csv(args.urunler_csv)

    ham_satirlar = read_csv(args.raw_products_csv)

    fiyat_satirlari = read_csv(args.normalized_price_csv)

    guncel_satirlar = build_current_rows(urunler_rows, ham_satirlar, fiyat_satirlari)



    baglanti = psycopg2.connect(veritabani_adresi)

    cur = baglanti.imlec()

    try:

        if not args.skip_migration:

            sql = read_sql_file(args.migration_sql).strip()

            if sql:

                cur.execute(sql)

                baglanti.commit()



        market_adi = detect_market_name(urunler_rows, ham_satirlar, args.market_adi)

        market_kimligi = load_market_id(cur, market_adi)

        baglanti.commit()



        by_site_code, by_url_key, by_url, by_legacy_signature = load_existing_product_maps(cur, market_kimligi)



        predicted_audit_rows = []

        would_insert_products = 0

        would_update_products = 0

        for satir in guncel_satirlar:

            urun_id, eslestiren = resolve_existing_product_id(

                satir,

                by_site_code,

                by_url_key,

                by_url,

                by_legacy_signature,

            )

            product_action = "update" if urun_id is not None else "insert"

            if product_action == "insert":

                would_insert_products += 1

            else:

                would_update_products += 1



            predicted_audit_rows.append(

                {

                    "urun_ad": satir["urun_ad"],

                    "urun_url": satir["urun_url"],

                    "site_product_code": satir["site_product_code"] or "",

                    "url_key": satir["url_key"] or "",

                    "legacy_signature": satir.get("legacy_signature") or "",

                    "matched_by": eslestiren,

                    "resolved_urun_id": urun_id or "",

                    "product_action": product_action,

                    "price_action": "would_insert",

                    "kazima_tarihi": satir["kazima_tarihi"].isoformat() if satir["kazima_tarihi"] else "",

                }

            )



        if args.apply:

            stable_rows, eski_satirlar = split_current_rows_for_apply(guncel_satirlar)

            stable_predicted_rows = [satir for satir in predicted_audit_rows if not satir["legacy_signature"]]

            legacy_predicted_rows = [satir for satir in predicted_audit_rows if satir["legacy_signature"]]



            denetim_satirlari = []

            eklenen_urunler = 0

            guncellenen_urunler = 0

            eklenen_fiyatlar = 0

            skipped_prices = 0



            bulk_audit_rows, bulk_inserted_products, bulk_updated_products, bulk_inserted_prices = apply_bulk_rows(

                cur,

                market_kimligi,

                market_adi,

                stable_rows,

                stable_predicted_rows,

            )

            denetim_satirlari.extend(bulk_audit_rows)

            eklenen_urunler += bulk_inserted_products

            guncellenen_urunler += bulk_updated_products

            eklenen_fiyatlar += bulk_inserted_prices

            legacy_audit_rows, legacy_inserted_products, legacy_updated_products, legacy_inserted_prices = apply_legacy_bulk_rows(

                cur,

                market_kimligi,

                market_adi,

                eski_satirlar,

                legacy_predicted_rows,

            )

            denetim_satirlari.extend(legacy_audit_rows)

            eklenen_urunler += legacy_inserted_products

            guncellenen_urunler += legacy_updated_products

            eklenen_fiyatlar += legacy_inserted_prices



            baglanti.commit()

            print(f"Applied inserted_products={inserted_products}")

            print(f"Applied updated_products={updated_products}")

            print(f"Applied inserted_prices={inserted_prices}")

            print(f"Applied skipped_prices={skipped_prices}")

        else:

            denetim_satirlari = [

                {

                    **satir,

                    "product_action": f"would_{satir['product_action']}",

                }

                for satir in predicted_audit_rows

            ]

            print(f"Dry run inserted_products={would_insert_products}")

            print(f"Dry run updated_products={would_update_products}")

            print(f"Dry run inserted_prices={len(guncel_satirlar)}")



        write_csv(args.denetim_csv, denetim_satirlari)

        print(f"Audit CSV: {args.audit_csv}")

        print(f"Toplam current row: {len(guncel_satirlar)}")

    finally:

        cur.close()

        baglanti.close()





if __name__ == "__main__":

    main()

