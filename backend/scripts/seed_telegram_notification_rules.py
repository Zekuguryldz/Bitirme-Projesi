import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal
from app.services.telegram_notifications import upsert_notification_rule


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram bildirim kurallarini bildirim_kurali tablosuna kaydet.")
    parser.add_argument(
        "--migros-center",
        default="https://t.me/bitirmeshrinkflationmigros",
    )
    parser.add_argument(
        "--sok-center",
        default="https://t.me/bitirmeshrinkflationsok",
    )
    parser.add_argument("--min-size-drop-pct", type=float, default=3.0)
    parser.add_argument("--min-unit-price-increase-pct", type=float, default=3.0)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        migros_rule_id = upsert_notification_rule(
            db,
            notification_center=args.migros_center,
            min_unit_price_increase_pct=args.min_unit_price_increase_pct,
            min_size_drop_pct=args.min_size_drop_pct,
        )
        sok_rule_id = upsert_notification_rule(
            db,
            notification_center=args.sok_center,
            min_unit_price_increase_pct=args.min_unit_price_increase_pct,
            min_size_drop_pct=args.min_size_drop_pct,
        )
    finally:
        db.close()

    print(f"Migros kural kaydi hazir: {migros_rule_id}")
    print(f"SOK kural kaydi hazir: {sok_rule_id}")


if __name__ == "__main__":
    main()
