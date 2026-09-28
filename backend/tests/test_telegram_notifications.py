import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch


os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.services.shrinkflation import DetectionThresholds
from app.services.telegram_notifications import (
    MarketWeeklyNotificationPayload,
    NotificationRule,
    TelegramNotificationConfig,
    TelegramTarget,
    build_weekly_price_increase_notification_messages,
    dispatch_market_notification,
    extract_chat_id_from_notification_center,
    get_market_snapshot_count,
    infer_market_from_notification_center,
    load_telegram_notification_config,
    send_configured_shrinkflation_notifications,
)


def sample_row() -> dict[str, object]:
    return {
        "urun_id": 1,
        "urun_ad": "Migros Sut",
        "market_adi": "Migros",
        "urun_kategori": "Sut Kahvaltilik",
        "eski_fiyat": 49.95,
        "yeni_fiyat": 49.95,
        "eski_gramaj": 1000.0,
        "yeni_gramaj": 900.0,
        "gramaj_birimi": "ml",
        "eski_birim_fiyat": 0.05,
        "yeni_birim_fiyat": 0.0555,
        "birim_fiyat_degisim_yuzdesi": 11.11,
        "gramaj_degisim_yuzdesi": -10.0,
        "eski_birim_gramaj": 1000.0,
        "yeni_birim_gramaj": 900.0,
        "eski_adet_sayisi": None,
        "yeni_adet_sayisi": None,
        "adet_degisim_yuzdesi": None,
        "birim_icerik_degisim_yuzdesi": -10.0,
        "fiyat_degisim_yuzdesi": 0.0,
        "shrinkflation_orani_yuzdesi": 11.11,
        "severity": "medium",
        "direction": "decrease",
        "reason": "unit_size_reduced",
        "is_shrinkflation": True,
        "eski_tarih": datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc),
        "yeni_tarih": datetime(2026, 4, 28, 10, 0, tzinfo=timezone.utc),
        "kazima_tarihi": datetime(2026, 4, 28, 10, 0, tzinfo=timezone.utc),
    }


