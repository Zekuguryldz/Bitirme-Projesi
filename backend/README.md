# FastAPI Backend

Bu servis Supabase PostgreSQL veritabanindaki `urunler`, `market` ve `fiyat_zaman_serisi` tablolarindaki verileri API olarak sunar.

## Kurulum

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

## Ortam Degiskenleri

Proje klasorunde `.env` dosyasi olusturup baglanti bilgisini yazin. Ornek:

- `DATABASE_URL`

```env
DATABASE_URL=postgresql://postgres.PROJECT_REF:SIFRE@aws-REGION.pooler.supabase.com:5432/postgres
```

## Klasor Yapisi

- `app/main.py`
- `app/database.py`
- `app/models.py`
- `app/schemas.py`
- `app/routers/products.py`
- `app/routers/dashboard.py`

## Endpointler

- `GET /`
- `GET /api`
- `GET /health`
- `GET /products`
- `GET /dashboard/summary`
- `GET /dashboard/category-distribution`
- `GET /dashboard/top-cheapest`
- `GET /dashboard/top-expensive`
- `GET /dashboard/top-price-changes`
- `GET /dashboard/category-price-changes`
- `GET /dashboard/risky-products`
- `POST /notifications/telegram/shrinkflation`
- `GET /urunler`
- `GET /riskli-urunler`
- `GET /hakkinda`

## Telegram Bildirimleri

Telegram'a market bazli haftalik birim fiyat raporu gonderebilirsiniz. Mesajda guncel cekilen benzersiz urun sayisi, karsilastirma tarih araligi, birim fiyati artan urun sayisi, birim fiyati azalan urun sayisi ve shrinkflation riskli urun sayisi yer alir. Ayrica her baslik altinda ilk 5 urun ve secili tarih araligi icin dashboard linki gonderilir. Urun sayisi fazla ise mesaj birden fazla parcaya bolunur.

Gerekli ortam degiskenleri:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_MIGROS_BOT_TOKEN` (opsiyonel, Migros icin ayri bot kullaniliyorsa)
- `TELEGRAM_SOK_BOT_TOKEN` (opsiyonel, SOK icin ayri bot kullaniliyorsa)
- `TELEGRAM_MIGROS_CHAT_ID` (opsiyonel fallback)
- `TELEGRAM_SOK_CHAT_ID` (opsiyonel fallback)
- `TELEGRAM_MIGROS_THREAD_ID` (opsiyonel)
- `TELEGRAM_SOK_THREAD_ID` (opsiyonel)
- `TELEGRAM_REQUEST_TIMEOUT_SECONDS` (opsiyonel, varsayilan `10`)
- `TELEGRAM_DASHBOARD_BASE_URL` (opsiyonel, varsayilan `http://127.0.0.1:8000`)

Isterseniz kanal hedeflerini ve esikleri `bildirim_kurali` tablosunda da tutabilirsiniz. Bu durumda `bildirim_merkezi` alanina `@kanal_adi` veya `https://t.me/kanal_adi` yazilir. Kod aktif kurallari otomatik okuyup gonderim basarisi ile mesaj icerigini `gecmis_bildirimler` tablosuna kaydeder.

Kural kayitlarini olusturma ornegi:

```bash
python scripts/seed_telegram_notification_rules.py
```

Manuel tetikleme ornekleri:

```bash
python scripts/send_telegram_notifications.py --dry-run
python scripts/send_telegram_notifications.py --market migros
```

Veri cekimi sirasinda bekleyip otomatik gonderim icin:

```bash
python scripts/watch_market_refresh_and_notify.py --market sok --send-when-empty
python scripts/watch_market_refresh_and_notify.py --market migros --send-when-empty
```

Veri zaten cekildiyse ve script baslarken mevcut son snapshot icin de bildirim denemek istiyorsaniz:

```bash
python scripts/watch_market_refresh_and_notify.py --market migros --notify-on-start
```

Surekli izleyip her yeni SQL aktarimindan sonra otomatik bildirim icin:

```bash
python scripts/run_market_notification_daemon.py --send-when-empty
```

Daemon basladiginda mevcut snapshot'lari da kontrol etmek icin:

```bash
python scripts/run_market_notification_daemon.py --notify-on-start --send-when-empty
```

API uzerinden tetikleme:

```bash
curl -X POST "http://127.0.0.1:8000/notifications/telegram/shrinkflation"
curl -X POST "http://127.0.0.1:8000/notifications/telegram/shrinkflation?market=sok&dry_run=true"
```

## Not

`/products` endpointi `kategori` ve `search` filtrelerini destekler. Sunum cumlesi:

`FastAPI kullanilarak Supabase PostgreSQL veritabanindaki verileri sunan backend servis gelistirilmis ve dashboard icin gerekli API endpointleri olusturulmustur.`

Detayli kapsam ve proje planina gore guncellenmis backend sartnamesi icin bkz. `SARTNAME.md`.
