from __future__ import annotations

import json
import os
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib import error, request
from urllib.parse import urlencode, urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.shrinkflation import DetectionThresholds, list_market_date_comparison_findings
from app.sql_helpers import build_canonical_product_identity_sql


DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_DASHBOARD_BASE_URL = "http://127.0.0.1:8000"
MAX_TELEGRAM_MESSAGE_LENGTH = 4000
MARKET_LABELS = {
    "migros": "Migros",
    "sok": "ŞOK",
}
URUN_DURUMU_ZAMLANMIS = "zamlanmis_urunler"
URUN_DURUMU_INDIRIMDEKI = "indirimdeki_urunler"
URUN_DURUMU_SHRINKFLATION = "shrinkflation_riskli_urunler"
REASON_LABELS = {
    "total_content_reduced": "toplam icerik azaldi",
    "unit_size_reduced": "birim icerik azaldi",
    "pack_count_reduced": "adet azaldi",
    "pack_count_and_unit_size_reduced": "adet ve birim icerik azaldi",
}
SEVERITY_LABELS = {
    "high": "yuksek",
    "medium": "orta",
    "low": "dusuk",
    "info": "bilgi",
}
MARKET_TRANSLATION_SOURCE = "CGIOSUcgiosuÇĞİIÖŞÜçğıöşü"
MARKET_TRANSLATION_TARGET = "cgiosucgiosucgiiosucgiosu"


class TelegramNotificationError(RuntimeError):
    pass


class TelegramConfigurationError(TelegramNotificationError):
    pass


class TelegramDeliveryError(TelegramNotificationError):
    pass


@dataclass(frozen=True)
class TelegramTarget:
    chat_id: str
    thread_id: Optional[int] = None


@dataclass(frozen=True)
class TelegramNotificationConfig:
    default_bot_token: str
    api_base_url: str
    timeout_seconds: float
    targets: dict[str, TelegramTarget]
    market_bot_tokens: dict[str, str]


@dataclass(frozen=True)
class TelegramDispatchResult:
    market: str
    sent: bool
    skipped: bool
    target_configured: bool
    item_count: int
    current_snapshot_count: int
    latest_snapshot_date: Optional[date]
    previous_snapshot_date: Optional[date]
    reason: Optional[str]
    preview: str
    rule_id: Optional[int] = None
    notification_center: Optional[str] = None
    artan_urun_sayisi: int = 0
    azalan_urun_sayisi: int = 0
    shrinkflation_riskli_urun_sayisi: int = 0


@dataclass(frozen=True)
class NotificationRule:
    rule_id: int
    market: str
    notification_center: str
    target: TelegramTarget
    thresholds: DetectionThresholds


@dataclass(frozen=True)
class MarketWeeklyNotificationPayload:
    market: str
    latest_snapshot_date: Optional[date]
    previous_snapshot_date: Optional[date]
    current_snapshot_count: int
    rows: list[dict[str, object]] = field(default_factory=list)
    artan_urunler: list[dict[str, object]] = field(default_factory=list)
    azalan_urunler: list[dict[str, object]] = field(default_factory=list)
    shrinkflation_riskli_urunler: list[dict[str, object]] = field(default_factory=list)
    artan_urun_sayisi: int = 0
    azalan_urun_sayisi: int = 0
    shrinkflation_riskli_urun_sayisi: int = 0


def market_label(value: str) -> str:
    return MARKET_LABELS.get(value, value.upper())


def fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    return without_marks.translate(str.maketrans("çğıöşü", "cgiosu"))


def parse_optional_int_env(name: str) -> Optional[int]:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return None

    try:
        return int(raw_value)
    except ValueError as exc:
        raise TelegramConfigurationError(f"{name} gecersiz bir tam sayi olmali.") from exc


