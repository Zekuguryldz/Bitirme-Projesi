import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException


os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.routers.products import (
    canonical_category_label,
    coerce_decimal,
    deduplicate_category_labels,
    get_products,
    get_product_dates,
    normalize_market_value,
    normalize_urun_durumu_value,
    parse_product_datetime_end,
    parse_product_datetime_range,
    parse_product_datetime_start,
)


class ProductsRouterTests(unittest.TestCase):
    class _FakeMappingsResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _FakeExecuteResult:
        def __init__(self, rows):
            self._rows = rows

        def mappings(self):
            return ProductsRouterTests._FakeMappingsResult(self._rows)

    class _FakeSession:
        def __init__(self, rows):
            self._rows = rows
            self.statement = None
            self.params = None

        def execute(self, statement, params=None):
            self.statement = statement
            self.params = params
            return ProductsRouterTests._FakeExecuteResult(self._rows)

    class _FakeQuery:
        def __init__(self, rows):
            self._rows = rows
            self.filters = []
            self.ordering = []
            self.distinct_called = False
            self.selected_from = None
            self.joins = []

        def select_from(self, model):
            self.selected_from = model
            return self

        def filter(self, *conditions):
            self.filters.extend(conditions)
            return self

        def join(self, *args):
            self.joins.append(args)
            return self

        def distinct(self):
            self.distinct_called = True
            return self

        def order_by(self, *columns):
            self.ordering.extend(columns)
            return self

        def all(self):
            return self._rows

    class _FakeDateSession:
        def __init__(self, rows):
            self._rows = rows
            self.query_args = None
            self.query_result = None

        def query(self, *args):
            self.query_args = args
            self.query_result = ProductsRouterTests._FakeQuery(self._rows)
            return self.query_result

    def test_normalize_market_value_accepts_migros(self) -> None:
        self.assertEqual(normalize_market_value("Migros"), "migros")
        self.assertEqual(normalize_market_value("Migros Sanal Market"), "migros")

    def test_canonical_category_label_normalizes_known_values(self) -> None:
        self.assertEqual(canonical_category_label("Icecekler"), "İçecekler")
        self.assertEqual(canonical_category_label("Icecek"), "İçecekler")
        self.assertEqual(canonical_category_label(" Icecekler "), "İçecekler")
        self.assertEqual(canonical_category_label("Atistirmalik"), "Atıştırmalıklar")
        self.assertEqual(canonical_category_label("Deterjan & Temizlik"), "Deterjan ve Temizlik")
        self.assertEqual(canonical_category_label("Et, Tavuk ve Balık"), "Et Tavuk Balık")

    def test_deduplicate_category_labels_collapses_duplicate_variants(self) -> None:
        self.assertEqual(
            deduplicate_category_labels([
                "Icecek",
                "Icecekler",
                "İçecekler",
                " İçecekler ",
                "Atistirmalik",
                "Atistirmaliklar",
                "Deterjan & Temizlik",
                "Deterjan ve Temizlik",
                "Temizlik",
            ]),
            ["Atıştırmalıklar", "Deterjan ve Temizlik", "İçecekler", "Temizlik"],
        )

    def test_parse_product_datetime_range_accepts_iso_date_format(self) -> None:
        start, end = parse_product_datetime_range("2025-03-20")

        self.assertEqual(start, datetime(2025, 3, 20))
        self.assertEqual(end, datetime(2025, 3, 21))

    def test_parse_product_datetime_range_accepts_display_format(self) -> None:
        start, end = parse_product_datetime_range("20.03.2025")

        self.assertEqual(start, datetime(2025, 3, 20))
        self.assertEqual(end, datetime(2025, 3, 21))

    def test_parse_product_datetime_range_accepts_iso_datetime(self) -> None:
        start, end = parse_product_datetime_range("2026-04-21T19:32:44.033386+00:00")

        self.assertEqual(
            start,
            datetime(2026, 4, 21, 19, 32, 44, 33386, tzinfo=timezone.utc),
        )
        self.assertEqual(end - start, timedelta(minutes=1))

    def test_parse_product_datetime_start_and_end_support_range_filters(self) -> None:
        self.assertEqual(
            parse_product_datetime_start("2026-04-21T19:32:00+00:00"),
            datetime(2026, 4, 21, 19, 32, tzinfo=timezone.utc),
        )
        self.assertEqual(
            parse_product_datetime_end("2026-04-21T19:32:00+00:00"),
            datetime(2026, 4, 21, 19, 33, tzinfo=timezone.utc),
        )

    def test_parse_product_datetime_range_rejects_invalid_format(self) -> None:
        with self.assertRaises(HTTPException) as context:
            parse_product_datetime_range("20/03/2025")

        self.assertEqual(context.exception.status_code, 422)

    def test_normalize_urun_durumu_value_accepts_aliases(self) -> None:
        self.assertEqual(normalize_urun_durumu_value("zamlanan"), "zamlanmis_urunler")
        self.assertEqual(normalize_urun_durumu_value("İndirimli Ürünler"), "indirimdeki_urunler")
        self.assertEqual(normalize_urun_durumu_value("shrinkflation riskli"), "shrinkflation_riskli_urunler")
        self.assertIsNone(normalize_urun_durumu_value(""))

    @patch("app.routers.products.list_latest_product_comparisons")
    def test_get_products_filters_by_urun_durumu_and_exposes_status(self, mock_list_latest_product_comparisons) -> None:
        mock_list_latest_product_comparisons.return_value = [
            {
                "urun_id": 2,
                "urun_kategori": "Atistirmaliklar",
                "birim_fiyat_degisim_yuzdesi": Decimal("12.5"),
                "is_shrinkflation": False,
            },
            {
                "urun_id": 3,
                "urun_kategori": "Icecekler",
                "birim_fiyat_degisim_yuzdesi": Decimal("-4.0"),
                "is_shrinkflation": False,
            },
        ]
        fake_db = self._FakeSession([
            {
                "id": 2,
                "urun_ad": "Muratbey Kraker",
                "urun_url": "https://example.com/muratbey-kraker",
                "urun_kategori": "Atistirmaliklar",
                "market_adi": "MİGROS",
                "urun_fiyat": Decimal("42.90"),
                "gramaj_degeri": Decimal("180"),
                "gramaj_birimi": "g",
                "birim_fiyat": Decimal("0.2383"),
                "urun_marka": "Muratbey",
                "eklenme_tarihi": datetime(2026, 4, 21, 13, 4, 2, tzinfo=timezone.utc),
                "total_count": 1,
            }
        ])

        response = get_products(
            db=fake_db,
            market="MİGROS",
            kategori="Atıştırmalıklar",
            urun_durumu="zamlanan",
            limit=1,
            offset=0,
        )

        self.assertEqual(response["total"], 1)
        self.assertEqual(response["items"][0]["urun_durumu"], "zamlanmis_urunler")
        self.assertIn("IN", str(fake_db.statement))
        self.assertEqual(mock_list_latest_product_comparisons.call_args.kwargs["market"], "migros")

    @patch("app.routers.products.list_latest_product_comparisons")
    def test_get_products_returns_empty_when_urun_durumu_has_no_matching_products(self, mock_list_latest_product_comparisons) -> None:
        mock_list_latest_product_comparisons.return_value = [
            {
                "urun_id": 3,
                "urun_kategori": "Icecekler",
                "birim_fiyat_degisim_yuzdesi": Decimal("8.0"),
                "is_shrinkflation": False,
            }
        ]
        fake_db = self._FakeSession([
            {
                "id": 3,
                "urun_ad": "Deneme",
                "urun_url": "https://example.com/deneme",
                "urun_kategori": "Icecekler",
                "market_adi": "ŞOK",
                "urun_fiyat": Decimal("9.90"),
                "gramaj_degeri": Decimal("100"),
                "gramaj_birimi": "g",
                "birim_fiyat": Decimal("0.0990"),
                "urun_marka": "Marka",
                "eklenme_tarihi": datetime(2026, 4, 21, 13, 4, 2, tzinfo=timezone.utc),
                "total_count": 1,
            }
        ])

        response = get_products(
            db=fake_db,
            urun_durumu="indirimli",
            kategori="Temizlik",
            limit=1,
            offset=0,
        )

        self.assertEqual(response, {"total": 0, "items": []})
        self.assertIsNone(fake_db.statement)

    @patch("app.routers.products.list_latest_product_comparisons")
    @patch("app.routers.products.build_shrinkflation_status_lookup_from_anomali")
    def test_get_products_uses_anomali_lookup_for_shrinkflation_date_ranges(
        self,
        mock_build_shrinkflation_status_lookup_from_anomali,
        mock_list_latest_product_comparisons,
    ) -> None:
        mock_build_shrinkflation_status_lookup_from_anomali.return_value = {
            2: "shrinkflation_riskli_urunler",
        }
        fake_db = self._FakeSession([
            {
                "id": 2,
                "urun_ad": "Muratbey Kraker",
                "urun_url": "https://example.com/muratbey-kraker",
                "urun_kategori": "Atistirmaliklar",
                "market_adi": "ŞOK",
                "urun_fiyat": Decimal("42.90"),
                "gramaj_degeri": Decimal("180"),
                "gramaj_birimi": "g",
                "birim_fiyat": Decimal("0.2383"),
                "urun_marka": "Muratbey",
                "eklenme_tarihi": datetime(2026, 5, 16, 13, 4, 2, tzinfo=timezone.utc),
                "total_count": 1,
            }
        ])

        response = get_products(
            db=fake_db,
            market="ŞOK",
            kategori="Atıştırmalıklar",
            urun_durumu="shrinkflation_riskli_urunler",
            tarih_baslangic="2026-05-09",
            tarih_bitis="2026-05-16",
            limit=1,
            offset=0,
        )

        self.assertEqual(response["total"], 1)
        self.assertEqual(response["items"][0]["urun_durumu"], "shrinkflation_riskli_urunler")
        mock_build_shrinkflation_status_lookup_from_anomali.assert_called_once()
        mock_list_latest_product_comparisons.assert_not_called()

    def test_coerce_decimal_rejects_non_finite_values(self) -> None:
        self.assertIsNone(coerce_decimal("NaN"))
        self.assertIsNone(coerce_decimal("Infinity"))

    def test_get_products_returns_snapshot_price_fields_for_date_range(self) -> None:
        fake_db = self._FakeSession([
            {
                "id": 1,
                "urun_ad": "Eti Süt Burger",
                "urun_url": "https://example.com/eti-sut-burger",
                "urun_kategori": "Icecekler",
                "market_adi": "MİGROS",
                "urun_fiyat": Decimal("18.50"),
                "gramaj_degeri": Decimal("35"),
                "gramaj_birimi": "g",
                "birim_fiyat": Decimal("999.99"),
                "urun_marka": "Eti",
                "eklenme_tarihi": datetime(2026, 3, 22, 17, 10, 14, tzinfo=timezone.utc),
                "kayit_id": 10,
                "total_count": 1,
            }
        ])

        response = get_products(
            db=fake_db,
            market="MİGROS",
            tarih_baslangic="2026-03-01",
            tarih_bitis="2026-04-30",
            limit=1,
            offset=0,
        )

        self.assertEqual(response["total"], 1)
        self.assertEqual(response["items"][0]["urun_url"], "https://example.com/eti-sut-burger")
        self.assertEqual(response["items"][0]["urun_fiyat"], Decimal("18.50"))
        self.assertEqual(response["items"][0]["gramaj_degeri"], Decimal("35"))
        self.assertEqual(response["items"][0]["gramaj_birimi"], "g")
        self.assertEqual(response["items"][0]["birim_fiyat"], Decimal("0.5286"))
        self.assertIn("fiyat_zaman_serisi", str(fake_db.statement))

    def test_get_products_returns_latest_snapshot_price_fields_without_date_range(self) -> None:
        fake_db = self._FakeSession([
            {
                "id": 2,
                "urun_ad": "Muratbey Taze Peynir",
                "urun_url": "https://example.com/muratbey-taze-peynir",
                "urun_kategori": "Sut Kahvaltilik",
                "market_adi": "MİGROS",
                "urun_fiyat": Decimal("99.95"),
                "gramaj_degeri": Decimal("200"),
                "gramaj_birimi": "g",
                "birim_fiyat": Decimal("999.99"),
                "urun_marka": "Muratbey",
                "eklenme_tarihi": datetime(2026, 4, 21, 13, 4, 2, tzinfo=timezone.utc),
                "total_count": 1,
            }
        ])

        response = get_products(
            db=fake_db,
            market="MİGROS",
            limit=1,
            offset=0,
        )

        self.assertEqual(response["total"], 1)
        self.assertEqual(response["items"][0]["urun_url"], "https://example.com/muratbey-taze-peynir")
        self.assertEqual(response["items"][0]["urun_fiyat"], Decimal("99.95"))
        self.assertEqual(response["items"][0]["gramaj_degeri"], Decimal("200"))
        self.assertEqual(response["items"][0]["gramaj_birimi"], "g")
        self.assertEqual(response["items"][0]["birim_fiyat"], Decimal("0.4998"))
        self.assertIn("latest_price_snapshots", str(fake_db.statement))

    def test_get_products_ignores_non_finite_measure_values(self) -> None:
        fake_db = self._FakeSession([
            {
                "id": 4,
                "urun_ad": "Deneme Urun",
                "urun_url": "https://example.com/deneme-urun",
                "urun_kategori": "Icecekler",
                "market_adi": "MİGROS",
                "urun_fiyat": Decimal("10.00"),
                "gramaj_degeri": "NaN",
                "gramaj_birimi": "g",
                "birim_fiyat": None,
                "urun_marka": "Marka",
                "eklenme_tarihi": datetime(2026, 4, 21, 13, 4, 2, tzinfo=timezone.utc),
                "total_count": 1,
            }
        ])

        response = get_products(
            db=fake_db,
            market="MİGROS",
            limit=1,
            offset=0,
        )

        self.assertEqual(response["total"], 1)
        self.assertIsNone(response["items"][0]["gramaj_degeri"])
        self.assertIsNone(response["items"][0]["birim_fiyat"])

    def test_get_products_applies_category_filter_without_market(self) -> None:
        fake_db = self._FakeSession([
            {
                "id": 3,
                "urun_ad": "Dimes Meyve Suyu",
                "urun_url": "https://example.com/dimes-meyve-suyu",
                "urun_kategori": "Icecekler",
                "market_adi": "ŞOK",
                "urun_fiyat": Decimal("42.90"),
                "gramaj_degeri": Decimal("1"),
                "gramaj_birimi": "l",
                "birim_fiyat": Decimal("42.90"),
                "urun_marka": "Dimes",
                "eklenme_tarihi": datetime(2026, 4, 21, 13, 4, 2, tzinfo=timezone.utc),
                "total_count": 1,
            }
        ])

        response = get_products(
            db=fake_db,
            kategori="İçecekler",
            limit=1,
            offset=0,
        )

        self.assertEqual(response["total"], 1)
        self.assertEqual(response["items"][0]["urun_kategori"], "İçecekler")
        self.assertEqual(response["items"][0]["gramaj_degeri"], Decimal("1000"))
        self.assertEqual(response["items"][0]["gramaj_birimi"], "ml")
        self.assertEqual(response["items"][0]["birim_fiyat"], Decimal("0.0429"))
        self.assertIn("regexp_replace", str(fake_db.statement))

    def test_get_product_dates_reads_from_price_time_series(self) -> None:
        fake_db = self._FakeDateSession([
            SimpleNamespace(tarih=date(2026, 4, 21)),
            SimpleNamespace(tarih=date(2026, 4, 20)),
        ])

        response = get_product_dates(db=fake_db)

        self.assertEqual(response["total"], 2)
        self.assertEqual(response["items"], [date(2026, 4, 21), date(2026, 4, 20)])
        self.assertIsNotNone(fake_db.query_args)
        self.assertIn("fiyat_zaman_serisi.kazima_tarihi", str(fake_db.query_args[0]))
        self.assertTrue(fake_db.query_result.distinct_called)
        self.assertIsNotNone(fake_db.query_result.selected_from)

    def test_get_product_dates_can_filter_by_market(self) -> None:
        fake_db = self._FakeDateSession([
            SimpleNamespace(tarih=date(2026, 4, 21)),
        ])

        response = get_product_dates(db=fake_db, market="Migros")

        self.assertEqual(response["total"], 1)
        self.assertEqual(len(fake_db.query_result.joins), 1)


if __name__ == "__main__":
    unittest.main()
