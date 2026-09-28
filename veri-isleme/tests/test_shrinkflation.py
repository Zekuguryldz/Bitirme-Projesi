from datetime import datetime, timezone

import unittest



from shrinkflation import (

    TespitEsikleri,

    FiyatKaydi,

    classify_severity,

    detect_shrinkflation,

    detect_shrinkflation_series,

    is_tartimli_kg_urun,

    pct_change,

)





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





class ShrinkflationTests(unittest.TestCase):

    def test_pct_change(self) -> None:

        self.assertAlmostEqual(pct_change(100, 110), 10.0)

        self.assertAlmostEqual(pct_change(100, 90), -10.0)



    def test_detects_stable_price_with_smaller_size(self) -> None:

        onceki = snapshot(at="2026-03-23T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=100)

        guncel = snapshot(at="2026-04-18T10:00:00", fiyat=50, quantity=450, birim="g", birim_fiyat=111.1111)



        bulgu = detect_shrinkflation(onceki, guncel, TespitEsikleri())



        self.assertIsNotNone(bulgu)

        assert bulgu is not None

        self.assertEqual(bulgu.reason, "price_stable_while_quantity_dropped")

        self.assertEqual(bulgu.severity, "medium")



    def test_detects_price_increase_with_smaller_size(self) -> None:

        onceki = snapshot(at="2026-03-23T10:00:00", fiyat=40, quantity=1000, birim="ml", birim_fiyat=40)

        guncel = snapshot(at="2026-04-18T10:00:00", fiyat=45, quantity=900, birim="ml", birim_fiyat=50)



        bulgu = detect_shrinkflation(onceki, guncel, TespitEsikleri())



        self.assertIsNotNone(bulgu)

        assert bulgu is not None

        self.assertEqual(bulgu.reason, "price_increased_while_quantity_dropped")



    def test_ignores_proportional_price_drop(self) -> None:

        onceki = snapshot(at="2026-03-23T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=100)

        guncel = snapshot(at="2026-04-18T10:00:00", fiyat=43, quantity=430, birim="g", birim_fiyat=100)



        bulgu = detect_shrinkflation(onceki, guncel, TespitEsikleri())



        self.assertIsNone(bulgu)



    def test_ignores_small_unit_price_increase_below_threshold(self) -> None:

        onceki = snapshot(at="2026-03-23T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=100)

        guncel = snapshot(at="2026-04-18T10:00:00", fiyat=50, quantity=490, birim="g", birim_fiyat=102.0408)



        bulgu = detect_shrinkflation(onceki, guncel, TespitEsikleri())



        self.assertIsNone(bulgu)



    def test_ignores_same_size_price_increase(self) -> None:

        onceki = snapshot(at="2026-03-23T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=100)

        guncel = snapshot(at="2026-04-18T10:00:00", fiyat=60, quantity=500, birim="g", birim_fiyat=120)



        bulgu = detect_shrinkflation(onceki, guncel, TespitEsikleri())



        self.assertIsNone(bulgu)



    def test_ignores_extreme_size_drop_as_different_package_variant(self) -> None:

        onceki = snapshot(at="2026-03-23T10:00:00", fiyat=100, quantity=1000, birim="g", birim_fiyat=100)

        guncel = snapshot(at="2026-04-18T10:00:00", fiyat=30, quantity=40, birim="g", birim_fiyat=750)



        bulgu = detect_shrinkflation(onceki, guncel, TespitEsikleri())



        self.assertIsNone(bulgu)



    def test_ignores_variable_weight_kg_products(self) -> None:

        onceki = snapshot(
            at="2026-03-23T10:00:00",
            fiyat=120,
            quantity=1000,
            birim="g",
            birim_fiyat=120,
            urun_ad="Gedik Bütün Piliç Kg",
        )

        guncel = snapshot(
            at="2026-04-18T10:00:00",
            fiyat=125,
            quantity=400,
            birim="g",
            birim_fiyat=312.5,
            urun_ad="Gedik Bütün Piliç Kg",
        )



        bulgu = detect_shrinkflation(onceki, guncel, TespitEsikleri())



        self.assertIsNone(bulgu)



    def test_does_not_treat_fixed_kg_package_as_variable_weight(self) -> None:

        self.assertFalse(is_tartimli_kg_urun("Migros Un 2 Kg"))

        self.assertTrue(is_tartimli_kg_urun("Gedik Bütün Piliç Kg"))



    def test_ignores_different_units(self) -> None:

        onceki = snapshot(at="2026-03-23T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=100)

        guncel = snapshot(at="2026-04-18T10:00:00", fiyat=50, quantity=450, birim="ml", birim_fiyat=111.1111)



        bulgu = detect_shrinkflation(onceki, guncel, TespitEsikleri())



        self.assertIsNone(bulgu)



    def test_detects_count_based_shrinkflation(self) -> None:

        onceki = snapshot(at="2026-03-23T10:00:00", fiyat=50, quantity=10, birim="adet", birim_fiyat=5)

        guncel = snapshot(at="2026-04-18T10:00:00", fiyat=50, quantity=8, birim="adet", birim_fiyat=6.25)



        bulgu = detect_shrinkflation(onceki, guncel, TespitEsikleri())



        self.assertIsNotNone(bulgu)

        assert bulgu is not None

        self.assertEqual(bulgu.reason, "price_stable_while_quantity_dropped")



    def test_detects_usage_based_shrinkflation(self) -> None:

        onceki = snapshot(at="2026-03-23T10:00:00", fiyat=300, quantity=50, birim="adet", birim_fiyat=6)

        guncel = snapshot(at="2026-04-18T10:00:00", fiyat=305, quantity=42, birim="adet", birim_fiyat=7.2619)



        bulgu = detect_shrinkflation(onceki, guncel, TespitEsikleri())



        self.assertIsNotNone(bulgu)

        assert bulgu is not None

        self.assertEqual(bulgu.reason, "price_increased_while_quantity_dropped")



    def test_classic_mode_ignores_price_drop_even_if_unit_price_rose(self) -> None:

        onceki = snapshot(at="2026-03-23T10:00:00", fiyat=50, quantity=20, birim="adet", birim_fiyat=2.5)

        guncel = snapshot(at="2026-04-18T10:00:00", fiyat=48, quantity=16, birim="adet", birim_fiyat=3)



        bulgu = detect_shrinkflation(onceki, guncel, TespitEsikleri())



        self.assertIsNone(bulgu)



    def test_extended_mode_can_flag_insufficient_price_drop(self) -> None:

        onceki = snapshot(at="2026-03-23T10:00:00", fiyat=50, quantity=20, birim="adet", birim_fiyat=2.5)

        guncel = snapshot(at="2026-04-18T10:00:00", fiyat=48, quantity=16, birim="adet", birim_fiyat=3)



        bulgu = detect_shrinkflation(

            onceki,

            guncel,

            TespitEsikleri(sabit_fiyat_alt_yuzdesi=-5.0),

        )



        self.assertIsNotNone(bulgu)

        assert bulgu is not None

        self.assertEqual(bulgu.reason, "price_dropped_but_not_enough_after_quantity_drop")



    def test_series_compares_adjacent_snapshots(self) -> None:

        snapshots = [

            snapshot(at="2026-03-01T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=100),

            snapshot(at="2026-03-20T10:00:00", fiyat=50, quantity=500, birim="g", birim_fiyat=100),

            snapshot(at="2026-04-18T10:00:00", fiyat=52, quantity=450, birim="g", birim_fiyat=115.5556),

        ]



        bulgular = detect_shrinkflation_series(snapshots, TespitEsikleri())



        self.assertEqual(len(bulgular), 1)

        self.assertEqual(bulgular[0].onceki_kayit_tarihi, snapshots[1].kazima_tarihi)



    def test_series_does_not_compare_same_calendar_day_duplicates(self) -> None:

        snapshots = [

            snapshot(at="2026-03-23T10:00:00", fiyat=100, quantity=1000, birim="g", birim_fiyat=100),

            snapshot(at="2026-03-23T12:00:00", fiyat=30, quantity=300, birim="g", birim_fiyat=100),

            snapshot(at="2026-04-18T10:00:00", fiyat=30, quantity=300, birim="g", birim_fiyat=100),

        ]



        bulgular = detect_shrinkflation_series(snapshots, TespitEsikleri())



        self.assertEqual(bulgular, [])



    def test_classify_severity(self) -> None:

        self.assertEqual(classify_severity(4, 5), "low")

        self.assertEqual(classify_severity(12, 8), "medium")

        self.assertEqual(classify_severity(5, 30), "high")





if __name__ == "__main__":

    unittest.main()