class TelegramNotificationsTests(unittest.TestCase):
    class _FakeMappingsResult:
        def __init__(self, row):
            self._row = row

        def one(self):
            return self._row

    class _FakeExecuteResult:
        def __init__(self, row):
            self._row = row

        def mappings(self):
            return TelegramNotificationsTests._FakeMappingsResult(self._row)

    class _FakeExecuteSession:
        def __init__(self, row):
            self._row = row
            self.statement = None
            self.params = None

        def execute(self, statement, params=None):
            self.statement = statement
            self.params = params
            return TelegramNotificationsTests._FakeExecuteResult(self._row)

    def test_build_notification_message_includes_market_header(self) -> None:
        messages = build_weekly_price_increase_notification_messages(
            market="migros",
            current_snapshot_count=1483,
            previous_snapshot_date=date(2026, 4, 21),
            latest_snapshot_date=date(2026, 4, 28),
            rows=[sample_row()],
        )
        message = messages[0]

        self.assertIn("Migros haftalık birim fiyat raporu", message)
        self.assertIn("Güncel Çekilen Veri Sayısı: 1483", message)
        self.assertIn("Karşılaştırma Tarihi: 2026-04-21 - 2026-04-28", message)
        self.assertIn("Birim Fiyatı Artan Ürün Sayısı: 1", message)
        self.assertIn("Birim Fiyatı Azalan Ürünler İlk 5 Adet:", message)
        self.assertIn("Yeni indirime girmiş ürünler bulunamadı.", message)
        self.assertIn("http://127.0.0.1:8000/?market=migros&urun_durumu=zamlanmis_urunler", message)
        self.assertIn("Migros Sut", message)
        self.assertIn("Birim fiyat: 0.05 -> 0.0555 (+11.11%)", message)

    def test_get_market_snapshot_count_uses_canonical_product_identity(self) -> None:
        fake_db = self._FakeExecuteSession({"snapshot_count": 1483})

        result = get_market_snapshot_count(
            fake_db,
            market="sok",
            snapshot_date=date(2026, 5, 2),
        )

        self.assertEqual(result, 1483)
        self.assertIsNotNone(fake_db.statement)
        self.assertIn("count(distinct coalesce(", str(fake_db.statement))
        self.assertIn("regexp_replace", str(fake_db.statement))
        self.assertEqual(fake_db.params["market_pattern"], "sok%")

    def test_load_config_reads_separate_market_targets(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "fallback-token",
                "TELEGRAM_MIGROS_BOT_TOKEN": "migros-token",
                "TELEGRAM_MIGROS_CHAT_ID": "-1001",
                "TELEGRAM_MIGROS_THREAD_ID": "11",
                "TELEGRAM_SOK_BOT_TOKEN": "sok-token",
                "TELEGRAM_SOK_CHAT_ID": "-1002",
            },
            clear=False,
        ):
            config = load_telegram_notification_config()

        self.assertEqual(config.default_bot_token, "fallback-token")
        self.assertEqual(config.market_bot_tokens["migros"], "migros-token")
        self.assertEqual(config.market_bot_tokens["sok"], "sok-token")
        self.assertEqual(config.targets["migros"].chat_id, "-1001")
        self.assertEqual(config.targets["migros"].thread_id, 11)
        self.assertEqual(config.targets["sok"].chat_id, "-1002")

    def test_infer_market_from_notification_center_supports_channel_links(self) -> None:
        self.assertEqual(
            infer_market_from_notification_center("https://t.me/bitirmeshrinkflationmigros"),
            "migros",
        )
        self.assertEqual(
            infer_market_from_notification_center("@bitirmeshrinkflationsok"),
            "sok",
        )

    def test_extract_chat_id_from_notification_center_supports_t_me_urls(self) -> None:
        self.assertEqual(
            extract_chat_id_from_notification_center("https://t.me/bitirmeshrinkflationmigros"),
            "@bitirmeshrinkflationmigros",
        )

    @patch("app.services.telegram_notifications.record_notification_history")
    @patch("app.services.telegram_notifications.notification_history_exists", return_value=False)
    @patch("app.services.telegram_notifications.send_telegram_messages")
    @patch("app.services.telegram_notifications.load_market_weekly_notification_payload")
    def test_dispatch_market_notification_sends_summary_when_sections_empty(
        self,
        payload_mock,
        send_telegram_messages_mock,
        notification_history_exists_mock,
        record_notification_history_mock,
    ) -> None:
        payload_mock.return_value = MarketWeeklyNotificationPayload(
            market="migros",
            latest_snapshot_date=date(2026, 4, 28),
            previous_snapshot_date=date(2026, 4, 21),
            current_snapshot_count=1483,
            rows=[],
        )
        config = TelegramNotificationConfig(
            default_bot_token="token",
            api_base_url="https://api.telegram.org",
            timeout_seconds=10.0,
            targets={"migros": TelegramTarget(chat_id="-1001")},
            market_bot_tokens={},
        )

        result = dispatch_market_notification(
            db=object(),
            market="migros",
            config=config,
            thresholds=DetectionThresholds(),
        )

        self.assertTrue(result.sent)
        self.assertFalse(result.skipped)
        self.assertIsNone(result.reason)
        self.assertEqual(result.current_snapshot_count, 1483)
        send_telegram_messages_mock.assert_called_once()
        notification_history_exists_mock.assert_called_once()
        record_notification_history_mock.assert_called_once()

    @patch("app.services.telegram_notifications.record_notification_history")
    @patch("app.services.telegram_notifications.notification_history_exists", return_value=False)
    @patch("app.services.telegram_notifications.send_telegram_messages")
    @patch("app.services.telegram_notifications.load_market_weekly_notification_payload")
    def test_dispatch_market_notification_sends_to_market_target(
        self,
        payload_mock,
        send_telegram_messages_mock,
        notification_history_exists_mock,
        record_notification_history_mock,
    ) -> None:
        payload_mock.return_value = MarketWeeklyNotificationPayload(
            market="migros",
            latest_snapshot_date=date(2026, 4, 28),
            previous_snapshot_date=date(2026, 4, 21),
            current_snapshot_count=1483,
            rows=[sample_row()],
        )
        config = TelegramNotificationConfig(
            default_bot_token="token",
            api_base_url="https://api.telegram.org",
            timeout_seconds=10.0,
            targets={"migros": TelegramTarget(chat_id="-1001")},
            market_bot_tokens={},
        )

        result = dispatch_market_notification(
            db=object(),
            market="migros",
            config=config,
            thresholds=DetectionThresholds(),
            limit=5,
        )

        self.assertTrue(result.sent)
        self.assertFalse(result.skipped)
        self.assertEqual(result.current_snapshot_count, 1483)
        send_telegram_messages_mock.assert_called_once()
        notification_history_exists_mock.assert_called_once()
        record_notification_history_mock.assert_called_once()

    @patch("app.services.telegram_notifications.load_active_telegram_rules", return_value=[])
    @patch("app.services.telegram_notifications.load_market_weekly_notification_payload")
    def test_send_configured_notifications_supports_dry_run_without_bot_token(
        self,
        payload_mock,
        load_active_telegram_rules_mock,
    ) -> None:
        payload_mock.return_value = MarketWeeklyNotificationPayload(
            market="migros",
            latest_snapshot_date=date(2026, 4, 28),
            previous_snapshot_date=date(2026, 4, 21),
            current_snapshot_count=1483,
            rows=[sample_row()],
        )
        config = TelegramNotificationConfig(
            default_bot_token="",
            api_base_url="https://api.telegram.org",
            timeout_seconds=10.0,
            targets={
                "migros": TelegramTarget(chat_id="-1001"),
                "sok": TelegramTarget(chat_id="-1002"),
            },
            market_bot_tokens={},
        )

        results = send_configured_shrinkflation_notifications(
            db=object(),
            markets=["migros", "sok"],
            thresholds=DetectionThresholds(),
            dry_run=True,
            config=config,
        )

        self.assertEqual(len(results), 2)
        self.assertTrue(all(result.skipped for result in results))
        self.assertTrue(all(result.reason == "dry_run" for result in results))
        load_active_telegram_rules_mock.assert_called_once()
        self.assertTrue(all(result.current_snapshot_count == 1483 for result in results))

    @patch("app.services.telegram_notifications.dispatch_market_notification")
    @patch("app.services.telegram_notifications.load_active_telegram_rules")
    def test_send_configured_notifications_uses_database_rules_when_present(
        self,
        load_active_telegram_rules_mock,
        dispatch_market_notification_mock,
    ) -> None:
        config = TelegramNotificationConfig(
            default_bot_token="token",
            api_base_url="https://api.telegram.org",
            timeout_seconds=10.0,
            targets={},
            market_bot_tokens={},
        )
        load_active_telegram_rules_mock.return_value = [
            NotificationRule(
                rule_id=7,
                market="migros",
                notification_center="https://t.me/bitirmeshrinkflationmigros",
                target=TelegramTarget(chat_id="@bitirmeshrinkflationmigros"),
                thresholds=DetectionThresholds(),
            )
        ]
        dispatch_market_notification_mock.return_value = (
            type(
                "Result",
                (),
                {
                    "market": "migros",
                    "sent": False,
                    "skipped": True,
                    "target_configured": True,
                    "item_count": 1,
                    "current_snapshot_count": 1483,
                    "latest_snapshot_date": date(2026, 4, 28),
                    "previous_snapshot_date": date(2026, 4, 21),
                    "reason": "dry_run",
                    "preview": "preview",
                    "rule_id": 7,
                    "notification_center": "https://t.me/bitirmeshrinkflationmigros",
                },
            )()
        )

        results = send_configured_shrinkflation_notifications(
            db=object(),
            markets=["migros", "sok"],
            thresholds=DetectionThresholds(),
            dry_run=True,
            config=config,
        )

        self.assertEqual(len(results), 1)
        load_active_telegram_rules_mock.assert_called_once()
        dispatch_market_notification_mock.assert_called_once()
