import psycopg2



baglanti = psycopg2.connect('postgresql://postgres:Zekyildiz.34@db.jxvuoblbceaqmadvnsvu.supabase.co:5432/postgres')

cur = baglanti.imlec()



cur.execute('ALTER TABLE urunler ADD COLUMN IF NOT EXISTS market_adi TEXT')

cur.execute("UPDATE urunler SET market_adi = 'ŞOK'")

cur.execute('ALTER TABLE urunler DROP CONSTRAINT urunler_market_id_fkey')

cur.execute('DELETE FROM market')

cur.execute('ALTER SEQUENCE market_market_id_seq RESTART WITH 1')

cur.execute("INSERT INTO market (market_adi) VALUES ('ŞOK')")

cur.execute("INSERT INTO market (market_adi) VALUES ('Migros')")

cur.execute('UPDATE urunler SET market_id = 1')

cur.execute('ALTER TABLE urunler ADD CONSTRAINT urunler_market_id_fkey FOREIGN KEY (market_id) REFERENCES market(market_id)')



baglanti.commit()



cur.execute('SELECT * FROM market')

print('market:', cur.fetchall())

cur.execute('SELECT id, market_id, market_adi, urun_ad FROM urunler LIMIT 3')

print('urunler sample:', cur.fetchall())



cur.close()

baglanti.close()

print('Done!')

