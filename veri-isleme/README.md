# Market Fiyat Takip Projesi

Migros ve ŞOK market verilerini scrape edip normalize eden, Supabase/Postgres'e ürün ve fiyat geçmişi olarak senkronize eden çalışma alanı.

## Ana Akışlar

- `sok_weekly_supabase_sync.py`: ŞOK haftalık scrape + normalize + veritabanı senkronizasyonu.
- `migros_weekly_supabase_sync.py`: Migros haftalık scrape + normalize + veritabanı senkronizasyonu.
- `detect_shrinkflation_csv.py`: İki output klasörü arasında shrinkflation tespiti yapar.
- `audit_market_identity.py`: Farklı market output klasörlerinde ürün kimliği çakışma risklerini denetler.
- `import_current_normalized_to_supabase.py`: Normalize edilmiş güncel CSV çıktılarını kalıcı ürün kimliğiyle veritabanına aktarır.

## Dizinler

- `outputs/`: Tek seferlik veya manuel koşuların çıktı dosyaları.
- `scheduled_outputs/`: Zamanlanmış haftalık koşuların çıktı ve logları.
- `migrations/`: Ürün kimliği, tekillik ve senkronizasyon güvenliği için SQL migration dosyaları.
- `schedules/`: Cron örnekleri.
- `tests/`: Birim testleri.

## Hızlı Kullanım

Testleri çalıştır:

```bash
pytest -q
```

ŞOK akışını veritabanına yazmadan dry-run çalıştır:

```bash
python sok_weekly_supabase_sync.py --dry-run
```

Pazar günü koşuyu Cumartesi 19:00 tarihli yazmak için:

```bash
python sok_weekly_supabase_sync.py --dry-run --scrape-datetime 2026-05-09
```

Migros akışını veritabanına yazmadan dry-run çalıştır:

```bash
python migros_weekly_supabase_sync.py --dry-run
```

İki klasör arasında shrinkflation tespiti yap:

```bash
python detect_shrinkflation_csv.py \
  outputs/migros_mart_2026_fixed \
  outputs/migros_nisan_2026_fixed \
  --audit-csv outputs/migros_mart_nisan_2026_shrinkflation.csv \
  --summary-json outputs/migros_mart_nisan_2026_shrinkflation_summary.json
```

## Ortam

- Veritabanı bağlantısı için varsayılan ortam değişkeni: `SUPABASE_DB_URL`
- ŞOK ve Migros haftalık senkronizasyon scriptleri `--help` ile tüm opsiyonları gösterir.
- Haftalık senkronizasyon scriptleri geçmiş `fiyat_zaman_serisi` kayıtlarını okuyup varsayılan olarak shrinkflation ve `unit_price_zscore` anomalileri üretir; bulgu varsa hem `anomalies_detected.csv` dosyasına hem de `anomali` tablosuna yazar.
- Cron örnekleri `schedules/` altında tutulur; sistem kurulumundan önce interpreter yolu ve proje dizini doğrulanmalıdır.
