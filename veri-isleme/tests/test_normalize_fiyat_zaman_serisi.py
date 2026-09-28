import unittest



from normalize_fiyat_zaman_serisi import (

    choose_candidate,

    compute_unit_price,

    extract_candidate,

)





class NormalizeFiyatZamanSerisiTests(unittest.TestCase):

    def test_simple_weight_is_normalized(self) -> None:

        aday = extract_candidate("650 g", "raw_field")

        self.assertIsNotNone(aday)

        assert aday is not None

        self.assertEqual(aday.total_base, 650.0)

        self.assertEqual(aday.temel_birim, "g")

        self.assertAlmostEqual(compute_unit_price(72.5, aday.total_base, aday.taban_birim), 111.5385, places=4)



    def test_kg_is_converted_to_grams(self) -> None:

        aday = extract_candidate("1.5 kg", "raw_field")

        self.assertIsNotNone(aday)

        assert aday is not None

        self.assertEqual(aday.total_base, 1500.0)

        self.assertEqual(aday.temel_birim, "g")



    def test_multipack_liter_is_converted_to_ml(self) -> None:

        aday = extract_candidate("4*1 lt", "raw_field")

        self.assertIsNotNone(aday)

        assert aday is not None

        self.assertEqual(aday.total_base, 4000.0)

        self.assertEqual(aday.temel_birim, "ml")

        self.assertAlmostEqual(compute_unit_price(150.0, aday.total_base, aday.taban_birim), 37.5, places=4)



    def test_product_name_total_wins_when_count_is_before_amount(self) -> None:

        ham_aday = extract_candidate("3*103 g", "raw_field")

        ad_adayi = extract_candidate("Çerezza 3'lü 103 g", "product_name")

        chosen, _ = choose_candidate(ham_aday, ad_adayi)

        self.assertIsNotNone(chosen)

        assert chosen is not None

        self.assertEqual(chosen.source, "product_name")

        self.assertEqual(chosen.total_base, 103.0)



    def test_raw_pack_wins_when_count_marker_is_after_amount(self) -> None:

        ham_aday = extract_candidate("10*17,5 g", "raw_field")

        ad_adayi = extract_candidate("Nescafe 3'ü 1 Arada 17.5 g 10'lu", "product_name")

        chosen, _ = choose_candidate(ham_aday, ad_adayi)

        self.assertIsNotNone(chosen)

        assert chosen is not None

        self.assertEqual(chosen.source, "raw_field")

        self.assertEqual(chosen.total_base, 175.0)



    def test_product_name_pack_is_extracted_when_count_is_after_amount(self) -> None:

        aday = extract_candidate("Nescafe 3'ü 1 Arada 17.5 g 10'lu", "product_name")

        self.assertIsNotNone(aday)

        assert aday is not None

        self.assertEqual(aday.total_base, 175.0)

        self.assertEqual(aday.temel_birim, "g")



    def test_product_name_pack_is_extracted_when_x_precedes_count_marker(self) -> None:

        aday = extract_candidate("Nescafe 2in1 Sütlü Köpüklü 10 g x 10'lu", "product_name")

        self.assertIsNotNone(aday)

        assert aday is not None

        self.assertEqual(aday.total_base, 100.0)

        self.assertEqual(aday.temel_birim, "g")



    def test_name_wins_when_units_conflict(self) -> None:

        ham_aday = extract_candidate("20x70 g", "raw_field")

        ad_adayi = extract_candidate("Golf Bravo Crazy Nutty 90 ml", "product_name")

        chosen, _ = choose_candidate(ham_aday, ad_adayi)

        self.assertIsNotNone(chosen)

        assert chosen is not None

        self.assertEqual(chosen.source, "product_name")

        self.assertEqual(chosen.temel_birim, "ml")

        self.assertEqual(chosen.total_base, 90.0)



    def test_decimal_ml_is_treated_as_liter(self) -> None:

        aday = extract_candidate("12*0.33 ml", "product_name")

        self.assertIsNotNone(aday)

        assert aday is not None

        self.assertEqual(aday.total_base, 3960.0)

        self.assertEqual(aday.temel_birim, "ml")



    def test_bare_kg_in_product_name_is_interpreted_as_one_kilogram(self) -> None:

        aday = extract_candidate("Kent Dökme Şeker Kg", "product_name")

        self.assertIsNotNone(aday)

        assert aday is not None

        self.assertEqual(aday.total_base, 1000.0)

        self.assertEqual(aday.temel_birim, "g")

        self.assertAlmostEqual(compute_unit_price(159.9, aday.total_base, aday.taban_birim), 159.9, places=4)



    def test_count_based_product_is_normalized_as_adet(self) -> None:

        aday = extract_candidate("Fairy Hepsi Bir Arada 42 Tablet", "product_name")

        self.assertIsNotNone(aday)

        assert aday is not None

        self.assertEqual(aday.total_base, 42.0)

        self.assertEqual(aday.temel_birim, "adet")

        self.assertAlmostEqual(compute_unit_price(210.0, aday.total_base, aday.taban_birim), 5.0, places=4)



    def test_usage_count_is_normalized_as_adet(self) -> None:

        aday = extract_candidate("Persil Jel 50 Yıkama", "product_name")

        self.assertIsNotNone(aday)

        assert aday is not None

        self.assertEqual(aday.total_base, 50.0)

        self.assertEqual(aday.temel_birim, "adet")

        self.assertAlmostEqual(compute_unit_price(300.0, aday.total_base, aday.taban_birim), 6.0, places=4)





if __name__ == "__main__":

    unittest.main()

