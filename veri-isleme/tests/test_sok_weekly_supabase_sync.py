import unittest

from datetime import datetime, timezone

from pathlib import Path

from tempfile import TemporaryDirectory

from unittest.mock import patch



import pandas as pd

import requests



from sok_weekly_supabase_sync import (

    build_default_anomaly_detector,

    derive_sok_site_product_code,

    derive_sok_url_key,

    filter_rows_by_timestamp_window,

    prepare_sync_rows,

    run_scrape,

    run_price_change_detection_from_history,

    parse_timestamp_bound,

    upsert_price_snapshot,

    upsert_product,

)

from sok_scraper import (

    KATEGORI_HEDEFLERI,

    SokMarketScraper,

    deduplicate_relisted_products,

    format_sql_tables,

    load_reference_csv,

    parse_category_listing_page,

    parse_product_detail_page,

    parse_scrape_datetime_input,

)

from shrinkflation import TespitEsikleri





class SokWeeklySupabaseSyncTests(unittest.TestCase):

    class FakeCursor:

        def __init__(self, steps):

            self.steps = list(steps)

            self.current_fetchone = None

            self.executed: list[tuple[str, object]] = []



        def execute(self, sorgu, params=None):

            normalize_sorgu = " ".join(sorgu.strip().split())

            self.executed.append((normalize_sorgu, params))

            if not self.steps:

                self.current_fetchone = None

                return

            expected = self.steps.pop(0)

            eslestirici = expected.get("match")

            if eslestirici and eslestirici not in normalize_sorgu:

                raise AssertionError(f"Unexpected query. Expected match={matcher!r}, got={normalized_query!r}")

            error = expected.get("error")

            if error is not None:

                raise error

            self.current_fetchone = expected.get("fetchone")



        def fetchone(self):

            return self.current_fetchone



    def test_category_targets_match_requested_scope(self) -> None:

        self.assertEqual(len(KATEGORI_HEDEFLERI), 9)

        self.assertEqual(KATEGORI_HEDEFLERI[0].expected_count, 484)

        self.assertEqual(KATEGORI_HEDEFLERI[4].adres, "https://www.sokmarket.com.tr/icecek-c-20505")

        self.assertEqual(KATEGORI_HEDEFLERI[-1].expected_count, 46)



    def test_derive_sok_site_product_code_prefers_explicit_code(self) -> None:

        self.assertEqual(

            derive_sok_site_product_code(

                "https://www.sokmarket.com.tr/akturk-vanilyali-gofret-300-g-p-309449",

                "00147499",

            ),

            "00147499",

        )



    def test_derive_sok_url_key_uses_numeric_suffix(self) -> None:

        self.assertEqual(

            derive_sok_url_key("https://www.sokmarket.com.tr/akturk-vanilyali-gofret-300-g-p-309449"),

            "309449",

        )



    def test_prepare_sync_rows_normalizes_measure_and_unit_price(self) -> None:

        raw_df = pd.DataFrame(

            [

                {

                    "product_name": "Deneme Makarna 500 G",

                    "product_url": "https://www.sokmarket.com.tr/deneme-makarna-500-g-p-1234",

                    "product_code": "00012345",

                    "brand": "Deneme",

                    "site_main_category": "Makarna",

                    "scrape_timestamp": "2026-04-25T18:30:00+03:00",

                    "first_reference_date": "2026-04-20T18:30:00+03:00",

                    "current_price": "50",

                    "package_total_value": "500",

                    "package_unit": "g",

                    "unit_price": "",

                    "item_count": "1",

                }

            ]

        )



        prepared = prepare_sync_rows(raw_df)



        self.assertEqual(prepared.loc[0, "site_product_code"], "00012345")

        self.assertEqual(prepared.loc[0, "url_key"], "1234")

        self.assertEqual(prepared.loc[0, "gramaj_degeri"], 500.0)

        self.assertEqual(prepared.loc[0, "gramaj_birimi"], "g")

        self.assertAlmostEqual(prepared.loc[0, "birim_fiyat"], 100.0, places=4)

        self.assertEqual(

            prepared.loc[0, "son_gorulme_tarihi"].isoformat(),

            "2026-04-25T15:30:00+00:00",

        )



    def test_filter_rows_by_timestamp_window_keeps_only_requested_range(self) -> None:

        df = pd.DataFrame(

            [

                {"id": 1, "zam_tespit_tarihi": pd.Timestamp("2026-05-01T19:00:00+03:00")},

                {"id": 2, "zam_tespit_tarihi": pd.Timestamp("2026-05-09T19:00:00+03:00")},

                {"id": 3, "zam_tespit_tarihi": pd.Timestamp("2026-05-10T19:00:00+03:00")},

            ]

        )



        start = parse_timestamp_bound("2026-05-02")

        end = parse_timestamp_bound("2026-05-09", end_of_day=True)

        filtered = filter_rows_by_timestamp_window(df, "zam_tespit_tarihi", start, end)



        self.assertEqual(filtered["id"].tolist(), [2])



    def test_parse_scrape_datetime_input_defaults_date_only_to_1900(self) -> None:

        ayristirilmis = parse_scrape_datetime_input("2026-05-09")



        self.assertEqual(ayristirilmis.isoformat(), "2026-05-09T19:00:00+03:00")



    def test_prepare_sync_rows_deduplicates_relisted_same_slug_products(self) -> None:

        raw_df = pd.DataFrame(

            [

                {

                    "product_name": "Merba White Chocolate&Cranberry Cookies 150 G",

                    "product_url": "https://www.sokmarket.com.tr/merba-white-chocolate-cranberry-cookies-150-g-p-712749",

                    "product_code": "712749",

                    "brand": "Merba",

                    "site_main_category": "Atıştırmalıklar",

                    "scrape_timestamp": "2026-05-02T19:22:25+03:00",

                    "first_reference_date": None,

                    "current_price": "99",

                    "package_total_value": "150",

                    "package_unit": "g",

                    "unit_price": "660",

                    "item_count": "100",

                },

                {

                    "product_name": "Merba White Chocolate&Cranberry Cookies 150 g",

                    "product_url": "https://www.sokmarket.com.tr/merba-white-chocolate-cranberry-cookies-150-g-p-711822",

                    "product_code": "711822",

                    "brand": "Merba",

                    "site_main_category": "Atıştırmalıklar",

                    "scrape_timestamp": "2026-05-02T19:22:25+03:00",

                    "first_reference_date": None,

                    "current_price": "99",

                    "package_total_value": "150",

                    "package_unit": "g",

                    "unit_price": "660",

                    "item_count": "100",

                },

            ]

        )



        prepared = prepare_sync_rows(raw_df)



        self.assertEqual(len(prepared), 1)

        self.assertEqual(prepared.loc[0, "site_product_code"], "711822")

        self.assertEqual(prepared.loc[0, "urun_ad"], "Merba White Chocolate&Cranberry Cookies 150 g")



    def test_upsert_product_uses_existing_lookup_when_insert_conflicts(self) -> None:

        satir = pd.Series(

            {

                "urun_ad": "Algida Choconetto 430 ml",

                "urun_url": "https://www.sokmarket.com.tr/algida-choconetto-430-ml-p-663689",

                "urun_kategori": "Dondurma",

                "eklenme_tarihi": pd.Timestamp("2026-05-09T19:00:00+03:00"),

                "son_gorulme_tarihi": pd.Timestamp("2026-05-09T19:00:00+03:00"),

                "kazima_tarihi": pd.Timestamp("2026-05-09T19:00:00+03:00"),

                "market_adi": "ŞOK",

                "urun_marka": "Algida",

                "sira_no": 10,

                "site_product_code": "663689",

                "url_key": "663689",

            }

        )

        imlec = self.FakeCursor(

            [

                {"match": "INSERT INTO urunler", "fetchone": None},

                {"match": "WHERE market_id = %s AND site_product_code = %s", "fetchone": {"id": 33245}},

                {"match": "UPDATE urunler"},

            ]

        )



        urun_kimligi, inserted = upsert_product(imlec, satir, market_kimligi=3, urun_kimligi=None)



        self.assertEqual(urun_kimligi, 33245)

        self.assertFalse(inserted)

        self.assertTrue(any("UPDATE urunler" in sorgu for sorgu, _params in imlec.executed))



    def test_upsert_product_uses_current_scrape_timestamp_for_eklenme_tarihi(self) -> None:

        satir = pd.Series(

            {

                "urun_ad": "Algida Choconetto 430 ml",

                "urun_url": "https://www.sokmarket.com.tr/algida-choconetto-430-ml-p-663689",

                "urun_kategori": "Dondurma",

                "eklenme_tarihi": pd.Timestamp("2026-04-25T19:00:00+03:00"),

                "son_gorulme_tarihi": pd.Timestamp("2026-05-09T19:00:00+03:00"),

                "kazima_tarihi": pd.Timestamp("2026-05-09T19:00:00+03:00"),

                "market_adi": "ŞOK",

                "urun_marka": "Algida",

                "sira_no": 10,

                "site_product_code": "663689",

                "url_key": "663689",

            }

        )

        imlec = self.FakeCursor([{"match": "UPDATE urunler"}])



        urun_kimligi, inserted = upsert_product(imlec, satir, market_kimligi=1, urun_kimligi=33245)



        self.assertEqual(urun_kimligi, 33245)

        self.assertFalse(inserted)

        guncelleme_sorgusu, guncelleme_parametreleri = imlec.executed[-1]

        self.assertIn("UPDATE urunler", guncelleme_sorgusu)

        self.assertEqual(guncelleme_parametreleri[3].isoformat(), "2026-05-09T19:00:00+03:00")

        self.assertEqual(guncelleme_parametreleri[5].isoformat(), "2026-05-09T19:00:00+03:00")



    def test_upsert_price_snapshot_updates_existing_row_when_insert_conflicts(self) -> None:

        satir = pd.Series(

            {

                "urun_fiyat": 50.0,

                "gramaj_degeri": 430.0,

                "gramaj_birimi": "ml",

                "birim_fiyat": 116.2791,

                "kazima_tarihi": pd.Timestamp("2026-05-09T19:00:00+03:00"),

                "adet_sayisi": 1,

            }

        )

        imlec = self.FakeCursor(

            [

                {"match": "SELECT kayit_id FROM fiyat_zaman_serisi", "fetchone": None},

                {"match": "INSERT INTO fiyat_zaman_serisi", "fetchone": None},

                {"match": "SELECT kayit_id FROM fiyat_zaman_serisi", "fetchone": {"kayit_id": 987}},

                {"match": "UPDATE fiyat_zaman_serisi"},

            ]

        )



        inserted = upsert_price_snapshot(imlec, urun_kimligi=33245, satir=satir)



        self.assertFalse(inserted)

        self.assertTrue(any("UPDATE fiyat_zaman_serisi" in sorgu for sorgu, _params in imlec.executed))



    def test_parse_category_listing_page_falls_back_to_structured_json(self) -> None:

        html = """
        <html>
          <body>
            <p>1 adet ürün listelendi</p>
            <script type="application/ld+json">
              {
                "@context": "https://schema.org",
                "@type": "ItemList",
                "itemListElement": [
                  {
                    "@type": "ListItem",
                    "position": 1,
                    "item": {
                      "@type": "Product",
                      "name": "Fallback Kola 1 L",
                      "url": "https://www.sokmarket.com.tr/fallback-kola-1-l-p-12345",
                      "sku": "12345",
                      "offers": {
                        "@type": "Offer",
                        "price": "49.95"
                      }
                    }
                  }
                ]
              }
            </script>
          </body>
        </html>
        """



        live_total_count, satirlar = parse_category_listing_page(html, KATEGORI_HEDEFLERI[4], KATEGORI_HEDEFLERI[4].adres)



        self.assertEqual(live_total_count, 1)

        self.assertEqual(len(satirlar), 1)

        self.assertEqual(satirlar[0]["product_name"], "Fallback Kola 1 L")

        self.assertEqual(satirlar[0]["product_url"], "https://www.sokmarket.com.tr/fallback-kola-1-l-p-12345")

        self.assertEqual(satirlar[0]["product_code"], "12345")

        self.assertAlmostEqual(satirlar[0]["listing_price"], 49.95)



    def test_parse_product_detail_page_falls_back_to_next_data(self) -> None:

        html = """
        <html>
          <head>
            <script id="__NEXT_DATA__" type="application/json">
              {
                "props": {
                  "pageProps": {
                    "product": {
                      "name": "Fallback Biskuvi 500 G",
                      "url": "https://www.sokmarket.com.tr/fallback-biskuvi-500-g-p-999",
                      "brand": { "name": "Fallback" },
                      "description": "Deneme açıklama",
                      "sku": "999",
                      "offers": {
                        "price": "87.5"
                      }
                    }
                  }
                }
              }
            </script>
          </head>
          <body></body>
        </html>
        """

        satir = {

            "product_name": "Liste Adı",

            "product_url": "https://www.sokmarket.com.tr/fallback-biskuvi-500-g-p-999",

            "listing_price": None,

            "product_code": "999",

        }



        ayristirilmis = parse_product_detail_page(html, satir, parse_scrape_datetime_input("2026-05-09"))



        self.assertEqual(ayristirilmis["product_name"], "Fallback Biskuvi 500 G")

        self.assertEqual(ayristirilmis["brand"], "Fallback")

        self.assertEqual(ayristirilmis["description"], "Deneme açıklama")

        self.assertEqual(ayristirilmis["product_code"], "999")

        self.assertAlmostEqual(ayristirilmis["current_price"], 87.5)



    def test_deduplicate_relisted_products_keeps_same_url_in_multiple_categories(self) -> None:

        raw_df = pd.DataFrame(

            [

                {

                    "product_name": "Cafe Crown 2'si 1 Arada Fındık 11 g",

                    "product_url": "https://www.sokmarket.com.tr/cafe-crown-2-si-1-arada-findik-11-g-p-3490",

                    "product_code": "3490",

                    "brand": "Cafe",

                    "site_main_category": "İçecek",

                    "current_price": "11.5",

                    "package_total_value": "11",

                    "package_unit": "g",

                    "unit_price": "1045.4545",

                    "item_count": "100",

                    "first_reference_date": None,

                },

                {

                    "product_name": "Cafe Crown 2'si 1 Arada Fındık 11 g",

                    "product_url": "https://www.sokmarket.com.tr/cafe-crown-2-si-1-arada-findik-11-g-p-3490",

                    "product_code": "3490",

                    "brand": "Cafe",

                    "site_main_category": "Kahvaltılık",

                    "current_price": "11.5",

                    "package_total_value": "11",

                    "package_unit": "g",

                    "unit_price": "1045.4545",

                    "item_count": "100",

                    "first_reference_date": None,

                },

            ]

        )



        deduped = deduplicate_relisted_products(raw_df)



        self.assertEqual(len(deduped), 2)



    def test_default_anomaly_detector_flags_shrinkflation(self) -> None:

        tespit_edici = build_default_anomaly_detector(TespitEsikleri())

        guncel_df = pd.DataFrame(

            [

                {

                    "urun_id": 1,

                    "urun_ad": "Test Ürün 450 G",

                    "urun_fiyat": 50,

                    "gramaj_degeri": 450,

                    "gramaj_birimi": "g",

                    "birim_fiyat": 111.1111,

                    "kazima_tarihi": datetime(2026, 4, 25, 15, 30, tzinfo=timezone.utc),

                }

            ]

        )

        history_df = pd.DataFrame(

            [

                {

                    "urun_id": 1,

                    "urun_ad": "Test Ürün 500 G",

                    "urun_fiyat": 50,

                    "gramaj_degeri": 500,

                    "gramaj_birimi": "g",

                    "birim_fiyat": 100,

                    "kazima_tarihi": datetime(2026, 4, 18, 15, 30, tzinfo=timezone.utc),

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

                    "urun_ad": "Test Ürün 500 G",

                    "urun_fiyat": 60,

                    "gramaj_degeri": 500,

                    "gramaj_birimi": "g",

                    "birim_fiyat": 120,

                    "kazima_tarihi": datetime(2026, 4, 25, 15, 30, tzinfo=timezone.utc),

                }

            ]

        )

        history_df = pd.DataFrame(

            [

                {

                    "urun_id": 1,

                    "urun_ad": "Test Ürün 500 G",

                    "urun_fiyat": 50,

                    "gramaj_degeri": 500,

                    "gramaj_birimi": "g",

                    "birim_fiyat": 100,

                    "kazima_tarihi": datetime(2026, 3, 28, 15, 30, tzinfo=timezone.utc),

                },

                {

                    "urun_id": 1,

                    "urun_ad": "Test Ürün 500 G",

                    "urun_fiyat": 50.5,

                    "gramaj_degeri": 500,

                    "gramaj_birimi": "g",

                    "birim_fiyat": 101,

                    "kazima_tarihi": datetime(2026, 4, 4, 15, 30, tzinfo=timezone.utc),

                },

                {

                    "urun_id": 1,

                    "urun_ad": "Test Ürün 500 G",

                    "urun_fiyat": 49.5,

                    "gramaj_degeri": 500,

                    "gramaj_birimi": "g",

                    "birim_fiyat": 99,

                    "kazima_tarihi": datetime(2026, 4, 11, 15, 30, tzinfo=timezone.utc),

                },

                {

                    "urun_id": 1,

                    "urun_ad": "Test Ürün 500 G",

                    "urun_fiyat": 50,

                    "gramaj_degeri": 500,

                    "gramaj_birimi": "g",

                    "birim_fiyat": 100,

                    "kazima_tarihi": datetime(2026, 4, 18, 15, 30, tzinfo=timezone.utc),

                },

            ]

        )



        anomalies = tespit_edici(guncel_df, history_df)



        self.assertEqual(len(anomalies), 1)

        self.assertEqual(anomalies.loc[0, "anomali_turu"], "unit_price_zscore")

        self.assertEqual(anomalies.loc[0, "reason"], "unit_price_above_history_zscore")



    def test_price_change_detection_builds_increase_rows(self) -> None:

        guncel_df = pd.DataFrame(

            [

                {

                    "urun_id": 1,

                    "urun_ad": "Test Ürün 500 G",

                    "urun_fiyat": 55,

                    "gramaj_degeri": 500,

                    "gramaj_birimi": "g",

                    "birim_fiyat": 110,

                    "kazima_tarihi": datetime(2026, 4, 25, 15, 30, tzinfo=timezone.utc),

                }

            ]

        )

        history_df = pd.DataFrame(

            [

                {

                    "urun_id": 1,

                    "urun_ad": "Test Ürün 500 G",

                    "urun_fiyat": 50,

                    "gramaj_degeri": 500,

                    "gramaj_birimi": "g",

                    "birim_fiyat": 100,

                    "kazima_tarihi": datetime(2026, 4, 18, 15, 30, tzinfo=timezone.utc),

                }

            ]

        )



        zamli_df, indirimli_df = run_price_change_detection_from_history(guncel_df, history_df)



        self.assertEqual(len(zamli_df), 1)

        self.assertTrue(indirimli_df.empty)

        self.assertEqual(zamli_df.loc[0, "reason"], "price_increased_same_quantity")



    def test_price_change_detection_skips_false_discount_when_unit_price_rises(self) -> None:

        guncel_df = pd.DataFrame(

            [

                {

                    "urun_id": 1,

                    "urun_ad": "Test Ürün 400 G",

                    "urun_fiyat": 48,

                    "gramaj_degeri": 400,

                    "gramaj_birimi": "g",

                    "birim_fiyat": 120,

                    "kazima_tarihi": datetime(2026, 4, 25, 15, 30, tzinfo=timezone.utc),

                }

            ]

        )

        history_df = pd.DataFrame(

            [

                {

                    "urun_id": 1,

                    "urun_ad": "Test Ürün 500 G",

                    "urun_fiyat": 50,

                    "gramaj_degeri": 500,

                    "gramaj_birimi": "g",

                    "birim_fiyat": 100,

                    "kazima_tarihi": datetime(2026, 4, 18, 15, 30, tzinfo=timezone.utc),

                }

            ]

        )



        zamli_df, indirimli_df = run_price_change_detection_from_history(guncel_df, history_df)



        self.assertTrue(zamli_df.empty)

        self.assertTrue(indirimli_df.empty)



    def test_load_reference_csv_handles_metadata_row_and_semicolon_delimiter(self) -> None:

        with TemporaryDirectory() as tmp_dir:

            csv_path = Path(tmp_dir) / "sokdata.csv"

            csv_path.write_text(

                "\n".join(

                    [

                        "sokmarket_tum_kategoriler_20260323_1604_1425",

                        "Sira;Market;Site Kategori;Marka;Urun Adi;Fiyat (TL);Gramaj/Hacim;Adet;URL;Cekim Tarihi",

                        "1;ŞOK;Temizlik;Ebru;Ebru Sıvı Sabun 750 ml;42.5;750 ml;1;https://www.sokmarket.com.tr/test-p-1;23.03.2026 15:56:49",

                    ]

                ),

                encoding="utf-8-sig",

            )



            referans_df = load_reference_csv(csv_path)



        self.assertEqual(referans_df.columns.tolist()[0], "Sira")

        self.assertEqual(referans_df.loc[0, "Market"], "ŞOK")

        self.assertEqual(referans_df.loc[0, "URL"], "https://www.sokmarket.com.tr/test-p-1")



    def test_format_sql_tables_maps_current_price_to_urun_fiyat(self) -> None:

        raw_df = pd.DataFrame(

            [

                {

                    "product_name": "Test Ürün 500 G",

                    "product_url": "https://www.sokmarket.com.tr/test-urun-500-g-p-123",

                    "site_main_category": "Atıştırmalıklar",

                    "brand": "Test",

                    "product_code": "123",

                    "scrape_timestamp": "2026-04-25T19:00:00+03:00",

                    "current_price": "42.5",

                    "package_total_value": 500,

                    "package_unit": "g",

                    "unit_price": 85,

                    "item_count": 1,

                    "first_reference_date": "2026-03-23T15:56:49+03:00",

                }

            ]

        )



        ciktilar = format_sql_tables(raw_df)



        self.assertEqual(ciktilar["fiyat_zaman_serisi"].loc[0, "urun_fiyat"], 42.5)



    def test_collect_product_details_skips_request_errors_and_records_failure(self) -> None:

        listing_df = pd.DataFrame(

            [

                {"product_url": "https://www.sokmarket.com.tr/basarili-urun-p-1", "product_name": "Basarili Urun"},

                {"product_url": "https://www.sokmarket.com.tr/kayip-urun-p-2", "product_name": "Kayip Urun"},

            ]

        )

        scraper = SokMarketScraper(pause_range=(0, 0))

        not_found = requests.HTTPError("404 Client Error: Not Found")

        not_found.response = requests.Response()

        not_found.response.status_code = 404



        with patch.object(scraper, "fetch_html", side_effect=["<html></html>", not_found]):

            with patch(

                "sok_scraper.parse_product_detail_page",

                return_value={

                    "product_name": "Basarili Urun",

                    "product_url": "https://www.sokmarket.com.tr/basarili-urun-p-1",

                    "current_price": 10.0,

                },

            ):

                sonuc = scraper.collect_product_details(listing_df)



        self.assertEqual(len(sonuc), 1)

        self.assertEqual(sonuc.loc[0, "product_name"], "Basarili Urun")

        self.assertEqual(len(scraper.failed_product_rows), 1)

        self.assertEqual(scraper.failed_product_rows[0]["product_name"], "Kayip Urun")

        self.assertEqual(scraper.failed_product_rows[0]["status_code"], 404)

        self.assertEqual(scraper.failed_product_rows[0]["error_type"], "HTTPError")



    def test_collect_product_details_uses_override_scrape_timestamp(self) -> None:

        listing_df = pd.DataFrame(

            [

                {"product_url": "https://www.sokmarket.com.tr/basarili-urun-p-1", "product_name": "Basarili Urun"},

            ]

        )

        scraper = SokMarketScraper(pause_range=(0, 0))

        gecersiz_kilma_zamani = parse_scrape_datetime_input("2026-05-09")



        with patch.object(scraper, "fetch_html", return_value="<html></html>"):

            with patch(

                "sok_scraper.parse_product_detail_page",

                side_effect=lambda _html, satir, kazima_zaman_damgasi: {

                    "product_name": satir["product_name"],

                    "product_url": satir["product_url"],

                    "scrape_timestamp": kazima_zaman_damgasi.isoformat(),

                },

            ):

                sonuc = scraper.collect_product_details(listing_df, kazima_zaman_damgasi=gecersiz_kilma_zamani)



        self.assertEqual(sonuc.loc[0, "scrape_timestamp"], "2026-05-09T19:00:00+03:00")



    def test_run_scrape_uses_override_timestamp_for_output_dir(self) -> None:

        with TemporaryDirectory() as tmp_dir:

            gecersiz_kilma_zamani = parse_scrape_datetime_input("2026-05-09")

            with patch(

                "sok_weekly_supabase_sync.run_pipeline",

                return_value={"raw_products": pd.DataFrame()},

            ) as mocked_run_pipeline:

                cikti_dizini, raw_df = run_scrape(

                    cikti_koku=Path(tmp_dir),

                    reference_csv_path=Path(tmp_dir) / "sokdata.csv",

                    limit=None,

                    kazima_zaman_damgasi=gecersiz_kilma_zamani,

                )



        self.assertEqual(cikti_dizini.name, "sok_sync_20260509_190000")

        self.assertTrue(raw_df.empty)

        self.assertEqual(mocked_run_pipeline.call_args.kwargs["kazima_zaman_damgasi"], gecersiz_kilma_zamani)





if __name__ == "__main__":

    unittest.main()

