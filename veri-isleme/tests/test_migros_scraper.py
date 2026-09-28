import unittest



import pandas as pd



from migros_scraper import filter_listing_rows_by_brand, filter_packaged_product_rows, run_pipeline_from_raw_df





class MigrosScraperTests(unittest.TestCase):

    def test_filter_listing_rows_by_brand_excludes_reyondan(self) -> None:

        listing_df = pd.DataFrame(

            [

                {"product_name_from_listing": "A", "listing_brand": "Reyondan", "product_url": "u1"},

                {"product_name_from_listing": "B", "listing_brand": "Migros", "product_url": "u2"},

            ]

        )



        filtered = filter_listing_rows_by_brand(listing_df, excluded_brands={"Reyondan"})



        self.assertEqual(filtered["product_url"].tolist(), ["u2"])



    def test_filter_packaged_product_rows_excludes_household_tools_but_keeps_consumables(self) -> None:

        raw_df = pd.DataFrame(

            [

                {

                    "site_main_category": "Deterjan ve Temizlik",

                    "listing_subcategory": "Temizlik Fırçası",

                    "product_name": "A-plex Bulaşık Fırçası",

                    "brand": "A-plex",

                },

                {

                    "site_main_category": "Deterjan ve Temizlik",

                    "listing_subcategory": "Çöp Poşeti",

                    "product_name": "Migros Çöp Torbası 20 Adet",

                    "brand": "Migros",

                },

                {

                    "site_main_category": "Süt ve Kahvaltılık",

                    "listing_subcategory": "Tereyağı",

                    "product_name": "Hasmandıra Kova Tereyağ 500 G",

                    "brand": "Hasmandıra",

                },

                {

                    "site_main_category": "Atıştırmalık",

                    "listing_subcategory": "Kuruyemiş",

                    "product_name": "Kuru Üzüm 300 G",

                    "brand": "Reyondan",

                },

            ]

        )



        filtered = filter_packaged_product_rows(raw_df)



        self.assertEqual(

            filtered["product_name"].tolist(),

            ["Migros Çöp Torbası 20 Adet", "Hasmandıra Kova Tereyağ 500 G"],

        )



    def test_run_pipeline_from_raw_df_builds_standard_outputs(self) -> None:

        raw_df = pd.DataFrame(

            [

                {

                    "site_main_category": "Atıştırmalık",

                    "product_name": "Godiva Fındık-Badem Krokantlı Sütlü Çikolata 92 G",

                    "product_url": "https://www.migros.com.tr/godiva-findik-badem-krokantli-sutlu-cikolata-92-g-p-6b4acc",

                    "brand": "Godiva",

                    "site_product_code": "7031500",

                    "url_key": "godiva-findik-badem-krokantli-sutlu-cikolata-92-g-p-6b4acc",

                    "current_price": 324.95,

                    "package_total_value": 92.0,

                    "package_unit": "g",

                    "unit_price_numeric": 3532.0652,

                    "scrape_timestamp": "2026-03-22 20:10:14+03:00",

                    "item_count": 1,

                },

                {

                    "site_main_category": "Atıştırmalık",

                    "product_name": "Kent Dökme Şeker Kg",

                    "product_url": None,

                    "brand": "Kent",

                    "site_product_code": None,

                    "url_key": None,

                    "current_price": 159.90,

                    "package_total_value": 1000.0,

                    "package_unit": "g",

                    "unit_price_numeric": 159.9,

                    "scrape_timestamp": "2026-03-22 20:10:14+03:00",

                    "item_count": 1,

                },

            ]

        )



        ciktilar = run_pipeline_from_raw_df(raw_df)



        market_df = ciktilar["market"]

        self.assertEqual(market_df.loc[0, "market_id"], 2)

        self.assertEqual(market_df.loc[0, "market_adi"], "Migros")



        urunler_df = ciktilar["urunler"]

        self.assertEqual(len(urunler_df), 2)

        self.assertEqual(urunler_df.loc[0, "site_product_code"], "7031500")

        self.assertEqual(

            urunler_df.loc[0, "url_key"],

            "godiva-findik-badem-krokantli-sutlu-cikolata-92-g-p-6b4acc",

        )

        self.assertTrue(pd.isna(urunler_df.loc[1, "site_product_code"]))



        fiyat_df = ciktilar["fiyat_zaman_serisi"]

        self.assertEqual(len(fiyat_df), 2)

        self.assertAlmostEqual(fiyat_df.loc[0, "urun_fiyat"], 324.95)

        self.assertEqual(fiyat_df.loc[0, "gramaj_birimi"], "g")

        self.assertAlmostEqual(fiyat_df.loc[1, "gramaj_degeri"], 1000.0)

        self.assertAlmostEqual(fiyat_df.loc[1, "adet_sayisi"], 1.0)



    def test_run_pipeline_from_raw_df_deduplicates_relisted_products(self) -> None:

        raw_df = pd.DataFrame(

            [

                {

                    "site_main_category": "Temel Gıda",

                    "category_page_url": "https://www.migros.com.tr/temel-gida-c-5",

                    "product_name": "Migros Un 2 Kg",

                    "product_url": "https://www.migros.com.tr/migros-un-2-kg-p-4c7706",

                    "brand": "Migros",

                    "site_product_code": "5011206",

                    "url_key": "migros-un-2-kg-p-4c7706",

                    "current_price": 53.75,

                    "package_total_value": 2.0,

                    "package_unit": "kg",

                    "unit_price_numeric": 26.875,

                    "scrape_timestamp": "2026-05-04T19:00:00+03:00",

                    "item_count": 1,

                },

                {

                    "site_main_category": "Temel Gıda",

                    "category_page_url": "https://www.migros.com.tr/temel-gida-c-5",

                    "product_name": "Migros Un 2 Kg",

                    "product_url": "https://www.migros.com.tr/migros-un-2-kg-p-4c8057",

                    "brand": "Migros",

                    "site_product_code": "5013591",

                    "url_key": "migros-un-2-kg-p-4c8057",

                    "current_price": 53.75,

                    "package_total_value": 2.0,

                    "package_unit": "kg",

                    "unit_price_numeric": 26.875,

                    "scrape_timestamp": "2026-05-04T19:00:00+03:00",

                    "item_count": 1,

                },

            ]

        )



        ciktilar = run_pipeline_from_raw_df(raw_df)



        self.assertEqual(len(ciktilar["raw_products"]), 1)

        self.assertEqual(len(ciktilar["urunler"]), 1)

        self.assertEqual(len(ciktilar["fiyat_zaman_serisi"]), 1)

        self.assertEqual(

            ciktilar["raw_products"].loc[0, "source_product_urls"],

            "https://www.migros.com.tr/migros-un-2-kg-p-4c7706 | https://www.migros.com.tr/migros-un-2-kg-p-4c8057",

        )

        self.assertEqual(

            ciktilar["raw_products"].loc[0, "source_site_product_codes"],

            "5011206 | 5013591",

        )



    def test_run_pipeline_from_raw_df_filters_reyondan_and_household_tools(self) -> None:

        raw_df = pd.DataFrame(

            [

                {

                    "site_main_category": "Atıştırmalık",

                    "product_name": "Kuru Üzüm 300 G",

                    "product_url": "https://www.migros.com.tr/kuru-uzum-300-g-p-1",

                    "brand": "Reyondan",

                    "site_product_code": "1",

                    "url_key": "kuru-uzum-300-g-p-1",

                    "current_price": 99.0,

                    "package_total_value": 300.0,

                    "package_unit": "g",

                    "unit_price_numeric": 330.0,

                    "scrape_timestamp": "2026-05-04T19:00:00+03:00",

                    "item_count": 1,

                },

                {

                    "site_main_category": "Deterjan ve Temizlik",

                    "listing_subcategory": "Plastik Kovalar",

                    "product_name": "Bee Home Katlanır Su Kovası 13 L",

                    "product_url": "https://www.migros.com.tr/bee-home-katlanir-su-kovasi-13-l-p-2",

                    "brand": "Bee Home",

                    "site_product_code": "2",

                    "url_key": "bee-home-katlanir-su-kovasi-13-l-p-2",

                    "current_price": 199.0,

                    "package_total_value": 13.0,

                    "package_unit": "l",

                    "unit_price_numeric": 15.3,

                    "scrape_timestamp": "2026-05-04T19:00:00+03:00",

                    "item_count": 1,

                },

                {

                    "site_main_category": "Deterjan ve Temizlik",

                    "listing_subcategory": "Çöp Poşeti",

                    "product_name": "Migros Çöp Torbası 20 Adet",

                    "product_url": "https://www.migros.com.tr/migros-cop-torbasi-20-adet-p-3",

                    "brand": "Migros",

                    "site_product_code": "3",

                    "url_key": "migros-cop-torbasi-20-adet-p-3",

                    "current_price": 74.95,

                    "package_total_value": None,

                    "package_unit": "adet",

                    "unit_price_numeric": 3.74,

                    "scrape_timestamp": "2026-05-04T19:00:00+03:00",

                    "item_count": 20,

                },

                {

                    "site_main_category": "Atıştırmalık",

                    "product_name": "Bisküvi 200 G",

                    "product_url": "https://www.migros.com.tr/biskuvi-200-g-p-4",

                    "brand": "Migros",

                    "site_product_code": "4",

                    "url_key": "biskuvi-200-g-p-4",

                    "current_price": 29.95,

                    "package_total_value": 200.0,

                    "package_unit": "g",

                    "unit_price_numeric": 149.75,

                    "scrape_timestamp": "2026-05-04T19:00:00+03:00",

                    "item_count": 1,

                },

            ]

        )



        ciktilar = run_pipeline_from_raw_df(raw_df)



        self.assertEqual(ciktilar["raw_products"]["product_name"].tolist(), ["Bisküvi 200 G", "Migros Çöp Torbası 20 Adet"])

        self.assertEqual(ciktilar["urunler"]["urun_ad"].tolist(), ["Bisküvi 200 G", "Migros Çöp Torbası 20 Adet"])





if __name__ == "__main__":

    unittest.main()

