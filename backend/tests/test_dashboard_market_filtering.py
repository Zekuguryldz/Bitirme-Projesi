import os
from datetime import date, datetime, timezone
from typing import Optional
import unittest
from unittest.mock import ANY, Mock, patch

from fastapi import HTTPException


os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.routers.dashboard import (
    build_market_filter_sql,
    filter_dashboard_rows_by_category,
    fold_market_text,
    get_dashboard_summary,
    get_first_market_snapshot_date_on_or_after,
    get_latest_market_snapshot_date_on_or_before,
    get_product_price_comparisons,
    get_previous_market_snapshot_date,
    get_risky_products,
    get_snapshot_record_count,
    get_top_price_changes,
    parse_dashboard_market_value,
    parse_urun_durumu,
    parse_dashboard_selected_date,
    resolve_dashboard_comparison_dates,
    resolve_dashboard_selected_dates,
)
from app.services.shrinkflation import ProductChangeFinding, filter_findings
from app.sql_helpers import build_canonical_product_identity_sql


def finding(
    *,
    urun_id: int,
    market_adi: str,
    yeni_kayit_tarihi: Optional[datetime] = None,
) -> ProductChangeFinding:
    return ProductChangeFinding(
        urun_id=urun_id,
        urun_ad=f"Urun {urun_id}",
        market_adi=market_adi,
        urun_kategori="Icecekler",
        onceki_kayit_tarihi=datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
        yeni_kayit_tarihi=yeni_kayit_tarihi or datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc),
        onceki_fiyat=10.0,
        yeni_fiyat=12.0,
        onceki_toplam_icerik=500.0,
        yeni_toplam_icerik=450.0,
        icerik_birimi="g",
        onceki_birim_icerik=50.0,
        yeni_birim_icerik=45.0,
        onceki_birim_fiyat=20.0,
        yeni_birim_fiyat=26.67,
        onceki_adet_sayisi=10.0,
        yeni_adet_sayisi=10.0,
        gramaj_degisim_yuzdesi=-10.0,
        adet_degisim_yuzdesi=0.0,
        birim_icerik_degisim_yuzdesi=-10.0,
        fiyat_degisim_yuzdesi=20.0,
        birim_fiyat_degisim_yuzdesi=33.33,
        shrinkflation_orani_yuzdesi=33.33,
        severity="medium",
        direction="decrease",
        reason="unit_size_reduced",
        is_shrinkflation=True,
    )


