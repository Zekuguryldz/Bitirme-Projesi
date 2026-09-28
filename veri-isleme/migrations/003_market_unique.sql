WITH canonical_market AS (
    SELECT market_adi, MIN(market_id) AS keep_market_id
    FROM market
    GROUP BY market_adi
),
duplicate_market AS (
    SELECT m.market_id, c.keep_market_id
    FROM market AS m
    JOIN canonical_market AS c
      ON c.market_adi = m.market_adi
    WHERE m.market_id <> c.keep_market_id
)
UPDATE urunler AS u
SET market_id = d.keep_market_id
FROM duplicate_market AS d
WHERE u.market_id = d.market_id;

WITH canonical_market AS (
    SELECT market_adi, MIN(market_id) AS keep_market_id
    FROM market
    GROUP BY market_adi
)
DELETE FROM market AS m
USING canonical_market AS c
WHERE m.market_adi = c.market_adi
  AND m.market_id <> c.keep_market_id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_market_market_adi
ON market (market_adi);
