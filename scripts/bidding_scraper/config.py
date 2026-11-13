# coding=utf-8
"""配置管理模块。

本模块只负责读取配置，不含任何网络/通知逻辑。
地区词表的单一事实源为 ``config/regions.json``，通过 :meth:`Config.get_regions`
供 Python 打标与前端构建共用。
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# 项目根目录：<root>/scripts/bidding_scraper/config.py → <root>
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def resolve_project_path(path: str) -> Path:
    """把配置里的相对路径解析为以项目根为基准的绝对路径。

    避免产物位置依赖进程当前工作目录（.command 双击或计划任务触发时 CWD 不固定）。
    """
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


class Config:
    """配置管理类（单例）。"""

    _instance: Optional["Config"] = None
    _config: Dict[str, Any] = {}
    _regions_cache: Optional[Dict[str, Any]] = None

    def __new__(cls) -> "Config":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Config":
        """加载 YAML 配置文件；文件不存在时回退到内置默认配置。"""
        instance = cls()

        if config_path is None:
            config_path = PROJECT_ROOT / "config" / "bidding_scraper.yaml"

        config_file = Path(config_path)
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                instance._config = yaml.safe_load(f) or {}
        else:
            instance._config = instance._get_default_config()

        instance._regions_cache = None
        return instance

    @classmethod
    def get_instance(cls) -> "Config":
        """获取配置实例（未加载时自动加载默认配置）。"""
        if cls._instance is None:
            cls.load()
        return cls._instance

    # ------------------------------------------------------------------
    # 通用读取
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持点号分隔的嵌套键。"""
        value: Any = self._config
        for part in key.split("."):
            if not isinstance(value, dict):
                return default
            value = value.get(part)
            if value is None:
                return default
        return value

    def get_list(self, key: str, default: Optional[List] = None) -> List:
        """获取列表配置；非列表值包装为单元素列表。"""
        value = self.get(key, default or [])
        if isinstance(value, list):
            return value
        return [value] if value else []

    def get_int(self, key: str, default: int = 0) -> int:
        """获取整数配置，转换失败时返回默认值。"""
        value = self.get(key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """获取布尔配置，兼容字符串形式的真假值。"""
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "yes", "1", "on")
        return bool(value)

    # ------------------------------------------------------------------
    # 数据源与关键词
    # ------------------------------------------------------------------

    def get_sources(self) -> Dict[str, Dict]:
        """获取所有数据源配置。"""
        sources = self.get("sources", {})
        return sources if isinstance(sources, dict) else {}

    def get_enabled_sources(self) -> Dict[str, Dict]:
        """获取已启用的数据源配置。"""
        return {
            name: config
            for name, config in self.get_sources().items()
            if isinstance(config, dict) and config.get("enabled", True)
        }

    def get_core_keywords(self) -> List[str]:
        """获取铁塔核心关键词。"""
        return self.get_list("keywords.core")

    def get_industry_keywords(self) -> List[str]:
        """获取行业关键词。"""
        return self.get_list("keywords.industry")

    def get_user_agents(self) -> List[str]:
        """获取 User-Agent 列表。"""
        return self.get_list("request.user_agents")

    def get_proxies(self) -> Dict[str, str]:
        """获取代理配置。

        优先级：环境变量 ``BIDDING_PROXY`` > 配置文件 ``request.proxy``。
        返回 ``{"http": url, "https": url}``；未配置返回空字典（直连）。
        """
        proxy_url = os.environ.get("BIDDING_PROXY", "") or self.get("request.proxy", "")
        if proxy_url:
            return {"http": proxy_url, "https": proxy_url}
        return {}

    # ------------------------------------------------------------------
    # 地区词表（单一事实源）
    # ------------------------------------------------------------------

    def get_regions(self) -> Dict[str, Any]:
        """读取 ``config/regions.json``，供 Python 打标与前端下拉共用。

        返回结构：``{provinces[], city_to_province{}, yunnan_cities[], default_view}``。
        文件缺失或损坏时返回内置最小默认，保证构建流程不中断。
        """
        if self._regions_cache is not None:
            return self._regions_cache

        regions_path = PROJECT_ROOT / "config" / "regions.json"
        fallback: Dict[str, Any] = {
            "version": 1,
            "default_view": "云南",
            "provinces": ["云南"],
            "yunnan_cities": ["云南", "昆明", "大理", "丽江"],
            "city_to_province": {"昆明": "云南", "大理": "云南", "丽江": "云南"},
        }
        try:
            with open(regions_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if (
                isinstance(data, dict)
                and isinstance(data.get("provinces"), list)
                and isinstance(data.get("city_to_province"), dict)
            ):
                self._regions_cache = data
                return data
        except (OSError, json.JSONDecodeError):
            pass

        self._regions_cache = fallback
        return fallback

    # ------------------------------------------------------------------
    # 各业务段配置
    # ------------------------------------------------------------------

    def get_relevance_config(self) -> Dict[str, Any]:
        """相关性校验配置：``require_core`` 为 True 时强制铁塔相关性过滤。"""
        return {
            "require_core": self.get_bool("relevance.require_core", True),
        }

    def get_download_config(self) -> Dict[str, Any]:
        """下载降级 L1~L4 配置（档位文案、目录、是否联网预取）。"""
        tiers = self.get("download.tiers", {})
        if not isinstance(tiers, dict):
            tiers = {}
        return {
            "prefetch": self.get_bool("download.prefetch", False),
            "attachment_enabled": self.get_bool("download.attachment_enabled", True),
            "snapshot_enabled": self.get_bool("download.snapshot_enabled", True),
            "attachments_dir": self.get("download.attachments_dir", "output/attachments"),
            "snapshots_dir": self.get("download.snapshots_dir", "output/snapshots"),
            "tiers": {
                "L1": tiers.get("L1", "原始文件"),
                "L2": tiers.get("L2", "源文件副本"),
                "L3": tiers.get("L3", "原站未提供文件下载，以下为详情页快照"),
                "L4": tiers.get("L4", "该来源不提供下载，请前往出处查看"),
            },
        }

    def get_publish_config(self) -> Dict[str, Any]:
        """发布配置（兼容保留）。

        mac 本地闭环不使用推送/同步通道：这些键只为可选的 Windows 备用入口保留，
        编排层不会据此触发任何发布动作，产物生成与发布完全解耦。
        """
        return {
            "git_push": self.get_bool("publish.git_push", False),
            "git_remote": self.get("publish.git_remote", "origin"),
            "git_branch": self.get("publish.git_branch", "master"),
            "sync_dir": self.get("publish.sync_dir", "") or "",
        }

    def get_offline_config(self) -> Dict[str, Any]:
        """离线新鲜度配置：数据截至超过 stale_days 时页面标黄提示。"""
        return {"stale_days": self.get_int("offline.stale_days", 2)}

    def get_cleanup_config(self) -> Dict[str, Any]:
        """清理配置：默认禁用；即便启用也只按 created_at 清理。"""
        return {
            "enabled": self.get_bool("cleanup.enabled", False),
            "retention_days": self.get_int("cleanup.retention_days", 3650),
        }

    def get_output_config(self) -> Dict[str, Any]:
        """产物路径配置。"""
        return {
            "index_file": self.get("output.index_file", "output/index.html"),
            "data_file": self.get("output.data_file", "output/data.json"),
            "rss_file": self.get("output.rss_file", "output/bidding_feed.xml"),
            "max_items": self.get_int("output.max_items", 0),
        }

    # ------------------------------------------------------------------
    # 内置默认配置（配置文件缺失时使用）
    # ------------------------------------------------------------------

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置（不含任何推送/通知段）。"""
        return {
            "keywords": {
                "core": ["铁塔", "塔桅", "通信铁塔", "中国铁塔", "广播电视"],
                "yunnan": ["云南", "昆明", "大理", "丽江"],
                "industry": ["通信", "移动", "联通", "电信", "5G", "基站"],
            },
            "relevance": {"require_core": True},
            "filter": {"days_limit": 7},
            "sources": {
                "cebpubservice": {"enabled": True, "name": "中国招标投标公共服务平台"},
                "chinatowercom": {"enabled": True, "name": "中国铁塔电子采购平台"},
                "yfbzb": {"enabled": True, "name": "乙方宝"},
                "ynggzy": {"enabled": True, "name": "云南省公共资源交易中心"},
            },
            "request": {
                "timeout": 30,
                "retry_attempts": 3,
                "delay_between_requests": 5,
                "delay_between_sources": 20,
                "user_agents": [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ],
            },
            "database": {"path": "output/bidding_history.db", "retention_days": 3650},
            "cleanup": {"enabled": False, "retention_days": 3650},
            "download": {"prefetch": False, "attachment_enabled": True, "snapshot_enabled": True},
            "publish": {"git_push": False, "git_remote": "origin", "git_branch": "master", "sync_dir": ""},
            "offline": {"stale_days": 2},
            "output": {
                "rss_file": "output/bidding_feed.xml",
                "rss_title": "铁塔招标信息",
                "rss_description": "全国铁塔相关招标信息聚合",
                "rss_link": "",
                "max_items": 0,
                "index_file": "output/index.html",
                "data_file": "output/data.json",
            },
            "logging": {"level": "INFO", "file": "output/bidding_scraper.log"},
        }