def parse_timeout_seconds() -> float:
    raw_value = os.getenv("TELEGRAM_REQUEST_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)).strip()
    try:
        timeout_seconds = float(raw_value)
    except ValueError as exc:
        raise TelegramConfigurationError(
            "TELEGRAM_REQUEST_TIMEOUT_SECONDS gecerli bir sayi olmali."
        ) from exc

    if timeout_seconds <= 0:
        raise TelegramConfigurationError("TELEGRAM_REQUEST_TIMEOUT_SECONDS sifirdan buyuk olmali.")
    return timeout_seconds


def load_telegram_notification_config(
    *,
    require_bot_token: bool = True,
) -> TelegramNotificationConfig:
    default_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    api_base_url = os.getenv("TELEGRAM_API_BASE_URL", "https://api.telegram.org").strip() or "https://api.telegram.org"
    targets: dict[str, TelegramTarget] = {}
    market_bot_tokens: dict[str, str] = {}
    for market, env_prefix in (("migros", "MIGROS"), ("sok", "SOK")):
        bot_token = os.getenv(f"TELEGRAM_{env_prefix}_BOT_TOKEN", "").strip()
        if bot_token:
            market_bot_tokens[market] = bot_token
        chat_id = os.getenv(f"TELEGRAM_{env_prefix}_CHAT_ID", "").strip()
        if not chat_id:
            continue
        targets[market] = TelegramTarget(
            chat_id=chat_id,
            thread_id=parse_optional_int_env(f"TELEGRAM_{env_prefix}_THREAD_ID"),
        )

    if require_bot_token and not default_bot_token and not market_bot_tokens:
        raise TelegramConfigurationError(
            "TELEGRAM_BOT_TOKEN veya markete ozel TELEGRAM_<MARKET>_BOT_TOKEN tanimli degil."
        )

    return TelegramNotificationConfig(
        default_bot_token=default_bot_token,
        api_base_url=api_base_url.rstrip("/"),
        timeout_seconds=parse_timeout_seconds(),
        targets=targets,
        market_bot_tokens=market_bot_tokens,
    )


def coerce_decimal(value: object) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return decimal_value if decimal_value.is_finite() else None


def format_number(value: object, *, precision: int = 2) -> str:
    numeric_value = coerce_decimal(value)
    if numeric_value is None:
        return "-"

    normalized = numeric_value.quantize(Decimal(1)) if numeric_value == numeric_value.to_integral() else numeric_value
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return f"{float(normalized):.{precision}f}".rstrip("0").rstrip(".")


def format_currency(value: object) -> str:
    formatted = format_number(value, precision=2)
    return "-" if formatted == "-" else f"{formatted} TL"


def format_percent(value: object) -> str:
    numeric_value = coerce_decimal(value)
    if numeric_value is None:
        return "-"
    sign = "+" if numeric_value > 0 else ""
    return f"{sign}{format_number(numeric_value, precision=2)}%"


def format_measure(value: object, unit: Optional[str]) -> str:
    formatted = format_number(value, precision=4)
    if formatted == "-" or not unit:
        return "-"
    return f"{formatted} {unit}"


def get_dashboard_base_url() -> str:
    configured_value = os.getenv("TELEGRAM_DASHBOARD_BASE_URL", DEFAULT_DASHBOARD_BASE_URL).strip()
    return (configured_value or DEFAULT_DASHBOARD_BASE_URL).rstrip("/")


def preview_text(value: str, *, max_length: int = 600) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3].rstrip() + "..."


def limit_message_size(value: str) -> str:
    if len(value) <= MAX_TELEGRAM_MESSAGE_LENGTH:
        return value
    return value[: MAX_TELEGRAM_MESSAGE_LENGTH - 20].rstrip() + "\n\nDevami kisaltildi."


def find_latest_snapshot_date(rows: list[dict[str, object]]) -> Optional[date]:
    latest_dates = [
        snapshot_value.date()
        for snapshot_value in (row.get("kazima_tarihi") for row in rows)
        if isinstance(snapshot_value, datetime)
    ]
    return max(latest_dates) if latest_dates else None


def build_market_pattern(market: str) -> str:
    return "sok%" if market == "sok" else "migros%"


def get_market_comparison_dates(
    db: Session,
    *,
    market: str,
) -> tuple[Optional[date], Optional[date]]:
    rows = db.execute(
        text(
            """
            select distinct date(f.kazima_tarihi) as snapshot_date
            from fiyat_zaman_serisi f
            join urunler u on u.id = f.urun_id
            where f.kazima_tarihi is not null
              and lower(
                    translate(
                        coalesce(u.market_adi, ''),
                        :translation_source,
                        :translation_target
                    )
                ) like :market_pattern
            order by snapshot_date desc
            limit 2
            """
        ),
        {
            "translation_source": MARKET_TRANSLATION_SOURCE,
            "translation_target": MARKET_TRANSLATION_TARGET,
            "market_pattern": build_market_pattern(market),
        },
    ).mappings().all()
    if not rows:
        return None, None

    latest_date = rows[0]["snapshot_date"]
    previous_date = rows[1]["snapshot_date"] if len(rows) > 1 else None
    return previous_date, latest_date


