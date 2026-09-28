from dataclasses import dataclass

from datetime import datetime

import re

from typing import Iterable, Optional



KARSILASTIRILABILIR_BIRIMLER = {"g", "ml", "adet"}

FIYAT_EPSILON = 1e-9

SABIT_KG_PAKET_RE = re.compile(r"\d+(?:[.,]\d+)?\s*kg\b", re.IGNORECASE)

TARTIMLI_KG_URUN_RE = re.compile(r"\bkg\b", re.IGNORECASE)





@dataclass(frozen=True)

class FiyatKaydi:

    urun_id: int

    urun_ad: str

    kazima_tarihi: datetime

    urun_fiyat: float

    gramaj_degeri: Optional[float]

    gramaj_birimi: Optional[str]

    birim_fiyat: Optional[float]





@dataclass(frozen=True)

class TespitEsikleri:

    min_size_drop_pct: float = 3.0

    max_size_drop_pct: float = 70.0

    min_birim_fiyat_artis_yuzdesi: float = 3.0

    sabit_fiyat_alt_yuzdesi: float = 0.0





@dataclass(frozen=True)

class ShrinkflationBulgusu:

    urun_id: int

    urun_ad: str

    onceki_kayit_tarihi: datetime

    yeni_kayit_tarihi: datetime

    onceki_fiyat: float

    yeni_fiyat: float

    onceki_gramaj_degeri: float

    yeni_gramaj_degeri: float

    gramaj_birimi: str

    onceki_birim_fiyat: float

    yeni_birim_fiyat: float

    gramaj_degisim_pct: float

    fiyat_degisim_pct: float

    birim_fiyat_degisim_pct: float

    shrinkflation_orani_pct: float

    severity: str

    reason: str





def pct_change(old_value: Optional[float], new_value: Optional[float]) -> Optional[float]:

    if old_value is None or new_value is None or old_value == 0:

        return None

    return ((new_value - old_value) / old_value) * 100.0





def classify_severity(size_drop_pct: float, unit_price_increase_pct: float) -> str:

    if size_drop_pct >= 20.0 or unit_price_increase_pct >= 25.0:

        return "high"

    if size_drop_pct >= 10.0 or unit_price_increase_pct >= 10.0:

        return "medium"

    return "low"


def is_tartimli_kg_urun(urun_ad: str) -> bool:

    normalize_ad = " ".join(str(urun_ad).casefold().split())

    if not TARTIMLI_KG_URUN_RE.search(normalize_ad):

        return False

    return SABIT_KG_PAKET_RE.search(normalize_ad) is None





def detect_shrinkflation(

    onceki_kayit: FiyatKaydi,

    guncel_kayit: FiyatKaydi,

    thresholds: TespitEsikleri,

) -> Optional[ShrinkflationBulgusu]:

    if is_tartimli_kg_urun(onceki_kayit.urun_ad) or is_tartimli_kg_urun(guncel_kayit.urun_ad):

        return None

    if onceki_kayit.gramaj_birimi is None or guncel_kayit.gramaj_birimi is None:

        return None

    if onceki_kayit.gramaj_birimi not in KARSILASTIRILABILIR_BIRIMLER:

        return None

    if guncel_kayit.gramaj_birimi not in KARSILASTIRILABILIR_BIRIMLER:

        return None

    if onceki_kayit.gramaj_birimi != guncel_kayit.gramaj_birimi:

        return None

    if onceki_kayit.gramaj_degeri is None or guncel_kayit.gramaj_degeri is None:

        return None

    if onceki_kayit.birim_fiyat is None or guncel_kayit.birim_fiyat is None:

        return None

    if onceki_kayit.gramaj_degeri <= 0 or guncel_kayit.gramaj_degeri <= 0:

        return None



    gramaj_degisim_pct = pct_change(onceki_kayit.gramaj_degeri, guncel_kayit.gramaj_degeri)

    fiyat_degisim_pct = pct_change(onceki_kayit.urun_fiyat, guncel_kayit.urun_fiyat)

    birim_fiyat_degisim_pct = pct_change(onceki_kayit.birim_fiyat, guncel_kayit.birim_fiyat)

    if gramaj_degisim_pct is None or fiyat_degisim_pct is None or birim_fiyat_degisim_pct is None:

        return None



    size_drop_pct = -gramaj_degisim_pct

    if size_drop_pct < thresholds.min_size_drop_pct:

        return None

    if size_drop_pct > thresholds.max_size_drop_pct:

        return None

    if birim_fiyat_degisim_pct < thresholds.min_birim_fiyat_artis_yuzdesi:

        return None

    if fiyat_degisim_pct < thresholds.sabit_fiyat_alt_yuzdesi:

        return None



    if guncel_kayit.urun_fiyat > onceki_kayit.urun_fiyat + FIYAT_EPSILON:

        reason = "price_increased_while_quantity_dropped"

    elif guncel_kayit.urun_fiyat < onceki_kayit.urun_fiyat - FIYAT_EPSILON:

        reason = "price_dropped_but_not_enough_after_quantity_drop"

    else:

        reason = "price_stable_while_quantity_dropped"



    severity = classify_severity(size_drop_pct, birim_fiyat_degisim_pct)

    return ShrinkflationBulgusu(

        urun_id=guncel_kayit.urun_id,

        urun_ad=guncel_kayit.urun_ad,

        onceki_kayit_tarihi=onceki_kayit.kazima_tarihi,

        yeni_kayit_tarihi=guncel_kayit.kazima_tarihi,

        onceki_fiyat=onceki_kayit.urun_fiyat,

        yeni_fiyat=guncel_kayit.urun_fiyat,

        onceki_gramaj_degeri=onceki_kayit.gramaj_degeri,

        yeni_gramaj_degeri=guncel_kayit.gramaj_degeri,

        gramaj_birimi=guncel_kayit.gramaj_birimi,

        onceki_birim_fiyat=onceki_kayit.birim_fiyat,

        yeni_birim_fiyat=guncel_kayit.birim_fiyat,

        gramaj_degisim_pct=gramaj_degisim_pct,

        fiyat_degisim_pct=fiyat_degisim_pct,

        birim_fiyat_degisim_pct=birim_fiyat_degisim_pct,

        shrinkflation_orani_pct=birim_fiyat_degisim_pct,

        severity=severity,

        reason=reason,

    )





def detect_shrinkflation_series(

    snapshots: Iterable[FiyatKaydi],

    thresholds: TespitEsikleri,

) -> list[ShrinkflationBulgusu]:

    ordered = sorted(snapshots, key=lambda item: item.kazima_tarihi)

    daily_snapshots: dict[object, FiyatKaydi] = {}

    for snapshot in ordered:

        daily_snapshots[snapshot.kazima_tarihi.date()] = snapshot

    ordered = [daily_snapshots[tarih] for tarih in sorted(daily_snapshots)]

    bulgular: list[ShrinkflationBulgusu] = []

    for onceki_kayit, guncel_kayit in zip(ordered, ordered[1:]):

        bulgu = detect_shrinkflation(onceki_kayit, guncel_kayit, thresholds)

        if bulgu is not None:

            bulgular.append(bulgu)

    return bulgular
