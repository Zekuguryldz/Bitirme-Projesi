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


@dataclass
class MarketWatcher:
    market: str
    last_seen_state: "MarketSnapshotState"
    change_detected: bool = False
    last_change_at: float = 0.0


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
        description="Market veri aktarimlarini surekli izle, veri sabitlenince Telegram bildirimi gonder."
    )
    parser.add_argument("--market", choices=["migros", "sok"], action="append")
    parser.add_argument("--poll-interval", type=int, default=30)
    parser.add_argument("--stable-seconds", type=int, default=120)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--send-when-empty", action="store_true")
    parser.add_argument(
        "--notify-on-start",
        action="store_true",
        help="Daemon basladiginda mevcut son snapshot icin de bildirim gondermeyi dener.",
    )
    args = parser.parse_args()

    markets = args.market or ["sok", "migros"]
    watchers: list[MarketWatcher] = []
    now = time.monotonic()
    for market in markets:
        baseline_state = read_market_state(market)
        watchers.append(
            MarketWatcher(
                market=market,
                last_seen_state=baseline_state,
                change_detected=False,
                last_change_at=now,
            )
        )
        print(f"[{market.upper()}] baseline {format_state(baseline_state)}")
        if args.notify_on_start:
            print(f"[{market.upper()}] baslangicta mevcut snapshot icin bildirim kontrol ediliyor.")
            dispatch_notification(
                market,
                limit=args.limit,
                send_when_empty=args.send_when_empty,
            )

    while True:
        for watcher in watchers:
            current_state = read_market_state(watcher.market)
            if current_state != watcher.last_seen_state:
                watcher.change_detected = True
                watcher.last_change_at = time.monotonic()
                watcher.last_seen_state = current_state
                print(f"[{watcher.market.upper()}] update {format_state(current_state)}")
                continue

            if watcher.change_detected and (time.monotonic() - watcher.last_change_at) >= args.stable_seconds:
                print(
                    f"[{watcher.market.upper()}] veri {args.stable_seconds} sn boyunca degismedi; bildirim gonderiliyor."
                )
                dispatch_notification(
                    watcher.market,
                    limit=args.limit,
                    send_when_empty=args.send_when_empty,
                )
                watcher.change_detected = False
                watcher.last_seen_state = read_market_state(watcher.market)
                watcher.last_change_at = time.monotonic()
                print(f"[{watcher.market.upper()}] yeni baseline {format_state(watcher.last_seen_state)}")

        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