def get_market_snapshot_count(
    db: Session,
    *,
    market: str,
    snapshot_date: Optional[date],
) -> int:
    if snapshot_date is None:
        return 0

    product_identity_sql = build_canonical_product_identity_sql("u.urun_url", "u.urun_ad")
    row = db.execute(
        text(
            f"""
            select count(distinct {product_identity_sql}) as snapshot_count
            from fiyat_zaman_serisi f
            join urunler u on u.id = f.urun_id
            where date(f.kazima_tarihi) = :snapshot_date
              and lower(
                    translate(
                        coalesce(u.market_adi, ''),
                        :translation_source,
                        :translation_target
                    )
                ) like :market_pattern
            """
        ),
        {
            "snapshot_date": snapshot_date,
            "translation_source": MARKET_TRANSLATION_SOURCE,
            "translation_target": MARKET_TRANSLATION_TARGET,
            "market_pattern": build_market_pattern(market),
        },
    ).mappings().one()
    return int(row["snapshot_count"] or 0)


def resolve_notification_comparison_dates(
    db: Session,
    *,
    market: str,
    date_start: Optional[datetime] = None,
    date_end: Optional[datetime] = None,
) -> tuple[Optional[date], Optional[date]]:
    if date_start is not None and date_end is not None:
        selected_start_date = date_start.date()
        selected_end_date = (date_end - timedelta(microseconds=1)).date()
        if selected_start_date <= selected_end_date:
            return selected_start_date, selected_end_date
        return selected_end_date, selected_start_date

    return get_market_comparison_dates(
        db,
        market=market,
    )


def load_market_weekly_notification_payload(
    db: Session,
    *,
    market: str,
    thresholds: Optional[DetectionThresholds] = None,
    limit: Optional[int] = None,
    date_start: Optional[datetime] = None,
    date_end: Optional[datetime] = None,
) -> MarketWeeklyNotificationPayload:
    previous_snapshot_date, latest_snapshot_date = resolve_notification_comparison_dates(
        db,
        market=market,
        date_start=date_start,
        date_end=date_end,
    )
    current_snapshot_count = get_market_snapshot_count(
        db,
        market=market,
        snapshot_date=latest_snapshot_date,
    )

    if previous_snapshot_date is None or latest_snapshot_date is None:
        return MarketWeeklyNotificationPayload(
            market=market,
            latest_snapshot_date=latest_snapshot_date,
            previous_snapshot_date=previous_snapshot_date,
            current_snapshot_count=current_snapshot_count,
            rows=[],
        )

    effective_limit = limit if limit is not None else 5
    artan_urunlerin_tumu = list_market_date_comparison_findings(
        db,
        thresholds=thresholds,
        limit=None,
        market=market,
        old_date=previous_snapshot_date,
        new_date=latest_snapshot_date,
        increases_only=True,
        sort_by_unit_price=True,
    )
    azalan_urunlerin_tumu = list_market_date_comparison_findings(
        db,
        thresholds=thresholds,
        limit=None,
        market=market,
        old_date=previous_snapshot_date,
        new_date=latest_snapshot_date,
        decreases_only=True,
        sort_by_unit_price_decrease=True,
    )
    shrinkflation_urunlerinin_tumu = list_market_date_comparison_findings(
        db,
        thresholds=thresholds,
        limit=None,
        market=market,
        old_date=previous_snapshot_date,
        new_date=latest_snapshot_date,
        shrinkflation_only=True,
        sort_by_shrinkflation_risk=True,
    )
    artan_urunler = artan_urunlerin_tumu[:effective_limit]
    azalan_urunler = azalan_urunlerin_tumu[:effective_limit]
    shrinkflation_riskli_urunler = shrinkflation_urunlerinin_tumu[:effective_limit]
    return MarketWeeklyNotificationPayload(
        market=market,
        latest_snapshot_date=latest_snapshot_date,
        previous_snapshot_date=previous_snapshot_date,
        current_snapshot_count=current_snapshot_count,
        rows=artan_urunler,
        artan_urunler=artan_urunler,
        azalan_urunler=azalan_urunler,
        shrinkflation_riskli_urunler=shrinkflation_riskli_urunler,
        artan_urun_sayisi=len(artan_urunlerin_tumu),
        azalan_urun_sayisi=len(azalan_urunlerin_tumu),
        shrinkflation_riskli_urun_sayisi=len(shrinkflation_urunlerinin_tumu),
    )


