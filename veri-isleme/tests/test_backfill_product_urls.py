import unittest



from backfill_product_urls import (

    backfill_rows,

    build_reference_indexes,

    is_product_url,

    needs_url_backfill,

    normalize_name_for_match,

)





class BackfillProductUrlsTests(unittest.TestCase):

    def test_is_product_url(self) -> None:

        self.assertTrue(

            is_product_url("https://www.sokmarket.com.tr/pepsi-cola-4-1-lt-p-12345")

        )

        self.assertTrue(

            is_product_url("https://www.migros.com.tr/akturk-vanilyali-gofret-300-g-p-6b0073")

        )

        self.assertFalse(

            is_product_url("https://www.sokmarket.com.tr/icecekler-c-20370?page=2")

        )



    def test_needs_url_backfill(self) -> None:

        self.assertTrue(

            needs_url_backfill("https://www.sokmarket.com.tr/icecekler-c-20370?page=2")

        )

        self.assertFalse(

            needs_url_backfill("https://www.sokmarket.com.tr/pepsi-cola-4-1-lt-p-12345")

        )

        self.assertFalse(

            needs_url_backfill("https://www.migros.com.tr/atistirmalik-c-113fb/akturk-vanilyali-gofret-300-g-p-6b0073")

        )



    def test_normalize_name_for_match(self) -> None:

        self.assertEqual(

            normalize_name_for_match("Çilekli Şölen 100 g"),

            "cilekli solen 100 g",

        )



    def test_backfill_uses_exact_name_match(self) -> None:

        referans_satirlar = [

            {

                "product_name": "Pepsi Cola 4*1 Lt",

                "product_url": "https://www.sokmarket.com.tr/pepsi-cola-4-1-lt-p-12345",

                "product_code": "001",

            }

        ]

        indexes = build_reference_indexes(referans_satirlar)

        eski_satirlar = [

            {

                "id": "10",

                "urun_ad": "Pepsi Cola 4*1 Lt",

                "urun_url": "https://www.sokmarket.com.tr/icecekler-c-20370?page=2",

            }

        ]



        guncellenen_satirlar, denetim_satirlari, stats = backfill_rows(eski_satirlar, indexes)



        self.assertEqual(

            guncellenen_satirlar[0]["urun_url"],

            "https://www.sokmarket.com.tr/pepsi-cola-4-1-lt-p-12345",

        )

        self.assertEqual(denetim_satirlari[0]["status"], "backfilled")

        self.assertEqual(denetim_satirlari[0]["match_type"], "exact_name")

        self.assertEqual(stats["updated"], 1)



    def test_backfill_uses_normalized_name_match(self) -> None:

        referans_satirlar = [

            {

                "product_name": "Cilekli Solen 100 g",

                "product_url": "https://www.sokmarket.com.tr/cilekli-solen-100-g-p-999",

                "product_code": "999",

            }

        ]

        indexes = build_reference_indexes(referans_satirlar)

        eski_satirlar = [

            {

                "id": "11",

                "urun_ad": "Çilekli Şölen 100 g",

                "urun_url": "https://www.sokmarket.com.tr/atistirmaliklar-c-20376",

            }

        ]



        guncellenen_satirlar, denetim_satirlari, stats = backfill_rows(eski_satirlar, indexes)



        self.assertEqual(

            guncellenen_satirlar[0]["urun_url"],

            "https://www.sokmarket.com.tr/cilekli-solen-100-g-p-999",

        )

        self.assertEqual(denetim_satirlari[0]["match_type"], "normalized_name")

        self.assertEqual(stats["updated"], 1)



    def test_product_url_rows_are_left_untouched(self) -> None:

        referans_satirlar = [

            {

                "product_name": "Pepsi Cola 4*1 Lt",

                "product_url": "https://www.sokmarket.com.tr/pepsi-cola-4-1-lt-p-12345",

                "product_code": "001",

            }

        ]

        indexes = build_reference_indexes(referans_satirlar)

        eski_satirlar = [

            {

                "id": "12",

                "urun_ad": "Pepsi Cola 4*1 Lt",

                "urun_url": "https://www.sokmarket.com.tr/pepsi-cola-4-1-lt-p-12345",

            }

        ]



        guncellenen_satirlar, denetim_satirlari, stats = backfill_rows(eski_satirlar, indexes)



        self.assertEqual(

            guncellenen_satirlar[0]["urun_url"],

            "https://www.sokmarket.com.tr/pepsi-cola-4-1-lt-p-12345",

        )

        self.assertEqual(denetim_satirlari[0]["status"], "already_product_url")

        self.assertEqual(stats["already_product_url"], 1)



    def test_backfill_prefers_explicit_reference_url_key(self) -> None:

        referans_satirlar = [

            {

                "product_name": "Aktürk Vanilyalı Gofret 300 G",

                "product_url": "https://www.migros.com.tr/akturk-vanilyali-gofret-300-g-p-6b0073",

                "site_product_code": "7012467",

                "url_key": "akturk-vanilyali-gofret-300-g-p-6b0073",

            }

        ]

        indexes = build_reference_indexes(referans_satirlar)

        eski_satirlar = [

            {

                "id": "13",

                "urun_ad": "Aktürk Vanilyalı Gofret 300 G",

                "urun_url": "",

                "site_product_code": "",

                "url_key": "",

            }

        ]



        guncellenen_satirlar, denetim_satirlari, stats = backfill_rows(eski_satirlar, indexes)



        self.assertEqual(

            guncellenen_satirlar[0]["url_key"],

            "akturk-vanilyali-gofret-300-g-p-6b0073",

        )

        self.assertEqual(denetim_satirlari[0]["reference_url_key"], "akturk-vanilyali-gofret-300-g-p-6b0073")

        self.assertEqual(stats["updated"], 1)



    def test_backfill_uses_token_bag_name_match(self) -> None:

        referans_satirlar = [

            {

                "product_name": "Lipton Yellow Label Demlik Poşet Çay 120'li 384 G",

                "product_url": "https://www.migros.com.tr/lipton-yellow-label-demlik-poset-cay-120-li-384-g-p-abc123",

                "site_product_code": "123",

            }

        ]

        indexes = build_reference_indexes(referans_satirlar)

        eski_satirlar = [

            {

                "id": "14",

                "urun_ad": "Lipton Yellow Label 120'li Demlik Poşet Çay 384 G",

                "urun_url": "",

            }

        ]



        guncellenen_satirlar, denetim_satirlari, stats = backfill_rows(eski_satirlar, indexes)



        self.assertEqual(

            guncellenen_satirlar[0]["urun_url"],

            "https://www.migros.com.tr/lipton-yellow-label-demlik-poset-cay-120-li-384-g-p-abc123",

        )

        self.assertEqual(denetim_satirlari[0]["match_type"], "token_bag_name")

        self.assertEqual(stats["updated"], 1)



    def test_backfill_uses_reduced_token_bag_name_match(self) -> None:

        referans_satirlar = [

            {

                "product_name": "Barilla Fusilli (Burgu) Makarna 500 G",

                "product_url": "https://www.migros.com.tr/barilla-fusilli-burgu-makarna-500-g-p-xyz987",

                "site_product_code": "987",

            }

        ]

        indexes = build_reference_indexes(referans_satirlar)

        eski_satirlar = [

            {

                "id": "15",

                "urun_ad": "Barilla Fusilli Burgu 500 G",

                "urun_url": "",

            }

        ]



        guncellenen_satirlar, denetim_satirlari, stats = backfill_rows(eski_satirlar, indexes)



        self.assertEqual(

            guncellenen_satirlar[0]["urun_url"],

            "https://www.migros.com.tr/barilla-fusilli-burgu-makarna-500-g-p-xyz987",

        )

        self.assertEqual(denetim_satirlari[0]["match_type"], "reduced_token_bag_name")

        self.assertEqual(stats["updated"], 1)





if __name__ == "__main__":

    unittest.main()

