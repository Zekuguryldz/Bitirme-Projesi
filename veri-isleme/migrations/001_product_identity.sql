ALTER TABLE urunler
ADD COLUMN IF NOT EXISTS site_product_code TEXT;

ALTER TABLE urunler
ADD COLUMN IF NOT EXISTS url_key TEXT;

ALTER TABLE urunler
ADD COLUMN IF NOT EXISTS urun_marka TEXT;

ALTER TABLE urunler
ADD COLUMN IF NOT EXISTS market_adi TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_urunler_market_site_product_code
ON urunler (market_id, site_product_code)
WHERE site_product_code IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_urunler_market_url_key
ON urunler (market_id, url_key)
WHERE url_key IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_fiyat_zaman_serisi_urun_tarih
ON fiyat_zaman_serisi (urun_id, kazima_tarihi);
