BEGIN;

CREATE TABLE IF NOT EXISTS zamli_urunler (
    zamli_urun_id BIGSERIAL PRIMARY KEY,
    ilgili_urun_id INTEGER NOT NULL REFERENCES urunler(id) ON DELETE CASCADE,
    eski_degeri NUMERIC,
    yeni_degeri NUMERIC,
    zam_tespit_tarihi TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    onceki_fiyat NUMERIC,
    yeni_fiyat_detay NUMERIC,
    onceki_gramaj_degeri NUMERIC,
    yeni_gramaj_degeri_detay NUMERIC,
    gramaj_birimi TEXT,
    onceki_birim_fiyat NUMERIC,
    yeni_birim_fiyat_detay NUMERIC,
    gramaj_degisim_pct NUMERIC,
    fiyat_degisim_pct NUMERIC,
    birim_fiyat_degisim_pct NUMERIC,
    zam_orani_pct NUMERIC,
    severity TEXT,
    reason TEXT,
    onceki_kayit_tarihi TIMESTAMPTZ,
    yeni_kayit_tarihi TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_zamli_urunler_fiyat_yonu
        CHECK (onceki_fiyat IS NULL OR yeni_fiyat_detay IS NULL OR yeni_fiyat_detay >= onceki_fiyat),
    CONSTRAINT chk_zamli_urunler_fiyat_degisim_pct
        CHECK (fiyat_degisim_pct IS NULL OR fiyat_degisim_pct >= 0),
    CONSTRAINT chk_zamli_urunler_zam_orani_pct
        CHECK (zam_orani_pct IS NULL OR zam_orani_pct >= 0)
);

CREATE TABLE IF NOT EXISTS indirimli_urunler (
    indirimli_urun_id BIGSERIAL PRIMARY KEY,
    ilgili_urun_id INTEGER NOT NULL REFERENCES urunler(id) ON DELETE CASCADE,
    eski_degeri NUMERIC,
    yeni_degeri NUMERIC,
    indirim_tespit_tarihi TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    onceki_fiyat NUMERIC,
    yeni_fiyat_detay NUMERIC,
    onceki_gramaj_degeri NUMERIC,
    yeni_gramaj_degeri_detay NUMERIC,
    gramaj_birimi TEXT,
    onceki_birim_fiyat NUMERIC,
    yeni_birim_fiyat_detay NUMERIC,
    gramaj_degisim_pct NUMERIC,
    fiyat_degisim_pct NUMERIC,
    birim_fiyat_degisim_pct NUMERIC,
    indirim_orani_pct NUMERIC,
    severity TEXT,
    reason TEXT,
    onceki_kayit_tarihi TIMESTAMPTZ,
    yeni_kayit_tarihi TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_indirimli_urunler_fiyat_yonu
        CHECK (onceki_fiyat IS NULL OR yeni_fiyat_detay IS NULL OR yeni_fiyat_detay <= onceki_fiyat),
    CONSTRAINT chk_indirimli_urunler_fiyat_degisim_pct
        CHECK (fiyat_degisim_pct IS NULL OR fiyat_degisim_pct <= 0),
    CONSTRAINT chk_indirimli_urunler_indirim_orani_pct
        CHECK (indirim_orani_pct IS NULL OR indirim_orani_pct >= 0)
);

CREATE INDEX IF NOT EXISTS zamli_urunler_ilgili_urun_id_idx
    ON zamli_urunler (ilgili_urun_id);

CREATE INDEX IF NOT EXISTS indirimli_urunler_ilgili_urun_id_idx
    ON indirimli_urunler (ilgili_urun_id);

CREATE INDEX IF NOT EXISTS zamli_urunler_tespit_tarihi_idx
    ON zamli_urunler (zam_tespit_tarihi DESC);

CREATE INDEX IF NOT EXISTS indirimli_urunler_tespit_tarihi_idx
    ON indirimli_urunler (indirim_tespit_tarihi DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_zamli_urunler_window
    ON zamli_urunler (ilgili_urun_id, onceki_kayit_tarihi, yeni_kayit_tarihi);

CREATE UNIQUE INDEX IF NOT EXISTS uq_indirimli_urunler_window
    ON indirimli_urunler (ilgili_urun_id, onceki_kayit_tarihi, yeni_kayit_tarihi);

COMMIT;
