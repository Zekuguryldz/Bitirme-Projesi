import unittest



from import_current_normalized_to_supabase import (

    build_current_rows,

    build_legacy_signature,

    canonicalize_market_name,

    detect_market_name,

    resolve_existing_product_id,

)





class ImportCurrentNormalizedToSupabaseTests(unittest.TestCase):

    def test_detect_market_name_prefers_explicit_value(self) -> None:

        self.assertEqual(

            detect_market_name([], [], "Migros"),

            "MİGROS",

        )



    def test_detect_market_name_reads_csv_value(self) -> None:

        self.assertEqual(

            detect_market_name([{"market_adi": "Migros"}], [], None),

            "MİGROS",

        )



    def test_canonicalize_market_name_handles_sok_variants(self) -> None:

        self.assertEqual(canonicalize_market_name("Şok Market"), "ŞOK")

        self.assertEqual(canonicalize_market_name("sok"), "ŞOK")



    def test_build_current_rows_uses_site_product_code_and_birim_fiyat(self) -> None:

        urunler_rows = [

            {

                "id": "1",

                "urun_ad": "Aktürk Vanilyalı Gofret 300 G",

                "urun_url": "https://www.migros.com.tr/akturk-vanilyali-gofret-300-g-p-6b0073",

                "urun_kategori": "Atıştırmalık",

                "urun_marka": "Aktürk",

            }

        ]

        ham_satirlar = [

            {

                "product_name": "Aktürk Vanilyalı Gofret 300 G",

                "product_url": "https://www.migros.com.tr/akturk-vanilyali-gofret-300-g-p-6b0073",

                "site_product_code": "7012467",

                "brand": "Aktürk",

                "site_main_category": "Atıştırmalık",

            }

        ]

        fiyat_satirlari = [

            {

                "urun_id": "1",

                "urun_fiyat": "62.5",

                "gramaj_degeri": "300",

                "gramaj_birimi": "g",

                "birim_fiyat": "208.33",

                "kazima_tarihi": "2026-04-21 16:04:02+03:00",

            }

        ]



        satirlar = build_current_rows(urunler_rows, ham_satirlar, fiyat_satirlari)



        self.assertEqual(len(satirlar), 1)

        self.assertEqual(satirlar[0]["site_product_code"], "7012467")

        self.assertEqual(satirlar[0]["url_key"], "akturk-vanilyali-gofret-300-g-p-6b0073")

        self.assertEqual(satirlar[0]["birim_fiyat"], 208.33)

        self.assertIsNone(satirlar[0]["legacy_signature"])



    def test_build_current_rows_falls_back_to_urunler_when_raw_missing(self) -> None:

        urunler_rows = [

            {

                "id": "1",

                "urun_ad": "Legacy Ürün 500 G",

                "urun_url": "",

                "urun_kategori": "Temel Gıda",

                "urun_marka": "Deneme",

                "site_product_code": "",

            }

        ]

        fiyat_satirlari = [

            {

                "urun_id": "1",

                "urun_fiyat": "10.0",

                "gramaj_degeri": "500",

                "gramaj_birimi": "g",

                "birim_fiyat": "20.0",

                "kazima_tarihi": "2026-03-21 16:04:02+03:00",

            }

        ]



        satirlar = build_current_rows(urunler_rows, [], fiyat_satirlari)



        self.assertEqual(len(satirlar), 1)

        self.assertEqual(satirlar[0]["urun_ad"], "Legacy Ürün 500 G")

        self.assertEqual(satirlar[0]["urun_kategori"], "Temel Gıda")

        self.assertEqual(satirlar[0]["urun_marka"], "Deneme")

        self.assertEqual(

            satirlar[0]["legacy_signature"],

            build_legacy_signature(

                urun_ad="Legacy Ürün 500 G",

                urun_kategori="Temel Gıda",

                urun_marka="Deneme",

                site_urun_kodu=None,

                adres_anahtari=None,

                urun_url=None,

            ),

        )



    def test_resolve_existing_product_id_uses_legacy_signature(self) -> None:

        legacy_signature = build_legacy_signature(

            urun_ad="Legacy Ürün 500 G",

            urun_kategori="Temel Gıda",

            urun_marka="Deneme",

            site_urun_kodu=None,

            adres_anahtari=None,

            urun_url=None,

        )



        urun_id, eslestiren = resolve_existing_product_id(

            {

                "site_product_code": None,

                "url_key": None,

                "urun_url": "",

                "legacy_signature": legacy_signature,

            },

            {},

            {},

            {},

            {legacy_signature: 99},

        )



        self.assertEqual(urun_id, 99)

        self.assertEqual(eslestiren, "legacy_signature")





if __name__ == "__main__":

    unittest.main()

