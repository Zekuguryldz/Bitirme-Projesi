from datetime import datetime, timezone
import unittest
from unittest.mock import patch
from typing import Optional

from app.services.shrinkflation import (
    DetectionThresholds,
    FamilySnapshot,
    PriceSnapshot,
    classify_severity,
    compare_snapshots,
    compute_unit_price,
    detect_change_series,
    extract_candidate,
    filter_product_comparison_findings,
    filter_findings,
    list_latest_product_comparisons,
    market_matches,
    pair_family_snapshots,
    pct_change,
)


def snapshot(
    *,
    urun_id: int = 1,
    urun_ad: str = "Test Urun",
    at: str,
    price: float,
    total_quantity: Optional[float],
    unit: Optional[str],
    unit_price: Optional[float],
    unit_quantity: Optional[float] = None,
    pack_count: Optional[float] = None,
) -> PriceSnapshot:
    return PriceSnapshot(
        urun_id=urun_id,
        urun_ad=urun_ad,
        kaynak_urun_ad=urun_ad,
        market_adi="SOK Market",
        urun_kategori="Icecekler",
        kazima_tarihi=datetime.fromisoformat(at).replace(tzinfo=timezone.utc),
        urun_fiyat=price,
        toplam_icerik_degeri=total_quantity,
        icerik_birimi=unit,
        birim_icerik_degeri=unit_quantity if unit_quantity is not None else total_quantity,
        adet_sayisi=pack_count,
        birim_fiyat=unit_price,
    )


