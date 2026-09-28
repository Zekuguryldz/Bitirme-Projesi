import unittest



from import_shrinkflation_csv_to_supabase import (

    build_anomaly_record,

    build_resolved_product_lookup,

    resolve_related_product_id,

)





class ImportShrinkflationCsvToSupabaseTests(unittest.TestCase):

    def test_build_resolved_product_lookup_maps_url_to_resolved_id(self) -> None:

        lookup = build_resolved_product_lookup(

            [

                {

                    "urun_ad": "Test Ürün",

                    "urun_url": "https://example.com/test-urun",

                    "resolved_urun_id": "123",

                }

            ]

        )



        self.assertEqual(lookup["https://example.com/test-urun"], 123)



    def test_resolve_related_product_id_uses_current_url(self) -> None:

        ilgili_urun_kimligi = resolve_related_product_id(

            {"current_urun_url": "https://example.com/test-urun"},

            {"https://example.com/test-urun": 321},

        )



        self.assertEqual(ilgili_urun_kimligi, 321)



    def test_build_anomaly_record_maps_shrinkflation_fields(self) -> None:

        kayit = build_anomaly_record(

            {

                "urun_ad": "Test Ürün 500 G",

                "onceki_kayit_tarihi": "2026-03-22 20:10:14+03:00",

                "yeni_kayit_tarihi": "2026-04-21 16:04:02+03:00",

                "onceki_fiyat": "72.50",

                "yeni_fiyat": "24.95",

                "onceki_gramaj_degeri": "393",

                "yeni_gramaj_degeri": "131",

                "gramaj_birimi": "g",

                "onceki_birim_fiyat": "184.4784",

                "yeni_birim_fiyat": "190.458",

                "gramaj_degisim_pct": "-66.6667",

                "fiyat_degisim_pct": "-65.5862",

                "birim_fiyat_degisim_pct": "3.2414",

                "shrinkflation_orani_pct": "3.2414",

                "severity": "high",

                "reason": "price_dropped_but_not_enough_after_quantity_drop",

            },

            ilgili_urun_kimligi=24087,

        )



        self.assertEqual(kayit["ilgili_urun_id"], 24087)

        self.assertEqual(kayit["eski_degeri"], "184.4784")

        self.assertEqual(kayit["yeni_degeri"], "190.458")

        self.assertEqual(kayit["gramaj_birimi"], "g")

        self.assertEqual(kayit["severity"], "high")

        self.assertEqual(kayit["reason"], "price_dropped_but_not_enough_after_quantity_drop")





if __name__ == "__main__":

    unittest.main()

