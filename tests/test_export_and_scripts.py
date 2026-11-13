# coding=utf-8
"""FR-12/FR-14、AC-09/AC-11：导出载荷、RSS 全量、update.bat、README、mac 入口、门禁 grep。

全部为静态文本检查 + 临时库内存计算，不执行 update.bat、不联网、不 push。
"""

from __future__ import annotations

import os
import re
import subprocess
from xml.etree import ElementTree as ET

import pytest
import yaml

from scripts.bidding_scraper.exporter import Exporter, now_iso
from scripts.bidding_scraper.output import OutputFormatter


# 模块级 fixture（避免 pytest 9 对「类内实例方法 fixture」的弃用警告）
@pytest.fixture(scope="module")
def text(project_root):
    """update.bat 全文。"""
    return (project_root / "update.bat").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def readme(project_root):
    """README.md 全文。"""
    return (project_root / "README.md").read_text(encoding="utf-8")


class TestExporterPayload:
    def test_export_contains_required_top_level_keys(self, tmp_db, make_item):
        tmp_db.upsert_items(
            [make_item(date="2026-07-20"), make_item(date="2026-08-01")]
        )

        payload = Exporter().export(tmp_db)

        assert {"generated_at", "data_as_of", "meta", "items", "source_health"} <= set(
            payload
        )
        assert payload["generated_at"]
        assert payload["data_as_of"] == "2026-08-01"
        assert len(payload["items"]) == 2
        assert isinstance(payload["source_health"], list)

    def test_export_meta_contains_freshness_and_regions(self, tmp_db, make_item):
        tmp_db.upsert_items([make_item()])

        meta = Exporter().export(tmp_db)["meta"]

        assert meta["data_as_of"] == "2026-08-01"
        assert meta["stale_days"] == 2
        assert meta["default_view"] == "云南"
        assert "provinces" in meta["regions"]
        assert meta["total"] == 1

    def test_exported_item_has_download_tier_and_safe_urls(self, tmp_db, make_item):
        item = make_item()
        item.url = "javascript:alert(1)"
        item.original_url = "https://example.com/origin"
        tmp_db.upsert_items([item])

        exported = Exporter().export(tmp_db)["items"][0]

        assert exported["url"] == ""  # 生成期 URL 白名单：非法 scheme 置空
        assert exported["original_url"] == "https://example.com/origin"
        assert exported["download"]["level"] in {"L1", "L2", "L3", "L4"}
        assert isinstance(exported["download"]["enabled"], bool)

    def test_rss_from_payload_is_not_truncated(self, tmp_db, make_item):
        tmp_db.upsert_items(
            [
                make_item(url=f"https://a.com/{i}", native_id=f"N{i}")
                for i in range(150)
            ]
        )
        payload = Exporter().export(tmp_db)

        rss = OutputFormatter().format_rss_from_payload(payload)

        assert rss.count("<item>") == 150  # 旧版 100 条截断已修

    def test_now_iso_uses_fixed_shanghai_offset(self):
        # 固定 +08:00，不依赖系统时区
        assert "+08:00" in now_iso()


class TestUpdateBatStatic:
    def test_sync_dir_unset_skips_copy_without_blocking(self, text):
        assert "BIDDING_SYNC_DIR" in text
        assert 'if "%SYNC_DIR%"==""' in text
        assert "跳过复制" in text
        # [3/4] 复制段内不得有阻断性退出
        copy_section = text.split("[3/4]")[1].split("[4/4]")[0]
        assert "exit /b 1" not in copy_section

    def test_push_failure_only_warns(self, text):
        assert "git push origin master" in text
        assert "[告警] Git 推送失败" in text
        assert "不阻断" in text

    def test_no_github_actions_auto_deploy_claim(self, text):
        assert "GitHub Actions" not in text
        assert "自动部署" not in text
        assert "deploy.yml" not in text

    def test_atomic_write_note_present(self, text):
        assert "原子写" in text


