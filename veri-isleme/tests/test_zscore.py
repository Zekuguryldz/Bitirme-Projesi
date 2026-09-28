from datetime import datetime, timezone

import unittest



from shrinkflation import FiyatKaydi

from zscore import ZScoreThresholds, classify_z_score_severity, detect_unit_price_zscore_anomaly





def snapshot(

    *,

    urun_id: int = 1,

    urun_ad: str = "Test Urun",

    at: str,

    fiyat: float,

    quantity: float,

    birim: str,

    birim_fiyat: float,

) -> FiyatKaydi:

    return FiyatKaydi(

        urun_id=urun_id,

        urun_ad=urun_ad,

        kazima_tarihi=datetime.fromisoformat(at).replace(tzinfo=timezone.utc),

        urun_fiyat=fiyat,

        gramaj_degeri=quantity,

        gramaj_birimi=birim,

        birim_fiyat=birim_fiyat,

    )





class ZScoreTests(unittest.TestCase):

    def test_detects_positive_unit_price_zscore(self) -> None:

        history = [

            snapshot(at="2026-03-01T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=100),

            snapshot(at="2026-03-08T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=101),

            snapshot(at="2026-03-15T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=99),

            snapshot(at="2026-03-22T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=100),

        ]

        guncel = snapshot(at="2026-04-01T10:00:00", fiyat=60, quantity=500, birim="g", birim_fiyat=120)



        bulgu = detect_unit_price_zscore_anomaly(history, guncel, ZScoreThresholds())



        self.assertIsNotNone(bulgu)

        assert bulgu is not None

        self.assertEqual(bulgu.reason, "unit_price_above_history_zscore")

        self.assertEqual(bulgu.history_sample_count, 4)

        self.assertGreater(bulgu.z_score, 2.5)



    def test_ignores_insufficient_history(self) -> None:

        history = [

            snapshot(at="2026-03-01T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=100),

            snapshot(at="2026-03-08T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=101),

        ]

        guncel = snapshot(at="2026-04-01T10:00:00", fiyat=60, quantity=500, birim="g", birim_fiyat=120)



        bulgu = detect_unit_price_zscore_anomaly(history, guncel, ZScoreThresholds())



        self.assertIsNone(bulgu)



    def test_ignores_small_latest_unit_price_change(self) -> None:

        history = [

            snapshot(at="2026-03-01T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=100),

            snapshot(at="2026-03-08T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=101),

            snapshot(at="2026-03-15T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=99),

            snapshot(at="2026-03-22T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=100),

        ]

        guncel = snapshot(at="2026-04-01T10:00:00", fiyat=50.5, quantity=500, birim="g", birim_fiyat=101)



        bulgu = detect_unit_price_zscore_anomaly(history, guncel, ZScoreThresholds())



        self.assertIsNone(bulgu)



    def test_classify_z_score_severity(self) -> None:

        self.assertEqual(classify_z_score_severity(2.6), "low")

        self.assertEqual(classify_z_score_severity(3.4), "medium")

        self.assertEqual(classify_z_score_severity(4.5), "high")





if __name__ == "__main__":

    unittest.main()

