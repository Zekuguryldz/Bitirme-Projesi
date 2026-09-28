ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS anomali_turu TEXT DEFAULT 'shrinkflation';

ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS onceki_fiyat NUMERIC;

ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS yeni_fiyat_detay NUMERIC;

ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS onceki_gramaj_degeri NUMERIC;

ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS yeni_gramaj_degeri_detay NUMERIC;

ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS gramaj_birimi TEXT;

ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS onceki_birim_fiyat NUMERIC;

ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS yeni_birim_fiyat_detay NUMERIC;

ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS gramaj_degisim_pct NUMERIC;

ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS fiyat_degisim_pct NUMERIC;

ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS birim_fiyat_degisim_pct NUMERIC;

ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS shrinkflation_orani_pct NUMERIC;

ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS severity TEXT;

ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS reason TEXT;

ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS onceki_kayit_tarihi TIMESTAMPTZ;

ALTER TABLE anomali
ADD COLUMN IF NOT EXISTS yeni_kayit_tarihi TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS uq_anomali_shrinkflation_window
ON anomali (ilgili_urun_id, onceki_kayit_tarihi, yeni_kayit_tarihi, anomali_turu);
