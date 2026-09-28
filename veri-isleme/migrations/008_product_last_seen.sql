ALTER TABLE urunler
ADD COLUMN IF NOT EXISTS son_gorulme_tarihi TIMESTAMPTZ;

UPDATE urunler AS u
SET son_gorulme_tarihi = latest.max_kazima_tarihi
FROM (
    SELECT urun_id, MAX(kazima_tarihi) AS max_kazima_tarihi
    FROM fiyat_zaman_serisi
    GROUP BY urun_id
) AS latest
WHERE u.id = latest.urun_id
  AND (
    u.son_gorulme_tarihi IS NULL
    OR u.son_gorulme_tarihi < latest.max_kazima_tarihi
  );

CREATE INDEX IF NOT EXISTS urunler_son_gorulme_tarihi_idx
    ON urunler (son_gorulme_tarihi);
