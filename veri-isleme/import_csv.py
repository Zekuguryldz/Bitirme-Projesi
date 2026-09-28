import re

import pandas as pd

import psycopg2

from dotenv import load_dotenv

import os



from product_identity import build_product_identity, clean_optional_text



load_dotenv()



VERITABANI_ADRESI = os.environ.get("DATABASE_URL")

CSV_YOLU = "/Users/uguryildiz/Downloads/sokmarket_tum_kategoriler_20260323_1604_1425.csv"

VARSAYILAN_MARKET_ADI = "ŞOK"





def pick_first(satir, *columns):

    for column in columns:

        value = clean_optional_text(satir.get(column))

        if value is not None:

            return value

    return None



                       

def normalize_gramaj(raw):

    """
    Input:  '1.5 Kg', '750 ml', '4 L', 'Belirtilmemis', '6 adet', None ...
    Output: (gramaj_degeri: float|None, gramaj_birimi: str|None)
    Kurallar:
      kg/kilo      → değeri *1000, birim='g'
      g/gr/gram    → birim='g'
      l/lt/litre   → değeri *1000, birim='ml'
      ml           → birim='ml'
      adet/ad/pk/paket/pcs/piece → birim='adet'
      belirtilmemis/yok/None    → (None, None)
    """

    if raw is None or str(raw).strip() == "":

        return None, None



    raw = str(raw).strip()



    if raw.lower() in ("belirtilmemis", "belirtilmemiş", "-", "yok", "nan"):

        return None, None



                                                          

    eslesme = re.eslesme(r"^([\d.,]+)\s*([a-zA-ZğüşıöçĞÜŞİÖÇ]+)$", raw)

    if not eslesme:

        return None, None



    sayi_str = eslesme.group(1).replace(",", ".")

    birim_str = eslesme.group(2).lower().strip()



    try:

        sayi = float(sayi_str)

    except ValueError:

        return None, None



                     

    if birim_str in ("kg", "kilo", "kilogram"):

        return sayi * 1000, "g"

    if birim_str in ("g", "gr", "gram"):

        return sayi, "g"



                   

    if birim_str in ("l", "lt", "litre", "liter"):

        return sayi * 1000, "ml"

    if birim_str in ("ml", "mililitre", "milliliter"):

        return sayi, "ml"



                  

    if birim_str in ("adet", "ad", "pk", "paket", "pcs", "piece", "li", "lu", "lü", "lı"):

        return sayi, "adet"



    return None, None





def birim_fiyat_hesapla(fiyat, gramaj_degeri, gramaj_birimi):

    if fiyat is None or gramaj_degeri is None or gramaj_degeri <= 0 or gramaj_birimi is None:

        return None



    if gramaj_birimi in ("g", "ml"):

        return round((fiyat * 1000) / gramaj_degeri, 4)



    if gramaj_birimi == "adet":

        return round(fiyat / gramaj_degeri, 4)



    return None





def find_existing_product_id(cur, market_kimligi, identity):

    for column, value in identity.adaylar():

        cur.execute(

            f"SELECT id FROM urunler WHERE market_id = %s AND {column} = %s LIMIT 1",

            (market_kimligi, value),

        )

        satir = cur.fetchone()

        if satir:

            return satir[0]

    return None