class ShrinkflationServiceTests(unittest.TestCase):
    def test_pct_change(self) -> None:
        self.assertAlmostEqual(pct_change(100, 110), 10.0)
        self.assertAlmostEqual(pct_change(100, 90), -10.0)

    def test_compute_unit_price_returns_tl_per_kg_for_gram_inputs(self) -> None:
        self.assertAlmostEqual(compute_unit_price(50, 500, "g") or 0, 0.1)

    def test_compute_unit_price_returns_tl_per_l_for_milliliter_inputs(self) -> None:
        self.assertAlmostEqual(compute_unit_price(30, 1500, "ml") or 0, 0.02)

    def test_compute_unit_price_returns_tl_per_count_for_adet_inputs(self) -> None:
        self.assertAlmostEqual(compute_unit_price(50, 10, "adet") or 0, 5.0)

    def test_detects_stable_price_with_smaller_total_content(self) -> None:
        previous = snapshot(at="2026-03-23T10:00:00", price=50, total_quantity=500, unit="g", unit_price=100)
        current = snapshot(at="2026-04-18T10:00:00", price=50, total_quantity=450, unit="g", unit_price=111.1111)

        finding = compare_snapshots(previous, current, DetectionThresholds())

        self.assertIsNotNone(finding)
        assert finding is not None
        self.assertTrue(finding.is_shrinkflation)
        self.assertEqual(finding.direction, "decrease")
        self.assertIn(finding.reason, {"total_content_reduced", "unit_size_reduced"})
        self.assertEqual(finding.severity, "medium")

    def test_detects_shrinkflation_when_nominal_price_drops_but_unit_price_rises(self) -> None:
        previous = snapshot(at="2026-03-23T10:00:00", price=499.95, total_quantity=5000, unit="ml", unit_price=0.1)
        current = snapshot(at="2026-04-18T10:00:00", price=429.95, total_quantity=3000, unit="ml", unit_price=0.1433)

        finding = compare_snapshots(previous, current, DetectionThresholds())

        self.assertIsNotNone(finding)
        assert finding is not None
        self.assertTrue(finding.is_shrinkflation)
        self.assertLess(finding.fiyat_degisim_yuzdesi or 0, 0)
        self.assertGreater(finding.birim_fiyat_degisim_yuzdesi or 0, 0)

    def test_detects_pack_count_reduction_when_unit_size_same(self) -> None:
        previous = snapshot(
            at="2026-03-23T10:00:00",
            price=50,
            total_quantity=175,
            unit="g",
            unit_price=285.7143,
            unit_quantity=17.5,
            pack_count=10,
        )
        current = snapshot(
            at="2026-04-18T10:00:00",
            price=50,
            total_quantity=140,
            unit="g",
            unit_price=357.1429,
            unit_quantity=17.5,
            pack_count=8,
        )

        finding = compare_snapshots(previous, current, DetectionThresholds())

        self.assertIsNotNone(finding)
        assert finding is not None
        self.assertEqual(finding.reason, "pack_count_reduced")
        self.assertAlmostEqual(finding.adet_degisim_yuzdesi or 0, -20.0, places=2)
        self.assertTrue(finding.is_shrinkflation)

    def test_detects_pack_count_reduction_without_gramaj_metadata(self) -> None:
        previous = snapshot(
            at="2026-03-23T10:00:00",
            price=50,
            total_quantity=None,
            unit=None,
            unit_price=5,
            pack_count=10,
        )
        current = snapshot(
            at="2026-04-18T10:00:00",
            price=50,
            total_quantity=None,
            unit=None,
            unit_price=6.25,
            pack_count=8,
        )

        finding = compare_snapshots(previous, current, DetectionThresholds())

        self.assertIsNotNone(finding)
        assert finding is not None
        self.assertEqual(finding.reason, "pack_count_reduced")
        self.assertAlmostEqual(finding.adet_degisim_yuzdesi or 0, -20.0, places=2)
        self.assertTrue(finding.is_shrinkflation)

    def test_ignores_pure_price_change_when_content_same(self) -> None:
        previous = snapshot(at="2026-03-23T10:00:00", price=50, total_quantity=500, unit="g", unit_price=100)
        current = snapshot(at="2026-04-18T10:00:00", price=60, total_quantity=500, unit="g", unit_price=120)

        self.assertIsNone(compare_snapshots(previous, current, DetectionThresholds()))

    def test_returns_general_comparison_when_material_change_not_required(self) -> None:
        previous = snapshot(at="2026-03-23T10:00:00", price=50, total_quantity=500, unit="g", unit_price=100)
        current = snapshot(at="2026-04-18T10:00:00", price=60, total_quantity=500, unit="g", unit_price=120)

        finding = compare_snapshots(previous, current, DetectionThresholds(), require_material_change=False)

        self.assertIsNotNone(finding)
        assert finding is not None
        self.assertEqual(finding.reason, "content_unchanged")
        self.assertEqual(finding.direction, "stable")
        self.assertFalse(finding.is_shrinkflation)

    def test_detects_series_adjacent_only(self) -> None:
        snapshots = [
            snapshot(at="2026-03-01T10:00:00", price=50, total_quantity=500, unit="g", unit_price=100),
            snapshot(at="2026-03-20T10:00:00", price=50, total_quantity=500, unit="g", unit_price=100),
            snapshot(at="2026-04-18T10:00:00", price=52, total_quantity=450, unit="g", unit_price=115.5556),
        ]

        findings = detect_change_series(snapshots, DetectionThresholds())

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].onceki_kayit_tarihi, snapshots[1].kazima_tarihi)

    def test_filters_latest_daily_decrease_findings(self) -> None:
        findings = [
            compare_snapshots(
                snapshot(at="2026-03-01T10:00:00", price=50, total_quantity=500, unit="g", unit_price=100),
                snapshot(at="2026-03-20T10:00:00", price=50, total_quantity=450, unit="g", unit_price=111.1111),
                DetectionThresholds(),
            ),
            compare_snapshots(
                snapshot(at="2026-03-20T10:00:00", price=50, total_quantity=450, unit="g", unit_price=111.1111),
                snapshot(at="2026-04-18T10:00:00", price=50, total_quantity=400, unit="g", unit_price=125),
                DetectionThresholds(),
            ),
        ]

        filtered = filter_findings(
            [item for item in findings if item is not None],
            latest_day_only=True,
            decreases_only=True,
        )

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].yeni_kayit_tarihi, datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc))

    def test_filter_product_comparison_findings_supports_increase_and_date_filters(self) -> None:
        older_gain = compare_snapshots(
            snapshot(at="2026-03-01T10:00:00", price=50, total_quantity=500, unit="g", unit_price=0.1),
            snapshot(at="2026-03-20T10:00:00", price=55, total_quantity=500, unit="g", unit_price=0.11),
            DetectionThresholds(),
            require_material_change=False,
        )
        recent_drop = compare_snapshots(
            snapshot(at="2026-03-20T10:00:00", price=55, total_quantity=500, unit="g", unit_price=0.11),
            snapshot(at="2026-04-18T10:00:00", price=50, total_quantity=500, unit="g", unit_price=0.1),
            DetectionThresholds(),
            require_material_change=False,
        )

        filtered = filter_product_comparison_findings(
            [item for item in [older_gain, recent_drop] if item is not None],
            increases_only=True,
            date_start=datetime(2026, 3, 15, tzinfo=timezone.utc),
            date_end=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )

        self.assertEqual(len(filtered), 1)
        self.assertAlmostEqual(filtered[0].birim_fiyat_degisim_yuzdesi or 0, 10.0, places=2)

    def test_filter_product_comparison_findings_supports_discount_filter(self) -> None:
        gain = compare_snapshots(
            snapshot(at="2026-03-01T10:00:00", price=50, total_quantity=500, unit="g", unit_price=0.1),
            snapshot(at="2026-03-20T10:00:00", price=55, total_quantity=500, unit="g", unit_price=0.11),
            DetectionThresholds(),
            require_material_change=False,
        )
        discount = compare_snapshots(
            snapshot(at="2026-03-20T10:00:00", price=55, total_quantity=500, unit="g", unit_price=0.11),
            snapshot(at="2026-04-18T10:00:00", price=50, total_quantity=500, unit="g", unit_price=0.1),
            DetectionThresholds(),
            require_material_change=False,
        )

        filtered = filter_product_comparison_findings(
            [item for item in [gain, discount] if item is not None],
            decreases_only=True,
        )

        self.assertEqual(len(filtered), 1)
        self.assertAlmostEqual(filtered[0].birim_fiyat_degisim_yuzdesi or 0, -9.09, places=2)

    def test_filter_product_comparison_findings_can_keep_only_shrinkflation(self) -> None:
        shrink = compare_snapshots(
            snapshot(at="2026-03-01T10:00:00", price=50, total_quantity=500, unit="g", unit_price=0.1),
            snapshot(at="2026-03-20T10:00:00", price=50, total_quantity=450, unit="g", unit_price=0.1111),
            DetectionThresholds(),
            require_material_change=False,
        )
        non_shrink = compare_snapshots(
            snapshot(at="2026-03-20T10:00:00", price=50, total_quantity=500, unit="g", unit_price=0.1),
            snapshot(at="2026-04-18T10:00:00", price=55, total_quantity=500, unit="g", unit_price=0.11),
            DetectionThresholds(),
            require_material_change=False,
        )

        filtered = filter_product_comparison_findings(
            [item for item in [shrink, non_shrink] if item is not None],
            shrinkflation_only=True,
        )

        self.assertEqual(len(filtered), 1)
        self.assertTrue(filtered[0].is_shrinkflation)

    def test_market_matches_accepts_migros_variants(self) -> None:
        self.assertTrue(market_matches("Migros", "migros"))
        self.assertTrue(market_matches("Migros Sanal Market", "migros"))
        self.assertFalse(market_matches("SOK Market", "migros"))

    def test_filter_findings_can_require_content_drop_and_unit_price_increase(self) -> None:
        shrink = compare_snapshots(
            snapshot(at="2026-03-01T10:00:00", price=50, total_quantity=500, unit="g", unit_price=0.1),
            snapshot(at="2026-03-20T10:00:00", price=50, total_quantity=450, unit="g", unit_price=0.1111),
            DetectionThresholds(),
            require_material_change=False,
        )
        no_content_drop = compare_snapshots(
            snapshot(at="2026-03-20T10:00:00", price=50, total_quantity=500, unit="g", unit_price=0.1),
            snapshot(at="2026-04-18T10:00:00", price=55, total_quantity=500, unit="g", unit_price=0.11),
            DetectionThresholds(),
            require_material_change=False,
        )

        filtered = filter_findings(
            [item for item in [shrink, no_content_drop] if item is not None],
            decreases_only=True,
            shrinkflation_only=True,
            content_decrease_only=True,
            unit_price_increase_only=True,
        )

        self.assertEqual(len(filtered), 1)
        self.assertAlmostEqual(filtered[0].gramaj_degisim_yuzdesi or 0, -10.0, places=2)

    def test_list_latest_product_comparisons_supports_shrinkflation_risk_sorting(self) -> None:
        lower_risk = compare_snapshots(
            snapshot(at="2026-03-01T10:00:00", price=50, total_quantity=500, unit="g", unit_price=0.1),
            snapshot(at="2026-03-20T10:00:00", price=50, total_quantity=450, unit="g", unit_price=0.1111),
            DetectionThresholds(),
            require_material_change=False,
        )
        higher_risk = compare_snapshots(
            snapshot(at="2026-03-01T10:00:00", price=50, total_quantity=500, unit="g", unit_price=0.1, urun_id=2),
            snapshot(at="2026-03-20T10:00:00", price=50, total_quantity=400, unit="g", unit_price=0.125, urun_id=2),
            DetectionThresholds(),
            require_material_change=False,
        )

        findings = [item for item in [lower_risk, higher_risk] if item is not None]

        with patch("app.services.shrinkflation.build_latest_product_comparisons", return_value=findings):
            rows = list_latest_product_comparisons(
                object(),
                shrinkflation_only=True,
                sort_by_shrinkflation_risk=True,
            )

        self.assertEqual([row["urun_id"] for row in rows], [2, 1])

    def test_list_latest_product_comparisons_groups_split_ids_by_canonical_identity(self) -> None:
        rows = [
            {
                "urun_kimligi": "twister-orman-meyveli",
                "urun_id": 181,
                "urun_ad": "Twister Orman Meyveli 70 ml",
                "market_adi": "ŞOK",
                "urun_kategori": "Dondurma",
                "kazima_tarihi": datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
                "urun_fiyat": 15.0,
                "gramaj_degeri": 70.0,
                "gramaj_birimi": "ml",
                "birim_fiyat": 0.2143,
                "adet_sayisi": None,
            },
            {
                "urun_kimligi": "twister-orman-meyveli",
                "urun_id": 35312,
                "urun_ad": "Twister Orman Meyveli 65 ml",
                "market_adi": "ŞOK",
                "urun_kategori": "Dondurma",
                "kazima_tarihi": datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc),
                "urun_fiyat": 15.0,
                "gramaj_degeri": 65.0,
                "gramaj_birimi": "ml",
                "birim_fiyat": 0.2308,
                "adet_sayisi": None,
            },
        ]

        class _FakeMappingsResult:
            def __iter__(self):
                return iter(rows)

        class _FakeExecuteResult:
            def mappings(self):
                return _FakeMappingsResult()

        class _FakeSession:
            def execute(self, *_args, **_kwargs):
                return _FakeExecuteResult()

        findings = list_latest_product_comparisons(_FakeSession(), market="sok")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["urun_id"], 35312)
        self.assertTrue(findings[0]["is_shrinkflation"])

    def test_pair_family_snapshots_skips_extreme_quantity_mismatch(self) -> None:
        previous = FamilySnapshot(
            urun_id=1,
            display_name="Loco No:13 Vişne Çikolata 900 Ml",
            family_key="loco no visne cikolata",
            market="MIGROS",
            category="Icecekler",
            snapshot=snapshot(
                urun_id=1,
                urun_ad="Loco No:13 Vişne Çikolata 900 Ml",
                at="2026-03-22T10:00:00",
                price=850.95,
                total_quantity=900,
                unit="ml",
                unit_price=0.9455,
            ),
        )
        current_valid = FamilySnapshot(
            urun_id=2,
            display_name="Loco No:13 Vişne Çikolata 450 Ml",
            family_key="loco no visne cikolata",
            market="MIGROS",
            category="Icecekler",
            snapshot=snapshot(
                urun_id=2,
                urun_ad="Loco No:13 Vişne Çikolata 450 Ml",
                at="2026-04-21T10:00:00",
                price=685.95,
                total_quantity=450,
                unit="ml",
                unit_price=1.5243,
            ),
        )
        current_invalid = FamilySnapshot(
            urun_id=3,
            display_name="Loco No:13 Vişne Çikolata 100 Ml",
            family_key="loco no visne cikolata",
            market="MIGROS",
            category="Icecekler",
            snapshot=snapshot(
                urun_id=3,
                urun_ad="Loco No:13 Vişne Çikolata 100 Ml",
                at="2026-04-21T10:00:00",
                price=199.95,
                total_quantity=100,
                unit="ml",
                unit_price=1.9995,
            ),
        )

        pairs = pair_family_snapshots([previous], [current_valid, current_invalid])

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0][1].urun_id, 2)

    def test_extracts_trailing_pack_patterns(self) -> None:
        candidate = extract_candidate("Nescafe 2in1 Sütlü Köpüklü 10 g x 10'lu", "product_name")

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.total_base, 100.0)
        self.assertEqual(candidate.base_unit, "g")
        self.assertEqual(candidate.pack_count, 10.0)
        self.assertEqual(candidate.unit_base, 10.0)

    def test_extracts_leading_pack_patterns(self) -> None:
        candidate = extract_candidate("10'lu 17.5 g", "product_name")

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertEqual(candidate.total_base, 175.0)
        self.assertEqual(candidate.pack_count, 10.0)
        self.assertEqual(candidate.unit_base, 17.5)

    def test_classify_severity(self) -> None:
        self.assertEqual(classify_severity(4), "low")
        self.assertEqual(classify_severity(12), "medium")
        self.assertEqual(classify_severity(25), "high")


if __name__ == "__main__":
    unittest.main()
