import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal
from app.routers.dashboard import build_thresholds, parse_dashboard_datetime_end, parse_dashboard_datetime_start
from app.services.telegram_notifications import (
    TelegramConfigurationError,
    send_configured_shrinkflation_notifications,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Market bazli Telegram haftalik birim fiyat bildirimi gonder.")
    parser.add_argument("--market", choices=["migros", "sok"], action="append")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--send-when-empty", action="store_true")
    parser.add_argument("--tarih-baslangic", default=None)
    parser.add_argument("--tarih-bitis", default=None)
    parser.add_argument("--min-size-drop-pct", type=float, default=3.0)
    parser.add_argument("--min-unit-price-increase-pct", type=float, default=3.0)
    parser.add_argument("--stable-price-floor-pct", type=float, default=0.0)
    args = parser.parse_args()

    markets = args.market or ["migros", "sok"]
    date_start = parse_dashboard_datetime_start(args.tarih_baslangic) if args.tarih_baslangic else None
    date_end = parse_dashboard_datetime_end(args.tarih_bitis) if args.tarih_bitis else None
    thresholds = build_thresholds(
        min_size_drop_pct=args.min_size_drop_pct,
        min_unit_price_increase_pct=args.min_unit_price_increase_pct,
        stable_price_floor_pct=args.stable_price_floor_pct,
    )

    db = SessionLocal()
    try:
        results = send_configured_shrinkflation_notifications(
            db,
            markets=markets,
            thresholds=thresholds,
            limit=args.limit,
            date_start=date_start,
            date_end=date_end,
            dry_run=args.dry_run,
            send_when_empty=args.send_when_empty,
        )
    except TelegramConfigurationError as exc:
        print(f"Konfigurasyon hatasi: {exc}")
        raise SystemExit(1) from exc
    finally:
        db.close()

    has_failure = False
    for result in results:
        if result.sent:
            status = "sent"
        elif result.skipped:
            status = "skipped"
        else:
            status = "failed"
            has_failure = True

        print(
            f"[{result.market.upper()}] {status} | "
            f"guncel veri: {result.current_snapshot_count} | "
            f"artan: {result.artan_urun_sayisi} | "
            f"azalan: {result.azalan_urun_sayisi} | "
            f"shrinkflation: {result.shrinkflation_riskli_urun_sayisi} | "
            f"karsilastirma: {result.previous_snapshot_date or '-'} -> {result.latest_snapshot_date or '-'}"
        )
        if result.rule_id is not None:
            print(f"kural_id: {result.rule_id}")
        if result.notification_center:
            print(f"bildirim_merkezi: {result.notification_center}")
        if result.reason:
            print(f"neden: {result.reason}")

    if has_failure:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
