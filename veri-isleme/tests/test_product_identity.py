import unittest



from product_identity import build_product_identity, extract_url_key





class ProductIdentityTests(unittest.TestCase):

    def test_extract_url_key(self) -> None:

        adres = "https://www.sokmarket.com.tr/akturk-vanilyali-gofret-300-g-p-309449"

        self.assertEqual(extract_url_key(adres), "309449")



    def test_extract_url_key_supports_migros_slug(self) -> None:

        adres = "https://www.migros.com.tr/akturk-vanilyali-gofret-300-g-p-6b0073"

        self.assertEqual(extract_url_key(adres), "akturk-vanilyali-gofret-300-g-p-6b0073")



    def test_extract_url_key_returns_none_for_invalid_url(self) -> None:

        adres = "https://www.sokmarket.com.tr/akturk-vanilyali-gofret-300-g"

        self.assertIsNone(extract_url_key(adres))



    def test_build_product_identity_prefers_product_code(self) -> None:

        identity = build_product_identity(

            site_urun_kodu="00147499",

            urun_url="https://www.sokmarket.com.tr/akturk-vanilyali-gofret-300-g-p-309449",

        )

        self.assertEqual(

            list(identity.adaylar()),

            [

                ("site_product_code", "00147499"),

                ("url_key", "309449"),

                (

                    "urun_url",

                    "https://www.sokmarket.com.tr/akturk-vanilyali-gofret-300-g-p-309449",

                ),

            ],

        )



    def test_build_product_identity_uses_url_when_code_missing(self) -> None:

        identity = build_product_identity(

            urun_url="https://www.sokmarket.com.tr/pepsi-cola-4-1-lt-p-12345",

        )

        self.assertEqual(

            list(identity.adaylar()),

            [

                ("url_key", "12345"),

                ("urun_url", "https://www.sokmarket.com.tr/pepsi-cola-4-1-lt-p-12345"),

            ],

        )



    def test_build_product_identity_uses_migros_slug_key(self) -> None:

        identity = build_product_identity(

            urun_url="https://www.migros.com.tr/akturk-vanilyali-gofret-300-g-p-6b0073",

        )

        self.assertEqual(

            list(identity.adaylar()),

            [

                ("url_key", "akturk-vanilyali-gofret-300-g-p-6b0073"),

                (

                    "urun_url",

                    "https://www.migros.com.tr/akturk-vanilyali-gofret-300-g-p-6b0073",

                ),

            ],

        )





if __name__ == "__main__":

    unittest.main()

