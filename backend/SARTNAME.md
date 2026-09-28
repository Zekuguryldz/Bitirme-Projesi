# Proje Sartnamesi

## Proje Adi

Shrinkflation Tespit ve Takip Sistemi Backend

## Dokuman Amaci

Bu sartname, haftalik proje planinda tanimlanan calismalar ile bu repository icindeki mevcut backend uygulamasinin kapsamını ayni eksende tanimlamak icin hazirlanmistir.

## Plan ile Uyumlu Hedef

Projenin genel amaci; e-ticaret ve market verilerinden urun, fiyat ve gramaj bilgisini toplayip temizlemek, PostgreSQL veritabaninda saklamak ve shrinkflation analizi ile dashboard ihtiyaclarini destekleyen bir backend servisi sunmaktir.

Bu repository icindeki teslimat, projenin backend ve veri sunum katmanina odaklanir.

## Teknoloji Kapsami

- Backend servis: FastAPI
- Veritabani erisimi: SQLAlchemy
- Veritabani: PostgreSQL
- Ortam yonetimi: python-dotenv
- API sunucusu: Uvicorn

Plan dokumaninda gecen `Requests`, `BeautifulSoup`, `Selenium`, `pandas`, `Bootstrap` ve `Chart.js` bu repository'nin dogrudan zorunlu calisma alani degildir; bunlar veri toplama, analiz veya arayuz katmani olarak ayri moduller halinde ele alinabilir. `Telegram Bot API` tarafinda ise market bazli bildirim gonderimi icin opsiyonel bir entegrasyon katmani eklenmistir.

## Backend Teslimat Kapsami

Bu backend asagidaki ihtiyaclari karsilar:

- PostgreSQL uzerindeki `urunler`, `market` ve `fiyat_zaman_serisi` tablolarina erisim
- Urun listeleme ve filtreleme API'si
- Dashboard icin ozet, kategori dagilimi, en ucuz ve en pahali urun endpointleri
- Uygulama saglik kontrol endpointi
- `.env` ile `DATABASE_URL` tabanli konfigurasyon

## Mevcut Endpointler

- `GET /`
- `GET /health`
- `GET /products`
- `GET /dashboard/summary`
- `GET /dashboard/category-distribution`
- `GET /dashboard/top-cheapest`
- `GET /dashboard/top-expensive`

## Haftalik Plan ile Eslestirme

### Tamamlanmis veya Bu Repository'de Karsilanan Kalemler

- FastAPI tabanli backend servisinin kurulmasi
- PostgreSQL veritabanina baglanti yapisinin kurulmasi
- `urunler`, `market` ve `fiyat_zaman_serisi` tablolarina karsilik gelen model yapilarinin tanimlanmasi
- Urun listeleme, arama ve kategori filtreleme endpointinin saglanmasi
- Dashboard icin temel toplu veri endpointlerinin saglanmasi

### Kismen Karsilanan Kalemler

- Birim fiyat analizi:
  Su an backend `fiyat_zaman_serisi` verisini kullanan dashboard sorgularina sahiptir; ancak gramaj normalizasyonu ve shrinkflation mantigini acikca hesaplayan ayri bir analiz endpointi bu repository'de bulunmamaktadir.

### Bu Repository Disinda veya Henuz Tamamlanmamis Kalemler

- Scraper veya veri cekici botlarin yazilmasi
- Veri temizleme ve `pandas` tabanli preprocessing scriptleri
- Jupyter notebook tabanli analiz calismalari
- Kullanici komutlari, webhook akislari veya ileri seviye bot etkileşimleri
- Bootstrap veya Chart.js tabanli frontend arayuz
- Deploy, raporlama ve sunum ciktilari

## Fonksiyonel Gereksinimler

- Sistem, PostgreSQL veritabanina `DATABASE_URL` ile baglanabilmelidir.
- Sistem, urunleri sayfalama (`limit`, `offset`) ile listeleyebilmelidir.
- Sistem, urunleri kategori ve metin aramasi ile filtreleyebilmelidir.
- Sistem, dashboard ozet verilerini tek endpoint uzerinden donebilmelidir.
- Sistem, kategori bazli urun dagilimini donebilmelidir.
- Sistem, son fiyat kaydina gore en ucuz ve en pahali urunleri donebilmelidir.

## Fonksiyonel Olmayan Gereksinimler

- API JSON formatinda cevap vermelidir.
- Kod yapisi router bazli ve genisletilebilir olmalidir.
- Ortam degiskenleri kaynak koda gomulmemelidir.
- Servis yerelde `python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000` veya `make dev` ile calistirilabilmelidir.

## Sonuc

Bu repository, proje planinin backend ve veri sunum bolumunu karsilayan bir cekirdek servis teslimatidir. Haftalik planin tum maddeleri tek repository icinde tamamlanmis kabul edilmemelidir; scraper, veri temizleme, analiz notebooklari, frontend ve bildirim sistemleri ayri teslimatlar veya ek moduller olarak planlanmalidir.
