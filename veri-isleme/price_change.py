from dataclasses import dataclass

from datetime import datetime

from typing import Iterable, Optional



from shrinkflation import KARSILASTIRILABILIR_BIRIMLER, FIYAT_EPSILON, FiyatKaydi, pct_change





@dataclass(frozen=True)

class FiyatDegisimEsikleri:

    min_fiyat_artis_yuzdesi: float = 0.0

    min_fiyat_dusus_yuzdesi: float = 0.0





@dataclass(frozen=True)

class FiyatDegisimBulgusu:

    urun_id: int

    urun_ad: str

    onceki_kayit_tarihi: datetime

    yeni_kayit_tarihi: datetime

    onceki_fiyat: float

    yeni_fiyat: float

    onceki_gramaj_degeri: Optional[float]

    yeni_gramaj_degeri: Optional[float]

    gramaj_birimi: Optional[str]

    onceki_birim_fiyat: Optional[float]

    yeni_birim_fiyat: Optional[float]

    gramaj_degisim_pct: Optional[float]

    fiyat_degisim_pct: float

    birim_fiyat_degisim_pct: Optional[float]

    change_ratio_pct: float

    severity: str

    reason: str

    direction: str





def classify_price_change_severity(fiyat_degisim_yuzdesi: float) -> str:

    magnitude = abs(fiyat_degisim_yuzdesi)

    if magnitude >= 25.0:

        return "high"

    if magnitude >= 10.0:

        return "medium"

    return "low"





def _compute_measure_change(

    onceki_kayit: FiyatKaydi,

    guncel_kayit: FiyatKaydi,

) -> tuple[Optional[float], Optional[float], Optional[str]]:

    onceki_birim = onceki_kayit.gramaj_birimi

    guncel_birim = guncel_kayit.gramaj_birimi

    if onceki_birim is None or guncel_birim is None:

        return None, None, None

    if onceki_birim != guncel_birim:

        return None, None, None

    if onceki_birim not in KARSILASTIRILABILIR_BIRIMLER:

        return None, None, None

    if onceki_kayit.gramaj_degeri is None or guncel_kayit.gramaj_degeri is None:

        return None, None, onceki_birim

    if onceki_kayit.gramaj_degeri <= 0 or guncel_kayit.gramaj_degeri <= 0:

        return None, None, onceki_birim



    return (

        pct_change(onceki_kayit.gramaj_degeri, guncel_kayit.gramaj_degeri),

        pct_change(onceki_kayit.birim_fiyat, guncel_kayit.birim_fiyat),

        onceki_birim,

    )





def _build_reason(

    direction: str,

    gramaj_degisim_pct: Optional[float],

) -> str:

    if direction == "increase":

        default_reason = "price_increased"

        same_quantity_reason = "price_increased_same_quantity"

        dropped_reason = "price_increased_while_quantity_dropped"

        grew_reason = "price_increased_with_quantity_increase"

    else:

        default_reason = "price_decreased"

        same_quantity_reason = "price_decreased_same_quantity"

        dropped_reason = "price_decreased_with_quantity_drop"

        grew_reason = "price_decreased_while_quantity_increased"



    if gramaj_degisim_pct is None:

        return default_reason

    if abs(gramaj_degisim_pct) <= FIYAT_EPSILON:

        return same_quantity_reason

    if gramaj_degisim_pct < 0:

        return dropped_reason

    return grew_reason





def _build_finding(

    onceki_kayit: FiyatKaydi,

    guncel_kayit: FiyatKaydi,

    *,

    direction: str,

    fiyat_degisim_yuzdesi: float,

    gramaj_degisim_pct: Optional[float],

    birim_fiyat_degisim_pct: Optional[float],

    gramaj_birimi: Optional[str],

) -> FiyatDegisimBulgusu:

    severity = classify_price_change_severity(fiyat_degisim_yuzdesi)

    return FiyatDegisimBulgusu(

        urun_id=guncel_kayit.urun_id,

        urun_ad=guncel_kayit.urun_ad,

        onceki_kayit_tarihi=onceki_kayit.kazima_tarihi,

        yeni_kayit_tarihi=guncel_kayit.kazima_tarihi,

        onceki_fiyat=onceki_kayit.urun_fiyat,

        yeni_fiyat=guncel_kayit.urun_fiyat,

        onceki_gramaj_degeri=onceki_kayit.gramaj_degeri,

        yeni_gramaj_degeri=guncel_kayit.gramaj_degeri,

        gramaj_birimi=gramaj_birimi,

        onceki_birim_fiyat=onceki_kayit.birim_fiyat,

        yeni_birim_fiyat=guncel_kayit.birim_fiyat,

        gramaj_degisim_pct=gramaj_degisim_pct,

        fiyat_degisim_pct=fiyat_degisim_yuzdesi,

        birim_fiyat_degisim_pct=birim_fiyat_degisim_pct,

        change_ratio_pct=abs(fiyat_degisim_yuzdesi),

        severity=severity,

        reason=_build_reason(direction, gramaj_degisim_pct),

        direction=direction,

    )





