import argparse

import csv

import os

from pathlib import Path



import psycopg2

from psycopg2.extras import execute_values

from dotenv import load_dotenv



from backfill_product_urls import build_reference_indexes, backfill_rows





def read_sql_file(yol: Path) -> str:

    return yol.read_text(encoding="utf-8")





def fetch_urunler(cur) -> list[dict[str, object]]:

    cur.execute(

        """
        SELECT id, market_id, urun_ad, urun_url, urun_kategori, eklenme_tarihi,
               market_adi, urun_marka, site_product_code, url_key
        FROM urunler
        ORDER BY id
        """

    )

    columns = [desc[0] for desc in cur.description]

    return [dict(zip(columns, satir)) for satir in cur.fetchall()]





def write_csv(yol: Path, satirlar: list[dict[str, object]]) -> None:

    if not satirlar:

        return

    yol.parent.mkdir(parents=True, exist_ok=True)

    with yol.open("w", encoding="utf-8", newline="") as handle:

        yazici = csv.DictWriter(handle, fieldnames=list(satirlar[0].keys()))

        yazici.writeheader()

        yazici.writerows(satirlar)





def argumanlari_ayristir() -> argparse.Namespace:

    komut_ayristirici = argparse.ArgumentParser(

        description="Supabase'teki eski urunler kayitlarinin bozuk URL'lerini ve kimlik alanlarini duzeltir."

    )

    komut_ayristirici.add_argument(

        "--reference-csv",

        type=Path,

        required=True,

        help="Guncel product_url ve product_code alanlarini iceren referans CSV",

    )

    komut_ayristirici.add_argument(

        "--migration-sql",

        type=Path,

        default=Path("migrations/001_product_identity.sql"),

    )

    komut_ayristirici.add_argument(

        "--backup-csv",

        type=Path,

        default=Path("outputs/supabase_urunler_before_repair.csv"),

    )

    komut_ayristirici.add_argument(

        "--audit-csv",

        type=Path,

        default=Path("outputs/supabase_urunler_url_backfill_audit.csv"),

    )

    komut_ayristirici.add_argument(

        "--apply",

        action="store_true",

        help="Gercekten veritabanini guncelle. Bu bayrak yoksa sadece dry-run yapar.",

    )

    return komut_ayristirici.argumanlari_ayristir()





def main() -> None:

    args = argumanlari_ayristir()

    load_dotenv(".env")

    veritabani_adresi = os.environ["DATABASE_URL"]



    with args.reference_csv.open("r", encoding="utf-8-sig", newline="") as handle:

        referans_satirlar = list(csv.DictReader(handle))

    indexes = build_reference_indexes(referans_satirlar)



    baglanti = psycopg2.connect(veritabani_adresi)

    cur = baglanti.imlec()

    try:

        cur.execute(read_sql_file(args.migration_sql))

        baglanti.commit()



        eski_satirlar = fetch_urunler(cur)

        write_csv(args.backup_csv, eski_satirlar)



        guncellenen_satirlar, denetim_satirlari, stats = backfill_rows(eski_satirlar, indexes)

        write_csv(args.denetim_csv, denetim_satirlari)



        if args.apply:

            yuk = []

            for satir, audit in zip(guncellenen_satirlar, denetim_satirlari):

                if audit["status"] != "backfilled":

                    continue

                yuk.append(

                    (

                        int(satir["id"]),

                        satir["urun_url"],

                        audit["reference_site_product_code"] or None,

                        audit["reference_url_key"] or None,

                    )

                )



            cur.execute(

                """
                CREATE TEMP TABLE _url_fix_payload (
                    id BIGINT PRIMARY KEY,
                    urun_url TEXT NOT NULL,
                    site_product_code TEXT,
                    url_key TEXT
                ) ON COMMIT DROP
                """

            )

            if yuk:

                execute_values(

                    cur,

                    """
                    INSERT INTO _url_fix_payload (id, urun_url, site_product_code, url_key)
                    VALUES %s
                    """,

                    yuk,

                    page_size=500,

                )

                cur.execute(

                    """
                    UPDATE urunler AS u
                    SET urun_url = p.urun_url,
                        site_product_code = COALESCE(u.site_product_code, p.site_product_code),
                        url_key = COALESCE(u.url_key, p.url_key)
                    FROM _url_fix_payload AS p
                    WHERE u.id = p.id
                    """

                )

                guncellenen = cur.rowcount

            else:

                guncellenen = 0

            baglanti.commit()

            print(f"Applied updates: {updated}")

        else:

            print("Dry run only; no database rows updated.")



        print(f"Backup CSV: {args.backup_csv}")

        print(f"Audit CSV: {args.audit_csv}")

        print(f"Toplam satir: {stats['total']}")

        print(f"Geri doldurulabilir URL: {stats['updated']}")

        print(f"Eslesmeyen: {stats['no_match']}")

        print(f"Belirsiz eslesme: {stats['ambiguous']}")

    finally:

        cur.close()

        baglanti.close()





if __name__ == "__main__":

    main()