class DashboardMarketFilteringTests(unittest.TestCase):
    class _FakeMappingsResult:
        def __init__(self, row):
            self._row = row

        def one(self):
            return self._row

        def first(self):
            return self._row

    class _FakeExecuteResult:
        def __init__(self, row):
            self._row = row

        def mappings(self):
            return DashboardMarketFilteringTests._FakeMappingsResult(self._row)

    class _FakeExecuteSession:
        def __init__(self, row):
            self._row = row
            self.statement = None
            self.params = None

        def execute(self, statement, params=None):
            self.statement = statement
            self.params = params
            return DashboardMarketFilteringTests._FakeExecuteResult(self._row)

    class _FakeDateQuery:
        def __init__(self, row):
            self._row = row
            self.filters = []
            self.joins = []
            self.distinct_called = False
            self.ordering = []

        def select_from(self, *_args):
            return self

        def join(self, *args):
            self.joins.append(args)
            return self

        def filter(self, *conditions):
            self.filters.extend(conditions)
            return self

        def distinct(self):
            self.distinct_called = True
            return self

        def order_by(self, *columns):
            self.ordering.extend(columns)
            return self

        def first(self):
            return self._row

    class _FakeDateSession:
        def __init__(self, row):
            self._row = row
            self.query_result = DashboardMarketFilteringTests._FakeDateQuery(row)
            self.query_args = None

        def query(self, *args):
            self.query_args = args
            return self.query_result

    def test_parse_dashboard_market_value_accepts_sok_variants(self) -> None:
        self.assertEqual(parse_dashboard_market_value("ŞOK"), "sok")
        self.assertEqual(parse_dashboard_market_value("SOK Market"), "sok")

    def test_parse_dashboard_market_value_accepts_migros(self) -> None:
        self.assertEqual(parse_dashboard_market_value("Migros"), "migros")
        self.assertEqual(parse_dashboard_market_value("MİGROS"), "migros")
        self.assertEqual(parse_dashboard_market_value("Migros Sanal Market"), "migros")

    def test_parse_urun_durumu_supports_known_aliases(self) -> None:
        self.assertEqual(parse_urun_durumu(None), "zamlanmis_urunler")
        self.assertEqual(parse_urun_durumu("zamlanan"), "zamlanmis_urunler")
        self.assertEqual(parse_urun_durumu("indirimli"), "indirimdeki_urunler")
        self.assertEqual(parse_urun_durumu("shrinkflation riskli"), "shrinkflation_riskli_urunler")

    def test_fold_market_text_normalizes_turkish_characters(self) -> None:
        self.assertEqual(fold_market_text("MİGROS"), "migros")

    def test_build_market_filter_sql_normalizes_migros_match(self) -> None:
        sql, params = build_market_filter_sql("market_adi", "migros")

        self.assertIn("translate", sql)
        self.assertEqual(params["market_pattern_1"], "migros%")

    def test_build_canonical_product_identity_sql_strips_trailing_product_code(self) -> None:
        sql = build_canonical_product_identity_sql("p.urun_url", "p.urun_ad")

        self.assertIn("regexp_replace", sql)
        self.assertIn("(-p-)[^/?#]+(?=$|[/?#])", sql)
        self.assertIn("p.urun_url", sql)
        self.assertIn("p.urun_ad", sql)

    def test_parse_dashboard_market_value_rejects_unknown_market(self) -> None:
        with self.assertRaises(HTTPException) as context:
            parse_dashboard_market_value("Carrefour")

        self.assertEqual(context.exception.status_code, 422)

    def test_parse_dashboard_selected_date_supports_day_month_year(self) -> None:
        self.assertEqual(parse_dashboard_selected_date("22.03.2026"), date(2026, 3, 22))

    def test_resolve_dashboard_selected_dates_uses_single_date_when_only_start_exists(self) -> None:
        self.assertEqual(
            resolve_dashboard_selected_dates("2026-04-25", None),
            (date(2026, 4, 25), date(2026, 4, 25)),
        )

    def test_resolve_dashboard_selected_dates_orders_range(self) -> None:
        self.assertEqual(
            resolve_dashboard_selected_dates("2026-04-27", "2026-04-21"),
            (date(2026, 4, 21), date(2026, 4, 27)),
        )

    def test_get_previous_market_snapshot_date_returns_previous_market_day(self) -> None:
        fake_db = self._FakeDateSession(type("Row", (), {"tarih": date(2026, 4, 21)})())

        result = get_previous_market_snapshot_date(
            fake_db,
            market="migros",
            selected_date=date(2026, 4, 27),
        )

        self.assertEqual(result, date(2026, 4, 21))
        self.assertIsNotNone(fake_db.query_args)
        self.assertTrue(fake_db.query_result.distinct_called)

    def test_get_latest_market_snapshot_date_on_or_before_returns_previous_market_day(self) -> None:
        fake_db = self._FakeDateSession(type("Row", (), {"tarih": date(2026, 4, 21)})())

        result = get_latest_market_snapshot_date_on_or_before(
            fake_db,
            market="migros",
            selected_date=date(2026, 4, 27),
        )

        self.assertEqual(result, date(2026, 4, 21))
        self.assertIsNotNone(fake_db.query_args)
        self.assertTrue(fake_db.query_result.distinct_called)

    def test_get_first_market_snapshot_date_on_or_after_returns_next_market_day(self) -> None:
        fake_db = self._FakeDateSession(type("Row", (), {"tarih": date(2026, 3, 22)})())

        result = get_first_market_snapshot_date_on_or_after(
            fake_db,
            market="migros",
            selected_date=date(2026, 3, 20),
            max_date=date(2026, 4, 21),
        )

        self.assertEqual(result, date(2026, 3, 22))
        self.assertIsNotNone(fake_db.query_args)
        self.assertTrue(fake_db.query_result.distinct_called)

    def test_resolve_dashboard_comparison_dates_uses_latest_available_day_for_single_date(self) -> None:
        with patch(
            "app.routers.dashboard.get_latest_market_snapshot_date_on_or_before",
            return_value=date(2026, 4, 21),
        ):
            with patch("app.routers.dashboard.get_previous_market_snapshot_date", return_value=date(2026, 3, 22)):
                result = resolve_dashboard_comparison_dates(
                    db=object(),
                    market="migros",
                    tarih_baslangic="2026-04-27",
                    tarih_bitis=None,
                )

        self.assertEqual(result, (date(2026, 3, 22), date(2026, 4, 21), True))

    def test_resolve_dashboard_comparison_dates_uses_available_range_boundaries(self) -> None:
        with patch(
            "app.routers.dashboard.get_latest_market_snapshot_date_on_or_before",
            return_value=date(2026, 4, 21),
        ):
            with patch(
                "app.routers.dashboard.get_first_market_snapshot_date_on_or_after",
                return_value=date(2026, 3, 22),
            ):
                result = resolve_dashboard_comparison_dates(
                    db=object(),
                    market="migros",
                    tarih_baslangic="2026-03-22",
                    tarih_bitis="2026-04-27",
                )

        self.assertEqual(result, (date(2026, 3, 22), date(2026, 4, 21), True))

    def test_get_snapshot_record_count_counts_distinct_products_on_latest_day(self) -> None:
        fake_db = self._FakeExecuteSession({"snapshot_count": 1483})

        result = get_snapshot_record_count(fake_db, "sok")

        self.assertEqual(result, 1483)
        self.assertIsNotNone(fake_db.statement)
        self.assertIn("max(date(f.kazima_tarihi))", str(fake_db.statement))
        self.assertIn("count(distinct coalesce(", str(fake_db.statement))
        self.assertIn("regexp_replace", str(fake_db.statement))
        self.assertEqual(fake_db.params["market_pattern_1"], "sok%")

    def test_get_snapshot_record_count_can_count_selected_snapshot_day(self) -> None:
        fake_db = self._FakeExecuteSession({"snapshot_count": 983})

        result = get_snapshot_record_count(
            fake_db,
            "migros",
            snapshot_date=date(2026, 4, 21),
        )

        self.assertEqual(result, 983)
        self.assertIsNotNone(fake_db.statement)
        self.assertIn("date(f.kazima_tarihi) = :snapshot_date", str(fake_db.statement))
        self.assertIn("count(distinct coalesce(", str(fake_db.statement))
        self.assertEqual(fake_db.params["market_pattern_1"], "migros%")
        self.assertEqual(fake_db.params["snapshot_date"], date(2026, 4, 21))

    def test_filter_findings_filters_by_market(self) -> None:
        findings = [
            finding(urun_id=1, market_adi="SOK Market"),
            finding(urun_id=2, market_adi="Migros Sanal Market"),
        ]

        filtered = filter_findings(findings, market="migros")

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].market_adi, "Migros Sanal Market")

    def test_filter_findings_can_filter_by_selected_day(self) -> None:
        findings = [
            finding(urun_id=1, market_adi="SOK Market"),
            finding(
                urun_id=2,
                market_adi="SOK Market",
                yeni_kayit_tarihi=datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc),
            ),
        ]

        filtered = filter_findings(
            findings,
            date_start=datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc),
            date_end=datetime(2026, 4, 28, 0, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].urun_id, 2)

    def test_filter_dashboard_rows_by_category_matches_canonical_labels(self) -> None:
        rows = [
            {"urun_id": 1, "urun_kategori": "Icecekler"},
            {"urun_id": 2, "urun_kategori": "Temizlik"},
        ]

        filtered = filter_dashboard_rows_by_category(rows, "İçecekler")

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["urun_id"], 1)

    def test_get_top_price_changes_uses_date_comparison_flow_when_dates_are_selected(self) -> None:
        payload = [
            {
                "urun_id": 1,
                "urun_ad": "Deneme",
                "market_adi": "MIGROS",
                "urun_kategori": "Icecekler",
                "eski_birim_fiyat": 0.1,
                "yeni_birim_fiyat": 0.12,
                "birim_fiyat_degisim_yuzdesi": 20.0,
            }
        ]

        with patch(
            "app.routers.dashboard.resolve_dashboard_comparison_dates",
            return_value=(date(2026, 3, 22), date(2026, 4, 21), True),
        ):
            with patch("app.routers.dashboard.list_market_date_comparison_findings", return_value=payload) as date_flow:
                with patch("app.routers.dashboard.list_latest_product_comparisons") as latest_flow:
                    response = get_top_price_changes(
                        market="migros",
                        tarih_baslangic="2026-03-22",
                        tarih_bitis="2026-04-21",
                        db=object(),
                    )

        date_flow.assert_called_once()
        latest_flow.assert_not_called()
        self.assertEqual(response["total"], 1)
        self.assertEqual(response["items"][0]["degisim_yuzdesi"], 20.0)

    def test_get_top_price_changes_uses_previous_day_when_single_date_selected(self) -> None:
        payload = [
            {
                "urun_id": 1,
                "urun_ad": "Deneme",
                "birim_fiyat_degisim_yuzdesi": 20.0,
            }
        ]

        with patch(
            "app.routers.dashboard.get_latest_market_snapshot_date_on_or_before",
            return_value=date(2026, 4, 21),
        ):
            with patch("app.routers.dashboard.get_previous_market_snapshot_date", return_value=date(2026, 3, 22)):
                with patch("app.routers.dashboard.list_market_date_comparison_findings", return_value=payload) as date_flow:
                    with patch("app.routers.dashboard.list_latest_product_comparisons") as latest_flow:
                        response = get_top_price_changes(
                            market="migros",
                            tarih_baslangic="2026-04-27",
                            db=object(),
                        )

        date_flow.assert_called_once()
        latest_flow.assert_not_called()
        self.assertEqual(response["total"], 1)
        self.assertEqual(response["items"][0]["degisim_yuzdesi"], 20.0)

    def test_get_top_price_changes_returns_empty_when_range_collapses_to_same_snapshot_day(self) -> None:
        with patch(
            "app.routers.dashboard.resolve_dashboard_comparison_dates",
            return_value=(date(2026, 4, 21), date(2026, 4, 21), True),
        ):
            with patch("app.routers.dashboard.list_market_date_comparison_findings") as date_flow:
                response = get_top_price_changes(
                    market="migros",
                    tarih_baslangic="2026-04-21",
                    tarih_bitis="2026-04-27",
                    db=object(),
                )

        date_flow.assert_not_called()
        self.assertEqual(response["total"], 0)
        self.assertEqual(response["items"], [])

    def test_get_top_price_changes_uses_discount_flow_for_indirimdeki_urunler(self) -> None:
        payload = [
            {
                "urun_id": 1,
                "urun_ad": "Deneme",
                "birim_fiyat_degisim_yuzdesi": -20.0,
            }
        ]

        with patch("app.routers.dashboard.list_latest_product_comparisons", return_value=payload) as latest_flow:
            response = get_top_price_changes(
                market="migros",
                urun_durumu="indirimdeki_urunler",
                db=object(),
            )

        latest_flow.assert_called_once()
        self.assertTrue(latest_flow.call_args.kwargs["decreases_only"])
        self.assertTrue(latest_flow.call_args.kwargs["sort_by_unit_price_decrease"])
        self.assertEqual(response["items"][0]["degisim_yuzdesi"], -20.0)

    def test_get_risky_products_keeps_history_flow_without_selected_dates(self) -> None:
        payload = [{"urun_id": 1, "urun_ad": "Deneme"}]

        with patch("app.routers.dashboard.list_market_date_comparison_findings") as date_flow:
            with patch("app.routers.dashboard.list_shrinkflation_risk_findings", return_value=payload) as history_flow:
                response = get_risky_products(
                    market="migros",
                    db=object(),
                )

        date_flow.assert_not_called()
        history_flow.assert_called_once()
        self.assertEqual(response["total"], 1)

    def test_get_risky_products_uses_previous_day_comparison_when_single_date_selected(self) -> None:
        payload = [{"urun_id": 1, "urun_ad": "Deneme"}]

        with patch(
            "app.routers.dashboard.get_latest_market_snapshot_date_on_or_before",
            return_value=date(2026, 4, 21),
        ):
            with patch("app.routers.dashboard.get_previous_market_snapshot_date", return_value=date(2026, 3, 22)):
                with patch("app.routers.dashboard.list_market_date_comparison_findings", return_value=payload) as date_flow:
                    with patch("app.routers.dashboard.list_shrinkflation_risk_findings") as history_flow:
                        response = get_risky_products(
                            market="migros",
                            tarih_baslangic="2026-04-27",
                            db=object(),
                        )

        date_flow.assert_called_once()
        history_flow.assert_not_called()
        self.assertEqual(response["total"], 1)

    def test_get_risky_products_returns_empty_when_single_date_has_no_previous_snapshot(self) -> None:
        with patch(
            "app.routers.dashboard.get_latest_market_snapshot_date_on_or_before",
            return_value=date(2026, 4, 21),
        ):
            with patch("app.routers.dashboard.get_previous_market_snapshot_date", return_value=None):
                with patch("app.routers.dashboard.list_market_date_comparison_findings") as date_flow:
                    with patch("app.routers.dashboard.list_shrinkflation_risk_findings") as history_flow:
                        response = get_risky_products(
                            market="migros",
                            tarih_baslangic="2026-04-27",
                            db=object(),
                        )

        date_flow.assert_not_called()
        history_flow.assert_not_called()
        self.assertEqual(response["total"], 0)

    def test_get_risky_products_returns_empty_when_range_collapses_to_same_snapshot_day(self) -> None:
        with patch(
            "app.routers.dashboard.resolve_dashboard_comparison_dates",
            return_value=(date(2026, 4, 21), date(2026, 4, 21), True),
        ):
            with patch("app.routers.dashboard.list_market_date_comparison_findings") as date_flow:
                response = get_risky_products(
                    market="migros",
                    tarih_baslangic="2026-04-21",
                    tarih_bitis="2026-04-27",
                    db=object(),
                )

        date_flow.assert_not_called()
        self.assertEqual(response["total"], 0)
        self.assertEqual(response["items"], [])

    def test_get_risky_products_uses_date_comparison_flow_when_dates_are_selected(self) -> None:
        payload = [{"urun_id": 1, "urun_ad": "Deneme"}]

        with patch(
            "app.routers.dashboard.resolve_dashboard_comparison_dates",
            return_value=(date(2026, 3, 22), date(2026, 4, 21), True),
        ):
            with patch("app.routers.dashboard.list_market_date_comparison_findings", return_value=payload) as date_flow:
                with patch("app.routers.dashboard.list_shrinkflation_risk_findings") as history_flow:
                    response = get_risky_products(
                        market="migros",
                        tarih_baslangic="2026-03-22",
                        tarih_bitis="2026-04-21",
                        db=object(),
                    )

        date_flow.assert_called_once()
        history_flow.assert_not_called()
        self.assertEqual(response["total"], 1)

    def test_get_risky_products_uses_selected_range_for_anomali_rows(self) -> None:
        payload = [{"urun_id": 1, "urun_ad": "Deneme"}]
        fake_db = object()

        with patch(
            "app.routers.dashboard.resolve_dashboard_comparison_dates",
            return_value=(date(2026, 3, 22), date(2026, 4, 21), True),
        ):
            with patch("app.routers.dashboard.list_anomali_findings", return_value=payload) as anomali_rows:
                with patch("app.routers.dashboard.count_anomali_findings", return_value=5) as anomali_count:
                    response = get_risky_products(
                        market="migros",
                        tarih_baslangic="2026-03-22",
                        tarih_bitis="2026-04-27",
                        db=fake_db,
                    )

        anomali_rows.assert_called_once_with(
            fake_db,
            market="migros",
            selected_start_date=date(2026, 3, 22),
            selected_end_date=date(2026, 4, 27),
            limit=None,
        )
        anomali_count.assert_called_once_with(
            fake_db,
            market="migros",
            selected_start_date=date(2026, 3, 22),
            selected_end_date=date(2026, 4, 27),
        )
        self.assertEqual(response["total"], 5)
        self.assertEqual(response["items"], payload)

    def test_get_dashboard_summary_uses_selected_range_for_anomali_count(self) -> None:
        fake_category_query = Mock()
        fake_category_query.filter.return_value = fake_category_query
        fake_category_query.scalar.return_value = 12
        fake_db = Mock()
        fake_db.query.return_value = fake_category_query
        fake_db.execute.side_effect = [
            self._FakeExecuteResult(
                {
                    "ortalama_fiyat": 100.0,
                    "minimum_fiyat": 10.0,
                    "maksimum_fiyat": 250.0,
                }
            ),
            self._FakeExecuteResult({"urun_kategori": "Icecekler"}),
        ]

        with patch("app.routers.dashboard.get_snapshot_record_count", return_value=1483) as snapshot_count:
            with patch(
                "app.routers.dashboard.resolve_dashboard_comparison_dates",
                return_value=(date(2026, 3, 22), date(2026, 4, 21), True),
            ):
                with patch("app.routers.dashboard.count_anomali_findings", return_value=5) as anomali_count:
                    response = get_dashboard_summary(
                        market="migros",
                        tarih_baslangic="2026-03-22",
                        tarih_bitis="2026-04-27",
                        db=fake_db,
                    )

        snapshot_count.assert_called_once_with(
            fake_db,
            "migros",
            snapshot_date=date(2026, 4, 21),
        )
        anomali_count.assert_called_once_with(
            fake_db,
            market="migros",
            selected_start_date=date(2026, 3, 22),
            selected_end_date=date(2026, 4, 27),
        )
        self.assertEqual(response["bugun_guncellenen_kayit"], 5)
        self.assertEqual(response["toplam_urun_tarihi"], date(2026, 4, 21))

    def test_get_dashboard_summary_returns_zero_when_range_collapses_to_same_snapshot_day(self) -> None:
        fake_category_query = Mock()
        fake_category_query.filter.return_value = fake_category_query
        fake_category_query.scalar.return_value = 12
        fake_db = Mock()
        fake_db.query.return_value = fake_category_query
        fake_db.execute.side_effect = [
            self._FakeExecuteResult(
                {
                    "ortalama_fiyat": 100.0,
                    "minimum_fiyat": 10.0,
                    "maksimum_fiyat": 250.0,
                }
            ),
            self._FakeExecuteResult({"urun_kategori": "Icecekler"}),
        ]

        with patch("app.routers.dashboard.get_snapshot_record_count", return_value=1483) as snapshot_count:
            with patch(
                "app.routers.dashboard.resolve_dashboard_comparison_dates",
                return_value=(date(2026, 4, 21), date(2026, 4, 21), True),
            ):
                with patch("app.routers.dashboard.count_anomali_findings", return_value=0) as anomali_count:
                    response = get_dashboard_summary(
                        market="migros",
                        tarih_baslangic="2026-04-21",
                        tarih_bitis="2026-04-27",
                        db=fake_db,
                    )

        snapshot_count.assert_called_once_with(
            fake_db,
            "migros",
            snapshot_date=date(2026, 4, 21),
        )
        anomali_count.assert_called_once_with(
            fake_db,
            market="migros",
            selected_start_date=date(2026, 4, 21),
            selected_end_date=date(2026, 4, 27),
        )
        self.assertEqual(response["bugun_guncellenen_kayit"], 0)
        self.assertEqual(response["toplam_urun_tarihi"], date(2026, 4, 21))

    def test_get_product_price_comparisons_filters_latest_flow_by_category(self) -> None:
        payload = [
            {"urun_id": 1, "urun_kategori": "Icecekler", "urun_ad": "Icecek"},
            {"urun_id": 2, "urun_kategori": "Temizlik", "urun_ad": "Temizlik"},
        ]

        with patch("app.routers.dashboard.list_latest_product_comparisons", return_value=payload) as latest_flow:
            response = get_product_price_comparisons(
                market="migros",
                kategori="İçecekler",
                limit=10,
                offset=0,
                db=object(),
            )

        latest_flow.assert_called_once()
        self.assertEqual(response["total"], 1)
        self.assertEqual(response["items"][0]["urun_id"], 1)

    def test_get_product_price_comparisons_uses_shrinkflation_history_for_selected_status(self) -> None:
        payload = [
            {"urun_id": 1, "urun_kategori": "Icecekler", "urun_ad": "Icecek"},
        ]

        with patch("app.routers.dashboard.list_shrinkflation_risk_findings", return_value=payload) as history_flow:
            with patch("app.routers.dashboard.list_latest_product_comparisons") as latest_flow:
                response = get_product_price_comparisons(
                    market="migros",
                    urun_durumu="shrinkflation_riskli_urunler",
                    limit=10,
                    offset=0,
                    db=object(),
                )

        history_flow.assert_called_once()
        latest_flow.assert_not_called()
        self.assertEqual(response["total"], 1)
        self.assertEqual(response["items"][0]["urun_id"], 1)

    def test_get_product_price_comparisons_filters_date_flow_by_category(self) -> None:
        payload = [
            {"urun_id": 1, "urun_kategori": "Icecekler", "urun_ad": "Icecek"},
            {"urun_id": 2, "urun_kategori": "Temizlik", "urun_ad": "Temizlik"},
        ]

        with patch(
            "app.routers.dashboard.resolve_dashboard_comparison_dates",
            return_value=(date(2026, 3, 22), date(2026, 4, 21), True),
        ):
            with patch("app.routers.dashboard.list_market_date_comparison_findings", return_value=payload) as date_flow:
                response = get_product_price_comparisons(
                    market="migros",
                    kategori="İçecekler",
                    tarih_baslangic="2026-03-22",
                    tarih_bitis="2026-04-21",
                    limit=10,
                    offset=0,
                    db=object(),
                )

        date_flow.assert_called_once()
        self.assertEqual(response["total"], 1)
        self.assertEqual(response["items"][0]["urun_id"], 1)

    def test_get_product_price_comparisons_keeps_shrinkflation_empty_when_anomali_rows_empty(self) -> None:
        fake_db = Mock()

        with patch("app.routers.dashboard.list_anomali_findings", return_value=[]) as anomali_rows:
            with patch("app.routers.dashboard.list_shrinkflation_risk_findings") as history_flow:
                response = get_product_price_comparisons(
                    market="migros",
                    urun_durumu="shrinkflation_riskli_urunler",
                    limit=10,
                    offset=0,
                    db=fake_db,
                )

        anomali_rows.assert_called_once_with(
            fake_db,
            market="migros",
            selected_start_date=None,
            selected_end_date=None,
            limit=None,
        )
        history_flow.assert_not_called()
        self.assertEqual(response["total"], 0)
        self.assertEqual(response["items"], [])

    def test_get_product_price_comparisons_returns_empty_when_range_collapses_to_same_snapshot_day(self) -> None:
        with patch(
            "app.routers.dashboard.resolve_dashboard_comparison_dates",
            return_value=(date(2026, 4, 21), date(2026, 4, 21), True),
        ):
            with patch("app.routers.dashboard.list_market_date_comparison_findings") as date_flow:
                response = get_product_price_comparisons(
                    market="migros",
                    tarih_baslangic="2026-04-21",
                    tarih_bitis="2026-04-27",
                    limit=10,
                    offset=0,
                    db=object(),
                )

        date_flow.assert_not_called()
        self.assertEqual(response["total"], 0)
        self.assertEqual(response["items"], [])


if __name__ == "__main__":
    unittest.main()
