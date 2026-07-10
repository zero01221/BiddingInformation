# coding=utf-8
"""数据库管理模块 - 使用SQLite存储历史记录"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Set

from .config import Config
from .logger import get_logger
from .models import BidItem

logger = get_logger(__name__)


class Database:
    """数据库管理类"""
    
    def __init__(self, db_path: Optional[str] = None):
        """初始化数据库"""
        config = Config.get_instance()
        self.db_path = db_path or config.get("database.path", "output/bidding_history.db")
        self.retention_days = config.get_int("database.retention_days", 90)
        
        # 确保目录存在
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bid_items (
                    item_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    original_url TEXT,
                    date TEXT NOT NULL,
                    source TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_notified INTEGER DEFAULT 0
                )
            """)
            
            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON bid_items(date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON bid_items(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON bid_items(created_at)")
            
            conn.commit()
        logger.debug(f"数据库初始化完成: {self.db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)
    
    def save_item(self, item: BidItem) -> bool:
        """保存招标信息，返回是否为新项目"""
        with self._get_connection() as conn:
            # 检查是否已存在
            cursor = conn.execute(
                "SELECT item_id FROM bid_items WHERE item_id = ?",
                (item.item_id,)
            )
            if cursor.fetchone():
                logger.debug(f"项目已存在，跳过: {item.title[:50]}")
                return False
            
            # 插入新项目
            conn.execute(
                """
                INSERT INTO bid_items 
                (item_id, title, url, original_url, date, source, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.item_id,
                    item.title,
                    item.url,
                    item.original_url,
                    item.date,
                    item.source,
                    item.description,
                    item.created_at,
                )
            )
            conn.commit()
            logger.info(f"保存新项目: {item.title[:50]}")
            return True
    
    def save_items(self, items: List[BidItem]) -> int:
        """批量保存招标信息，返回新项目数量"""
        new_count = 0
        for item in items:
            if self.save_item(item):
                new_count += 1
        return new_count
    
    def get_item_ids(self) -> Set[str]:
        """获取所有已存在的项目ID"""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT item_id FROM bid_items")
            return {row[0] for row in cursor.fetchall()}
    
    def is_duplicate(self, item_id: str) -> bool:
        """检查项目是否已存在"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT item_id FROM bid_items WHERE item_id = ?",
                (item_id,)
            )
            return cursor.fetchone() is not None
    
    def get_recent_items(self, days: int = 30) -> List[BidItem]:
        """获取最近N天的招标信息"""
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT item_id, title, url, original_url, date, source, description, created_at
                FROM bid_items
                WHERE date >= ?
                ORDER BY date DESC, created_at DESC
                """,
                (cutoff_date,)
            )
            
            items = []
            for row in cursor.fetchall():
                item = BidItem(
                    item_id=row[0],
                    title=row[1],
                    url=row[2],
                    original_url=row[3] or "",
                    date=row[4],
                    source=row[5],
                    description=row[6] or "",
                )
                if row[7]:
                    try:
                        item.created_at = datetime.fromisoformat(row[7])
                    except (ValueError, TypeError):
                        pass
                items.append(item)
            
            return items
    
    def get_all_items(self, limit: int = 100) -> List[BidItem]:
        """获取所有招标信息（按日期降序）"""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT item_id, title, url, original_url, date, source, description, created_at
                FROM bid_items
                ORDER BY date DESC, created_at DESC
                LIMIT ?
                """,
                (limit,)
            )
            
            items = []
            for row in cursor.fetchall():
                item = BidItem(
                    item_id=row[0],
                    title=row[1],
                    url=row[2],
                    original_url=row[3] or "",
                    date=row[4],
                    source=row[5],
                    description=row[6] or "",
                )
                if row[7]:
                    try:
                        item.created_at = datetime.fromisoformat(row[7])
                    except (ValueError, TypeError):
                        pass
                items.append(item)
            
            return items
    
    def cleanup_old_items(self) -> int:
        """清理过期数据，返回删除数量"""
        cutoff_date = (datetime.now() - timedelta(days=self.retention_days)).strftime("%Y-%m-%d")
        
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM bid_items WHERE date < ?",
                (cutoff_date,)
            )
            conn.commit()
            deleted_count = cursor.rowcount
        
        if deleted_count > 0:
            logger.info(f"清理了 {deleted_count} 条过期数据")
        
        return deleted_count
    
    def get_stats(self) -> dict:
        """获取数据库统计信息"""
        with self._get_connection() as conn:
            # 总数
            cursor = conn.execute("SELECT COUNT(*) FROM bid_items")
            total = cursor.fetchone()[0]
            
            # 按来源统计
            cursor = conn.execute(
                "SELECT source, COUNT(*) FROM bid_items GROUP BY source"
            )
            by_source = {row[0]: row[1] for row in cursor.fetchall()}
            
            # 最近7天新增
            week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            cursor = conn.execute(
                "SELECT COUNT(*) FROM bid_items WHERE date >= ?",
                (week_ago,)
            )
            recent_week = cursor.fetchone()[0]
            
            return {
                "total": total,
                "by_source": by_source,
                "recent_week": recent_week,
                "db_path": self.db_path,
            }
