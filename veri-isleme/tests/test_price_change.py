from datetime import datetime, timezone

import unittest



from price_change import (

    FiyatDegisimEsikleri,

    classify_price_change_severity,

    detect_price_changes_series,

    detect_price_decrease,

    detect_price_increase,

)

from shrinkflation import FiyatKaydi





def snapshot(

    *,

    urun_id: int = 1,

    urun_ad: str = "Test Urun",

    at: str,

    fiyat: float,

    quantity: float | None,

    birim: str | None,

    birim_fiyat: float | None,

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





class PriceChangeTests(unittest.TestCase):

    def test_detects_price_increase_same_quantity(self) -> None:

        onceki = snapshot(at="2026-03-23T10:00:00", fiyat=40, quantity=1000, birim="ml", birim_fiyat=40)

        guncel = snapshot(at="2026-04-18T10:00:00", fiyat=45, quantity=1000, birim="ml", birim_fiyat=45)



        bulgu = detect_price_increase(onceki, guncel, FiyatDegisimEsikleri())



        self.assertIsNotNone(bulgu)

        assert bulgu is not None

        self.assertEqual(bulgu.reason, "price_increased_same_quantity")

        self.assertEqual(bulgu.direction, "increase")

        self.assertAlmostEqual(bulgu.change_ratio_pct, 12.5)



    def test_ignores_nominal_increase_when_unit_price_drops(self) -> None:

        onceki = snapshot(at="2026-03-23T10:00:00", fiyat=40, quantity=1000, birim="ml", birim_fiyat=40)

        guncel = snapshot(at="2026-04-18T10:00:00", fiyat=42, quantity=1200, birim="ml", birim_fiyat=35)



        bulgu = detect_price_increase(onceki, guncel, FiyatDegisimEsikleri())



        self.assertIsNone(bulgu)



    def test_detects_price_decrease_same_quantity(self) -> None:

        onceki = snapshot(at="2026-03-23T10:00:00", fiyat=100, quantity=500, birim="g", birim_fiyat=200)

        guncel = snapshot(at="2026-04-18T10:00:00", fiyat=80, quantity=500, birim="g", birim_fiyat=160)



        bulgu = detect_price_decrease(onceki, guncel, FiyatDegisimEsikleri())



        self.assertIsNotNone(bulgu)

        assert bulgu is not None

        self.assertEqual(bulgu.reason, "price_decreased_same_quantity")

        self.assertEqual(bulgu.direction, "decrease")

        self.assertAlmostEqual(bulgu.change_ratio_pct, 20.0)



    def test_ignores_nominal_decrease_when_unit_price_rises(self) -> None:

        onceki = snapshot(at="2026-03-23T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=100)

        guncel = snapshot(at="2026-04-18T10:00:00", fiyat=48, quantity=400, birim="g", birim_fiyat=120)



        bulgu = detect_price_decrease(onceki, guncel, FiyatDegisimEsikleri())



        self.assertIsNone(bulgu)



    def test_series_splits_increases_and_decreases(self) -> None:

        snapshots = [

            snapshot(at="2026-03-01T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=100),

            snapshot(at="2026-03-15T10:00:00", fiyat=55, quantity=500, birim="g", birim_fiyat=110),

            snapshot(at="2026-04-18T10:00:00", fiyat=45, quantity=500, birim="g", birim_fiyat=90),

        ]



        increases, decreases = detect_price_changes_series(snapshots, FiyatDegisimEsikleri())



        self.assertEqual(len(increases), 1)

        self.assertEqual(len(decreases), 1)

        self.assertEqual(increases[0].reason, "price_increased_same_quantity")

        self.assertEqual(decreases[0].reason, "price_decreased_same_quantity")



    def test_classify_price_change_severity(self) -> None:

        self.assertEqual(classify_price_change_severity(5), "low")

        self.assertEqual(classify_price_change_severity(12), "medium")

        self.assertEqual(classify_price_change_severity(30), "high")





if __name__ == "__main__":

    unittest.main()