def build_product_lines(index: int, row: dict[str, object]) -> list[str]:
    product_name = str(row.get("urun_ad") or f"Urun {index}")
    lines = [f"{index}. {product_name}"]

    old_date = row.get("eski_tarih")
    new_date = row.get("yeni_tarih")
    if isinstance(old_date, datetime) or isinstance(new_date, datetime):
        old_date_text = old_date.date().isoformat() if isinstance(old_date, datetime) else "-"
        new_date_text = new_date.date().isoformat() if isinstance(new_date, datetime) else "-"
        lines.append(f"Tarih: {old_date_text} -> {new_date_text}")

    lines.append(
        "Fiyat: "
        f"{format_currency(row.get('eski_fiyat'))} -> {format_currency(row.get('yeni_fiyat'))} "
        f"({format_percent(row.get('fiyat_degisim_yuzdesi'))})"
    )

    old_measure = format_measure(row.get("eski_gramaj"), row.get("gramaj_birimi"))
    new_measure = format_measure(row.get("yeni_gramaj"), row.get("gramaj_birimi"))
    if old_measure != "-" or new_measure != "-":
        lines.append(
            "Gramaj: "
            f"{old_measure} -> {new_measure} "
            f"({format_percent(row.get('gramaj_degisim_yuzdesi'))})"
        )

    lines.append(
        "Birim fiyat: "
        f"{format_number(row.get('eski_birim_fiyat'), precision=4)} -> "
        f"{format_number(row.get('yeni_birim_fiyat'), precision=4)} "
        f"({format_percent(row.get('birim_fiyat_degisim_yuzdesi'))})"
    )
    return lines


def build_message_chunks(
    *,
    title: str,
    summary_lines: list[str],
    product_blocks: list[str],
) -> list[str]:
    first_chunk = "\n".join([title, *summary_lines]).strip()
    if not product_blocks:
        return [limit_message_size(first_chunk)]

    chunks: list[str] = []
    current_chunk = first_chunk
    continuation_index = 2
    for block in product_blocks:
        candidate = f"{current_chunk}\n\n{block}".strip()
        if len(candidate) <= MAX_TELEGRAM_MESSAGE_LENGTH:
            current_chunk = candidate
            continue

        chunks.append(limit_message_size(current_chunk))
        current_chunk = f"{title} (devam {continuation_index})\n\n{block}".strip()
        continuation_index += 1

    chunks.append(limit_message_size(current_chunk))
    return chunks


def build_report_link(
    *,
    market: str,
    urun_durumu: str,
    previous_snapshot_date: Optional[date],
    latest_snapshot_date: Optional[date],
) -> str:
    params = {
        "market": market,
        "urun_durumu": urun_durumu,
    }
    if previous_snapshot_date is not None and latest_snapshot_date is not None:
        params["tarih_baslangic"] = previous_snapshot_date.isoformat()
        params["tarih_bitis"] = latest_snapshot_date.isoformat()
    return f"{get_dashboard_base_url()}/?{urlencode(params)}"


def build_report_section(
    *,
    title: str,
    rows: list[dict[str, object]],
    empty_message: str,
    detail_link: str,
) -> str:
    product_blocks = [
        "\n".join(build_product_lines(index, row))
        for index, row in enumerate(rows, start=1)
    ]
    section_body = "\n\n".join(product_blocks) if product_blocks else empty_message
    return (
        f"{title}\n\n"
        f"{section_body}\n\n"
        f"Diğer ürünler için bu linkten ulaşabilirsiniz = {detail_link}"
    ).strip()


