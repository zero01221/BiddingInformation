# coding=utf-8
"""AC-08 / ARCHITECTURE §4：843 条历史无损、20 列 schema、全量导出、迁移幂等。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from scripts.bidding_scraper.database import Database

EXPECTED_COLUMNS = [
    "item_id", "dedup_key", "native_id", "title", "date", "date_valid",
    "source", "url", "original_url", "description", "province", "city",
    "regions", "bid_type", "download_level", "attachment_url",
    "snapshot_url", "download_note", "created_at", "collected_at",
]


def _columns(conn) -> list:
    return [row[1] for row in conn.execute("PRAGMA table_info(bid_items)")]


def _unique_index_names(conn) -> set:
    return {
        row[1]
        for row in conn.execute("PRAGMA index_list(bid_items)").fetchall()
        if row[2] == 1
    }


class TestRealHistoryReadOnly:
    """真实 output/bidding_history.db 只读核验（immutable，绝不写盘）。"""

    def test_history_rows_intact_after_updates(self, readonly_db):
        # 843 是重构迁移时的历史基线；之后每次「更新数据」只新增不删除，
        # 故断言为「不少于基线」而非固定快照，避免数据增长后误报。
        total = readonly_db.execute("SELECT COUNT(*) FROM bid_items").fetchone()[0]
        assert total >= 843

    def test_schema_has_all_20_columns(self, readonly_db):
        assert _columns(readonly_db) == EXPECTED_COLUMNS
        assert len(EXPECTED_COLUMNS) == 20

    def test_dedup_key_unique_and_non_empty(self, readonly_db):
        distinct = readonly_db.execute(
            "SELECT COUNT(DISTINCT dedup_key) FROM bid_items"
        ).fetchone()[0]
        total = readonly_db.execute("SELECT COUNT(*) FROM bid_items").fetchone()[0]
        empty = readonly_db.execute(
            "SELECT COUNT(*) FROM bid_items WHERE dedup_key IS NULL OR dedup_key=''"
        ).fetchone()[0]
        assert distinct == total and empty == 0

    def test_unique_index_on_dedup_key_exists(self, readonly_db):
        names = _unique_index_names(readonly_db)
        assert any("dedup_key" in name for name in names), names

    def test_source_distribution_preserved_and_grows(self, readonly_db):
        rows = dict(
            readonly_db.execute(
                "SELECT source, COUNT(*) FROM bid_items GROUP BY source"
            ).fetchall()
        )
        # 两个原始来源的 843 条历史必须无损；新公告只会让条数增加。
        assert rows.get("中国招标投标公共服务平台", 0) >= 159
        assert rows.get("中国铁塔电子采购平台", 0) >= 684
        assert sum(rows.values()) >= 843

    def test_yunnan_region_tag_backfilled(self, readonly_db):
        tagged = readonly_db.execute(
            "SELECT COUNT(*) FROM bid_items WHERE province='云南'"
        ).fetchone()[0]
        assert tagged >= 61


class TestFreshDatabase:
    def test_new_db_has_20_columns_and_unique_index(self, tmp_db: Database):
        conn = sqlite3.connect(tmp_db.db_path)
        try:
            assert _columns(conn) == EXPECTED_COLUMNS
            assert any("dedup_key" in name for name in _unique_index_names(conn))
        finally:
            conn.close()

    def test_get_all_items_for_export_returns_all_not_100(
        self, tmp_db: Database, make_item
    ):
        # 回归旧版 get_all_items(limit=100) 静默丢数据缺陷
        items = [
            make_item(url=f"https://example.com/d/{i}", native_id=f"N-{i}")
            for i in range(250)
        ]
        assert tmp_db.upsert_items(items) == 250
        assert len(tmp_db.get_all_items_for_export()) == 250
        assert len(tmp_db.get_all_items()) == 250
        assert len(tmp_db.get_item_ids()) == 250

    def test_upsert_dedups_and_preserves_first_created_at(
        self, tmp_db: Database, make_item
    ):
        first = make_item(native_id="SAME", created_at=datetime(2000, 1, 1))
        assert tmp_db.upsert_items([first]) == 1

        updated = make_item(
            native_id="SAME", title="更新后的标题", created_at=datetime.now()
        )
        assert tmp_db.upsert_items([updated]) == 0

        all_items = tmp_db.get_all_items_for_export()
        assert len(all_items) == 1
        assert all_items[0].title == "更新后的标题"
        assert all_items[0].created_at.year == 2000

    def test_backfill_dedup_key_is_noop_on_healthy_db(self, tmp_db: Database, make_item):
        tmp_db.upsert_items([make_item()])
        assert tmp_db.backfill_dedup_key() == 0


class TestLegacyMigration:
    @staticmethod
    def _rows(count: int):
        return [
            (
                f"OLD-{i}", f"中国铁塔昆明基站项目-{i}", "2026-07-20",
                "中国铁塔电子采购平台", f"https://example.com/old/{i}", "",
                "[招标公告] 中国铁塔基站", "2026-07-21T10:00:00",
            )
            for i in range(count)
        ]

    def test_migration_is_lossless_and_idempotent(self, make_legacy_db):
        path = make_legacy_db(self._rows(12))

        first = Database(db_path=str(path))
        assert first.migrated_legacy is True
        assert len(first.get_all_items_for_export()) == 12

        conn = sqlite3.connect(path)
        try:
            assert _columns(conn) == EXPECTED_COLUMNS
            keys = [row[0] for row in conn.execute("SELECT dedup_key FROM bid_items")]
            assert all(keys) and len(set(keys)) == 12
        finally:
            conn.close()

        # 重复实例化不得报错、不得丢数据、不得重复迁移
        second = Database(db_path=str(path))
        third = Database(db_path=str(path))
        assert second.migrated_legacy is False
        assert len(third.get_all_items_for_export()) == 12
        assert third.backfill_dedup_key() == 0

    def test_migration_backfills_regions_bid_type_and_date_valid(self, make_legacy_db):
        path = make_legacy_db(self._rows(3))

        items = Database(db_path=str(path)).get_all_items_for_export()

        assert len(items) == 3
        for item in items:
            assert item.province == "云南" and item.city == "昆明"
            assert item.region_list == ["云南", "昆明"]
            assert item.bid_type == "招标公告"
            assert item.date_valid == 1
            assert item.download_level == "L4"