class TestReadmeAndMacEntry:
    @pytest.mark.parametrize(
        "stale_claim",
        ["github.io", "每日 11:00", "飞书", "crontab", "GitHub Actions 将自动部署"],
    )
    def test_readme_has_no_stale_claims(self, readme, stale_claim):
        assert stale_claim not in readme

    def test_readme_documents_offline_first(self, readme):
        assert "file://" in readme
        assert "数据截至" in readme
        assert "BIDDING_SYNC_DIR" in readme

    def test_mac_command_is_zero_dependency(self, project_root):
        text = (project_root / "打开_mac.command").read_text(encoding="utf-8")
        assert 'open "./output/index.html"' in text
        # 只看可执行行：注释里「不调用 python」是说明文字，不是依赖
        code_lines = [
            line for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines).lower()
        assert "python" not in code
        assert "curl" not in code and "wget" not in code

    def test_mac_command_mentions_gatekeeper(self, project_root):
        text = (project_root / "打开_mac.command").read_text(encoding="utf-8")
        assert "Gatekeeper" in text and "chmod +x" in text


class TestSecurityGate:
    """门禁：通知链路 / 明文凭据 / 旧部署 workflow 无残留。

    扫描范围为源码、配置、脚本、文档；排除 .git、tests/ 与 output/ 生成物。
    """

    DISALLOWED = re.compile(
        r"webhook|feishu|dingtalk|qyapi|open-apis|corp_id|bot_token",
        re.IGNORECASE,
    )
    SCAN_SUFFIXES = {
        ".py", ".yaml", ".yml", ".bat", ".command", ".js", ".html",
        ".json", ".md", ".toml", ".txt", ".cfg", ".ini",
    }

    def test_no_notification_keywords_in_source_text_files(self, project_root):
        hits = []
        for path in project_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in self.SCAN_SUFFIXES:
                continue
            rel = path.relative_to(project_root).as_posix()
            if rel.startswith((".git/", "tests/", "output/")) or "node_modules" in rel:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(content.splitlines(), 1):
                if self.DISALLOWED.search(line):
                    hits.append(f"{rel}:{lineno}: {line.strip()[:80]}")
        assert not hits, "发现通知/凭据关键词残留:\n" + "\n".join(hits)

    def test_yaml_has_no_notification_or_schedule_section(self, project_root):
        data = yaml.safe_load(
            (project_root / "config" / "bidding_scraper.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert "notification" not in data
        assert "schedule" not in data
        assert data["cleanup"]["enabled"] is False
        assert data["relevance"]["require_core"] is True
        assert data["offline"]["stale_days"] == 2
        assert data["download"]["prefetch"] is False

    def test_no_notification_dir_or_deploy_workflow_tracked(self, project_root):
        proc = subprocess.run(
            ["git", "ls-files"], cwd=project_root,
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        assert proc.returncode == 0
        tracked = proc.stdout.splitlines()
        assert not any("notification/" in name for name in tracked)
        assert not any("deploy.yml" in name for name in tracked)


class TestMacLocalSingleMachine:
    """mac 本地闭环：新增入口的存在性、可执行位、编码、零跨系统、配置与文档契约。"""

    COMMAND_FILES = (
        "更新数据.command",
        "安装环境.command",
        "查询.command",
        "安装每日更新.command",
        "打开_mac.command",
    )

    # 匹配 Windows 盘符绝对路径（如 D:\ 或 D:/），用前置字符排除 https:// 中的 "s:/"。
    WINDOWS_DRIVE = re.compile(r"(?:^|[^A-Za-z0-9_])[A-Za-z]:[\\/]")

    @staticmethod
    def _git_mode(project_root, rel):
        """读取文件在 git 索引中的权限位；尚未纳入索引时返回 None。"""
        proc = subprocess.run(
            ["git", "ls-files", "-s", "--", rel], cwd=project_root,
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        return proc.stdout.split()[0]

    @pytest.mark.parametrize("name", COMMAND_FILES)
    def test_command_file_exists_and_is_executable(self, project_root, name):
        path = project_root / name
        assert path.is_file(), f"缺少 mac 入口：{name}"
        mode = self._git_mode(project_root, name)
        if mode is None:
            # 尚未纳入 git 索引（本地开发中）时，退化为磁盘可执行位检查。
            assert os.access(path, os.X_OK), f"{name} 缺少可执行位"
        else:
            assert mode == "100755", f"{name} 索引权限为 {mode}，应为 100755"

    @pytest.mark.parametrize("name", COMMAND_FILES)
    def test_command_file_is_utf8_lf_without_bom(self, project_root, name):
        raw = (project_root / name).read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"{name} 含 UTF-8 BOM"
        assert b"\r" not in raw, f"{name} 含 CR，macOS bash 会报 bad interpreter"
        raw.decode("utf-8")  # 必须是合法 UTF-8，否则此处抛异常

    def test_update_command_stays_on_one_mac(self, project_root):
        text = (project_root / "更新数据.command").read_text(encoding="utf-8")
        assert 'cd "$(dirname "$0")"' in text
        assert "-m scripts.bidding_scraper.main" in text
        assert "pip3 install -r requirements.txt" in text
        assert "本次采集失败，已保留上一版产物" in text
        for forbidden in (
            "git push", "git commit", "git add", "xcopy", "BIDDING_SYNC_DIR",
        ):
            assert forbidden not in text, f"更新数据.command 含跨系统动作：{forbidden}"
        assert not self.WINDOWS_DRIVE.search(text), "更新数据.command 含 Windows 盘符路径"

    @pytest.mark.parametrize("name", ("查询.command", "打开_mac.command"))
    def test_query_commands_are_read_only(self, project_root, name):
        text = (project_root / name).read_text(encoding="utf-8")
        assert 'open "./output/index.html"' in text
        assert "Gatekeeper" in text and "chmod +x" in text
        code = "\n".join(
            line for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ).lower()
        for forbidden in ("python", "curl", "wget", "pip", "git push"):
            assert forbidden not in code, f"{name} 可执行行含 {forbidden}"

    def test_install_env_command(self, project_root):
        text = (project_root / "安装环境.command").read_text(encoding="utf-8")
        assert ".venv" in text
        assert "pip install -r requirements.txt" in text
        assert "python3" in text

    def test_publish_git_push_is_disabled(self, project_root):
        data = yaml.safe_load(
            (project_root / "config" / "bidding_scraper.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert data["publish"]["git_push"] is False

    def test_readme_documents_mac_local_loop(self, readme):
        for token in ("更新数据", "查询", "安装环境"):
            assert token in readme

    def test_readme_windows_channel_is_optional_only(self, readme):
        assert "BIDDING_SYNC_DIR" in readme
        assert "可选备用" in readme

    def test_launchd_plist_is_valid_xml_and_portable(self, project_root):
        path = project_root / "mac" / "每日自动更新.plist"
        assert path.is_file()
        raw = path.read_text(encoding="utf-8")
        assert "{{PROJECT_DIR}}" in raw
        assert "更新数据.command" in raw
        assert not self.WINDOWS_DRIVE.search(raw), "plist 含 Windows 绝对路径"

        root = ET.fromstring(raw)  # 必须是合法 XML
        assert root.tag == "plist"
        plist_dict = root.find("dict")
        assert plist_dict is not None
        children = list(plist_dict)
        pairs = {
            children[i].text: children[i + 1]
            for i in range(len(children) - 1)
            if children[i].tag == "key"
        }
        assert pairs["Label"].text == "com.biddinginformation.dailyupdate"
        assert pairs["RunAtLoad"].tag == "false"  # 默认不启用
        program = pairs["ProgramArguments"].find("string")
        assert program is not None and "{{PROJECT_DIR}}/更新数据.command" == program.text

    def test_gitattributes_pins_line_endings(self, project_root):
        """锁定 .command / .plist 为 LF、.bat 为 CRLF，覆盖 core.autocrlf 的机器差异。"""
        text = (project_root / ".gitattributes").read_text(encoding="utf-8")
        assert "*.command text eol=lf" in text
        assert "*.plist text eol=lf" in text
        # .bat 采用 text+eol=crlf：索引归一化 LF、工作区检出 CRLF，
        # 既保证 cmd.exe 可解析，又不会像 -text 那样把 CRLF 写进索引产生无关 diff。
        assert re.search(r"^\*\.bat\s+text eol=crlf\s*$", text, re.MULTILINE) is not None