def build_weekly_price_increase_notification_messages(
    *,
    market: str,
    current_snapshot_count: int,
    previous_snapshot_date: Optional[date],
    latest_snapshot_date: Optional[date],
    rows: list[dict[str, object]],
    artan_urun_sayisi: Optional[int] = None,
    azalan_urun_sayisi: int = 0,
    shrinkflation_riskli_urun_sayisi: int = 0,
    azalan_urunler: Optional[list[dict[str, object]]] = None,
    shrinkflation_riskli_urunler: Optional[list[dict[str, object]]] = None,
) -> list[str]:
    market_name = market_label(market)
    artan_urunler = rows or []
    azalan_urunler = azalan_urunler or []
    shrinkflation_riskli_urunler = shrinkflation_riskli_urunler or []
    effective_artan_urun_sayisi = artan_urun_sayisi if artan_urun_sayisi is not None else len(artan_urunler)

    title = f"{market_name} haftalık birim fiyat raporu"
    summary_lines = [f"Güncel Çekilen Veri Sayısı: {current_snapshot_count}"]
    if previous_snapshot_date and latest_snapshot_date:
        summary_lines.append(
            f"Karşılaştırma Tarihi: {previous_snapshot_date.isoformat()} - {latest_snapshot_date.isoformat()}"
        )
    elif latest_snapshot_date:
        summary_lines.append(f"Son Veri Tarihi: {latest_snapshot_date.isoformat()}")

    summary_lines.extend(
        [
            f"Birim Fiyatı Artan Ürün Sayısı: {effective_artan_urun_sayisi}",
            f"Birim Fiyatı Azalan Ürün Sayısı: {azalan_urun_sayisi}",
            f"Shrinkflation Riskli Ürün Sayısı: {shrinkflation_riskli_urun_sayisi}",
        ]
    )

    if previous_snapshot_date is None or latest_snapshot_date is None:
        summary_lines.append("Haftalık karşılaştırma için yeterli veri yok.")
        return [limit_message_size("\n".join([title, *summary_lines]).strip())]

    section_blocks = [
        build_report_section(
            title="Birim Fiyatı Artan Ürünler İlk 5 Adet:",
            rows=artan_urunler,
            empty_message="Yeni zamlanmış ürünler bulunamadı.",
            detail_link=build_report_link(
                market=market,
                urun_durumu=URUN_DURUMU_ZAMLANMIS,
                previous_snapshot_date=previous_snapshot_date,
                latest_snapshot_date=latest_snapshot_date,
            ),
        ),
        build_report_section(
            title="Birim Fiyatı Azalan Ürünler İlk 5 Adet:",
            rows=azalan_urunler,
            empty_message="Yeni indirime girmiş ürünler bulunamadı.",
            detail_link=build_report_link(
                market=market,
                urun_durumu=URUN_DURUMU_INDIRIMDEKI,
                previous_snapshot_date=previous_snapshot_date,
                latest_snapshot_date=latest_snapshot_date,
            ),
        ),
        build_report_section(
            title="Shrinkflation Riskli Ürünler İlk 5 Adet:",
            rows=shrinkflation_riskli_urunler,
            empty_message="Yeni shrinkflation bulgulu ürünler bulunamadı.",
            detail_link=build_report_link(
                market=market,
                urun_durumu=URUN_DURUMU_SHRINKFLATION,
                previous_snapshot_date=previous_snapshot_date,
                latest_snapshot_date=latest_snapshot_date,
            ),
        ),
    ]
    return build_message_chunks(
        title=title,
        summary_lines=summary_lines,
        product_blocks=section_blocks,
    )


