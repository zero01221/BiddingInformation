# coding=utf-8
"""AC-08 / ARCHITECTURE §9：历史清理回归。

旧缺陷：按「公告日期」DELETE 且每次运行执行，会逐步清空历史。
新口径：默认禁用；即便启用也只按 ``created_at`` 删除。
"""

from __future__ import annotations

from datetime import datetime

from scripts.bidding_scraper.database import Database


class TestCleanupRegression:
    def test_cleanup_is_disabled_by_default(self, app_config, tmp_db: Database, make_item):
        assert app_config.get_cleanup_config()["enabled"] is False
        old_announcement = make_item(date="2020-01-01", created_at=datetime.now())

        tmp_db.upsert_items([old_announcement])

        assert tmp_db.cleanup_by_created_at() == 0
        assert len(tmp_db.get_all_items_for_export()) == 1

    def test_old_announcement_with_today_created_at_never_deleted(
        self, tmp_db: Database, make_item, enable_cleanup
    ):
        # 40 天前（甚至 20 年前）的公告，只要 created_at 是今日就不该被删
        enable_cleanup(retention_days=1)
        old_announcement = make_item(date="2000-01-01", created_at=datetime.now())

        tmp_db.upsert_items([old_announcement])

        assert tmp_db.cleanup_by_created_at() == 0
        assert len(tmp_db.get_all_items_for_export()) == 1

    def test_very_old_created_at_is_deleted_when_enabled(
        self, tmp_db: Database, make_item, enable_cleanup
    ):
        enable_cleanup(retention_days=30)
        fresh = make_item(
            url="https://a.com/fresh", native_id="FRESH", created_at=datetime.now()
        )
        old = make_item(
            url="https://a.com/old", native_id="OLD", created_at=datetime(2000, 1, 1)
        )
        assert tmp_db.upsert_items([fresh, old]) == 2

        deleted = tmp_db.cleanup_by_created_at()

        assert deleted == 1
        remaining = [item.native_id for item in tmp_db.get_all_items_for_export()]
        assert remaining == ["FRESH"]

    def test_legacy_alias_cleanup_old_items_is_safe(
        self, tmp_db: Database, make_item, enable_cleanup
    ):
        # 兼容旧接口名必须转调安全口径，不能回到按公告日期删除
        enable_cleanup(retention_days=1)
        item = make_item(date="1999-01-01", created_at=datetime.now())
        tmp_db.upsert_items([item])

        assert tmp_db.cleanup_old_items() == 0
        assert len(tmp_db.get_all_items_for_export()) == 1

    def test_cleanup_is_idempotent_and_returns_int(
        self, tmp_db: Database, make_item, enable_cleanup
    ):
        enable_cleanup(retention_days=3650)
        tmp_db.upsert_items([make_item(created_at=datetime.now())])

        first = tmp_db.cleanup_by_created_at()
        second = tmp_db.cleanup_by_created_at()

        assert isinstance(first, int)
        assert first == 0 and second == 0
        assert len(tmp_db.get_all_items_for_export()) == 1
