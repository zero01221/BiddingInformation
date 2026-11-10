# coding=utf-8
"""爬虫基类与爬虫管理器。

关键实现（ARCHITECTURE §2 / §7 T03）：把「相关性 → 地区打标 → 下载档位 →
去重键」的处理链**真正串接进 :meth:`BaseCrawler.run`**，确保每个活跃源都经过。

分工：
- 相关性：强制 ``keywords.core`` / ``industry`` 校验，**不要求云南**；
- 地区：只打标不过滤，全国数据全量入库（默认云南优先仅是前端视图）；
- 公告类型：仅作 ``bid_type`` 标签，绝不参与过滤；
- 单源异常：记录到 ``SourceStatus.last_error`` 并打 ERROR 日志，不再静默吞掉。
"""

import json
import random
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Optional

from .config import Config
from .download_resolver import DownloadResolver, is_safe_url
from .logger import get_logger
from .models import BidItem, SourceStatus
from .relevance import is_relevant
from .region_tagger import tag as tag_region
from .snapshot import SnapshotStore
from .dedup import compute as compute_dedup_key
from .utils import random_delay

logger = get_logger(__name__)

_BID_TYPE_RE = re.compile(
    r"\[(招标公告|开标记录|评标公示|中标公告|采购公告|招标文件|中标结果|开标结果文件)\]"
)
_NATIVE_ID_PATTERNS = (
    r"[?&#]uuid=([^&#]+)",
    r"[?&#]infoid=([^&#]+)",
    r"[?&#]bulletinid=([^&#]+)",
    r"[?&#]businessId=([^&#]+)",
    r"[?&#]id=([^&#]+)",
    r"/([0-9a-fA-F]{16,})\.html",
)


