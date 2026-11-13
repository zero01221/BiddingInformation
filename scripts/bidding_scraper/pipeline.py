# coding=utf-8
"""构建编排：配置 → 抓取 → 处理 → 落库 → 导出 → 构建。

失败降级（ARCHITECTURE §1.5 / §7 T04）：
- 产物先写临时文件，经 :func:`builder.validate_html` 校验条数与内联 JSON 后
  才统一 ``os.replace`` 替换，任一步失败都不会写坏正式产物；
- 构建/校验异常或所有数据源本次均失败时**保留上一版** ``output/index.html``；
- 产物发布（推送 / 同步）与本编排解耦：mac 本地闭环不使用任何发布通道；
  可选的 Windows 备用入口若需要发布，由该入口自行处理且失败仅告警。
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .builder import build as build_html
from .builder import validate_html
from .config import Config, PROJECT_ROOT, resolve_project_path
from .database import Database
from .exporter import Exporter, now_iso
from .logger import get_logger
from .output import OutputFormatter

logger = get_logger(__name__)

# 平台专属离线快照包（相对 output/ 的产物，asset_prefix 需回到 output/ 根）
_PLATFORM_PAGES = (
    ("output/win/铁塔招标信息.html", "../"),
    ("output/mac/铁塔招标信息.html", "../"),
)


@dataclass
class BuildResult:
    """一次构建的摘要。"""

    success: bool = False
    used_previous: bool = False
    degraded: bool = False
    items_count: int = 0
    new_count: int = 0
    generated_at: str = ""
    data_as_of: str = ""
    index_path: str = ""
    data_path: str = ""
    source_health: List[dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（便于测试断言）。"""
        return {
            "success": self.success,
            "used_previous": self.used_previous,
            "degraded": self.degraded,
            "items_count": self.items_count,
            "new_count": self.new_count,
            "generated_at": self.generated_at,
            "data_as_of": self.data_as_of,
            "index_path": self.index_path,
            "data_path": self.data_path,
            "source_health": self.source_health,
            "errors": self.errors,
        }


