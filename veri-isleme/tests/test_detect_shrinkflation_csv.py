import csv

import tempfile

import unittest

from pathlib import Path



from detect_shrinkflation_csv import (

    analyze_market_pairs,

    format_summary_text,

    load_grouped_snapshots,

    select_identity_key,

)

from shrinkflation import TespitEsikleri





def write_csv(yol: Path, satirlar: list[dict[str, object]]) -> None:

    with yol.open("w", encoding="utf-8", newline="") as handle:

        yazici = csv.DictWriter(handle, fieldnames=list(satirlar[0].keys()))

        yazici.writeheader()

        yazici.writerows(satirlar)





class DetectShrinkflationCsvTests(unittest.TestCase):

    def test_select_identity_key_prefers_site_product_code(self) -> None:

        satir = {

            "site_product_code": "7012467",

            "url_key": "akturk-vanilyali-gofret-300-g-p-6b0073",

            "urun_url": "https://www.migros.com.tr/akturk-vanilyali-gofret-300-g-p-6b0073",

        }

        self.assertEqual(select_identity_key(satir), "site_product_code:7012467")



    def test_load_grouped_snapshots_uses_normalized_measure(self) -> None:

        with tempfile.TemporaryDirectory() as temp_dir:

            base = Path(temp_dir)

            write_csv(

                base / "urunler.csv",

                [

                    {

                        "id": "1",

                        "market_id": "2",

                        "urun_ad": "Kent Dökme Şeker Kg",

                        "urun_url": "https://www.migros.com.tr/kent-dokme-seker-kg-p-abc123",

                        "urun_kategori": "Atıştırmalık",

                        "eklenme_tarihi": "2026-03-22 20:10:14+03:00",

                        "market_adi": "Migros",

                        "urun_marka": "Kent",

                        "sira_no": "1",

                        "site_product_code": "123",

                        "url_key": "kent-dokme-seker-kg-p-abc123",

                    }

                ],

            )

            write_csv(

                base / "fiyat_zaman_serisi.csv",

                [

                    {

                        "kayit_id": "1",

                        "urun_id": "1",

                        "urun_fiyat": "159.9",

                        "gramaj_degeri": "",

                        "gramaj_birimi": "",

                        "birim_fiyat": "",

                        "kazima_tarihi": "2026-03-22 20:10:14+03:00",

                        "adet_sayisi": "1.0",

                    }

                ],

            )



            grouped = load_grouped_snapshots(base)

            snapshots = grouped["site_product_code:123"]

            self.assertEqual(len(snapshots), 1)

            self.assertEqual(snapshots[0].gramaj_degeri, 1000.0)

            self.assertEqual(snapshots[0].gramaj_birimi, "g")

            self.assertEqual(round(snapshots[0].birim_fiyat, 4), 159.9)



    def test_load_grouped_snapshots_supports_count_based_products(self) -> None:

        with tempfile.TemporaryDirectory() as temp_dir:

            base = Path(temp_dir)

            write_csv(

                base / "urunler.csv",

                [

                    {

                        "id": "1",

                        "market_id": "2",

                        "urun_ad": "Fairy Hepsi Bir Arada 42 Tablet",

                        "urun_url": "https://www.migros.com.tr/fairy-hepsi-bir-arada-42-tablet-p-abc123",

                        "urun_kategori": "Temizlik",

                        "eklenme_tarihi": "2026-03-22 20:10:14+03:00",

                        "market_adi": "Migros",

                        "urun_marka": "Fairy",

                        "sira_no": "1",

                        "site_product_code": "123",

                        "url_key": "fairy-hepsi-bir-arada-42-tablet-p-abc123",

                    }

                ],

            )

            write_csv(

                base / "fiyat_zaman_serisi.csv",

                [

                    {

                        "kayit_id": "1",

                        "urun_id": "1",

                        "urun_fiyat": "210",

                        "gramaj_degeri": "",

                        "gramaj_birimi": "",

                        "birim_fiyat": "",

                        "kazima_tarihi": "2026-03-22 20:10:14+03:00",

                        "adet_sayisi": "1.0",

                    }

                ],

            )



            grouped = load_grouped_snapshots(base)

            snapshots = grouped["site_product_code:123"]

            self.assertEqual(len(snapshots), 1)

            self.assertEqual(snapshots[0].gramaj_degeri, 42.0)

            self.assertEqual(snapshots[0].gramaj_birimi, "adet")

            self.assertEqual(round(snapshots[0].birim_fiyat, 4), 5.0)



    def test_analyze_market_pairs_builds_human_summary_style_counts(self) -> None:

        with tempfile.TemporaryDirectory() as temp_dir:

            base = Path(temp_dir)

            onceki_dizin = base / "previous"

            guncel_dizin = base / "current"

            onceki_dizin.mkdir()

            guncel_dizin.mkdir()



            write_csv(

                onceki_dizin / "urunler.csv",

                [

                    {

                        "id": "1",

                        "market_id": "2",

                        "urun_ad": "Loco No:13 Vişne Çikolata 900 ml",

                        "urun_url": "https://example.com/loco-900",

                        "urun_kategori": "Dondurma",

                        "eklenme_tarihi": "2026-03-22 20:10:14+03:00",

                        "market_adi": "Migros",

                        "urun_marka": "Loco",

                        "sira_no": "1",

                        "site_product_code": "111",

                        "url_key": "loco-900",

                    },

                    {

                        "id": "2",

                        "market_id": "2",

                        "urun_ad": "Yudum Ayçiçekyağı Köşeli Pet 5 L",

                        "urun_url": "https://example.com/yudum-5l",

                        "urun_kategori": "Temel Gıda",

                        "eklenme_tarihi": "2026-03-22 20:10:14+03:00",

                        "market_adi": "Migros",

                        "urun_marka": "Yudum",

                        "sira_no": "2",

                        "site_product_code": "222",

                        "url_key": "yudum-5l",

                    },

                    {

                        "id": "3",

                        "market_id": "2",

                        "urun_ad": "Torku Tam Buğdaylı Bisküvi 393 g",

                        "urun_url": "https://example.com/torku-393",

                        "urun_kategori": "Atıştırmalık",

                        "eklenme_tarihi": "2026-03-22 20:10:14+03:00",

                        "market_adi": "Migros",

                        "urun_marka": "Torku",

                        "sira_no": "3",

                        "site_product_code": "333",

                        "url_key": "torku-393",

                    },

                    {

                        "id": "4",

                        "market_id": "2",

                        "urun_ad": "Deneme Pirinç 1 kg",

                        "urun_url": "https://example.com/pirinc-1kg",

                        "urun_kategori": "Temel Gıda",

                        "eklenme_tarihi": "2026-03-22 20:10:14+03:00",

                        "market_adi": "Migros",

                        "urun_marka": "Deneme",

                        "sira_no": "4",

                        "site_product_code": "444",

                        "url_key": "pirinc-1kg",

                    },

                ],

            )

            write_csv(

                onceki_dizin / "fiyat_zaman_serisi.csv",

                [

                    {

                        "kayit_id": "1",

                        "urun_id": "1",

                        "urun_fiyat": "850.95",

                        "gramaj_degeri": "900",

                        "gramaj_birimi": "ml",

                        "birim_fiyat": str(850.95 / 900 * 1000),

                        "kazima_tarihi": "2026-03-22 20:10:14+03:00",

                        "adet_sayisi": "1.0",

                    },

                    {

                        "kayit_id": "2",

                        "urun_id": "2",

                        "urun_fiyat": "499.95",

                        "gramaj_degeri": "5000",

                        "gramaj_birimi": "ml",

                        "birim_fiyat": str(499.95 / 5000 * 1000),

                        "kazima_tarihi": "2026-03-22 20:10:14+03:00",

                        "adet_sayisi": "1.0",

                    },

                    {

                        "kayit_id": "3",

                        "urun_id": "3",

                        "urun_fiyat": "72.50",

                        "gramaj_degeri": "393",

                        "gramaj_birimi": "g",

                        "birim_fiyat": str(72.50 / 393 * 1000),

                        "kazima_tarihi": "2026-03-22 20:10:14+03:00",

                        "adet_sayisi": "1.0",

                    },

                    {

                        "kayit_id": "4",

                        "urun_id": "4",

                        "urun_fiyat": "100.00",

                        "gramaj_degeri": "1000",

                        "gramaj_birimi": "g",

                        "birim_fiyat": "100.0",

                        "kazima_tarihi": "2026-03-22 20:10:14+03:00",

                        "adet_sayisi": "1.0",

                    },

                ],

            )



            write_csv(

                guncel_dizin / "urunler.csv",

                [

                    {

                        "id": "10",

                        "market_id": "2",

                        "urun_ad": "Loco No:13 Vişne Çikolata 450 ml",

                        "urun_url": "https://example.com/loco-450",

                        "urun_kategori": "Dondurma",

                        "eklenme_tarihi": "2026-04-22 20:10:14+03:00",

                        "market_adi": "Migros",

                        "urun_marka": "Loco",

                        "sira_no": "1",

                        "site_product_code": "111",

                        "url_key": "loco-450",

                    },

                    {

                        "id": "20",

                        "market_id": "2",

                        "urun_ad": "Yudum Ayçiçekyağı Köşeli Pet 3 L",

                        "urun_url": "https://example.com/yudum-3l",

                        "urun_kategori": "Temel Gıda",

                        "eklenme_tarihi": "2026-04-22 20:10:14+03:00",

                        "market_adi": "Migros",

                        "urun_marka": "Yudum",

                        "sira_no": "2",

                        "site_product_code": "222",

                        "url_key": "yudum-3l",

                    },

                    {

                        "id": "30",

                        "market_id": "2",

                        "urun_ad": "Torku Tam Buğdaylı Bisküvi 131 g",

                        "urun_url": "https://example.com/torku-131",

                        "urun_kategori": "Atıştırmalık",

                        "eklenme_tarihi": "2026-04-22 20:10:14+03:00",

                        "market_adi": "Migros",

                        "urun_marka": "Torku",

                        "sira_no": "3",

                        "site_product_code": "333",

                        "url_key": "torku-131",

                    },

                    {

                        "id": "40",

                        "market_id": "2",

                        "urun_ad": "Deneme Pirinç 900 g",

                        "urun_url": "https://example.com/pirinc-900g",

                        "urun_kategori": "Temel Gıda",

                        "eklenme_tarihi": "2026-04-22 20:10:14+03:00",

                        "market_adi": "Migros",

                        "urun_marka": "Deneme",

                        "sira_no": "4",

                        "site_product_code": "444",

                        "url_key": "pirinc-900g",

                    },

                ],

            )

            write_csv(

                guncel_dizin / "fiyat_zaman_serisi.csv",

                [

                    {

                        "kayit_id": "10",

                        "urun_id": "10",

                        "urun_fiyat": "685.95",

                        "gramaj_degeri": "450",

                        "gramaj_birimi": "ml",

                        "birim_fiyat": str(685.95 / 450 * 1000),

                        "kazima_tarihi": "2026-04-22 20:10:14+03:00",

                        "adet_sayisi": "1.0",

                    },

                    {

                        "kayit_id": "20",

                        "urun_id": "20",

                        "urun_fiyat": "429.95",

                        "gramaj_degeri": "3000",

                        "gramaj_birimi": "ml",

                        "birim_fiyat": str(429.95 / 3000 * 1000),

                        "kazima_tarihi": "2026-04-22 20:10:14+03:00",

                        "adet_sayisi": "1.0",

                    },

                    {

                        "kayit_id": "30",

                        "urun_id": "30",

                        "urun_fiyat": "24.95",

                        "gramaj_degeri": "131",

                        "gramaj_birimi": "g",

                        "birim_fiyat": str(24.95 / 131 * 1000),

                        "kazima_tarihi": "2026-04-22 20:10:14+03:00",

                        "adet_sayisi": "1.0",

                    },

                    {

                        "kayit_id": "40",

                        "urun_id": "40",

                        "urun_fiyat": "85.50",

                        "gramaj_degeri": "900",

                        "gramaj_birimi": "g",

                        "birim_fiyat": str(85.5 / 900 * 1000),

                        "kazima_tarihi": "2026-04-22 20:10:14+03:00",

                        "adet_sayisi": "1.0",

                    },

                ],

            )



            (

                compared_identities,

                content_shrunk_count,

                aday_sayisi,

                strong_case_count,

                bulgu_satirlari,

            ) = analyze_market_pairs(onceki_dizin, guncel_dizin, TespitEsikleri())



            self.assertEqual(compared_identities, 4)

            self.assertEqual(content_shrunk_count, 4)

            self.assertEqual(aday_sayisi, 3)

            self.assertEqual(strong_case_count, 0)

            self.assertEqual(len(bulgu_satirlari), 3)

            self.assertEqual(bulgu_satirlari[0]["current_urun_url"], "https://example.com/loco-450")



            ozet_metni = format_summary_text(

                compared_identities=compared_identities,

                content_shrunk_count=content_shrunk_count,

                aday_sayisi=aday_sayisi,

                strong_case_count=strong_case_count,

                bulgu_satirlari=bulgu_satirlari,

            )



            self.assertIn("Eşleştirilen benzersiz ürün ailesi: 4", ozet_metni)

            self.assertIn("İçeriği küçülen ürün: 4", ozet_metni)

            self.assertIn("Birim fiyatı artan shrinkflation adayı: 3", ozet_metni)

            self.assertIn('Nominal fiyatı aynı kalıp ya da artıp küçülen "güçlü" vaka: 0', ozet_metni)

            self.assertIn(

                "Loco No:13 Vişne Çikolata 900 ml -> 450 ml, fiyat 850.95 TL -> 685.95 TL",

                ozet_metni,

            )

            self.assertIn("Güncel ürün: https://example.com/yudum-3l", ozet_metni)





if __name__ == "__main__":

    unittest.main()

