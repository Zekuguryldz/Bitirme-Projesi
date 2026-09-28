import csv

import json

import tempfile

import unittest

from pathlib import Path



from audit_market_identity import build_groups, summarize_groups





def write_csv(yol: Path, satirlar: list[dict[str, object]]) -> None:

    with yol.open("w", encoding="utf-8", newline="") as handle:

        yazici = csv.DictWriter(handle, fieldnames=list(satirlar[0].keys()))

        yazici.writeheader()

        yazici.writerows(satirlar)





class AuditMarketIdentityTests(unittest.TestCase):

    def test_name_variation_with_same_url_is_not_hard_conflict(self) -> None:

        with tempfile.TemporaryDirectory() as temp_dir:

            base = Path(temp_dir)

            mart = base / "mart"

            nisan = base / "nisan"

            mart.mkdir()

            nisan.mkdir()

            rows_mart = [

                {

                    "id": "1",

                    "urun_ad": "Barilla Fusilli Burgu 500 G",

                    "urun_url": "https://www.migros.com.tr/barilla-fusilli-burgu-makarna-500-g-p-4cc1c4",

                    "site_product_code": "5030340",

                    "url_key": "barilla-fusilli-burgu-makarna-500-g-p-4cc1c4",

                }

            ]

            rows_nisan = [

                {

                    "id": "2",

                    "urun_ad": "Barilla Fusilli (Burgu) Makarna 500 G",

                    "urun_url": "https://www.migros.com.tr/barilla-fusilli-burgu-makarna-500-g-p-4cc1c4",

                    "site_product_code": "5030340",

                    "url_key": "barilla-fusilli-burgu-makarna-500-g-p-4cc1c4",

                }

            ]

            write_csv(mart / "urunler.csv", rows_mart)

            write_csv(nisan / "urunler.csv", rows_nisan)



            groups = build_groups([mart, nisan], "site_product_code")

            satirlar, counts = summarize_groups(groups, "site_product_code")



            self.assertEqual(counts["hard_conflicts"], 0)

            self.assertEqual(counts["name_variation_only"], 1)

            self.assertEqual(satirlar[0]["status"], "name_variation_only")



    def test_different_urls_for_same_identity_is_hard_conflict(self) -> None:

        with tempfile.TemporaryDirectory() as temp_dir:

            base = Path(temp_dir)

            a = base / "a"

            b = base / "b"

            a.mkdir()

            b.mkdir()

            rows_a = [

                {

                    "id": "1",

                    "urun_ad": "X",

                    "urun_url": "https://example.com/a",

                    "site_product_code": "111",

                    "url_key": "x-a",

                }

            ]

            rows_b = [

                {

                    "id": "2",

                    "urun_ad": "X",

                    "urun_url": "https://example.com/b",

                    "site_product_code": "111",

                    "url_key": "x-b",

                }

            ]

            write_csv(a / "urunler.csv", rows_a)

            write_csv(b / "urunler.csv", rows_b)



            groups = build_groups([a, b], "site_product_code")

            satirlar, counts = summarize_groups(groups, "site_product_code")



            self.assertEqual(counts["hard_conflicts"], 1)

            self.assertEqual(satirlar[0]["status"], "hard_conflict")





if __name__ == "__main__":

    unittest.main()

