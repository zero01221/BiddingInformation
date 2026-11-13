# coding=utf-8
"""构建 win / mac 两个自包含、免安装分发包。

用法::

    python scripts/build_packages.py                 # 生成到 packages/
    python scripts/build_packages.py --verify-only   # 只校验已有包

设计约定：
- 每个包解压即用，内含核心代码、配置、预生成产物与平台专属入口；
- win 包只含 .bat，mac 包只含 .command，互不混装；
- 不含 .git / tests / docs / 虚拟环境 / 缓存 / 日志 / 快照附件；
- mac 包内 .command 保留 0755 可执行位与 LF 行尾（.gitattributes 保证）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "packages"

EXCLUDE_PARTS = {
    "__pycache__", ".git", ".venv", "venv", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "snapshots", "attachments", "tests",
}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log"}
COMMON_DIRS = ("config", "scripts", "web")
COMMON_FILES = ("requirements.txt", "pyproject.toml", "LICENSE", ".gitattributes")
OUTPUT_FILES = ("index.html", "data.json", "bidding_feed.xml", "bidding_history.db")


def _excluded(path: Path) -> bool:
    if any(part in EXCLUDE_PARTS for part in path.parts):
        return True
    return path.suffix.lower() in EXCLUDE_SUFFIXES


def _add_file(zf: zipfile.ZipFile, path: Path, arcname: str) -> None:
    """写入单个文件；.command 显式保留 0755 可执行位。"""
    info = zipfile.ZipInfo(arcname)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o100755 if path.suffix == ".command" else 0o100644) << 16
    # 固定时间戳，保证同一份源码重复打包得到稳定产物
    info.date_time = (2026, 1, 1, 0, 0, 0)
    zf.writestr(info, path.read_bytes())


def _add_tree(zf: zipfile.ZipFile, directory: Path, prefix: str) -> None:
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or _excluded(path):
            continue
        rel = path.relative_to(directory).as_posix()
        _add_file(zf, path, f"{prefix}/{rel}")


def _package_readme(platform: str) -> str:
    if platform == "mac":
        return """铁塔招标信息 · macOS 版（免安装，解压即用）
================================================

【三步开始】
1. 首次使用：双击「安装环境.command」→ 自动建 .venv 并安装依赖（只需一次）。
   若未装 Python 3：到 python.org 下载 macOS 安装包（.pkg）双击安装。
2. 更新数据：双击「更新数据.command」→ 本机抓取并生成 output/index.html。
3. 查询：双击「查询.command」→ 用浏览器打开页面，零依赖、不联网、不改数据。

【只想看数据】直接双击 output/index.html，不需要 Python、不需要联网。

【验证能否正常抓取】
- 「环境自检.command」：只读检查 Python / 依赖 / 配置 / 数据库 / 产物 / 各源连通性。
- 「试抓测试.command」：逐源真实联网试抓并报告条数，不写库、不写产物。
- 可选「安装每日更新.command」：launchd 每天 08:00 自动跑「更新数据」，默认不启用。

【首次打开提示】
- 若提示没有权限：在终端执行 chmod +x *.command
- 若被 Gatekeeper 拦截：Finder 中右键文件 → 打开 → 再点「打开」
- 所有 .command 均为 UTF-8 无 BOM、LF 换行、0755 可执行位。

【本包内容】
安装环境 / 更新数据 / 查询 / 环境自检 / 试抓测试 / 打开_mac(兼容别名) / 安装每日更新
mac/每日自动更新.plist · config/ · scripts/ · web/ · output/(含 843 条历史数据与离线页)
本包不含 Windows 脚本、不含 .git、不含虚拟环境与测试文件。
"""
    return """铁塔招标信息 · Windows 版（免安装，解压即用）
================================================

【三步开始】
1. 首次使用：双击「安装环境.bat」→ 自动建 .venv 并安装依赖（只需一次）。
   若未装 Python 3：到 python.org 下载安装包，安装时勾选 "Add Python to PATH"。
2. 更新数据：双击「更新数据.bat」→ 本机抓取并生成 output\\index.html。
3. 查询：双击「查询.bat」→ 用默认浏览器打开页面，零依赖、不联网、不改数据。

【只想看数据】直接双击 output\\index.html，不需要 Python、不需要联网。

【验证能否正常抓取】
- 「环境自检.bat」：只读检查 Python / 依赖 / 配置 / 数据库 / 产物 / 各源连通性。
- 「试抓测试.bat」：逐源真实联网试抓并报告条数，不写库、不写产物。
- 「update.bat」为可选备用入口（含 git push / 同步盘复制），主流程不需要它。

【中文文件名提示】
若用 Windows 自带解压后中文文件名乱码，请改用 7-Zip / Bandizip / WinRAR 解压
（这些工具正确处理 UTF-8 文件名）。bat 文件为 UTF-8 + CRLF，脚本内已切到 65001 代码页。