def _valid_date(text: str) -> bool:
    """公告日期是否为合法的 YYYY-MM-DD。"""
    if not text:
        return False
    try:
        datetime.strptime(str(text)[:10], "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def _extract_native_id(url: str) -> str:
    """从 URL 中兜底提取源站业务主键（各 crawler 应优先显式填充）。"""
    if not url:
        return ""
    for pattern in _NATIVE_ID_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def _infer_bid_type(description: str, source: str) -> str:
    """推断公告类型标签（仅标签，不过滤）。"""
    match = _BID_TYPE_RE.search(description or "")
    if match:
        return match.group(1)
    if "铁塔电子采购" in (source or ""):
        return "采购公告"
    if "乙方宝" in (source or ""):
        return "招标公告"
    return ""


class BaseCrawler(ABC):
    """所有数据源爬虫的基类。"""

    def __init__(self, source_name: str, source_config: dict) -> None:
        """初始化爬虫。"""
        self.source_name = source_name
        self.config = source_config or {}
        self.status = SourceStatus(name=source_name, enabled=self.is_enabled())

        app_config = Config.get_instance()
        self.timeout = app_config.get_int("request.timeout", 30)
        self.delay_between_requests = app_config.get_int("request.delay_between_requests", 5)
        self.proxies = app_config.get_proxies()
        self.days_limit = self.config.get(
            "days_limit", app_config.get_int("filter.days_limit", 7)
        )

    @abstractmethod
    def fetch(self) -> List[BidItem]:
        """抓取原始招标信息列表（子类实现）。"""
        raise NotImplementedError

    @property
    def display_name(self) -> str:
        """获取显示名称。"""
        return self.config.get("name", self.source_name)

    def is_enabled(self) -> bool:
        """检查是否启用。"""
        return bool(self.config.get("enabled", True))

    def is_healthy(self) -> bool:
        """检查是否健康。"""
        return self.status.healthy

    def filter_by_date(self, items: List[BidItem]) -> List[BidItem]:
        """只保留最近 N 天公告；日期不可解析时标 ``date_valid=0`` 并保留。"""
        cutoff = datetime.now() - timedelta(days=int(self.days_limit))
        filtered: List[BidItem] = []
        for item in items:
            if not _valid_date(item.date):
                item.date_valid = 0
                logger.warning(f"[{self.display_name}] 公告日期不可解析，标记 date_valid=0 并保留: {item.date!r}")
                filtered.append(item)
                continue
            item_date = datetime.strptime(item.date[:10], "%Y-%m-%d")
            if item_date >= cutoff:
                filtered.append(item)
            else:
                logger.debug(f"[{self.display_name}] 过滤旧公告: {item.title[:30]} ({item.date})")
        logger.info(f"[{self.display_name}] 日期过滤: {len(items)} -> {len(filtered)} 条（最近 {self.days_limit} 天）")
        return filtered

    def delay(self, min_seconds: Optional[float] = None, max_seconds: Optional[float] = None) -> None:
        """请求间随机延迟。"""
        low = min_seconds if min_seconds is not None else self.delay_between_requests * 0.5
        high = max_seconds if max_seconds is not None else self.delay_between_requests * 1.5
        random_delay(low, high)

    def get_random_user_agent(self) -> str:
        """获取随机 User-Agent。"""
        agents = Config.get_instance().get_user_agents()
        return random.choice(agents) if agents else "Mozilla/5.0"

    def record_success(self, items: List[BidItem]) -> None:
        """记录成功采集。"""
        self.status.record_success(len(items))
        logger.info(f"[{self.display_name}] 成功获取 {len(items)} 条（已过相关性/打标/档位/去重链）")

    def record_failure(self, error: str = "") -> None:
        """记录失败（错误信息进入 source_health，不再静默）。"""
        self.status.record_failure(error)
        logger.error(f"[{self.display_name}] 抓取失败: {error or '未知错误'}")

    # ------------------------------------------------------------------
    # 处理链
    # ------------------------------------------------------------------

    def _process_items(self, items: List[BidItem]) -> List[BidItem]:
        """统一处理链：相关性 → 打标 → 去重键 → 预取 → 下载档位。

        Returns:
            通过处理链且批次内去重的条目列表。
        """
        resolver = DownloadResolver()
        store = SnapshotStore()
        processed: List[BidItem] = []
        seen: set = set()

        for item in items:
            # 1) 铁塔相关性强制校验（不要求云南，公告类型不过滤）
            if not is_relevant(item.title, item.description):
                logger.debug(f"[{self.display_name}] 非铁塔相关，剔除: {item.title[:30]}")
                continue

            # 2) 日期有效性标记（脏数据保留但显式标注）
            item.date_valid = 1 if _valid_date(item.date) else 0

            # 3) 源站业务主键 / 公告类型标签兜底
            item.native_id = (item.native_id or "").strip() or _extract_native_id(item.url)
            item.bid_type = (item.bid_type or "").strip() or _infer_bid_type(
                item.description, item.source
            )

            # 4) 地区打标（只打标，绝不过滤）
            region = tag_region(item.title, item.description)
            item.province = region.province
            item.city = region.city
            item.regions = json.dumps(region.regions, ensure_ascii=False)

            # 5) 去重键（item_id 恒等于 dedup_key）
            key = compute_dedup_key(item)
            item.dedup_key = key
            item.item_id = key

            # 6) 详情页快照预取（默认关闭，不联网；失败返回空串）
            if store.prefetch and not item.snapshot_url and is_safe_url(item.url):
                item.snapshot_url = store.save(item.url, key)

            # 7) 下载档位判定；L4 时清空产物引用，杜绝伪造文件与 404
            tier = resolver.resolve(item)
            item.download_level = tier.level
            item.download_note = tier.note
            if tier.level == "L4":
                item.attachment_url = ""
                item.snapshot_url = ""
            elif tier.level in ("L2", "L3"):
                # 统一为前端可拼 asset_prefix 的相对路径
                if tier.level == "L2":
                    item.attachment_url = tier.url
                else:
                    item.snapshot_url = tier.url

            # 8) 批次内去重（同语义 URL 变体只保留一条）
            if key in seen:
                continue
            seen.add(key)
            processed.append(item)

        dropped = len(items) - len(processed)
        if dropped:
            logger.info(f"[{self.display_name}] 处理链剔除 {dropped} 条（非铁塔/批次重复）")
        return processed

    def run(self) -> List[BidItem]:
        """运行爬虫并串接完整处理链。

        Returns:
            处理完毕的条目列表；单源异常返回空列表并把错误写入 status，
            **不影响其他数据源**。
        """
        if not self.is_enabled():
            logger.info(f"[{self.display_name}] 已禁用，跳过")
            return []

        if not self.is_healthy():
            # 不再静默跳过：记录告警后仍尝试一次，状态由 source_health 暴露
            logger.warning(f"[{self.display_name}] 上次运行不健康，本次仍尝试抓取")

        try:
            logger.info(f"[{self.display_name}] 开始抓取")
            raw_items = self.fetch()
            dated_items = self.filter_by_date(raw_items)
            items = self._process_items(dated_items)
            self.record_success(items)
            return items
        except Exception as exc:  # noqa: BLE001 - 单源隔离，错误必须可见
            self.record_failure(f"{type(exc).__name__}: {exc}")
            return []


class CrawlerManager:
    """爬虫管理器（单源失败不影响整体）。"""

    def __init__(self) -> None:
        self.crawlers: List[BaseCrawler] = []
        self.config = Config.get_instance()

    def register(self, crawler: BaseCrawler) -> None:
        """注册爬虫。"""
        self.crawlers.append(crawler)
        logger.debug(f"注册爬虫: {crawler.display_name}")

    def run_all(self, apply_delay: bool = True) -> List[BidItem]:
        """运行所有已注册爬虫，聚合结果。

        Args:
            apply_delay: 是否应用数据源间延迟；离线重建时置 False。
        """
        all_items: List[BidItem] = []
        for index, crawler in enumerate(self.crawlers):
            if apply_delay and index > 0:
                delay = self.config.get_int("request.delay_between_sources", 20)
                logger.info(f"等待 {delay} 秒后继续下一个数据源...")
                time.sleep(delay)
            try:
                all_items.extend(crawler.run())
            except Exception as exc:  # noqa: BLE001 - 双保险隔离
                logger.error(f"[{crawler.display_name}] 管理器层捕获异常，跳过该源: {exc}")
        return all_items

    def get_status(self) -> List[dict]:
        """获取所有爬虫状态（含 last_error，供 source_health 使用）。"""
        return [crawler.status.to_dict() for crawler in self.crawlers]

    def health_check(self) -> bool:
        """健康检查：至少有一个健康源即可继续。"""
        healthy_count = sum(1 for c in self.crawlers if c.is_healthy())
        total_count = len(self.crawlers)
        logger.info(f"健康检查: {healthy_count}/{total_count} 个数据源健康")
        return healthy_count > 0
