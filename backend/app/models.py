from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, Text

from app.database import Base


class Product(Base):
    __tablename__ = "urunler"

    id = Column(Integer, primary_key=True, index=True)
    market_id = Column(Integer, ForeignKey("market.market_id"), nullable=True)
    urun_ad = Column(Text, nullable=False)
    urun_url = Column(Text, nullable=True)
    urun_kategori = Column(Text, nullable=True)
    eklenme_tarihi = Column(DateTime(timezone=True), nullable=True)
    market_adi = Column(Text, nullable=True)
    urun_marka = Column(Text, nullable=True)
    sira_no = Column(Integer, nullable=True)


class Market(Base):
    __tablename__ = "market"

    market_id = Column(Integer, primary_key=True, index=True)
    market_adi = Column(Text, nullable=False)


class PriceTimeSeries(Base):
    __tablename__ = "fiyat_zaman_serisi"

    kayit_id = Column(Integer, primary_key=True, index=True)
    urun_id = Column(Integer, ForeignKey("urunler.id"), nullable=False)
    urun_fiyat = Column(Numeric, nullable=True)
    gramaj_degeri = Column(Numeric, nullable=True)
    gramaj_birimi = Column(Text, nullable=True)
    birim_fiyat = Column(Numeric, nullable=True)
    kazima_tarihi = Column(DateTime(timezone=True), nullable=True)
    adet_sayisi = Column(Numeric, nullable=True)
