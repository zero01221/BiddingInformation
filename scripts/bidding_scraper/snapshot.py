# coding=utf-8
"""详情页快照 / 附件预取落盘（L2 / L3 产物）。

离线优先：``download.prefetch`` 默认 ``false``，此时 :meth:`SnapshotStore.save`
与 :meth:`SnapshotStore.save_attachment` 直接返回空字符串、**不发起任何网络请求**。
仅在 Windows 生产端显式开启后才会抓取，抓取失败同样返回空字符串，由
:mod:`download_resolver` 降级到 L4（不伪造文件）。
"""

import os
from pathlib import Path
from typing import Optional

import requests

from .config import Config, resolve_project_path
from .download_resolver import is_safe_url
from .logger import get_logger

logger = get_logger(__name__)


class SnapshotStore:
    """把详情页 HTML 与附件按 dedup_key 命名落盘到 output/ 下。"""

    def __init__(self, download_config: Optional[dict] = None) -> None:
        cfg = download_config if download_config is not None else Config.get_instance().get_download_config()
        self.prefetch: bool = bool(cfg["prefetch"])
        self.attachments_dir: Path = resolve_project_path(cfg["attachments_dir"])
        self.snapshots_dir: Path = resolve_project_path(cfg["snapshots_dir"])
        self.timeout: int = Config.get_instance().get_int("request.timeout", 30)
        self._dir_names = {
            "attachments": Path(cfg["attachments_dir"]).name or "attachments",
            "snapshots": Path(cfg["snapshots_dir"]).name or "snapshots",
        }

    def save(self, detail_url: str, dedup_key: str) -> str:
        """抓取详情页并保存为 ``snapshots/<dedup_key>.html``。

        Args:
            detail_url: 原文详情页 URL。
            dedup_key: 该条公告的去重键，用作文件名。

        Returns:
            相对路径 ``snapshots/<dedup_key>.html``；未开启预取 / 非法 URL /
            抓取失败时返回空字符串。
        """
        if not self.prefetch or not dedup_key or not is_safe_url(detail_url):
            return ""
        content = self._download_bytes(detail_url)
        if content is None:
            return ""
        return self._write(self.snapshots_dir, "snapshots", f"{dedup_key}.html", content)

    def save_attachment(
        self, attachment_url: str, dedup_key: str, filename: str = ""
    ) -> str:
        """抓取附件并保存为 ``attachments/<dedup_key><ext>``。

        Args:
            attachment_url: 附件直链。
            dedup_key: 去重键，用作文件名主体。
            filename: 仅用于推断扩展名（中文名由前端下载时重建）。

        Returns:
            相对路径；未开启预取 / 非法 URL / 抓取失败时返回空字符串。
        """
        if not self.prefetch or not dedup_key or not is_safe_url(attachment_url):
            return ""
        content = self._download_bytes(attachment_url)
        if content is None:
            return ""
        from urllib.parse import urlsplit

        ext = Path(urlsplit(attachment_url).path).suffix or Path(filename or "").suffix or ".bin"
        return self._write(self.attachments_dir, "attachments", f"{dedup_key}{ext}", content)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _download_bytes(self, url: str) -> Optional[bytes]:
        """执行一次 GET；任何失败都返回 None 并记录明确日志（不静默）。"""
        try:
            resp = requests.get(url, timeout=self.timeout, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as exc:
            logger.warning(f"快照/附件预取失败，降级到 L4: {url} -> {exc}")
            return None

    def _write(self, directory: Path, kind: str, name: str, content: bytes) -> str:
        """原子写入产物文件，返回前端可用的相对路径。"""
        try:
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / name
            tmp = directory / (name + ".tmp")
            tmp.write_bytes(content)
            os.replace(str(tmp), str(target))
            return f"{self._dir_names[kind]}/{name}"
        except OSError as exc:
            logger.warning(f"快照/附件落盘失败，降级到 L4: {name} -> {exc}")
            return ""
