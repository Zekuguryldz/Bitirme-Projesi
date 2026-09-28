from dataclasses import dataclass

from statistics import StatisticsError, mean, stdev

from typing import Sequence



from shrinkflation import FiyatKaydi, pct_change





@dataclass(frozen=True)

class ZScoreThresholds:

    z_score_threshold: float = 2.5

    min_history_count: int = 3

    min_mutlak_birim_fiyat_degisim_yuzdesi: float = 3.0





@dataclass(frozen=True)

class ZScoreBulgusu:

    urun_id: int

    urun_ad: str

    onceki_kayit_tarihi: object

    yeni_kayit_tarihi: object

    onceki_fiyat: float

    yeni_fiyat: float

    onceki_gramaj_degeri: float | None

    yeni_gramaj_degeri: float | None

    gramaj_birimi: str | None

    onceki_birim_fiyat: float | None

    yeni_birim_fiyat: float

    gramaj_degisim_pct: float | None

    fiyat_degisim_pct: float | None

    birim_fiyat_degisim_pct: float | None

    gecmis_ortalama_birim_fiyat: float

    gecmis_std_birim_fiyat: float

    history_sample_count: int

    z_score: float

    severity: str

    reason: str





def classify_z_score_severity(z_score_value: float) -> str:

    magnitude = abs(z_score_value)

    if magnitude >= 4.0:

        return "high"

    if magnitude >= 3.0:

        return "medium"

    return "low"





def detect_unit_price_zscore_anomaly(

    history_snapshots: Sequence[FiyatKaydi],

    guncel_kayit: FiyatKaydi,

    thresholds: ZScoreThresholds,

) -> ZScoreBulgusu | None:

    if guncel_kayit.birim_fiyat is None:

        return None



    comparable_history = [item for item in history_snapshots if item.birim_fiyat is not None]

    if len(comparable_history) < thresholds.min_history_count:

        return None



    gecmis_birim_fiyatlari = [float(item.birim_fiyat) for item in comparable_history if item.birim_fiyat is not None]

    try:

        history_std = stdev(gecmis_birim_fiyatlari)

    except StatisticsError:

        return None



    if history_std == 0:

        return None



    history_mean = mean(gecmis_birim_fiyatlari)

    z_score_value = (float(guncel_kayit.birim_fiyat) - history_mean) / history_std

    if abs(z_score_value) < thresholds.z_score_threshold:

        return None



    latest_snapshot = max(comparable_history, key=lambda item: item.kazima_tarihi)

    birim_fiyat_degisim_yuzdesi = pct_change(latest_snapshot.birim_fiyat, guncel_kayit.birim_fiyat)

    if birim_fiyat_degisim_yuzdesi is None:

        return None

    if abs(birim_fiyat_degisim_yuzdesi) < thresholds.min_mutlak_birim_fiyat_degisim_yuzdesi:

        return None



    reason = "unit_price_above_history_zscore" if z_score_value > 0 else "unit_price_below_history_zscore"

    return ZScoreBulgusu(

        urun_id=guncel_kayit.urun_id,

        urun_ad=guncel_kayit.urun_ad,

        onceki_kayit_tarihi=latest_snapshot.kazima_tarihi,

        yeni_kayit_tarihi=guncel_kayit.kazima_tarihi,

        onceki_fiyat=latest_snapshot.urun_fiyat,

        yeni_fiyat=guncel_kayit.urun_fiyat,

        onceki_gramaj_degeri=latest_snapshot.gramaj_degeri,

        yeni_gramaj_degeri=guncel_kayit.gramaj_degeri,

        gramaj_birimi=guncel_kayit.gramaj_birimi,

        onceki_birim_fiyat=latest_snapshot.birim_fiyat,

        yeni_birim_fiyat=float(guncel_kayit.birim_fiyat),

        gramaj_degisim_pct=pct_change(latest_snapshot.gramaj_degeri, guncel_kayit.gramaj_degeri),

        fiyat_degisim_pct=pct_change(latest_snapshot.urun_fiyat, guncel_kayit.urun_fiyat),

        birim_fiyat_degisim_pct=birim_fiyat_degisim_yuzdesi,

        gecmis_ortalama_birim_fiyat=float(history_mean),

        gecmis_std_birim_fiyat=float(history_std),

        history_sample_count=len(gecmis_birim_fiyatlari),

        z_score=float(z_score_value),

        severity=classify_z_score_severity(z_score_value),

        reason=reason,

    )