def infer_market_from_notification_center(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    normalized = fold_text(value)
    if "migros" in normalized:
        return "migros"
    if "sok" in normalized:
        return "sok"
    return None


def extract_chat_id_from_notification_center(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    stripped = value.strip()
    if not stripped:
        return None
    if stripped.startswith("@"):
        return stripped
    if stripped.lstrip("-").isdigit():
        return stripped

    parsed = urlparse(stripped)
    if parsed.scheme in {"http", "https"} and parsed.netloc.lower() in {
        "t.me",
        "www.t.me",
        "telegram.me",
        "www.telegram.me",
    }:
        username = parsed.path.strip("/").split("/", 1)[0]
        if username:
            return f"@{username}"
    return None


def resolve_market_bot_token(
    config: TelegramNotificationConfig,
    market: str,
) -> str:
    return config.market_bot_tokens.get(market, config.default_bot_token)


def load_active_telegram_rules(
    db: Session,
    *,
    markets: list[str],
    default_thresholds: DetectionThresholds,
    config_targets: dict[str, TelegramTarget],
) -> list[NotificationRule]:
    rows = db.execute(
        text(
            """
            select
                kural_id,
                yuzdesel_artis,
                esik_deger,
                bildirim_merkezi
            from bildirim_kurali
            where coalesce(kural_aktif_kontrolu, true) = true
            order by kural_id asc
            """
        )
    ).mappings().all()

    rules: list[NotificationRule] = []
    for row in rows:
        notification_center = str(row["bildirim_merkezi"] or "").strip()
        market = infer_market_from_notification_center(notification_center)
        if market is None or market not in markets:
            continue

        rule_chat_id = extract_chat_id_from_notification_center(notification_center)
        fallback_target = config_targets.get(market)
        if rule_chat_id:
            target = TelegramTarget(
                chat_id=rule_chat_id,
                thread_id=fallback_target.thread_id if fallback_target else None,
            )
        elif fallback_target is not None:
            target = fallback_target
        else:
            continue

        rules.append(
            NotificationRule(
                rule_id=int(row["kural_id"]),
                market=market,
                notification_center=notification_center,
                target=target,
                thresholds=DetectionThresholds(
                    min_size_drop_pct=(
                        float(row["esik_deger"])
                        if row["esik_deger"] is not None
                        else default_thresholds.min_size_drop_pct
                    ),
                    min_unit_price_increase_pct=(
                        float(row["yuzdesel_artis"])
                        if row["yuzdesel_artis"] is not None
                        else default_thresholds.min_unit_price_increase_pct
                    ),
                    stable_price_floor_pct=default_thresholds.stable_price_floor_pct,
                ),
            )
        )

    return rules


def notification_history_exists(
    db: Session,
    *,
    rule_id: Optional[int],
    message_text: str,
) -> bool:
    row = db.execute(
        text(
            """
            select 1
            from gecmis_bildirimler
            where tetiklenen_kural is not distinct from :rule_id
              and basari_testi = true
              and mesaj_icerigi = :message_text
            limit 1
            """
        ),
        {
            "rule_id": rule_id,
            "message_text": message_text,
        },
    ).first()
    return row is not None


def record_notification_history(
    db: Session,
    *,
    rule_id: Optional[int],
    success: bool,
    message_text: str,
) -> None:
    db.execute(
        text(
            """
            insert into gecmis_bildirimler (
                tetiklenen_kural,
                bildirim_tarihi,
                basari_testi,
                mesaj_icerigi
            )
            values (
                :rule_id,
                now(),
                :success,
                :message_text
            )
            """
        ),
        {
            "rule_id": rule_id,
            "success": success,
            "message_text": message_text,
        },
    )
    db.commit()


def upsert_notification_rule(
    db: Session,
    *,
    notification_center: str,
    min_unit_price_increase_pct: float,
    min_size_drop_pct: float,
    is_active: bool = True,
) -> int:
    existing_row = db.execute(
        text(
            """
            select kural_id
            from bildirim_kurali
            where lower(coalesce(bildirim_merkezi, '')) = lower(:notification_center)
            order by kural_id asc
            limit 1
            """
        ),
        {
            "notification_center": notification_center,
        },
    ).mappings().first()

    if existing_row is not None:
        rule_id = int(existing_row["kural_id"])
        db.execute(
            text(
                """
                update bildirim_kurali
                set
                    yuzdesel_artis = :min_unit_price_increase_pct,
                    esik_deger = :min_size_drop_pct,
                    kural_aktif_kontrolu = :is_active
                where kural_id = :rule_id
                """
            ),
            {
                "rule_id": rule_id,
                "min_unit_price_increase_pct": min_unit_price_increase_pct,
                "min_size_drop_pct": min_size_drop_pct,
                "is_active": is_active,
            },
        )
        db.commit()
        return rule_id

    created_row = db.execute(
        text(
            """
            insert into bildirim_kurali (
                urun_id,
                kullanici_id,
                yuzdesel_artis,
                esik_deger,
                bildirim_merkezi,
                kural_aktif_kontrolu,
                olusturulma_tarihi
            )
            values (
                null,
                null,
                :min_unit_price_increase_pct,
                :min_size_drop_pct,
                :notification_center,
                :is_active,
                now()
            )
            returning kural_id
            """
        ),
        {
            "notification_center": notification_center,
            "min_unit_price_increase_pct": min_unit_price_increase_pct,
            "min_size_drop_pct": min_size_drop_pct,
            "is_active": is_active,
        },
    ).mappings().one()
    db.commit()
    return int(created_row["kural_id"])


def send_telegram_message(
    config: TelegramNotificationConfig,
    bot_token: str,
    target: TelegramTarget,
    text: str,
) -> dict[str, object]:
    url = f"{config.api_base_url}/bot{bot_token}/sendMessage"
    payload: dict[str, object] = {
        "chat_id": target.chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if target.thread_id is not None:
        payload["message_thread_id"] = target.thread_id

    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=config.timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise TelegramDeliveryError(
            f"Telegram API HTTP {exc.code} hatasi: {error_body}"
        ) from exc
    except error.URLError as exc:
        raise TelegramDeliveryError(f"Telegram API baglantisi kurulamadi: {exc.reason}") from exc
    except OSError as exc:
        raise TelegramDeliveryError(f"Telegram mesaji gonderilemedi: {exc}") from exc

    if not response_payload.get("ok"):
        raise TelegramDeliveryError(
            f"Telegram API hatasi: {response_payload.get('description') or 'bilinmeyen hata'}"
        )
    return response_payload


def send_telegram_messages(
    config: TelegramNotificationConfig,
    bot_token: str,
    target: TelegramTarget,
    messages: list[str],
) -> None:
    for message in messages:
        send_telegram_message(config, bot_token, target, message)


def dispatch_market_notification(
    db: Session,
    *,
    market: str,
    config: TelegramNotificationConfig,
    thresholds: Optional[DetectionThresholds] = None,
    target: Optional[TelegramTarget] = None,
    rule_id: Optional[int] = None,
    notification_center: Optional[str] = None,
    limit: Optional[int] = None,
    date_start: Optional[datetime] = None,
    date_end: Optional[datetime] = None,
    dry_run: bool = False,
    send_when_empty: bool = False,
) -> TelegramDispatchResult:
    effective_target = target or config.targets.get(market)
    effective_bot_token = resolve_market_bot_token(config, market)
    payload = load_market_weekly_notification_payload(
        db,
        market=market,
        thresholds=thresholds,
        limit=limit,
        date_start=date_start,
        date_end=date_end,
    )
    message_chunks = build_weekly_price_increase_notification_messages(
        market=market,
        current_snapshot_count=payload.current_snapshot_count,
        previous_snapshot_date=payload.previous_snapshot_date,
        latest_snapshot_date=payload.latest_snapshot_date,
        rows=payload.rows,
        artan_urun_sayisi=payload.artan_urun_sayisi,
        azalan_urun_sayisi=payload.azalan_urun_sayisi,
        shrinkflation_riskli_urun_sayisi=payload.shrinkflation_riskli_urun_sayisi,
        azalan_urunler=payload.azalan_urunler,
        shrinkflation_riskli_urunler=payload.shrinkflation_riskli_urunler,
    )
    combined_message = "\n\n===MESAJ_PARCA===\n\n".join(message_chunks)
    item_count = payload.artan_urun_sayisi or len(payload.rows)

    if effective_target is None:
        return TelegramDispatchResult(
            market=market,
            sent=False,
            skipped=False,
            target_configured=False,
            item_count=item_count,
            current_snapshot_count=payload.current_snapshot_count,
            latest_snapshot_date=payload.latest_snapshot_date,
            previous_snapshot_date=payload.previous_snapshot_date,
            reason=(
                f"Telegram hedefi tanimli degil. "
                f"TELEGRAM_{market.upper()}_CHAT_ID veya bildirim_kurali.bildirim_merkezi gerekli."
            ),
            preview=preview_text(combined_message),
            rule_id=rule_id,
            notification_center=notification_center,
            artan_urun_sayisi=payload.artan_urun_sayisi,
            azalan_urun_sayisi=payload.azalan_urun_sayisi,
            shrinkflation_riskli_urun_sayisi=payload.shrinkflation_riskli_urun_sayisi,
        )

    if not effective_bot_token and not dry_run:
        return TelegramDispatchResult(
            market=market,
            sent=False,
            skipped=False,
            target_configured=True,
            item_count=item_count,
            current_snapshot_count=payload.current_snapshot_count,
            latest_snapshot_date=payload.latest_snapshot_date,
            previous_snapshot_date=payload.previous_snapshot_date,
            reason=(
                f"{market.upper()} icin bot token tanimli degil. "
                f"TELEGRAM_{market.upper()}_BOT_TOKEN veya TELEGRAM_BOT_TOKEN gerekli."
            ),
            preview=preview_text(combined_message),
            rule_id=rule_id,
            notification_center=notification_center,
            artan_urun_sayisi=payload.artan_urun_sayisi,
            azalan_urun_sayisi=payload.azalan_urun_sayisi,
            shrinkflation_riskli_urun_sayisi=payload.shrinkflation_riskli_urun_sayisi,
        )

    if (payload.previous_snapshot_date is None or payload.latest_snapshot_date is None) and not send_when_empty:
        return TelegramDispatchResult(
            market=market,
            sent=False,
            skipped=True,
            target_configured=True,
            item_count=item_count,
            current_snapshot_count=payload.current_snapshot_count,
            latest_snapshot_date=payload.latest_snapshot_date,
            previous_snapshot_date=payload.previous_snapshot_date,
            reason="Haftalik karsilastirma icin yeterli veri yok.",
            preview=preview_text(combined_message),
            rule_id=rule_id,
            notification_center=notification_center,
            artan_urun_sayisi=payload.artan_urun_sayisi,
            azalan_urun_sayisi=payload.azalan_urun_sayisi,
            shrinkflation_riskli_urun_sayisi=payload.shrinkflation_riskli_urun_sayisi,
        )

    if dry_run:
        return TelegramDispatchResult(
            market=market,
            sent=False,
            skipped=True,
            target_configured=True,
            item_count=item_count,
            current_snapshot_count=payload.current_snapshot_count,
            latest_snapshot_date=payload.latest_snapshot_date,
            previous_snapshot_date=payload.previous_snapshot_date,
            reason="dry_run",
            preview=preview_text(combined_message),
            rule_id=rule_id,
            notification_center=notification_center,
            artan_urun_sayisi=payload.artan_urun_sayisi,
            azalan_urun_sayisi=payload.azalan_urun_sayisi,
            shrinkflation_riskli_urun_sayisi=payload.shrinkflation_riskli_urun_sayisi,
        )

    if notification_history_exists(db, rule_id=rule_id, message_text=combined_message):
        return TelegramDispatchResult(
            market=market,
            sent=False,
            skipped=True,
            target_configured=True,
            item_count=item_count,
            current_snapshot_count=payload.current_snapshot_count,
            latest_snapshot_date=payload.latest_snapshot_date,
            previous_snapshot_date=payload.previous_snapshot_date,
            reason="Bu bildirim daha once gonderilmis.",
            preview=preview_text(combined_message),
            rule_id=rule_id,
            notification_center=notification_center,
            artan_urun_sayisi=payload.artan_urun_sayisi,
            azalan_urun_sayisi=payload.azalan_urun_sayisi,
            shrinkflation_riskli_urun_sayisi=payload.shrinkflation_riskli_urun_sayisi,
        )

    try:
        send_telegram_messages(config, effective_bot_token, effective_target, message_chunks)
    except TelegramDeliveryError as exc:
        record_notification_history(
            db,
            rule_id=rule_id,
            success=False,
            message_text=f"{combined_message}\n\nGONDERIM_HATASI: {exc}",
        )
        return TelegramDispatchResult(
            market=market,
            sent=False,
            skipped=False,
            target_configured=True,
            item_count=item_count,
            current_snapshot_count=payload.current_snapshot_count,
            latest_snapshot_date=payload.latest_snapshot_date,
            previous_snapshot_date=payload.previous_snapshot_date,
            reason=str(exc),
            preview=preview_text(combined_message),
            rule_id=rule_id,
            notification_center=notification_center,
            artan_urun_sayisi=payload.artan_urun_sayisi,
            azalan_urun_sayisi=payload.azalan_urun_sayisi,
            shrinkflation_riskli_urun_sayisi=payload.shrinkflation_riskli_urun_sayisi,
        )

    record_notification_history(
        db,
        rule_id=rule_id,
        success=True,
        message_text=combined_message,
    )
    return TelegramDispatchResult(
        market=market,
        sent=True,
        skipped=False,
        target_configured=True,
        item_count=item_count,
        current_snapshot_count=payload.current_snapshot_count,
        latest_snapshot_date=payload.latest_snapshot_date,
        previous_snapshot_date=payload.previous_snapshot_date,
        reason=None,
        preview=preview_text(combined_message),
        rule_id=rule_id,
        notification_center=notification_center,
        artan_urun_sayisi=payload.artan_urun_sayisi,
        azalan_urun_sayisi=payload.azalan_urun_sayisi,
        shrinkflation_riskli_urun_sayisi=payload.shrinkflation_riskli_urun_sayisi,
    )


def send_configured_shrinkflation_notifications(
    db: Session,
    *,
    markets: list[str],
    thresholds: Optional[DetectionThresholds] = None,
    limit: Optional[int] = None,
    date_start: Optional[datetime] = None,
    date_end: Optional[datetime] = None,
    dry_run: bool = False,
    send_when_empty: bool = False,
    config: Optional[TelegramNotificationConfig] = None,
) -> list[TelegramDispatchResult]:
    effective_config = config or load_telegram_notification_config(require_bot_token=not dry_run)
    effective_thresholds = thresholds or DetectionThresholds()
    active_rules = load_active_telegram_rules(
        db,
        markets=markets,
        default_thresholds=effective_thresholds,
        config_targets=effective_config.targets,
    )
    if active_rules:
        return [
            dispatch_market_notification(
                db,
                market=rule.market,
                config=effective_config,
                thresholds=rule.thresholds,
                target=rule.target,
                rule_id=rule.rule_id,
                notification_center=rule.notification_center,
                limit=limit,
                date_start=date_start,
                date_end=date_end,
                dry_run=dry_run,
                send_when_empty=send_when_empty,
            )
            for rule in active_rules
        ]

    return [
        dispatch_market_notification(
            db,
            market=market,
            config=effective_config,
            thresholds=effective_thresholds,
            limit=limit,
            date_start=date_start,
            date_end=date_end,
            dry_run=dry_run,
            send_when_empty=send_when_empty,
        )
        for market in markets
    ]
