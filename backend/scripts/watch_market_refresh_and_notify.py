import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal
from app.services.telegram_notifications import (
    TelegramDispatchResult,
    get_market_comparison_dates,
    get_market_snapshot_count,
    send_configured_shrinkflation_notifications,
)


@dataclass(frozen=True)
class MarketSnapshotState:
    latest_snapshot_date: Optional[object]
    snapshot_count: int


def read_market_state(market: str) -> MarketSnapshotState:
    db = SessionLocal()
    try:
        _previous_date, latest_date = get_market_comparison_dates(db, market=market)
        snapshot_count = get_market_snapshot_count(
            db,
            market=market,
            snapshot_date=latest_date,
        )
        return MarketSnapshotState(
            latest_snapshot_date=latest_date,
            snapshot_count=snapshot_count,
        )
    finally:
        db.close()


def format_state(state: MarketSnapshotState) -> str:
    return f"latest_date={state.latest_snapshot_date or '-'} count={state.snapshot_count}"


def print_dispatch_result(result: TelegramDispatchResult) -> None:
    status = "sent" if result.sent else "skipped" if result.skipped else "failed"
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


def dispatch_notification(
    market: str,
    *,
    limit: Optional[int],
    send_when_empty: bool,
) -> TelegramDispatchResult:
    db = SessionLocal()
    try:
        results = send_configured_shrinkflation_notifications(
            db,
            markets=[market],
            limit=limit,
            dry_run=False,
            send_when_empty=send_when_empty,
        )
    finally:
        db.close()

    result = results[0]
    print_dispatch_result(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Market verisi yenilenince sabitlenmesini bekleyip Telegram bildirimi gonder."
    )
    parser.add_argument("--market", choices=["migros", "sok"], required=True)
    parser.add_argument("--poll-interval", type=int, default=30)
    parser.add_argument("--stable-seconds", type=int, default=120)
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--send-when-empty", action="store_true")
    parser.add_argument(
        "--notify-on-start",
        action="store_true",
        help="Script basladiginda mevcut son snapshot icin de bildirim gondermeyi dener.",
    )
    args = parser.parse_args()

    baseline_state = read_market_state(args.market)
    last_seen_state = baseline_state
    print(f"[{args.market.upper()}] baseline {format_state(baseline_state)}")

    if args.notify_on_start:
        print(f"[{args.market.upper()}] baslangicta mevcut snapshot icin bildirim kontrol ediliyor.")
        initial_result = dispatch_notification(
            args.market,
            limit=args.limit,
            send_when_empty=args.send_when_empty,
        )
        if initial_result.sent:
            raise SystemExit(0)
        if not initial_result.skipped:
            raise SystemExit(1)

    change_detected = False
    last_change_at = time.monotonic()
    deadline = time.monotonic() + args.timeout_seconds

    while time.monotonic() < deadline:
        current_state = read_market_state(args.market)
        if current_state != last_seen_state:
            change_detected = True
            last_change_at = time.monotonic()
            last_seen_state = current_state
            print(f"[{args.market.upper()}] update {format_state(current_state)}")
        elif change_detected and (time.monotonic() - last_change_at) >= args.stable_seconds:
            print(
                f"[{args.market.upper()}] veri {args.stable_seconds} sn boyunca degismedi; bildirim gonderiliyor."
            )
            result = dispatch_notification(
                args.market,
                limit=args.limit,
                send_when_empty=args.send_when_empty,
            )
            raise SystemExit(0 if result.sent or result.skipped else 1)

        time.sleep(args.poll_interval)

    print(
        f"[{args.market.upper()}] timeout: {args.timeout_seconds} sn icinde yeni veri degisimi gorulmedi."
    )
    raise SystemExit(2)


if __name__ == "__main__":
    main()
