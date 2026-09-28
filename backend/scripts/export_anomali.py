import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import psycopg2
from psycopg2.extras import execute_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal
from app.services.shrinkflation import DetectionThresholds, list_shrinkflation_risk_findings


EXPORT_DIR = PROJECT_ROOT / "exports"
CSV_COLUMNS = [
    "urun_id",
    "urun_ad",
    "market_adi",
    "urun_kategori",
    "eski_fiyat",
    "yeni_fiyat",
    "eski_gramaj",
    "yeni_gramaj",
    "gramaj_birimi",
    "eski_birim_fiyat",
    "yeni_birim_fiyat",
    "birim_fiyat_degisim_yuzdesi",
    "gramaj_degisim_yuzdesi",
    "eski_birim_gramaj",
    "yeni_birim_gramaj",
    "eski_adet_sayisi",
    "yeni_adet_sayisi",
    "adet_degisim_yuzdesi",
    "birim_icerik_degisim_yuzdesi",
    "fiyat_degisim_yuzdesi",
    "shrinkflation_orani_yuzdesi",
    "severity",
    "direction",
    "reason",
    "is_shrinkflation",
    "eski_tarih",
    "yeni_tarih",
    "kazima_tarihi",
]


def serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def fetch_rows(market: Optional[str] = None) -> list[dict[str, Any]]:
    db = SessionLocal()
    try:
        rows = list_shrinkflation_risk_findings(
            db,
            thresholds=DetectionThresholds(
                min_size_drop_pct=3.0,
                min_unit_price_increase_pct=3.0,
                stable_price_floor_pct=0.0,
            ),
            limit=None,
            market=market,
        )
    finally:
        db.close()

    return [{column: serialize_value(row.get(column)) for column in CSV_COLUMNS} for row in rows]


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def load_into_supabase(rows: list[dict[str, Any]]) -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL tanimli degil.")

    create_table_sql = """
    create table if not exists public.anomali (
        anomali_id bigserial primary key,
        urun_id bigint not null,
        urun_ad text not null,
        market_adi text,
        urun_kategori text,
        eski_fiyat numeric,
        yeni_fiyat numeric,
        eski_gramaj numeric,
        yeni_gramaj numeric,
        gramaj_birimi text,
        eski_birim_fiyat numeric,
        yeni_birim_fiyat numeric,
        birim_fiyat_degisim_yuzdesi numeric,
        gramaj_degisim_yuzdesi numeric,
        eski_birim_gramaj numeric,
        yeni_birim_gramaj numeric,
        eski_adet_sayisi numeric,
        yeni_adet_sayisi numeric,
        adet_degisim_yuzdesi numeric,
        birim_icerik_degisim_yuzdesi numeric,
        fiyat_degisim_yuzdesi numeric,
        shrinkflation_orani_yuzdesi numeric,
        severity text,
        direction text,
        reason text,
        is_shrinkflation boolean not null default false,
        eski_tarih timestamptz,
        yeni_tarih timestamptz,
        kazima_tarihi timestamptz,
        created_at timestamptz not null default now(),
        unique (urun_id, eski_tarih, yeni_tarih)
    );
    """

    insert_columns = ", ".join(CSV_COLUMNS)
    update_columns = ", ".join(
        f"{column} = excluded.{column}"
        for column in CSV_COLUMNS
        if column not in {"urun_id", "eski_tarih", "yeni_tarih"}
    )
    insert_sql = f"""
    insert into public.anomali ({insert_columns})
    values %s
    on conflict (urun_id, eski_tarih, yeni_tarih) do update
    set {update_columns};
    """

    values = [tuple(row[column] for column in CSV_COLUMNS) for row in rows]

    with psycopg2.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(create_table_sql)
            if values:
                execute_values(cursor, insert_sql, values, page_size=500)
        connection.commit()

    return len(values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Shrinkflation riskli son iki kayit anomalilerini CSV ve Supabase'e aktar.")
    parser.add_argument("--market", choices=["sok", "migros"], default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--load", action="store_true")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_name = f"anomali_{args.market or 'tum_marketler'}_{timestamp}.csv"
    output_path = Path(args.output) if args.output else EXPORT_DIR / default_name

    rows = fetch_rows(args.market)
    write_csv(rows, output_path)
    print(f"CSV olusturuldu: {output_path}")
    print(f"Kayit sayisi: {len(rows)}")

    if args.load:
        inserted = load_into_supabase(rows)
        print(f"Supabase anomali tablosuna aktarilan kayit: {inserted}")


if __name__ == "__main__":
    main()
