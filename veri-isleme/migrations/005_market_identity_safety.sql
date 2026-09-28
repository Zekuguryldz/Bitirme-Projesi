BEGIN;

ALTER TABLE urunler
    ADD COLUMN IF NOT EXISTS sira_no INTEGER;

ALTER TABLE fiyat_zaman_serisi
    ADD COLUMN IF NOT EXISTS adet_sayisi NUMERIC;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'market_market_adi_key'
    ) THEN
        ALTER TABLE market
            ADD CONSTRAINT market_market_adi_key UNIQUE (market_adi);
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS urunler_market_site_product_code_uidx
    ON urunler (market_id, site_product_code)
    WHERE site_product_code IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS urunler_market_url_key_uidx
    ON urunler (market_id, url_key)
    WHERE url_key IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS urunler_market_urun_url_uidx
    ON urunler (market_id, urun_url)
    WHERE urun_url IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS fiyat_zaman_serisi_urun_id_kazima_tarihi_uidx
    ON fiyat_zaman_serisi (urun_id, kazima_tarihi);

CREATE INDEX IF NOT EXISTS urunler_market_id_idx
    ON urunler (market_id);

CREATE INDEX IF NOT EXISTS fiyat_zaman_serisi_urun_id_idx
    ON fiyat_zaman_serisi (urun_id);

CREATE INDEX IF NOT EXISTS anomali_ilgili_urun_id_idx
    ON anomali (ilgili_urun_id);

COMMIT;
