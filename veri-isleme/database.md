# Veritabanı Tabloları ve İlişkileri

## 1. market
- `market_id` → Primary Key
- `market_adi`

### Bağlı olduğu / bağlanan
- `urunler.market_id` → `market.market_id`

---

## 2. urunler
- `id` → Primary Key
- `market_id` → Foreign Key → `market.market_id`
- `urun_ad`
- `urun_url`
- `site_product_code`
- `url_key`
- `urun_kategori`
- `urun_marka`
- `market_adi`
- `eklenme_tarihi`
- `son_gorulme_tarihi`

### Bağlı olduğu / bağlanan
- `urunler.market_id` → `market.market_id`
- `fiyat_zaman_serisi.urun_id` → `urunler.id`
- `anomali.ilgili_urun_id` → `urunler.id`
- `zamli_urunler.ilgili_urun_id` → `urunler.id`
- `indirimli_urunler.ilgili_urun_id` → `urunler.id`
- `bildirim_kurali.urun_id` → `urunler.id`

---

## 3. fiyat_zaman_serisi
- `kayit_id` → Primary Key
- `urun_id` → Foreign Key → `urunler.id`
- `urun_fiyat`
- `gramaj_degeri`
- `gramaj_birimi`
- `birim_fiyat`
- `kazima_tarihi`

### Bağlı olduğu
- `fiyat_zaman_serisi.urun_id` → `urunler.id`

### Kimlik ve tekillik notu
- Aynı ürün her scrape'te yeniden oluşturulmamalı.
- ŞOK için önce `site_product_code`, yoksa `url_key`, son fallback olarak `urun_url` ile ürün eşleşmesi yapılmalı.
- `fiyat_zaman_serisi` tarafında aynı `urun_id + kazima_tarihi` kombinasyonu ikinci kez eklenmemeli.

---

## 4. anomali
- `anomali_id` → Primary Key
- `ilgili_urun_id` → Foreign Key → `urunler.id`
- `eski_degeri`
- `yeni_degeri`
- `anomali_tespit_tarihi`
- `anomali_turu`
- `onceki_fiyat`
- `yeni_fiyat_detay`
- `onceki_gramaj_degeri`
- `yeni_gramaj_degeri_detay`
- `gramaj_birimi`
- `onceki_birim_fiyat`
- `yeni_birim_fiyat_detay`
- `gramaj_degisim_pct`
- `fiyat_degisim_pct`
- `birim_fiyat_degisim_pct`
- `shrinkflation_orani_pct`
- `severity`
- `reason`
- `z_score`
- `history_sample_count`
- `onceki_kayit_tarihi`
- `yeni_kayit_tarihi`

### Bağlı olduğu
- `anomali.ilgili_urun_id` → `urunler.id`

### Week 4 notu
- Shrinkflation tespiti geçmiş snapshot ile güncel snapshot arasında yapılır.
- Temel kural: ürünün normalize edilmiş miktarı düşerken (`g`, `ml`, `adet/kullanim`), `birim_fiyat` belirgin artmalı ve klasik modda toplam fiyat düşmemeli.
- Varsayılan eşikler kodda `size_drop >= %3`, `unit_price_increase >= %3`, `price_change >= %0` olarak tanımlandı.
- Daha geniş yorum istenirse `stable_price_floor_pct` negatif verilerek "fiyat biraz düştü ama miktara göre yeterince düşmedi" durumu da dahil edilebilir.
- Ayrı bir `unit_price_zscore` anomali türü de vardır; bu sinyal ürünün güncel normalize `birim_fiyat` değerini kendi tarihsel dağılımına göre değerlendirir.

---

## 5. zamli_urunler
- `zamli_urun_id` → Primary Key
- `ilgili_urun_id` → Foreign Key → `urunler.id`
- `eski_degeri`
- `yeni_degeri`
- `zam_tespit_tarihi`
- `onceki_fiyat`
- `yeni_fiyat_detay`
- `onceki_gramaj_degeri`
- `yeni_gramaj_degeri_detay`
- `gramaj_birimi`
- `onceki_birim_fiyat`
- `yeni_birim_fiyat_detay`
- `gramaj_degisim_pct`
- `fiyat_degisim_pct`
- `birim_fiyat_degisim_pct`
- `zam_orani_pct`
- `severity`
- `reason`
- `onceki_kayit_tarihi`
- `yeni_kayit_tarihi`
- `created_at`

### Bağlı olduğu
- `zamli_urunler.ilgili_urun_id` → `urunler.id`

### Not
- Bu tablo, dashboarddaki zamlı ürün kartları için fiyat artışı snapshot'larını saklar.
- Yapı bilinçli olarak `anomali` tablosuna benzer tutuldu; insert/query tarafında aynı desen kolayca kopyalanabilir.

---

## 6. indirimli_urunler
- `indirimli_urun_id` → Primary Key
- `ilgili_urun_id` → Foreign Key → `urunler.id`
- `eski_degeri`
- `yeni_degeri`
- `indirim_tespit_tarihi`
- `onceki_fiyat`
- `yeni_fiyat_detay`
- `onceki_gramaj_degeri`
- `yeni_gramaj_degeri_detay`
- `gramaj_birimi`
- `onceki_birim_fiyat`
- `yeni_birim_fiyat_detay`
- `gramaj_degisim_pct`
- `fiyat_degisim_pct`
- `birim_fiyat_degisim_pct`
- `indirim_orani_pct`
- `severity`
- `reason`
- `onceki_kayit_tarihi`
- `yeni_kayit_tarihi`
- `created_at`

### Bağlı olduğu
- `indirimli_urunler.ilgili_urun_id` → `urunler.id`

### Not
- Bu tablo, dashboarddaki indirimli ürün kartları için fiyat düşüşü snapshot'larını saklar.
- İndirim oranı için `indirim_orani_pct`, fiyat yönü için `fiyat_degisim_pct <= 0` mantığı beklenir.

---

## 7. bildirim_kurali
- `kural_id` → Primary Key
- `urun_id` → Foreign Key → `urunler.id`
- `yuzdesel_artis`
- `esik_deger`
- `bildirim_merkezi`
- `kural_aktif_kontrolu`
- `olusturulma_tarihi`

### Bağlı olduğu / bağlanan
- `bildirim_kurali.urun_id` → `urunler.id`
- `gecmis_bildirimler.tetiklenen_kural` → `bildirim_kurali.kural_id`

---

## 8. gecmis_bildirimler
- `bildirim_id` → Primary Key
- `tetiklenen_kural` → Foreign Key → `bildirim_kurali.kural_id`
- `bildirim_tarihi`
- `basari_testi`
- `mesaj_icerigi`

### Bağlı olduğu
- `gecmis_bildirimler.tetiklenen_kural` → `bildirim_kurali.kural_id`

---

## 9. kullanicilar
- `kullanici_id` → Primary Key
- `telegram_chat_id`

### Bağlı olduğu / bağlanan
- Telegram chat kimliği kullanıcı veya grup hedefi olarak kullanılabilir

---

## 10. market_telegram_gruplari
- `market_id` → Primary Key / Foreign Key → `market.market_id`
- `telegram_chat_id`
- `grup_adi`
- `aktif`
- `olusturulma_tarihi`
- `guncellenme_tarihi`

### Bağlı olduğu / bağlanan
- `market_telegram_gruplari.market_id` → `market.market_id`
- ŞOK market grubu için `market_id = 1`
- Migros grubu için `market_id = 2`
