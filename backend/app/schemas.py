from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ProductResponse(BaseModel):
    id: int
    market_id: Optional[int] = None
    urun_ad: str
    urun_url: Optional[str] = None
    urun_kategori: Optional[str] = None
    eklenme_tarihi: Optional[datetime] = None
    market_adi: Optional[str] = None
    urun_marka: Optional[str] = None
    sira_no: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class ProductPriceItem(BaseModel):
    urun_id: int
    urun_ad: str
    market_adi: Optional[str] = None
    urun_kategori: Optional[str] = None
    urun_marka: Optional[str] = None
    urun_fiyat: Optional[Decimal] = None
    kazima_tarihi: Optional[datetime] = None


class ProductListItem(BaseModel):
    id: int
    urun_ad: str
    urun_url: Optional[str] = None
    urun_kategori: Optional[str] = None
    market_adi: Optional[str] = None
    urun_durumu: Optional[str] = None
    urun_fiyat: Optional[Decimal] = None
    gramaj_degeri: Optional[Decimal] = None
    gramaj_birimi: Optional[str] = None
    birim_fiyat: Optional[Decimal] = None
    urun_marka: Optional[str] = None
    eklenme_tarihi: Optional[datetime] = None


class ProductsListResponse(BaseModel):
    total: int
    items: list[ProductListItem]


class CategoryListResponse(BaseModel):
    total: int
    items: list[str]


class DateListResponse(BaseModel):
    total: int
    items: list[date]


class DashboardSummaryResponse(BaseModel):
    toplam_urun: int
    toplam_urun_tarihi: Optional[date] = None
    toplam_kategori: int
    bugun_guncellenen_kayit: int = 0
    karsilastirma_baslangic_tarihi: Optional[date] = None
    karsilastirma_bitis_tarihi: Optional[date] = None
    en_cok_hareket_gosteren_kategori: Optional[str] = None
    ortalama_fiyat: Optional[Decimal] = None
    minimum_fiyat: Optional[Decimal] = None
    maksimum_fiyat: Optional[Decimal] = None


class CategoryDistributionItem(BaseModel):
    kategori: str
    urun_sayisi: int


class CategoryDistributionResponse(BaseModel):
    total_categories: int
    items: list[CategoryDistributionItem]


class PriceChangeItem(BaseModel):
    urun_id: int
    urun_ad: str
    urun_url: Optional[str] = None
    market_adi: Optional[str] = None
    urun_kategori: Optional[str] = None
    eski_fiyat: Optional[Decimal] = None
    yeni_fiyat: Optional[Decimal] = None
    gramaj_birimi: Optional[str] = None
    eski_birim_fiyat: Optional[Decimal] = None
    yeni_birim_fiyat: Optional[Decimal] = None
    birim_fiyat_degisim_yuzdesi: Optional[Decimal] = None
    degisim_yuzdesi: Optional[Decimal] = None
    kazima_tarihi: Optional[datetime] = None


class PriceChangeListResponse(BaseModel):
    total: int
    items: list[PriceChangeItem]


class CategoryPriceChangeItem(BaseModel):
    kategori: str
    ortalama_degisim_yuzdesi: Optional[Decimal] = None
    urun_sayisi: int


class CategoryPriceChangeResponse(BaseModel):
    total: int
    items: list[CategoryPriceChangeItem]


class ProductPriceComparisonItem(BaseModel):
    urun_id: int
    urun_ad: str
    urun_url: Optional[str] = None
    market_adi: Optional[str] = None
    urun_kategori: Optional[str] = None
    eski_fiyat: Optional[Decimal] = None
    yeni_fiyat: Optional[Decimal] = None
    eski_gramaj: Optional[Decimal] = None
    yeni_gramaj: Optional[Decimal] = None
    gramaj_birimi: Optional[str] = None
    eski_birim_fiyat: Optional[Decimal] = None
    yeni_birim_fiyat: Optional[Decimal] = None
    eski_tarih: Optional[datetime] = None
    yeni_tarih: Optional[datetime] = None
    birim_fiyat_degisim_yuzdesi: Optional[Decimal] = None
    gramaj_degisim_yuzdesi: Optional[Decimal] = None
    eski_birim_gramaj: Optional[Decimal] = None
    yeni_birim_gramaj: Optional[Decimal] = None
    eski_adet_sayisi: Optional[Decimal] = None
    yeni_adet_sayisi: Optional[Decimal] = None
    adet_degisim_yuzdesi: Optional[Decimal] = None
    birim_icerik_degisim_yuzdesi: Optional[Decimal] = None
    fiyat_degisim_yuzdesi: Optional[Decimal] = None
    shrinkflation_orani_yuzdesi: Optional[Decimal] = None
    severity: Optional[str] = None
    direction: Optional[str] = None
    reason: Optional[str] = None
    is_shrinkflation: Optional[bool] = None


class ProductPriceComparisonResponse(BaseModel):
    total: int
    items: list[ProductPriceComparisonItem]


class RiskyProductItem(BaseModel):
    urun_id: int
    urun_ad: str
    urun_url: Optional[str] = None
    market_adi: Optional[str] = None
    urun_kategori: Optional[str] = None
    eski_fiyat: Optional[Decimal] = None
    yeni_fiyat: Optional[Decimal] = None
    eski_gramaj: Optional[Decimal] = None
    yeni_gramaj: Optional[Decimal] = None
    gramaj_birimi: Optional[str] = None
    eski_birim_fiyat: Optional[Decimal] = None
    yeni_birim_fiyat: Optional[Decimal] = None
    birim_fiyat_degisim_yuzdesi: Optional[Decimal] = None
    gramaj_degisim_yuzdesi: Optional[Decimal] = None
    eski_birim_gramaj: Optional[Decimal] = None
    yeni_birim_gramaj: Optional[Decimal] = None
    eski_adet_sayisi: Optional[Decimal] = None
    yeni_adet_sayisi: Optional[Decimal] = None
    adet_degisim_yuzdesi: Optional[Decimal] = None
    birim_icerik_degisim_yuzdesi: Optional[Decimal] = None
    fiyat_degisim_yuzdesi: Optional[Decimal] = None
    shrinkflation_orani_yuzdesi: Optional[Decimal] = None
    severity: Optional[str] = None
    direction: Optional[str] = None
    reason: Optional[str] = None
    is_shrinkflation: Optional[bool] = None
    eski_tarih: Optional[datetime] = None
    yeni_tarih: Optional[datetime] = None
    kazima_tarihi: Optional[datetime] = None


class RiskyProductListResponse(BaseModel):
    total: int
    items: list[RiskyProductItem]


class TopProductsResponse(BaseModel):
    total: int
    items: list[ProductPriceItem]


class TelegramNotificationDispatchItem(BaseModel):
    market: str
    sent: bool
    skipped: bool
    target_configured: bool
    item_count: int
    current_snapshot_count: int = 0
    artan_urun_sayisi: int = 0
    azalan_urun_sayisi: int = 0
    shrinkflation_riskli_urun_sayisi: int = 0
    latest_snapshot_date: Optional[date] = None
    previous_snapshot_date: Optional[date] = None
    reason: Optional[str] = None
    preview: str
    rule_id: Optional[int] = None
    notification_center: Optional[str] = None


class TelegramNotificationDispatchResponse(BaseModel):
    total: int
    sent_count: int
    failed_count: int
    skipped_count: int
    items: list[TelegramNotificationDispatchItem]
