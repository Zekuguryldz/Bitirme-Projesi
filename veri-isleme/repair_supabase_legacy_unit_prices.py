import argparse

import os

from datetime import date



import psycopg2

from dotenv import load_dotenv





def argumanlari_ayristir() -> argparse.Namespace:

    komut_ayristirici = argparse.ArgumentParser(

        description="Supabase'teki en eski fiyat snapshot'inin birim_fiyat degerlerini kg/l bazina cevirir."

    )

    komut_ayristirici.add_argument(

        "--legacy-date",

        type=date.fromisoformat,

        default=None,

        help="Onarilacak snapshot tarihi. Verilmezse veritabanindaki en eski tarih secilir.",

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

    baglanti = psycopg2.connect(os.environ["DATABASE_URL"])

    cur = baglanti.imlec()



    try:

        if args.legacy_date is None:

            cur.execute("select min(date(kazima_tarihi)) from fiyat_zaman_serisi")

            args.legacy_date = cur.fetchone()[0]



        cur.execute(

            """
            select count(*)
            from fiyat_zaman_serisi
            where date(kazima_tarihi) = %s
              and gramaj_birimi in ('g', 'ml')
              and gramaj_degeri is not null
              and gramaj_degeri > 0
              and urun_fiyat is not null
            """,

            (args.legacy_date,),

        )

        affected_rows = cur.fetchone()[0]



        if args.apply:

            cur.execute(

                """
                update fiyat_zaman_serisi
                set birim_fiyat = round((urun_fiyat * 1000.0) / gramaj_degeri, 4)
                where date(kazima_tarihi) = %s
                  and gramaj_birimi in ('g', 'ml')
                  and gramaj_degeri is not null
                  and gramaj_degeri > 0
                  and urun_fiyat is not null
                """,

                (args.legacy_date,),

            )

            baglanti.commit()

            print(f"Applied unit-price repair rows: {cur.rowcount}")

        else:

            print("Dry run only; no database rows updated.")



        print(f"Legacy snapshot date: {args.legacy_date}")

        print(f"Affected rows: {affected_rows}")

    finally:

        cur.close()

        baglanti.close()





if __name__ == "__main__":

    main()

