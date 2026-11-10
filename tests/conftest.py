# coding=utf-8
"""QA 回归测试的公共夹具（离线、零污染、可重复）。

约束：
- 全程离线：不发起任何网络请求，不执行 update.bat；
- 不污染仓库：所有写操作落到 pytest 的 ``tmp_path``（仓库外临时目录），
  真实 ``output/`` 一律以 SQLite ``mode=ro&immutable=1`` 只读打开；
- 可重复：会话级显式加载一次真实配置；测试内对配置的改动一律走
  ``monkeypatch``，由 pytest 自动还原，不依赖系统时区或运行日期。
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

# 让 ``scripts.bidding_scraper`` 可从任意 CWD 导入
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.bidding_scraper.config import Config  # noqa: E402

# 导入期即加载真实配置。后续被导入的模块（logger / relevance / database）在
# import 阶段就会读取 Config 单例，必须先关掉「文件日志」，避免测试写出
# output/*.log（保持 git 工作树干净）。
Config.load()
_APP_CONFIG = Config.get_instance()
_APP_CONFIG._config.setdefault("logging", {})["file"] = ""
_APP_CONFIG._config["logging"]["level"] = "ERROR"
_APP_CONFIG._regions_cache = None

from scripts.bidding_scraper.database import Database  # noqa: E402
from scripts.bidding_scraper.models import BidItem  # noqa: E402

_INLINE_DATA_RE = re.compile(
    r'<script type="application/json" id="DATA">(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 路径类
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def project_root() -> Path:
    """项目根目录。"""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def web_dir(project_root: Path) -> Path:
    """前端源码目录。"""
    return project_root / "web"


@pytest.fixture(scope="session")
def output_dir(project_root: Path) -> Path:
    """产物目录（只读使用）。"""
    return project_root / "output"


@pytest.fixture(scope="session")
def real_db_path(output_dir: Path) -> Path:
    """真实历史库路径（只读）。"""
    return output_dir / "bidding_history.db"


@pytest.fixture(scope="session")
def index_html_path(output_dir: Path) -> Path:
    """真实单文件离线页路径（只读）。"""
    return output_dir / "index.html"


@pytest.fixture(scope="session")
def built_index_html(index_html_path: Path) -> str:
    """真实产物全文。"""
    return index_html_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 配置 / 通用工具
# ---------------------------------------------------------------------------
@pytest.fixture
def app_config() -> Config:
    """已加载真实配置的单例；测试内改动请用 ``monkeypatch``。"""
    return Config.get_instance()


@pytest.fixture
def inline_block_of() -> Callable[[str], str]:
    """从 HTML 中提取内联 JSON 文本（断言放在测试调用栈内）。"""
    def _extract(html: str) -> str:
        match = _INLINE_DATA_RE.search(html)
        assert match is not None, "产物缺少 <script type=application/json id=DATA> 内联块"
        return match.group(1)
    return _extract


@pytest.fixture
def make_item() -> Callable[..., BidItem]:
    """BidItem 工厂：默认字段自洽且语义唯一，便于 Arrange。"""
    counter = {"n": 0}

    def _make(**overrides: Any) -> BidItem:
        counter["n"] += 1
        n = counter["n"]
        defaults: Dict[str, Any] = {
            "title": f"中国铁塔昆明基站项目-{n}",
            "url": f"https://example.com/detail/{n}",
            "date": "2026-08-01",
            "source": "测试源",
            "description": "中国铁塔基站维护招标公告",
            "native_id": f"NATIVE-{n}",
        }
        defaults.update(overrides)
        return BidItem(**defaults)

    return _make


# ---------------------------------------------------------------------------
# 临时数据库（仓库外）
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_db(tmp_path: Path) -> Database:
    """全新临时库：自动建表 + 20 列 + UNIQUE 索引，绝不触碰真实 DB。"""
    return Database(db_path=str(tmp_path / "qa_tmp.db"))


@pytest.fixture
def readonly_db(real_db_path: Path):
    """真实历史库的只读连接（immutable 保证不产生 -wal/-shm 等文件）。"""
    uri = f"file:{real_db_path.as_posix()}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def make_legacy_db(tmp_path: Path) -> Callable[[List[tuple]], Path]:
    """构造旧 9 列 schema 的临时库，用于验证无损迁移与幂等。"""
    counter = {"n": 0}

    def _make(rows: List[tuple]) -> Path:
        counter["n"] += 1
        path = tmp_path / f"legacy_{counter['n']}.db"
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                "CREATE TABLE bid_items ("
                "item_id TEXT PRIMARY KEY, title TEXT, date TEXT, source TEXT, "
                "url TEXT, original_url TEXT, description TEXT, "
                "created_at TIMESTAMP, is_notified INTEGER DEFAULT 0)"
            )
            conn.executemany(
                "INSERT INTO bid_items "
                "(item_id,title,date,source,url,original_url,description,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                rows,
            )
            conn.commit()
        finally:
            conn.close()
        return path

    return _make


# ---------------------------------------------------------------------------
# 下载档位 / 清理策略
# ---------------------------------------------------------------------------
@pytest.fixture
def make_download_config(tmp_path: Path) -> Callable[..., Dict[str, Any]]:
    """构造完整 download 配置，产物目录指向临时目录。"""
    def _make(**overrides: Any) -> Dict[str, Any]:
        cfg: Dict[str, Any] = {
            "prefetch": False,
            "attachment_enabled": True,
            "snapshot_enabled": True,
            "attachments_dir": str(tmp_path / "attachments"),
            "snapshots_dir": str(tmp_path / "snapshots"),
            "tiers": {
                "L1": "原始文件",
                "L2": "源文件副本",
                "L3": "原站未提供文件下载，以下为详情页快照",
                "L4": "该来源不提供下载，请前往出处查看",
            },
        }
        cfg.update(overrides)
        return cfg

    return _make


@pytest.fixture
def enable_cleanup(monkeypatch, app_config: Config) -> Callable[[int], None]:
    """按需启用清理策略（默认配置是禁用的），由 monkeypatch 自动还原。"""
    def _enable(retention_days: int = 30) -> None:
        monkeypatch.setattr(
            app_config,
            "get_cleanup_config",
            lambda: {"enabled": True, "retention_days": retention_days},
        )
    return _enable