def upsert_product(cur, market_kimligi, urun_ad, urun_url, kategori, marka, market_adi, site_urun_kodu):

    identity = build_product_identity(site_urun_kodu=site_urun_kodu, urun_url=urun_url)

    existing_id = find_existing_product_id(cur, market_kimligi, identity)



    if existing_id:

        cur.execute(

            """UPDATE urunler
               SET urun_ad = %s,
                   urun_url = %s,
                   urun_kategori = %s,
                   urun_marka = %s,
                   market_adi = %s,
                   site_product_code = COALESCE(site_product_code, %s),
                   url_key = COALESCE(url_key, %s)
               WHERE id = %s
               RETURNING id""",

            (

                urun_ad,

                urun_url,

                kategori,

                marka,

                market_adi,

                identity.site_urun_kodu,

                identity.adres_anahtari,

                existing_id,

            ),

        )

        return cur.fetchone()[0], "updated"



    cur.execute(

        """INSERT INTO urunler
           (market_id, urun_ad, urun_url, urun_kategori, urun_marka, market_adi, site_product_code, url_key)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",

        (

            market_kimligi,

            urun_ad,

            urun_url,

            kategori,

            marka,

            market_adi,

            identity.site_urun_kodu,

            identity.adres_anahtari,

        ),

    )

    return cur.fetchone()[0], "inserted"





                                  

def main():

    df = pd.read_csv(CSV_YOLU)

    df.columns = [c.strip() for c in df.columns]



    baglanti = psycopg2.connect(VERITABANI_ADRESI)

    cur = baglanti.imlec()



                          

    cur.execute("SELECT market_id FROM market WHERE market_adi = %s ORDER BY market_id LIMIT 1", (VARSAYILAN_MARKET_ADI,))

    satir = cur.fetchone()

    if satir:

        market_kimligi = satir[0]

    else:

        cur.execute(

            "INSERT INTO market (market_adi) VALUES (%s) RETURNING market_id",

            (VARSAYILAN_MARKET_ADI,)

        )

        market_kimligi = cur.fetchone()[0]

    baglanti.commit()

    print(f"{DEFAULT_MARKET_NAME} → market_id: {market_id}")



                                             

    urun_rows = []

    fiyat_rows = []

    skipped = 0



    for _, satir in df.iterrows():

        urun_ad = pick_first(satir, "Urun Adi", "product_name")

        urun_url = pick_first(satir, "URL", "product_url")

        kategori = pick_first(satir, "Site Kategori", "site_main_category", "site_subcategory")

        marka = pick_first(satir, "Marka", "brand")

        site_urun_kodu = pick_first(satir, "Product Code", "product_code")

        fiyat_raw = satir.get("Fiyat (TL)")

        if fiyat_raw is None:

            fiyat_raw = satir.get("current_price")

        gramaj_raw = satir.get("Gramaj/Hacim")

        if gramaj_raw is None:

            gramaj_raw = satir.get("package_value_text")

        tarih_raw = pick_first(satir, "Cekim Tarihi", "scrape_timestamp")



        if not urun_ad or not urun_url:

            skipped += 1

            continue



        try:

            fiyat = float(str(fiyat_raw).replace(",", ".")) if fiyat_raw else None

        except ValueError:

            fiyat = None



        gramaj_degeri, gramaj_birimi = normalize_gramaj(gramaj_raw)

        birim_fiyat = birim_fiyat_hesapla(fiyat, gramaj_degeri, gramaj_birimi)



                     

        try:

            from datetime import datetime

            kazima_tarihi = datetime.strptime(tarih_raw, "%d.%m.%Y %H:%M:%S")

        except Exception:

            try:

                from datetime import datetime

                kazima_tarihi = datetime.fromisoformat(tarih_raw)

            except Exception:

                kazima_tarihi = None



        urun_rows.append((market_kimligi, urun_ad, urun_url, kategori, marka, VARSAYILAN_MARKET_ADI, site_urun_kodu))

        fiyat_rows.append((fiyat, gramaj_degeri, gramaj_birimi, birim_fiyat, kazima_tarihi))



    print(f"Importing {len(urun_rows)} products with stable identity...")

    eklenen_urunler = 0

    guncellenen_urunler = 0

    eklenen_fiyatlar = 0

    for urun, fiyat_data in zip(urun_rows, fiyat_rows):

        market_kimligi, urun_ad, urun_url, kategori, marka, market_adi, site_urun_kodu = urun

        urun_id, status = upsert_product(

            cur,

            market_kimligi,

            urun_ad,

            urun_url,

            kategori,

            marka,

            market_adi,

            site_urun_kodu,

        )

        if status == "inserted":

            eklenen_urunler += 1

        else:

            guncellenen_urunler += 1



                            

        fiyat, gramaj_degeri, gramaj_birimi, birim_fiyat, kazima_tarihi = fiyat_data

        cur.execute(

            """INSERT INTO fiyat_zaman_serisi
               (urun_id, urun_fiyat, gramaj_degeri, gramaj_birimi, birim_fiyat, kazima_tarihi)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING""",

            (urun_id, fiyat, gramaj_degeri, gramaj_birimi, birim_fiyat, kazima_tarihi),

        )

        eklenen_fiyatlar += cur.rowcount



    baglanti.commit()

    cur.close()

    baglanti.close()



    print(

        f"Done! inserted_products={inserted_products}, updated_products={updated_products}, "

        f"inserted_prices={inserted_prices}, skipped={skipped}"

    )





if __name__ == "__main__":

    main()