def detect_price_increase(

    onceki_kayit: FiyatKaydi,

    guncel_kayit: FiyatKaydi,

    thresholds: FiyatDegisimEsikleri,

) -> Optional[FiyatDegisimBulgusu]:

    fiyat_degisim_yuzdesi = pct_change(onceki_kayit.urun_fiyat, guncel_kayit.urun_fiyat)

    if fiyat_degisim_yuzdesi is None:

        return None

    if guncel_kayit.urun_fiyat <= onceki_kayit.urun_fiyat + FIYAT_EPSILON:

        return None

    if fiyat_degisim_yuzdesi < thresholds.min_fiyat_artis_yuzdesi:

        return None



    gramaj_degisim_pct, birim_fiyat_degisim_pct, gramaj_birimi = _compute_measure_change(

        onceki_kayit,

        guncel_kayit,

    )

    if birim_fiyat_degisim_pct is not None and birim_fiyat_degisim_pct < -FIYAT_EPSILON:

        return None



    return _build_finding(

        onceki_kayit,

        guncel_kayit,

        direction="increase",

        fiyat_degisim_yuzdesi=fiyat_degisim_yuzdesi,

        gramaj_degisim_pct=gramaj_degisim_pct,

        birim_fiyat_degisim_pct=birim_fiyat_degisim_pct,

        gramaj_birimi=gramaj_birimi,

    )





def detect_price_decrease(

    onceki_kayit: FiyatKaydi,

    guncel_kayit: FiyatKaydi,

    thresholds: FiyatDegisimEsikleri,

) -> Optional[FiyatDegisimBulgusu]:

    fiyat_degisim_yuzdesi = pct_change(onceki_kayit.urun_fiyat, guncel_kayit.urun_fiyat)

    if fiyat_degisim_yuzdesi is None:

        return None

    if guncel_kayit.urun_fiyat >= onceki_kayit.urun_fiyat - FIYAT_EPSILON:

        return None

    if abs(fiyat_degisim_yuzdesi) < thresholds.min_fiyat_dusus_yuzdesi:

        return None



    gramaj_degisim_pct, birim_fiyat_degisim_pct, gramaj_birimi = _compute_measure_change(

        onceki_kayit,

        guncel_kayit,

    )

    if birim_fiyat_degisim_pct is not None and birim_fiyat_degisim_pct > FIYAT_EPSILON:

        return None



    return _build_finding(

        onceki_kayit,

        guncel_kayit,

        direction="decrease",

        fiyat_degisim_yuzdesi=fiyat_degisim_yuzdesi,

        gramaj_degisim_pct=gramaj_degisim_pct,

        birim_fiyat_degisim_pct=birim_fiyat_degisim_pct,

        gramaj_birimi=gramaj_birimi,

    )





def detect_price_changes_series(

    snapshots: Iterable[FiyatKaydi],

    thresholds: FiyatDegisimEsikleri,

) -> tuple[list[FiyatDegisimBulgusu], list[FiyatDegisimBulgusu]]:

    ordered = sorted(snapshots, key=lambda item: item.kazima_tarihi)

    fiyat_artislari: list[FiyatDegisimBulgusu] = []

    fiyat_dususleri: list[FiyatDegisimBulgusu] = []

    for onceki_kayit, guncel_kayit in zip(ordered, ordered[1:]):

        artis_bulgusu = detect_price_increase(onceki_kayit, guncel_kayit, thresholds)

        if artis_bulgusu is not None:

            fiyat_artislari.append(artis_bulgusu)



        dusus_bulgusu = detect_price_decrease(onceki_kayit, guncel_kayit, thresholds)

        if dusus_bulgusu is not None:

            fiyat_dususleri.append(dusus_bulgusu)



    return fiyat_artislari, fiyat_dususleri