class Pipeline:
    """全流程编排器。"""

    def __init__(self, config: Optional[Config] = None, db: Optional[Database] = None) -> None:
        self.config = config or Config.get_instance()
        self.db = db

    def run(
        self,
        crawl: bool = True,
        write_artifacts: bool = True,
        rss: bool = True,
        rss_path: Optional[str] = None,
    ) -> BuildResult:
        """执行一次完整构建。

        Args:
            crawl: 是否联网抓取；False 时只用现有 DB 重建产物（离线验证）。
            write_artifacts: 是否写出 HTML/data.json。
            rss: 是否重写 RSS（FR-14）。
            rss_path: 覆盖 RSS 输出路径。

        Returns:
            :class:`BuildResult`。
        """
        result = BuildResult(generated_at=now_iso())
        try:
            db = self.db or Database()
            # 幂等：修复任何原因产生的空去重键（迁移时已回填，通常返回 0）
            backfilled = db.backfill_dedup_key()
            if backfilled:
                result.errors.append(f"补充回填去重键 {backfilled} 条")

            run_health: List[dict] = []
            all_sources_failed = False
            if crawl:
                manager = self._build_manager()
                all_items = manager.run_all()
                run_health = manager.get_status()

                existing = db.get_item_ids()
                new_items = [item for item in all_items if item.dedup_key not in existing]
                result.new_count = db.upsert_items(new_items)

                # 单源异常可见：只要有 last_error 就记录，不再静默
                failures = [
                    f"{s.get('name')}: {s.get('last_error')}"
                    for s in run_health if s.get("last_error")
                ]
                result.errors.extend(failures)
                all_sources_failed = (
                    bool(run_health)
                    and not all_items
                    and all(
                        (not s.get("healthy", True)) or bool(s.get("last_error"))
                        for s in run_health
                    )
                )

            if self.config.get_cleanup_config()["enabled"]:
                deleted = db.cleanup_by_created_at()
                if deleted:
                    result.errors.append(f"按采集时间清理 {deleted} 条")

            export = Exporter().export(db)
            items = export["items"]
            meta = export["meta"]
            meta["source_health"] = export["source_health"]
            meta["run_status"] = run_health
            meta["degraded"] = all_sources_failed
            meta["degraded_reason"] = (
                "本次所有数据源均采集失败，以下为历史数据，请留意数据截至日期"
                if all_sources_failed else ""
            )

            result.items_count = len(items)
            result.data_as_of = export["data_as_of"]
            result.generated_at = export["generated_at"]
            result.source_health = export["source_health"]
            result.degraded = all_sources_failed

            if not write_artifacts:
                result.success = True
                return result

            output_cfg = self.config.get_output_config()
            index_path = resolve_project_path(output_cfg["index_file"])
            result.index_path = str(index_path)

            # 全源失败且已有上一版产物 → 保留上一版，不覆盖
            if all_sources_failed and index_path.exists():
                result.used_previous = True
                result.data_path = str(resolve_project_path(output_cfg["data_file"]))
                result.errors.append("所有数据源本次均失败，已保留上一版产物")
                result.success = True
                logger.warning("全源失败，保留上一版 index.html / data.json")
                return result

            self._build_artifacts(items, meta, export, output_cfg, result)
            if rss:
                self._write_rss(export, rss_path)

            result.success = True
            logger.info(
                f"构建成功: {result.items_count} 条 → {result.index_path} "
                f"(新增 {result.new_count}，数据截至 {result.data_as_of or '无'})"
            )
        except Exception as exc:  # noqa: BLE001 - 顶层保护：绝不写坏正式产物
            message = f"{type(exc).__name__}: {exc}"
            result.success = False
            result.used_previous = True
            result.errors.append(f"构建失败，保留上一版产物: {message}")
            logger.error(f"构建失败，保留上一版产物: {message}")
        return result

    # ------------------------------------------------------------------
    # 内部步骤
    # ------------------------------------------------------------------

    @staticmethod
    def _build_manager():
        """装配爬虫管理器（延迟导入 main，避免包初始化期循环依赖）。"""
        from .main import create_crawler_manager

        return create_crawler_manager()

    @staticmethod
    def _build_artifacts(
        items: List[dict],
        meta: Dict[str, Any],
        export: Dict[str, Any],
        output_cfg: Dict[str, Any],
        result: BuildResult,
    ) -> None:
        """渲染并两阶段原子提交全部产物文件。"""
        index_path = resolve_project_path(output_cfg["index_file"])
        data_path = resolve_project_path(output_cfg["data_file"])

        # 1) 先在内存里渲染并校验全部 HTML；任何失败都不落盘
        base_meta = dict(meta)
        base_meta["asset_prefix"] = ""
        base_html = build_html(items, base_meta)
        validate_html(base_html, {"items": items})

        html_files: List[Tuple[Path, str]] = [(index_path, base_html)]
        for relative, prefix in _PLATFORM_PAGES:
            platform_meta = dict(meta)
            platform_meta["asset_prefix"] = prefix
            html = build_html(items, platform_meta)
            validate_html(html, {"items": items})
            html_files.append((resolve_project_path(relative), html))

        # 2) 分离数据产物（不内联，供可选在线部署/调试；前端不 fetch 它）
        data_json = json.dumps(export, ensure_ascii=False, separators=(",", ":"))
        all_files: List[Tuple[Path, str]] = [(data_path, data_json)] + html_files
        Pipeline._stage_and_commit(all_files)

        result.index_path = str(index_path)
        result.data_path = str(data_path)

    @staticmethod
    def _stage_and_commit(files: List[Tuple[Path, str]]) -> None:
        """先写全部 ``.tmp``，全部成功后统一 ``os.replace``；失败清理临时文件。"""
        staged: List[Tuple[Path, Path]] = []
        try:
            for target, content in files:
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(target.name + ".tmp")
                with open(tmp, "w", encoding="utf-8", newline="") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                staged.append((tmp, target))
            for tmp, target in staged:
                os.replace(str(tmp), str(target))
        finally:
            for tmp, _target in staged:
                try:
                    if tmp.exists():
                        tmp.unlink()
                except OSError:
                    pass

    @staticmethod
    def _write_rss(export: Dict[str, Any], rss_path: Optional[str]) -> None:
        """用 exporter 的全量载荷重写 RSS（不再被 100 条截断）。"""
        OutputFormatter().save_rss_from_payload(export, rss_path)


def build_crawler_manager():
    """供外部复用的装配入口（与 ``main.create_crawler_manager`` 等价）。"""
    return Pipeline._build_manager()
