"""
Hizli bulk import: db_sync_input.csv -> Supabase urunler + fiyat_zaman_serisi
Tek tek satir yerine toplu SQL ile ~30 saniyede tamamlar.
"""

from __future__ import annotations



import os

import sys

from pathlib import Path



import pandas as pd

import psycopg2

from psycopg2.extras import execute_values, RealDictCursor

from dotenv import load_dotenv



load_dotenv(Path(__file__).parent / ".env")



VERITABANI_ADRESI = os.getenv("DATABASE_URL")

if not VERITABANI_ADRESI:

    sys.exit("DATABASE_URL bulunamadi")



GIRDI_CSV = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(

    "scheduled_outputs/migros_sync_20260504_190005_deduped_reyondansiz/db_sync_input.csv"

)

MARKET_ADI = "MİGROS"





def clean(v):

    if v is None:

        return None

    try:

        import pandas as pd

        if pd.isna(v):

            return None

    except Exception:

        pass

    s = str(v).strip()

    return s if s and s.lower() != "nan" else None





def main():

    print(f"CSV okunuyor: {INPUT_CSV}")

    df = pd.read_csv(GIRDI_CSV, dtype=str)

    df = df.where(pd.notna(df), None)

    print(f"Satir sayisi: {len(df)}")



    baglanti = psycopg2.connect(VERITABANI_ADRESI)

    baglanti.autocommit = False

    with baglanti.imlec() as cur:

        cur.execute("SET statement_timeout = 0")

        cur.execute("SET idle_in_transaction_session_timeout = 0")



    with baglanti.imlec(cursor_factory=RealDictCursor) as cur:

                      

        cur.execute("SELECT market_id FROM market WHERE market_adi = %s LIMIT 1", (MARKET_ADI,))

        satir = cur.fetchone()

        if satir:

            market_kimligi = int(satir["market_id"])

        else:

            cur.execute("INSERT INTO market (market_adi) VALUES (%s) RETURNING market_id", (MARKET_ADI,))

            market_kimligi = int(cur.fetchone()["market_id"])

        print(f"market_id: {market_id}")



                                 

        cur.execute("DROP TABLE IF EXISTS _bulk_sync_payload")

        cur.execute("""
            CREATE TEMP TABLE _bulk_sync_payload (
                urun_ad        TEXT,
                urun_url       TEXT,
                urun_kategori  TEXT,
                urun_marka     TEXT,
                market_adi     TEXT,
                site_product_code TEXT,
                url_key        TEXT,
                eklenme_tarihi TIMESTAMPTZ,
                son_gorulme_tarihi TIMESTAMPTZ,
                sira_no        INT,
                urun_fiyat     NUMERIC,
                gramaj_degeri  NUMERIC,
                gramaj_birimi  TEXT,
                birim_fiyat    NUMERIC,
                kazima_tarihi  TIMESTAMPTZ,
                adet_sayisi    NUMERIC,
                matched_id     BIGINT
            ) ON COMMIT DROP
        """)



                               

        satirlar = []

        for _, r in df.iterrows():

            satirlar.append((

                clean(r.get("urun_ad")),

                clean(r.get("urun_url")),

                clean(r.get("urun_kategori")),

                clean(r.get("urun_marka")),

                clean(r.get("market_adi")) or MARKET_ADI,

                clean(r.get("site_product_code")),

                clean(r.get("url_key")),

                clean(r.get("eklenme_tarihi")),

                clean(r.get("kazima_tarihi")),

                int(r["sira_no"]) if clean(r.get("sira_no")) else None,

                float(r["urun_fiyat"]) if clean(r.get("urun_fiyat")) else None,

                float(r["gramaj_degeri"]) if clean(r.get("gramaj_degeri")) else None,

                clean(r.get("gramaj_birimi")),

                float(r["birim_fiyat"]) if clean(r.get("birim_fiyat")) else None,

                clean(r.get("kazima_tarihi")),

                float(r["adet_sayisi"]) if clean(r.get("adet_sayisi")) else None,

                None,              

            ))



        execute_values(cur, """
            INSERT INTO _bulk_sync_payload
            (urun_ad, urun_url, urun_kategori, urun_marka, market_adi,
             site_product_code, url_key, eklenme_tarihi, son_gorulme_tarihi, sira_no,
             urun_fiyat, gramaj_degeri, gramaj_birimi, birim_fiyat,
             kazima_tarihi, adet_sayisi, matched_id)
            VALUES %s
        """, satirlar, page_size=500)

        print(f"Gecici tabloya {len(rows)} satir yuklendi")



                                                                               

        for col in ("site_product_code", "url_key", "urun_url"):

            cur.execute(f"""
                UPDATE _bulk_sync_payload AS p
                SET matched_id = u.id
                FROM urunler AS u
                WHERE u.market_id = %s
                  AND p.{col} IS NOT NULL AND p.{col} <> ''
                  AND u.{col} = p.{col}
                  AND p.matched_id IS NULL
            """, (market_kimligi,))

        cur.execute("SELECT COUNT(*) cnt FROM _bulk_sync_payload WHERE matched_id IS NOT NULL")

        eslesen = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) cnt FROM _bulk_sync_payload WHERE matched_id IS NULL")

        new_count = cur.fetchone()["cnt"]

        print(f"Eslesen (update): {matched} | Yeni (insert): {new_count}")



                                     

        cur.execute("""
            UPDATE urunler AS u
            SET urun_ad       = p.urun_ad,
                urun_url      = p.urun_url,
                urun_kategori = p.urun_kategori,
                urun_marka    = p.urun_marka,
                market_adi    = p.market_adi,
                eklenme_tarihi = COALESCE(u.eklenme_tarihi, p.eklenme_tarihi),
                son_gorulme_tarihi = CASE
                    WHEN p.son_gorulme_tarihi IS NULL THEN u.son_gorulme_tarihi
                    WHEN u.son_gorulme_tarihi IS NULL THEN p.son_gorulme_tarihi
                    WHEN p.son_gorulme_tarihi > u.son_gorulme_tarihi THEN p.son_gorulme_tarihi
                    ELSE u.son_gorulme_tarihi
                END,
                sira_no       = COALESCE(p.sira_no, u.sira_no),
                site_product_code = COALESCE(u.site_product_code, p.site_product_code),
                url_key       = COALESCE(u.url_key, p.url_key)
            FROM _bulk_sync_payload AS p
            WHERE u.id = p.matched_id
        """)

        guncellenen = cur.rowcount

        print(f"Guncellenen urun: {updated}")



                               

        cur.execute("""
            INSERT INTO urunler
                (market_id, urun_ad, urun_url, urun_kategori, urun_marka,
                 market_adi, site_product_code, url_key, eklenme_tarihi, son_gorulme_tarihi, sira_no)
            SELECT DISTINCT ON (
                COALESCE(
                    CASE WHEN site_product_code IS NOT NULL AND site_product_code <> ''
                         THEN 'sc:' || site_product_code END,
                    CASE WHEN url_key IS NOT NULL AND url_key <> ''
                         THEN 'uk:' || url_key END,
                    CASE WHEN urun_url IS NOT NULL AND urun_url <> ''
                         THEN 'url:' || urun_url END,
                    urun_ad
                )
            )
                %s, urun_ad, urun_url, urun_kategori, urun_marka,
                market_adi, site_product_code, url_key, eklenme_tarihi::TIMESTAMPTZ, son_gorulme_tarihi::TIMESTAMPTZ, sira_no
            FROM _bulk_sync_payload
            WHERE matched_id IS NULL AND urun_ad IS NOT NULL
            ORDER BY
                COALESCE(
                    CASE WHEN site_product_code IS NOT NULL AND site_product_code <> ''
                         THEN 'sc:' || site_product_code END,
                    CASE WHEN url_key IS NOT NULL AND url_key <> ''
                         THEN 'uk:' || url_key END,
                    CASE WHEN urun_url IS NOT NULL AND urun_url <> ''
                         THEN 'url:' || urun_url END,
                    urun_ad
                )
        """, (market_kimligi,))

        inserted = cur.rowcount

        print(f"Eklenen yeni urun: {inserted}")



                                                     

        for col in ("site_product_code", "url_key", "urun_url"):

            cur.execute(f"""
                UPDATE _bulk_sync_payload AS p
                SET matched_id = u.id
                FROM urunler AS u
                WHERE u.market_id = %s
                  AND p.{col} IS NOT NULL AND p.{col} <> ''
                  AND u.{col} = p.{col}
                  AND p.matched_id IS NULL
            """, (market_kimligi,))



                                         

        cur.execute("""
            INSERT INTO fiyat_zaman_serisi
                (urun_id, urun_fiyat, gramaj_degeri, gramaj_birimi,
                 birim_fiyat, kazima_tarihi, adet_sayisi)
            SELECT
                p.matched_id,
                p.urun_fiyat,
                p.gramaj_degeri,
                p.gramaj_birimi,
                p.birim_fiyat,
                p.kazima_tarihi::TIMESTAMPTZ,
                p.nameet_sayisi
            FROM _bulk_sync_payload AS p
            WHERE p.matched_id IS NOT NULL
              AND p.kazima_tarihi IS NOT NULL
            ON CONFLICT DO NOTHING
        """)

        eklenen_fiyat = cur.rowcount

        print(f"Eklenen fiyat kaydi: {eklenen_fiyat}")



        baglanti.commit()

        print("\n=== COMMIT TAMAMLANDI ===")



               

        cur.execute("SELECT COUNT(*) cnt FROM urunler WHERE market_id = %s", (market_kimligi,))

        print(f"Toplam Migros urun (urunler): {cur.fetchone()['cnt']}")

        cur.execute("""
            SELECT COUNT(*) cnt FROM fiyat_zaman_serisi fz
            JOIN urunler u ON fz.urun_id = u.id WHERE u.market_id = %s
        """, (market_kimligi,))

        print(f"Toplam Migros fiyat kaydi: {cur.fetchone()['cnt']}")



    baglanti.close()





if __name__ == "__main__":

    main()

