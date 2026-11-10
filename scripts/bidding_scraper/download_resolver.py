# coding=utf-8
"""下载降级 L1~L4 档位判定。

硬规则（PRD §5 / ARCHITECTURE §8）：
- L1 原站附件直链 → 原始文件；
- L2 抓取时预存的副本 → 源文件副本；
- L3 抓取时保存的详情页快照 → 明确提示「原站未提供文件下载」；
- L4 连快照也没有 → 按钮禁用、明确提示，**不得伪造文件、不得 404、不得静默失败**。

L2/L3 判定前会校验本地产物文件确实存在；不存在即降级到 L4。
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit

from .config import Config, resolve_project_path

__all__ = ["DownloadTier", "DownloadResolver", "is_safe_url", "resolve"]

_LEVELS = ("L1", "L2", "L3", "L4")
_ILLEGAL_FILENAME_RE = re.compile(r'[\\/:*?"<>|\r\n\t]')


def is_safe_url(url: str) -> bool:
    """URL 白名单：仅允许 http/https（生成期与前端双校验）。"""
    if not url:
        return False
    try:
        return urlsplit(str(url)).scheme.lower() in ("http", "https")
    except ValueError:
        return False


@dataclass
class DownloadTier:
    """一条公告的下载档位结果。"""

    level: str
    url: str
    filename: str
    note: str
    enabled: bool

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（供导出与前端消费）。"""
        return {
            "level": self.level,
            "url": self.url,
            "filename": self.filename,
            "note": self.note,
            "enabled": self.enabled,
        }


class DownloadResolver:
    """L1~L4 档位判定器。"""

    def __init__(self, download_config: Optional[Dict[str, Any]] = None) -> None:
        cfg = download_config if download_config is not None else Config.get_instance().get_download_config()
        self.tiers: Dict[str, str] = cfg["tiers"]
        self.attachment_enabled: bool = bool(cfg["attachment_enabled"])
        self.snapshot_enabled: bool = bool(cfg["snapshot_enabled"])
        self.attachments_dir: Path = resolve_project_path(cfg["attachments_dir"])
        self.snapshots_dir: Path = resolve_project_path(cfg["snapshots_dir"])
        self._dir_names: Dict[str, str] = {
            "attachments": Path(cfg["attachments_dir"]).name or "attachments",
            "snapshots": Path(cfg["snapshots_dir"]).name or "snapshots",
        }

    def resolve(self, item: Any) -> DownloadTier:
        """判定一条 :class:`BidItem` 的下载档位。

        Args:
            item: 具备 attachment_url / snapshot_url / title / dedup_key 的对象。

        Returns:
            :class:`DownloadTier`；L4 时 ``enabled=False`` 且 ``url=""``。
        """
        attachment = str(getattr(item, "attachment_url", "") or "").strip()
        snapshot = str(getattr(item, "snapshot_url", "") or "").strip()

        # L1：原站提供的附件直链
        if self.attachment_enabled and attachment and is_safe_url(attachment):
            return DownloadTier(
                level="L1",
                url=attachment,
                filename=self._filename(item, attachment),
                note=self.tiers["L1"],
                enabled=True,
            )

        # L2：应用侧预存的副本（必须真实存在）
        if self.attachment_enabled and attachment and not is_safe_url(attachment):
            found, relative = self._find_local(attachment, self.attachments_dir, "attachments")
            if found is not None:
                return DownloadTier(
                    level="L2",
                    url=relative,
                    filename=self._filename(item, attachment),
                    note=self.tiers["L2"],
                    enabled=True,
                )

        # L3：详情页快照（必须真实存在）
        if self.snapshot_enabled and snapshot:
            found, relative = self._find_local(snapshot, self.snapshots_dir, "snapshots")
            if found is not None:
                return DownloadTier(
                    level="L3",
                    url=relative,
                    filename=self._filename(item, snapshot, default_ext=".html"),
                    note=self.tiers["L3"],
                    enabled=True,
                )

        # L4：明确不可用，不伪造任何文件
        return DownloadTier(
            level="L4",
            url="",
            filename=self._filename(item, ""),
            note=self.tiers["L4"],
            enabled=False,
        )

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _find_local(self, raw: str, directory: Path, kind: str) -> Tuple[Optional[Path], str]:
        """校验本地产物是否存在，返回 (路径 或 None, 前端相对 URL)。"""
        name = Path(raw).name
        dir_name = self._dir_names[kind]
        relative = f"{dir_name}/{name}" if name else ""

        candidate = Path(raw)
        candidates = [candidate] if candidate.is_absolute() else [
            resolve_project_path(raw),
            directory / name,
        ]
        for path in candidates:
            try:
                if path.is_file():
                    return path, relative
            except OSError:
                continue
        return None, relative

    @staticmethod
    def _filename(item: Any, url: str, default_ext: str = "") -> str:
        """生成安全的中文下载文件名（保留原标题，替换路径非法字符）。"""
        title = str(getattr(item, "title", "") or "").strip()
        base = _ILLEGAL_FILENAME_RE.sub("_", title)[:100].strip() or str(
            getattr(item, "dedup_key", "") or "bidding-document"
        )
        suffix = ""
        if url:
            try:
                suffix = Path(urlsplit(url).path).suffix
            except ValueError:
                suffix = ""
        suffix = suffix or default_ext
        if suffix and not base.lower().endswith(suffix.lower()):
            base += suffix
        return base


def resolve(item: Any) -> DownloadTier:
    """模块级便捷函数：使用默认配置的判定器。"""
    return DownloadResolver().resolve(item)