【本包内容】
安装环境 / 更新数据 / 查询 / 环境自检 / 试抓测试 / update(备用)
config/ · scripts/ · web/ · output/(含 843 条历史数据与离线页)
本包不含 macOS 脚本、不含 .git、不含虚拟环境与测试文件。
"""


def build(platform: str, out_dir: Path) -> tuple[Path, dict]:
    root_name = f"BiddingInformation-{platform}"
    zip_path = out_dir / f"{root_name}.zip"
    entries: list[tuple[Path, str]] = []

    if platform == "win":
        scripts = sorted(ROOT.glob("*.bat"))
    else:
        scripts = sorted(ROOT.glob("*.command"))
    for path in scripts:
        entries.append((path, f"{root_name}/{path.name}"))
    if platform == "mac":
        plist = ROOT / "mac" / "每日自动更新.plist"
        if plist.exists():
            entries.append((plist, f"{root_name}/mac/{plist.name}"))

    for name in COMMON_FILES:
        path = ROOT / name
        if path.exists():
            entries.append((path, f"{root_name}/{name}"))
    for name in COMMON_DIRS:
        directory = ROOT / name
        if directory.is_dir():
            for path in sorted(directory.rglob("*")):
                if path.is_file() and not _excluded(path):
                    rel = path.relative_to(ROOT).as_posix()
                    entries.append((path, f"{root_name}/{rel}"))
    for name in OUTPUT_FILES:
        path = ROOT / "output" / name
        if path.exists():
            entries.append((path, f"{root_name}/output/{name}"))
    platform_dir = ROOT / "output" / platform
    if platform_dir.is_dir():
        for path in sorted(platform_dir.rglob("*")):
            if path.is_file() and not _excluded(path):
                rel = path.relative_to(ROOT).as_posix()
                entries.append((path, f"{root_name}/{rel}"))

    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path, arcname in entries:
            _add_file(zf, path, arcname)
        readme = zipfile.ZipInfo(f"{root_name}/使用说明.txt")
        readme.compress_type = zipfile.ZIP_DEFLATED
        readme.external_attr = 0o100644 << 16
        readme.date_time = (2026, 1, 1, 0, 0, 0)
        zf.writestr(readme, _package_readme(platform).encode("utf-8"))

    summary = verify(zip_path, platform)
    return zip_path, summary


def verify(zip_path: Path, platform: str) -> dict:
    root = f"BiddingInformation-{platform}"
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        infos = {i.filename: i for i in zf.infolist()}
        required = [
            f"{root}/使用说明.txt", f"{root}/requirements.txt",
            f"{root}/scripts/bidding_scraper/doctor.py",
            f"{root}/output/index.html", f"{root}/output/bidding_history.db",
        ]
        if platform == "win":
            required += [f"{root}/安装环境.bat", f"{root}/更新数据.bat",
                         f"{root}/查询.bat", f"{root}/环境自检.bat", f"{root}/试抓测试.bat"]
        else:
            required += [f"{root}/安装环境.command", f"{root}/更新数据.command",
                         f"{root}/查询.command", f"{root}/环境自检.command",
                         f"{root}/试抓测试.command", f"{root}/mac/每日自动更新.plist"]
        missing = [n for n in required if n not in names]
        assert not missing, f"缺少文件: {missing}"

        wrong = [n for n in names if n.endswith(".command" if platform == "win" else ".bat")]
        assert not wrong, f"混入另一平台脚本: {wrong}"
        dirty = [n for n in names if _excluded(Path(n)) or "/tests/" in n or n.startswith(".git")]
        assert not dirty, f"混入不应分发的文件: {dirty[:5]}"

        if platform == "mac":
            for name in names:
                if name.endswith(".command"):
                    mode = (infos[name].external_attr >> 16) & 0o777
                    assert mode & 0o111, f"缺少可执行位: {name}"
                    assert b"\r" not in zf.read(name), f"含 CR（会 bad interpreter）: {name}"

        html = zf.read(f"{root}/output/index.html").decode("utf-8")
        match = re.search(r'<script type="application/json" id="DATA">(.*?)</script>', html, re.S)
        assert match, "产物缺少内联数据块"
        items = json.loads(match.group(1))["items"]
        assert items, "产物内联数据为空"
        assert "fetch(" not in html and "XMLHttpRequest" not in html, "产物含外部请求"

    return {
        "files": len(names),
        "size": zip_path.stat().st_size,
        "items": len(items),
        "sha256": __import__("hashlib").sha256(zip_path.read_bytes()).hexdigest()[:16],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 win / mac 两个自包含分发包")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="输出目录")
    parser.add_argument("--verify-only", action="store_true", help="只校验已有包")
    args = parser.parse_args()

    for platform in ("win", "mac"):
        zip_path = args.out / f"BiddingInformation-{platform}.zip"
        if args.verify_only:
            summary = verify(zip_path, platform)
        else:
            zip_path, summary = build(platform, args.out)
        print(f"[{platform}] {zip_path}")
        print(f"    {summary['files']} 个文件 / {summary['size']/1024/1024:.2f} MiB / "
              f"内联 {summary['items']} 条 / sha256 {summary['sha256']} / 校验通过")
    print("两个包校验完成：win 只含 .bat，mac 只含 .command，零外部请求，产物可用。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
