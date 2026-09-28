import unittest

from datetime import datetime, timezone

from pathlib import Path



import pandas as pd

from psycopg2 import OperationalError



from migros_weekly_supabase_sync import (

    build_default_anomaly_detector,

    canonicalize_market_name,

    derive_migros_url_key,

    filter_reyondan_raw_df,

    prepare_sync_rows,

    sync_to_database_with_retry,

)

from shrinkflation import TespitEsikleri





class MigrosWeeklySupabaseSyncTests(unittest.TestCase):

    class _DummyConn:

        def __init__(self) -> None:

            self.rollback_calls = 0

            self.close_calls = 0



        def rollback(self) -> None:

            self.rollback_calls += 1



        def close(self) -> None:

            self.close_calls += 1



    def test_derive_migros_url_key_uses_path_slug(self) -> None:

        self.assertEqual(

            derive_migros_url_key("https://www.migros.com.tr/akturk-vanilyali-gofret-300-g-p-6b0073"),

            "akturk-vanilyali-gofret-300-g-p-6b0073",

        )



    def test_filter_reyondan_raw_df_excludes_reyondan_brand(self) -> None:

        raw_df = pd.DataFrame(

            [

                {"brand": "Reyondan", "product_name": "A"},

                {"brand": "Migros", "product_name": "B"},

            ]

        )



        filtered = filter_reyondan_raw_df(raw_df)



        self.assertEqual(filtered["product_name"].tolist(), ["B"])



    def test_filter_reyondan_raw_df_excludes_non_packaged_household_tools(self) -> None:

        raw_df = pd.DataFrame(

            [

                {

                    "brand": "Bee Home",

                    "product_name": "Bee Home Katlanır Su Kovası 13 L",

                    "site_main_category": "Deterjan ve Temizlik",

                    "listing_subcategory": "Plastik Kovalar",

                },

                {

                    "brand": "Migros",

                    "product_name": "Migros Çöp Torbası 20 Adet",

                    "site_main_category": "Deterjan ve Temizlik",

                    "listing_subcategory": "Çöp Poşeti",

                },

                {

                    "brand": "Hasmandıra",

                    "product_name": "Hasmandıra Kova Tereyağ 500 G",

                    "site_main_category": "Süt ve Kahvaltılık",

                    "listing_subcategory": "Tereyağı",

                },

            ]

        )



        filtered = filter_reyondan_raw_df(raw_df)



        self.assertEqual(

            filtered["product_name"].tolist(),

            ["Migros Çöp Torbası 20 Adet", "Hasmandıra Kova Tereyağ 500 G"],

        )



    def test_canonicalize_market_name_matches_existing_db_variant(self) -> None:

        self.assertEqual(canonicalize_market_name("Migros"), "MİGROS")

        self.assertEqual(canonicalize_market_name("MİGROS"), "MİGROS")



    def test_prepare_sync_rows_normalizes_measure_and_unit_price(self) -> None:

        raw_df = pd.DataFrame(

            [

                {

                    "product_name": "Test Sut 1 L",

                    "product_url": "https://www.migros.com.tr/test-sut-1-l-p-abc123",

                    "site_product_code": "123456",

                    "url_key": "test-sut-1-l-p-abc123",

                    "brand": "Test",

                    "site_main_category": "Icecek",

                    "scrape_timestamp": "2026-04-27T19:00:00+03:00",

                    "current_price": "50",

                    "package_total_value": "1",

                    "package_unit": "l",

                    "unit_price_numeric": "50",

                    "item_count": "1",

                }

            ]

        )



        prepared = prepare_sync_rows(raw_df)



        self.assertEqual(prepared.loc[0, "site_product_code"], "123456")

        self.assertEqual(prepared.loc[0, "url_key"], "test-sut-1-l-p-abc123")

        self.assertEqual(prepared.loc[0, "gramaj_degeri"], 1000.0)

        self.assertEqual(prepared.loc[0, "gramaj_birimi"], "ml")

        self.assertAlmostEqual(prepared.loc[0, "birim_fiyat"], 50.0, places=4)



    def test_prepare_sync_rows_deduplicates_relisted_migros_rows(self) -> None:

        raw_df = pd.DataFrame(

            [

                {

                    "product_name": "Migros Un 2 Kg",

                    "product_url": "https://www.migros.com.tr/migros-un-2-kg-p-4c7706",

                    "site_product_code": "5011206",

                    "url_key": "migros-un-2-kg-p-4c7706",

                    "brand": "Migros",

                    "site_main_category": "Temel Gıda",

                    "scrape_timestamp": "2026-05-04T19:00:00+03:00",

                    "current_price": "53.75",

                    "package_total_value": "2",

                    "package_unit": "kg",

                    "unit_price_numeric": "26.875",

                    "item_count": "1",

                },

                {

                    "product_name": "Migros Un 2 Kg",

                    "product_url": "https://www.migros.com.tr/migros-un-2-kg-p-4c8057",

                    "site_product_code": "5013591",

                    "url_key": "migros-un-2-kg-p-4c8057",

                    "brand": "Migros",

                    "site_main_category": "Temel Gıda",

                    "scrape_timestamp": "2026-05-04T19:00:00+03:00",

                    "current_price": "53.75",

                    "package_total_value": "2",

                    "package_unit": "kg",

                    "unit_price_numeric": "26.875",

                    "item_count": "1",

                },

            ]

        )



        prepared = prepare_sync_rows(raw_df)



        self.assertEqual(len(prepared), 1)

        self.assertEqual(prepared.loc[0, "site_product_code"], "5011206")

        self.assertEqual(

            prepared.loc[0, "source_product_urls"],

            "https://www.migros.com.tr/migros-un-2-kg-p-4c7706 | https://www.migros.com.tr/migros-un-2-kg-p-4c8057",

        )



    def test_default_anomaly_detector_flags_shrinkflation(self) -> None:

        tespit_edici = build_default_anomaly_detector(TespitEsikleri())

        guncel_df = pd.DataFrame(

            [

                {

                    "urun_id": 1,

                    "urun_ad": "Test Meyve Suyu 450 Ml",

                    "urun_fiyat": 60,

                    "gramaj_degeri": 450,

                    "gramaj_birimi": "ml",

                    "birim_fiyat": 133.3333,

                    "kazima_tarihi": datetime(2026, 4, 27, 16, 52, tzinfo=timezone.utc),

                }

            ]

        )

        history_df = pd.DataFrame(

            [

                {

                    "urun_id": 1,

                    "urun_ad": "Test Meyve Suyu 500 Ml",

                    "urun_fiyat": 60,

                    "gramaj_degeri": 500,

                    "gramaj_birimi": "ml",

                    "birim_fiyat": 120,

                    "kazima_tarihi": datetime(2026, 4, 21, 13, 4, tzinfo=timezone.utc),

                }

            ]

        )



        anomalies = tespit_edici(guncel_df, history_df)



        self.assertEqual(len(anomalies), 1)

        self.assertEqual(anomalies.loc[0, "anomali_turu"], "shrinkflation")

        self.assertEqual(anomalies.loc[0, "reason"], "price_stable_while_quantity_dropped")



    def test_default_anomaly_detector_flags_unit_price_zscore(self) -> None:

        tespit_edici = build_default_anomaly_detector(TespitEsikleri())

        guncel_df = pd.DataFrame(

            [

                {

                    "urun_id": 1,

                    "urun_ad": "Test Meyve Suyu 500 Ml",

                    "urun_fiyat": 60,

                    "gramaj_degeri": 500,

                    "gramaj_birimi": "ml",

                    "birim_fiyat": 120,

                    "kazima_tarihi": datetime(2026, 4, 27, 16, 52, tzinfo=timezone.utc),

                }

            ]

        )

        history_df = pd.DataFrame(

            [

                {

                    "urun_id": 1,

                    "urun_ad": "Test Meyve Suyu 500 Ml",

                    "urun_fiyat": 50,

                    "gramaj_degeri": 500,

                    "gramaj_birimi": "ml",

                    "birim_fiyat": 100,

                    "kazima_tarihi": datetime(2026, 3, 30, 13, 4, tzinfo=timezone.utc),

                },

                {

                    "urun_id": 1,

                    "urun_ad": "Test Meyve Suyu 500 Ml",

                    "urun_fiyat": 50.5,

                    "gramaj_degeri": 500,

                    "gramaj_birimi": "ml",

                    "birim_fiyat": 101,

                    "kazima_tarihi": datetime(2026, 4, 6, 13, 4, tzinfo=timezone.utc),

                },

                {

                    "urun_id": 1,

                    "urun_ad": "Test Meyve Suyu 500 Ml",

                    "urun_fiyat": 49.5,

                    "gramaj_degeri": 500,

                    "gramaj_birimi": "ml",

                    "birim_fiyat": 99,

                    "kazima_tarihi": datetime(2026, 4, 13, 13, 4, tzinfo=timezone.utc),

                },

                {

                    "urun_id": 1,

                    "urun_ad": "Test Meyve Suyu 500 Ml",

                    "urun_fiyat": 50,

                    "gramaj_degeri": 500,

                    "gramaj_birimi": "ml",

                    "birim_fiyat": 100,

                    "kazima_tarihi": datetime(2026, 4, 21, 13, 4, tzinfo=timezone.utc),

                },

            ]

        )



        anomalies = tespit_edici(guncel_df, history_df)



        self.assertEqual(len(anomalies), 1)

        self.assertEqual(anomalies.loc[0, "anomali_turu"], "unit_price_zscore")

        self.assertEqual(anomalies.loc[0, "reason"], "unit_price_above_history_zscore")



    def test_sync_to_database_with_retry_retries_after_operational_error(self) -> None:

        baglantilar: list[MigrosWeeklySupabaseSyncTests._DummyConn] = []

        sleep_calls: list[float] = []

        sonuc = object()

        attempts = {"count": 0}



        def baglanma_fonksiyonu(_database_url: str) -> MigrosWeeklySupabaseSyncTests._DummyConn:

            baglanti = self._DummyConn()

            baglantilar.append(baglanti)

            return baglanti



        def esitleme_fonksiyonu(**_kwargs):

            attempts["count"] += 1

            if attempts["count"] == 1:

                raise OperationalError("SSL connection has been closed unexpectedly")

            return sonuc



        esitleme_sonucu = sync_to_database_with_retry(

            veritabani_adresi="postgres://example",

            esitleme_satirlari=pd.DataFrame(),

            market_adi="MİGROS",

            tespit_edici=None,

            strict_identity=False,

            denetim_cikti_dizini=Path("/tmp"),

            max_attempts=2,

            retry_delay_seconds=0.25,

            baglanma_fonksiyonu=baglanma_fonksiyonu,

            esitleme_fonksiyonu=esitleme_fonksiyonu,

            sleep_fn=sleep_calls.append,

        )



        self.assertIs(esitleme_sonucu, sonuc)

        self.assertEqual(attempts["count"], 2)

        self.assertEqual(sleep_calls, [0.25])

        self.assertEqual(len(baglantilar), 2)

        self.assertEqual(baglantilar[0].rollback_calls, 1)

        self.assertEqual(baglantilar[0].close_calls, 1)

        self.assertEqual(baglantilar[1].rollback_calls, 0)

        self.assertEqual(baglantilar[1].close_calls, 1)



    def test_sync_to_database_with_retry_raises_after_final_attempt(self) -> None:

        baglantilar: list[MigrosWeeklySupabaseSyncTests._DummyConn] = []

        sleep_calls: list[float] = []



        def baglanma_fonksiyonu(_database_url: str) -> MigrosWeeklySupabaseSyncTests._DummyConn:

            baglanti = self._DummyConn()

            baglantilar.append(baglanti)

            return baglanti



        def esitleme_fonksiyonu(**_kwargs):

            raise OperationalError("SSL connection has been closed unexpectedly")



        with self.assertRaises(OperationalError):

            sync_to_database_with_retry(

                veritabani_adresi="postgres://example",

                esitleme_satirlari=pd.DataFrame(),

                market_adi="MİGROS",

                tespit_edici=None,

                strict_identity=False,

                denetim_cikti_dizini=Path("/tmp"),

                max_attempts=3,

                retry_delay_seconds=0.1,

                baglanma_fonksiyonu=baglanma_fonksiyonu,

                esitleme_fonksiyonu=esitleme_fonksiyonu,

                sleep_fn=sleep_calls.append,

            )



        self.assertEqual(sleep_calls, [0.1, 0.1])

        self.assertEqual(len(baglantilar), 3)

        self.assertTrue(all(baglanti.rollback_calls == 1 for baglanti in baglantilar))

        self.assertTrue(all(baglanti.close_calls == 1 for baglanti in baglantilar))





if __name__ == "__main__":

    unittest.main()

