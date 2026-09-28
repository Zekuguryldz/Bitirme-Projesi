from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.dashboard import (
    build_thresholds,
    parse_dashboard_datetime_end,
    parse_dashboard_datetime_start,
    parse_dashboard_market_value,
)
from app.schemas import TelegramNotificationDispatchResponse
from app.services.telegram_notifications import (
    TelegramConfigurationError,
    send_configured_shrinkflation_notifications,
)


router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.post(
    "/telegram/shrinkflation",
    response_model=TelegramNotificationDispatchResponse,
    summary="Telegram'a market bazli haftalik birim fiyat bildirimi gonder",
)
def send_telegram_shrinkflation_notifications(
    market: Annotated[
        Optional[str],
        Query(description="Tek bir market secilirse sadece o markete bildirim gider."),
    ] = None,
    limit: Annotated[Optional[int], Query(ge=1, le=500)] = None,
    dry_run: bool = False,
    send_when_empty: bool = False,
    tarih_baslangic: Annotated[
        Optional[str],
        Query(description="Bildirim icerigini bu tarihten baslayan kayitlarla sinirlar."),
    ] = None,
    tarih_bitis: Annotated[
        Optional[str],
        Query(description="Bildirim icerigini bu tarihten onceki kayitlarla sinirlar."),
    ] = None,
    min_size_drop_pct: Annotated[float, Query(ge=0)] = 3.0,
    min_unit_price_increase_pct: Annotated[float, Query(ge=0)] = 3.0,
    stable_price_floor_pct: float = 0.0,
    db: Session = Depends(get_db),
):
    market_value = parse_dashboard_market_value(market)
    markets = [market_value] if market_value else ["migros", "sok"]
    date_start = parse_dashboard_datetime_start(tarih_baslangic) if tarih_baslangic else None
    date_end = parse_dashboard_datetime_end(tarih_bitis) if tarih_bitis else None
    thresholds = build_thresholds(
        min_size_drop_pct=min_size_drop_pct,
        min_unit_price_increase_pct=min_unit_price_increase_pct,
        stable_price_floor_pct=stable_price_floor_pct,
    )

    try:
        results = send_configured_shrinkflation_notifications(
            db,
            markets=markets,
            thresholds=thresholds,
            limit=limit,
            date_start=date_start,
            date_end=date_end,
            dry_run=dry_run,
            send_when_empty=send_when_empty,
        )
    except TelegramConfigurationError as exc:
        return {
            "total": len(markets),
            "sent_count": 0,
            "failed_count": len(markets),
            "skipped_count": 0,
            "items": [
                {
                    "market": current_market,
                    "sent": False,
                    "skipped": False,
                    "target_configured": False,
                    "item_count": 0,
                    "current_snapshot_count": 0,
                    "artan_urun_sayisi": 0,
                    "azalan_urun_sayisi": 0,
                    "shrinkflation_riskli_urun_sayisi": 0,
                    "latest_snapshot_date": None,
                    "previous_snapshot_date": None,
                    "reason": str(exc),
                    "preview": "",
                    "rule_id": None,
                    "notification_center": None,
                }
                for current_market in markets
            ],
        }

    return {
        "total": len(results),
        "sent_count": sum(1 for result in results if result.sent),
        "failed_count": sum(1 for result in results if not result.sent and not result.skipped),
        "skipped_count": sum(1 for result in results if result.skipped),
        "items": [
            {
                "market": result.market,
                "sent": result.sent,
                "skipped": result.skipped,
                "target_configured": result.target_configured,
                "item_count": result.item_count,
                "current_snapshot_count": result.current_snapshot_count,
                "artan_urun_sayisi": result.artan_urun_sayisi,
                "azalan_urun_sayisi": result.azalan_urun_sayisi,
                "shrinkflation_riskli_urun_sayisi": result.shrinkflation_riskli_urun_sayisi,
                "latest_snapshot_date": result.latest_snapshot_date,
                "previous_snapshot_date": result.previous_snapshot_date,
                "reason": result.reason,
                "preview": result.preview,
                "rule_id": result.rule_id,
                "notification_center": result.notification_center,
            }
            for result in results
        ],
    }
