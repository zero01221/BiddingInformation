# coding=utf-8
"""数据库管理模块 - SQLite 为唯一事实源。

修复的历史缺陷（docs/ARCHITECTURE.md §9）：
1. ``get_all_items(limit=100)`` 静默截断 → 全量导出，无 LIMIT；
2. ``cleanup_old_items`` 按**公告日期**删除会清空历史 → 改
   :meth:`cleanup_by_created_at`，且默认禁用，只按采集时间；
3. 旧 schema 无 dedup_key / 地区 / 档位字段 → 自动迁移 + 一次性回填，
   **843 条历史必须无损保留**；
4. 新增 ``UNIQUE(dedup_key)`` 语义去重（替代 md5(title_url)）。
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, Iterator, List, Optional, Set

from .config import Config, resolve_project_path
from .dedup import legacy_key
from .logger import get_logger
from .models import BidItem

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Schema（列顺序即 INSERT 顺序）
# ---------------------------------------------------------------------------

_COLUMNS = (
    "item_id", "dedup_key", "native_id", "title", "date", "date_valid",
    "source", "url", "original_url", "description", "province", "city",
    "regions", "bid_type", "download_level", "attachment_url",
    "snapshot_url", "download_note", "created_at", "collected_at",
)

# 用于渐进式补列（不含约束，SQLite 的 ALTER TABLE ADD COLUMN 不支持 UNIQUE）
_COLUMN_DEFS: Dict[str, str] = {
    "item_id": "TEXT",
    "dedup_key": "TEXT",
    "native_id": "TEXT DEFAULT ''",
    "title": "TEXT",
    "date": "TEXT",
    "date_valid": "INTEGER DEFAULT 1",
    "source": "TEXT",
    "url": "TEXT",
    "original_url": "TEXT DEFAULT ''",
    "description": "TEXT DEFAULT ''",
    "province": "TEXT DEFAULT ''",
    "city": "TEXT DEFAULT ''",
    "regions": "TEXT DEFAULT '[]'",
    "bid_type": "TEXT DEFAULT ''",
    "download_level": "TEXT DEFAULT 'L4'",
    "attachment_url": "TEXT DEFAULT ''",
    "snapshot_url": "TEXT DEFAULT ''",
    "download_note": "TEXT DEFAULT ''",
    "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    "collected_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
}

_CREATE_SQL = """
CREATE TABLE bid_items (
    item_id        TEXT PRIMARY KEY NOT NULL,
    dedup_key      TEXT NOT NULL UNIQUE,
    native_id      TEXT DEFAULT '',
    title          TEXT NOT NULL,
    date           TEXT NOT NULL,
    date_valid     INTEGER DEFAULT 1,
    source         TEXT NOT NULL,
    url            TEXT NOT NULL,
    original_url   TEXT DEFAULT '',
    description    TEXT DEFAULT '',
    province       TEXT DEFAULT '',
    city           TEXT DEFAULT '',
    regions        TEXT DEFAULT '[]',
    bid_type       TEXT DEFAULT '',
    download_level TEXT NOT NULL DEFAULT 'L4',
    attachment_url TEXT DEFAULT '',
    snapshot_url   TEXT DEFAULT '',
    download_note  TEXT DEFAULT '',
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    collected_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_INDEX_SQLS = (
    "CREATE INDEX IF NOT EXISTS idx_date ON bid_items(date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_source ON bid_items(source)",
    "CREATE INDEX IF NOT EXISTS idx_created_at ON bid_items(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_province_date ON bid_items(province, date DESC)",
    # 双保险：渐进补列场景下也能保证去重键唯一
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_bid_items_dedup_key ON bid_items(dedup_key)",
)

_INSERT_SQL = (
    f"INSERT INTO bid_items ({', '.join(_COLUMNS)}) "
    f"VALUES ({', '.join(['?'] * len(_COLUMNS))})"
)

_UPDATE_SQL = """
UPDATE bid_items SET
    native_id=?, title=?, date=?, date_valid=?, source=?, url=?, original_url=?,
    description=?, province=?, city=?, regions=?, bid_type=?, download_level=?,
    attachment_url=?, snapshot_url=?, download_note=?
WHERE dedup_key=?
"""

_SELECT_ALL_SQL = f"SELECT {', '.join(_COLUMNS)} FROM bid_items"


class Database:
    """SQLite 数据库管理类。"""

    def __init__(self, db_path: Optional[str] = None) -> None:
        """初始化数据库；自动执行 schema 迁移与历史去重键回填。

        Args:
            db_path: 显式路径；为空时读取 ``database.path`` 配置。
        """
        config = Config.get_instance()
        raw_path = db_path or config.get("database.path", "output/bidding_history.db")
        self.db_path = str(resolve_project_path(str(raw_path)))
        self.migrated_legacy: bool = False

        resolve_project_path(str(raw_path)).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # 连接与 schema
    # ------------------------------------------------------------------

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        """事务型连接上下文：成功提交、异常回滚、始终关闭连接。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """建表 / 迁移 / 补列 / 建索引。"""
        with self._session() as conn:
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='bid_items'"
            ).fetchone()

            if not exists:
                conn.execute(_CREATE_SQL)
                logger.info(f"数据库建表完成: {self.db_path}")
            else:
                cols = {row["name"] for row in conn.execute("PRAGMA table_info(bid_items)")}
                if "dedup_key" not in cols:
                    self._migrate_legacy(conn)
                    self.migrated_legacy = True
                else:
                    self._ensure_columns(conn, cols)

            for sql in _INDEX_SQLS:
                conn.execute(sql)

        logger.debug(f"数据库初始化完成: {self.db_path}")

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection, existing: Set[str]) -> None:
        """为已存在的表补齐缺失列（渐进式迁移，不重建表）。"""
        for name, definition in _COLUMN_DEFS.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE bid_items ADD COLUMN {name} {definition}")
                logger.info(f"补列: bid_items.{name}")

    def _migrate_legacy(self, conn: sqlite3.Connection) -> None:
        """把旧 9 列表无损迁移到新 20 列 schema。

        步骤：读全部老行 → 计算 dedup_key（冲突消解，保证 UNIQUE 不丢行）
        → 重命名旧表 → 建新表 → 逐行插入（含地区打标）→ 删除旧表。
        全过程在同一事务内，失败自动回滚，旧库不会被破坏。
        """
        legacy_rows = [dict(row) for row in conn.execute("SELECT * FROM bid_items").fetchall()]
        total = len(legacy_rows)
        logger.info(f"检测到旧 schema，开始无损迁移 {total} 条历史记录")

        # 局部导入，避免模块加载期循环依赖
        from .region_tagger import RegionTagger

        tagger = RegionTagger()
        l4_note = Config.get_instance().get_download_config()["tiers"]["L4"]

        # 1) 计算去重键；基础键公式与新数据一致，撞车时用旧 item_id 加盐消解
        keys: List[str] = []
        used: Set[str] = set()
        for row in legacy_rows:
            key = legacy_key(
                row.get("source", ""), row.get("url", ""),
                row.get("title", ""), row.get("date", ""),
            )
            if key in used:
                old_id = str(row.get("item_id", "") or "")
                key = legacy_key(
                    row.get("source", ""), row.get("url", ""),
                    row.get("title", ""), row.get("date", ""), salt=old_id,
                )
                suffix = 1
                while key in used:
                    key = legacy_key(
                        row.get("source", ""), row.get("url", ""),
                        row.get("title", ""), row.get("date", ""),
                        salt=f"{old_id}#{suffix}",
                    )
                    suffix += 1
            used.add(key)
            keys.append(key)

        # 2) 建新表（旧表先改名，索引随旧表一起在 DROP 时清理）
        conn.execute("ALTER TABLE bid_items RENAME TO bid_items_legacy")
        conn.execute(_CREATE_SQL)

        for row, key in zip(legacy_rows, keys):
            title = row.get("title", "") or ""
            description = row.get("description", "") or ""
            region = tagger.tag(title, description)
            created = row.get("created_at") or datetime.now().isoformat()
            date_text = row.get("date", "") or ""

            conn.execute(
                _INSERT_SQL,
                (
                    key,                                   # item_id = dedup_key
                    key,                                   # dedup_key
                    "",                                    # native_id（老数据无）
                    title,
                    date_text,
                    1 if _is_valid_date(date_text) else 0,
                    row.get("source", "") or "",
                    row.get("url", "") or "",
                    row.get("original_url", "") or "",
                    description,
                    region.province,
                    region.city,
                    json.dumps(region.regions, ensure_ascii=False),
                    _infer_bid_type(description),
                    "L4",                                  # 老数据无附件/快照：诚实降级
                    "", "", l4_note,
                    created, created,
                ),
            )

        conn.execute("DROP TABLE bid_items_legacy")
        logger.info(f"迁移完成：{total} 条历史全部保留，去重键已回填，地区已打标")

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def upsert_items(self, items: List[BidItem]) -> int:
        """批量写入（按 dedup_key 去重），返回**新增**条数。

        已存在的条目只更新可变字段，绝不覆盖 ``created_at``（首次采集时间是
        清理的唯一口径）。dedup_key 缺失时按纯函数即时补算。
        """
        if not items:
            return 0

        from .dedup import compute

        with self._session() as conn:
            existing: Set[str] = {
                row[0] for row in conn.execute("SELECT dedup_key FROM bid_items")
                if row[0]
            }
            new_count = 0
            for item in items:
                key = item.dedup_key or compute(item)
                item.dedup_key = key
                item.item_id = key
                if key in existing:
                    conn.execute(_UPDATE_SQL, _update_tuple(item, key))
                else:
                    conn.execute(_INSERT_SQL, _item_to_row(item))
                    existing.add(key)
                    new_count += 1
        if new_count:
            logger.info(f"入库新增 {new_count} 条（共提交 {len(items)} 条）")
        return new_count

    def save_item(self, item: BidItem) -> bool:
        """保存单条，返回是否为新项目（兼容旧接口）。"""
        return self.upsert_items([item]) > 0

    def save_items(self, items: List[BidItem]) -> int:
        """批量保存（兼容旧接口，等价于 upsert_items）。"""
        return self.upsert_items(items)

    def backfill_dedup_key(self) -> int:
        """幂等回填：为 dedup_key 为空的行补算去重键，返回更新条数。

        迁移场景下所有行已在 ``_migrate_legacy`` 中回填完毕，本方法返回 0；
        保留它是为了未来任何原因产生空键时可安全修复，且不改动历史。
        """
        with self._session() as conn:
            rows = conn.execute(
                "SELECT rowid, item_id, source, url, title, date FROM bid_items "
                "WHERE dedup_key IS NULL OR dedup_key = ''"
            ).fetchall()
            if not rows:
                return 0

            used: Set[str] = {
                row[0] for row in conn.execute(
                    "SELECT dedup_key FROM bid_items WHERE dedup_key IS NOT NULL AND dedup_key != ''"
                )
            }
            updated = 0
            for row in rows:
                key = legacy_key(row["source"], row["url"], row["title"], row["date"])
                salt = str(row["item_id"] or "")
                suffix = 0
                while key in used:
                    suffix += 1
                    key = legacy_key(
                        row["source"], row["url"], row["title"], row["date"],
                        salt=f"{salt}#{suffix}",
                    )
                used.add(key)
                conn.execute(
                    "UPDATE bid_items SET dedup_key = ?, "
                    "item_id = CASE WHEN item_id IS NULL OR item_id = '' THEN ? ELSE item_id END "
                    "WHERE rowid = ?",
                    (key, key, row["rowid"]),
                )
                updated += 1
        logger.info(f"回填去重键 {updated} 条")
        return updated

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_item_ids(self) -> Set[str]:
        """获取所有已存在的去重键集合。"""
        with self._session() as conn:
            rows = conn.execute("SELECT dedup_key, item_id FROM bid_items").fetchall()
            return {(row[0] or row[1] or "") for row in rows} - {""}

    def is_duplicate(self, item_id: str) -> bool:
        """检查去重键是否已存在。"""
        with self._session() as conn:
            row = conn.execute(
                "SELECT 1 FROM bid_items WHERE dedup_key = ? OR item_id = ? LIMIT 1",
                (item_id, item_id),
            ).fetchone()
            return row is not None

    def get_recent_items(self, days: int = 30) -> List[BidItem]:
        """获取最近 N 天公告（按公告日期，仅供只读列表用）。"""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._session() as conn:
            rows = conn.execute(
                f"{_SELECT_ALL_SQL} WHERE date >= ? ORDER BY date DESC, created_at DESC",
                (cutoff,),
            ).fetchall()
            return [_row_to_item(row) for row in rows]

    def get_all_items(self, limit: Optional[int] = None) -> List[BidItem]:
        """获取全部记录（按日期降序）。

        Args:
            limit: 可选上限；**默认 None = 全量**（修复旧版 limit=100 静默截断）。
        """
        sql = f"{_SELECT_ALL_SQL} ORDER BY date DESC, created_at DESC"
        params: tuple = ()
        if limit is not None and limit > 0:
            sql += " LIMIT ?"
            params = (limit,)
        with self._session() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [_row_to_item(row) for row in rows]

    def get_all_items_for_export(self) -> List[BidItem]:
        """全量导出（无任何截断），供 Exporter / RSS 使用。"""
        return self.get_all_items(limit=None)

    def get_source_health(self) -> List[Dict[str, Any]]:
        """按来源聚合健康信息：条数、最晚公告日、最近采集时间。"""
        with self._session() as conn:
            rows = conn.execute(
                "SELECT source, COUNT(*) AS item_count, MAX(date) AS latest_date, "
                "MAX(created_at) AS latest_collected_at "
                "FROM bid_items GROUP BY source ORDER BY item_count DESC"
            ).fetchall()
            return [
                {
                    "source": row["source"],
                    "item_count": row["item_count"],
                    "latest_date": row["latest_date"] or "",
                    "latest_collected_at": row["latest_collected_at"] or "",
                }
                for row in rows
            ]

    def get_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息。"""
        with self._session() as conn:
            total = conn.execute("SELECT COUNT(*) FROM bid_items").fetchone()[0]
            by_source = {
                row[0]: row[1]
                for row in conn.execute("SELECT source, COUNT(*) FROM bid_items GROUP BY source")
            }
            week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            recent_week = conn.execute(
                "SELECT COUNT(*) FROM bid_items WHERE date >= ?", (week_ago,)
            ).fetchone()[0]
            return {
                "total": total,
                "by_source": by_source,
                "recent_week": recent_week,
                "db_path": self.db_path,
            }

    # ------------------------------------------------------------------
    # 清理（默认禁用）
    # ------------------------------------------------------------------

    def cleanup_by_created_at(self) -> int:
        """按**采集时间**清理，返回删除条数；默认禁用。

        绝不按公告日期删除（旧 ``cleanup_old_items`` 会逐步清空历史）。
        回归要点：40 天前的公告但 created_at 为今日的记录不被清理。
        """
        cleanup_cfg = Config.get_instance().get_cleanup_config()
        if not cleanup_cfg["enabled"]:
            logger.debug("清理默认禁用，跳过（历史全量保留）")
            return 0

        days = int(cleanup_cfg["retention_days"])
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        with self._session() as conn:
            cursor = conn.execute("DELETE FROM bid_items WHERE created_at < ?", (cutoff,))
            deleted = cursor.rowcount
        if deleted > 0:
            logger.info(f"按采集时间清理了 {deleted} 条数据（cutoff={cutoff}）")
        return deleted

    def cleanup_old_items(self) -> int:
        """兼容旧接口名：实际转调 :meth:`cleanup_by_created_at`（安全口径）。"""
        logger.debug("cleanup_old_items 已废弃，转调 cleanup_by_created_at")
        return self.cleanup_by_created_at()


# ---------------------------------------------------------------------------
# 行 ↔ 模型转换（模块级纯函数）
# ---------------------------------------------------------------------------

def _iso_or_text(value: Any) -> str:
    """datetime → ISO 字符串；其它值原样转字符串。"""
    if isinstance(value, datetime):
        return value.isoformat()
    return "" if value is None else str(value)


def _item_to_row(item: BidItem) -> tuple:
    """把 BidItem 转为与 _COLUMNS 对齐的元组。"""
    return (
        item.item_id,
        item.dedup_key,
        item.native_id or "",
        item.title or "",
        item.date or "",
        int(item.date_valid),
        item.source or "",
        item.url or "",
        item.original_url or "",
        item.description or "",
        item.province or "",
        item.city or "",
        item.regions or "[]",
        item.bid_type or "",
        item.download_level or "L4",
        item.attachment_url or "",
        item.snapshot_url or "",
        item.download_note or "",
        _iso_or_text(item.created_at),
        _iso_or_text(item.collected_at),
    )


def _update_tuple(item: BidItem, key: str) -> tuple:
    """把 BidItem 转为与 _UPDATE_SQL 对齐的元组（不含 created_at）。"""
    return (
        item.native_id or "", item.title or "", item.date or "", int(item.date_valid),
        item.source or "", item.url or "", item.original_url or "",
        item.description or "", item.province or "", item.city or "",
        item.regions or "[]", item.bid_type or "", item.download_level or "L4",
        item.attachment_url or "", item.snapshot_url or "", item.download_note or "",
        key,
    )


def _row_get(row: sqlite3.Row, key: str, default: Any = "") -> Any:
    """安全读取行字段（兼容列缺失）。"""
    try:
        value = row[key]
    except (IndexError, KeyError):
        return default
    return default if value is None else value


def _row_to_item(row: sqlite3.Row) -> BidItem:
    """把数据库行还原为 BidItem。"""
    from .models import _parse_dt  # 局部引用，避免模块级循环

    return BidItem(
        title=_row_get(row, "title"),
        url=_row_get(row, "url"),
        date=_row_get(row, "date"),
        source=_row_get(row, "source"),
        description=_row_get(row, "description"),
        original_url=_row_get(row, "original_url"),
        item_id=_row_get(row, "item_id"),
        dedup_key=_row_get(row, "dedup_key"),
        native_id=_row_get(row, "native_id"),
        date_valid=int(_row_get(row, "date_valid", 1) or 0),
        province=_row_get(row, "province"),
        city=_row_get(row, "city"),
        regions=_row_get(row, "regions", "[]") or "[]",
        bid_type=_row_get(row, "bid_type"),
        download_level=_row_get(row, "download_level", "L4") or "L4",
        attachment_url=_row_get(row, "attachment_url"),
        snapshot_url=_row_get(row, "snapshot_url"),
        download_note=_row_get(row, "download_note"),
        created_at=_parse_dt(_row_get(row, "created_at", None)),
        collected_at=_parse_dt(_row_get(row, "collected_at", None)),
    )


def _is_valid_date(text: str) -> bool:
    """判断公告日期是否为可解析的 YYYY-MM-DD。"""
    if not text:
        return False
    try:
        datetime.strptime(str(text)[:10], "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def _infer_bid_type(description: str) -> str:
    """从历史摘要的 ``[公告类型]`` 前缀推断标签（仅标签，不过滤）。"""
    import re

    match = re.search(r"\[(招标公告|开标记录|评标公示|中标公告|采购公告)\]", description or "")
    return match.group(1) if match else ""
