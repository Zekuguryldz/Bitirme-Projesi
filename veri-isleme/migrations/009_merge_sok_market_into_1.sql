BEGIN;

DROP INDEX IF EXISTS uq_urunler_market_site_product_code;
DROP INDEX IF EXISTS uq_urunler_market_url_key;

UPDATE urunler
SET
    market_id = 1,
    market_adi = 'ŞOK'
WHERE market_id = 3;

UPDATE urunler
SET market_adi = 'ŞOK'
WHERE market_id = 1;

DELETE FROM market
WHERE market_id = 3
  AND NOT EXISTS (
      SELECT 1
      FROM urunler
      WHERE market_id = 3
  );

COMMIT;
