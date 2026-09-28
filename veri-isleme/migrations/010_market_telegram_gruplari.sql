BEGIN;

CREATE TABLE IF NOT EXISTS market_telegram_gruplari (
    market_id INTEGER PRIMARY KEY REFERENCES market(market_id) ON DELETE CASCADE,
    telegram_chat_id BIGINT UNIQUE,
    grup_adi TEXT NOT NULL,
    aktif BOOLEAN NOT NULL DEFAULT TRUE,
    olusturulma_tarihi TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    guncellenme_tarihi TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO market_telegram_gruplari (market_id, grup_adi)
VALUES
    (1, 'ŞOK Telegram Grubu'),
    (2, 'Migros Telegram Grubu')
ON CONFLICT (market_id) DO UPDATE
SET grup_adi = EXCLUDED.grup_adi,
    guncellenme_tarihi = NOW();

CREATE INDEX IF NOT EXISTS market_telegram_gruplari_aktif_idx
    ON market_telegram_gruplari (aktif);

COMMIT;
