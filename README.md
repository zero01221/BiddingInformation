<div align="center">

# 铁塔招标信息聚合

**一台 mac 本地闭环 · 更新与查询分离 · 页面零安装 · 免翻墙 · 双击即用**

[![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg?style=flat-square)](LICENSE)

</div>

---

## 它是什么

一份 **零构建、零框架的纯静态 HTML**（`output/index.html`），数据以安全内联 JSON 嵌在页面里。
用系统自带浏览器双击打开，即可按地区 / 日期 / 文件名检索铁塔招投标公告、看摘要、跳原文、取源文件。

- **本版是 mac 单机方案**：抓取、处理、落库、生成、查看，**全部只在同一台 mac 上完成**；
- 不需要第二台机器，不需要 Windows 生产机，不需要同步盘，不需要 VPN，不需要 GitHub 在线访问；
- `file://` 下**零网络请求**，断网可看最近一次数据；
- 「查询」这一步**零依赖**：不需要 Python / Node / 命令行 / 依赖安装；
- 只有「更新数据」这一步需要一次性装一点简单环境（Python 3 + `requirements.txt`）。

> 形态与技术选型见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，需求见 [docs/PRD.md](docs/PRD.md)，
> 面向用户的图文操作见 [docs/使用说明.md](docs/使用说明.md)。
> **运行时形态以本文与「使用说明」为准**：架构文档中描述 Windows 生产机 / 同步盘的章节
> 自本版起仅代表可选备用入口，不再是主流程。

---

## 快速开始：三条命令，各司其职

| 步骤 | 命令（mac 双击） | 频率 | 干什么 | 依赖 |
| --- | --- | --- | --- | --- |
| ① 一次性准备 | `安装环境.command` | **仅首次一次** | 创建项目内 `.venv` 并 `pip install -r requirements.txt` | Python 3 |
| ② **更新数据** | `更新数据.command` | 每天 / 想更新时 | 抓取 → 相关性校验 → 落库 → 生成 `output/index.html` 等全部产物 | ① 的环境 |
| ③ **查询** | `查询.command` | 随时 | 用默认浏览器打开本地 `output/index.html`，**不抓取、不联网、不改数据** | 零依赖 |

`打开_mac.command` 是 `查询.command` 的兼容别名，内容等价，保留给旧书签使用。

**最省事的用法**：其实 ③ 也可以直接双击 `output/index.html`（或 `output/mac/铁塔招标信息.html`），
连 `.command` 都不用跑。`file://` 打开即可，数据已内联，不会触发跨域报错。

### 首次运行 `.command` 的提示

- 双击若提示「没有权限」，在「终端」里执行一次 `chmod +x *.command`；
- 若被 Gatekeeper 拦截，在 Finder 中**右键该文件 → 打开 → 再点「打开」**；
- 双击后终端窗口会在结束时停留（「按任意键关闭窗口…」），方便看清中文提示。

### 一次性安装环境（用户许可的「一点简单环境」）

mac 自带或可免费安装的 Python 3 即可，二选一：

1. 到 Python 官网 `python.org` 下载 macOS 安装包（`.pkg`），双击安装；
2. 已装 Homebrew 时，终端执行 `brew install python3`。

然后双击 `安装环境.command`：它会在项目内创建 `.venv/`（已被 `.gitignore` 忽略，不污染系统 Python）
并安装 `requests / PyYAML / beautifulsoup4 / lxml / tenacity`。
安装成功后再双击 `更新数据.command` 即可。依赖缺失时 `更新数据.command` 会打印可操作的中文指引，
**不会静默失败**。

---

## 页面功能

| 功能 | 说明 |
| --- | --- |
| 三类筛选（取交集） | **地区**（多选，默认只勾「云南」；可勾多个省，或选「全部（全国）」）、**日期区间**、**文件名关键字** |
| 日期区间约束 | 结束日期不能早于起始日期：日期控件用 min/max 直接限制，手输非法值会自动对齐并给出明确提示 |
| 四字段 | 每条显示 文件名 / 日期 / 来源 / 摘要，缺失时显示明确占位（「暂无摘要」等） |
| 两个按钮 | 「跳转出处」打开库中原始公告 URL；「下载源招标文件」按 L1~L4 档位下载 |
| 公告类型 | 全类型收录，**不设类型筛选控件**，`bid_type` 只作标签，不改变结果集 |
| 数据新鲜度 | 顶部显示「数据更新时间 / 数据截至」，超过 `offline.stale_days`（默认 2 天）标黄提示 |

### 下载降级 L1~L4

| 档 | 含义 | 按钮行为 |
| --- | --- | --- |
| L1 | 原站提供附件直链 | 下载原始文件，保留中文文件名 |
| L2 | 抓取时预存了附件副本 | 下载 `output/attachments/` 中的源文件副本 |
| L3 | 原站不提供下载 | 下载 `output/snapshots/` 中的详情页快照，并明确标注 |
| L4 | 连快照也没有 | **按钮禁用**并提示「该来源不提供下载，请前往出处查看」 |

硬规则：L4 不伪造文件、不产生 404、不静默失败；每条的档位与产物 URL 都会持久化并显示在页面上。
中文文件名按浏览器分支处理：macOS Safari 降级为「新标签打开 + 引导另存为」，
并给出 UTF-8 文件名与 RFC 5987 编码提示，避免乱码与点了没反应。

---

## 数据从哪来、每天怎么更新

```
同一台 mac（本机闭环）
  ├─ 安装环境.command   一次性：python3 -m venv .venv + 安装 requirements.txt
  ├─ 更新数据.command   python -m scripts.bidding_scraper.main
  │     ├─ 抓取 4 个已启用数据源 → 相关性校验 / 地区打标 / 去重 / 下载档位
  │     ├─ 落库 SQLite output/bidding_history.db（历史全量保留）
  │     └─ 原子写 output/index.html（数据内联）+ data.json + RSS + win/mac 平台包
  └─ 查询.command       open ./output/index.html（零依赖，只读）
```

- **两条命令职责分离**：`更新数据.command` 是唯一会联网、会写数据的入口；
  `查询.command` 只用系统自带 `open`，不调用 Python、不联网、不改数据。
- **国内站点 mac 直连可达**，抓数不需要 VPN；页面查看全程不需要联网。
- **不上传、不同步**：主流程不推送到远端仓库、不复制到任何同步目录、不依赖第二台机器。
  配置 `publish.git_push` 已置为 `false`（键保留仅为兼容可选的 Windows 备用入口）。
- **全失败降级**：产物先写临时文件，校验条数与内联 JSON 合法后才统一替换；
  异常或所有数据源本次均失败时**保留上一版** `index.html`，并提示「本次采集失败，已保留上一版产物」。

### 可选：每天 08:00 自动更新（默认不启用）

用户最初的「每天自动更新」诉求保留为**可选增强**，不装就绝不会自动运行：

1. 双击 `安装每日更新.command`；
2. 它把模板 `mac/每日自动更新.plist` 中的 `{{PROJECT_DIR}}` 替换为本机真实绝对路径，
   生成 `~/Library/LaunchAgents/com.biddinginformation.dailyupdate.plist` 并 `launchctl load`；
3. 任务是 `StartCalendarInterval` 每日 08:00、`RunAtLoad=false`，只调用本机的 `更新数据.command`。

关闭：`launchctl unload -w ~/Library/LaunchAgents/com.biddinginformation.dailyupdate.plist` 后删除该文件。
日志写入 `output/launchd.out.log` / `output/launchd.err.log`（日志文件已忽略入库）。

### 「数据截至」是什么意思

「数据更新时间」= 本次产物生成时刻；「数据截至」= 库中成功采集的最晚公告日。
离线 HTML 不会自己变新：想看最新数据，请**双击「更新数据」后刷新本页**。
本期不做任何消息推送，用户主动打开才看到更新。

---

## 数据源

| 层级 | 数据源 | 状态 | 备注 |
| --- | --- | --- | --- |
| 主源 P0 | 中国招标投标公共服务平台 `cebpubservice` | 启用 | 全国数据，地区只打标不过滤 |
| 辅源 P0 | 中国铁塔电子采购平台 `chinatowercom` | 启用 | 历史库 684 条 |
| 辅源 P0 | 乙方宝 `yfbzb` | 启用 | 历史长期 0 条，成因为反爬/页面结构，**需联网复测**；条数在页面数据源状态中如实可见 |
| 云南优先 P0 | 云南省公共资源交易中心 `ynggzy` | 启用 | 实现完整并已注册 |
| P1 | `ccgp` / `tower_com_cn` / `miit_txzbqy` | 禁用 | 分别为严格反爬 / 连接超时 / SPA 接口待逆向；本轮离线实施无法复测，保持禁用并写明结论，复测通过后把 `enabled` 改为 `true` 即可启用 |

地区词表单一事实源为 `config/regions.json`（全国省份 + 地州市 + 云南 16 州市），Python 打标与前端下拉共用。

---

## 可选备用：Windows 入口

**这不是主流程，mac 用户完全可以忽略本节。** `update.bat` 只是保留下来的 Windows 备用入口，
行为不变；不运行它不影响 mac 本地方案的任何功能。

- 它仍会尝试 `git push origin master`（失败仅告警、不阻断产物）；
- 它支持环境变量 `BIDDING_SYNC_DIR`（或配置 `publish.sync_dir`）指向同步盘目录，
  设置后才复制 `output/`；**未设置就跳过复制、不阻断**。`BIDDING_SYNC_DIR` 只属于这个备用入口，
  mac 本地方案不需要它，也不需要任何同步盘 / 文件传输 / 局域网 / U 盘通道；
- `output/win/` 目录里保留 Windows 平台的离线包与中文说明，供有需要的 Windows 用户使用。

---

## 开发 / 维护

环境：Python 3.9+（推荐 3.13）。`pip install -r requirements.txt`；开发测试用 `pip install -e ".[dev]"`。
以下 CLI 与 `更新数据.command` 调用的是同一套跨平台核心逻辑：

```bash
# 完整流程：抓取 → 处理 → 落库 → 导出 → 构建（原子写）
python -m scripts.bidding_scraper.main

# 不联网，只用现有数据库重建全部产物（离线验证，843 条历史无损）
python -m scripts.bidding_scraper.main --no-crawl

# 只打印不写产物 / 统计 / 列出记录
python -m scripts.bidding_scraper.main --dry-run
python -m scripts.bidding_scraper.main --stats
python -m scripts.bidding_scraper.main --list --days 7

# 本地静态预览（127.0.0.1:8080，可选；file:// 双击才是零依赖基线）
python scripts/serve_web.py --port 8080

# QA 回归
pytest
```

### 项目结构

```
BiddingInformation/
├── 安装环境.command               # ① 一次性装 Python 依赖到 .venv（mac 双击）
├── 更新数据.command               # ② 抓取 + 生成全部产物（mac 双击，唯一写数据入口）
├── 查询.command                   # ③ 只打开 output/index.html（mac 双击，零依赖）
├── 打开_mac.command               # ③ 的兼容别名（同样零依赖）
├── 安装每日更新.command           # 可选：安装 launchd 每日 08:00 自动更新
├── mac/每日自动更新.plist         # launchd 模板，路径用 {{PROJECT_DIR}} 占位
├── .gitattributes                 # 强制 .command/.sh 为 LF，避免 mac 上 bad interpreter
├── update.bat                     # 可选备用：Windows 入口（非主流程）
├── config/
│   ├── bidding_scraper.yaml       # 数据源 / 关键词 / 下载档位 / 发布 / 离线策略
│   └── regions.json               # 全国省份·地州市映射（Python 与前端共用）
├── scripts/
│   ├── bidding_scraper/           # 抓取/处理/落库/导出/构建（纯 Python，跨平台）
│   └── serve_web.py               # 本地预览 / 静态构建薄封装
├── web/                           # index.template.html · app.js · styles.css（内联进产物）
├── output/
│   ├── index.html                 # 单文件离线页（数据已安全内联，入库）
│   ├── data.json                  # 分离数据产物（入库）
│   ├── bidding_feed.xml           # RSS
│   ├── bidding_history.db         # SQLite 历史库（入库，请勿删除）
│   ├── win/  mac/                 # 平台专属离线包 + 中文使用说明
│   └── snapshots/  attachments/   # L2/L3 产物（按 dedup_key 命名，忽略入库）
└── docs/                          # PRD · ARCHITECTURE · 使用说明
```

### 关键配置

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `relevance.require_core` | `true` | 入库前强制 `keywords.core` / `industry` 校验，不要求云南 |
| `filter.days_limit` | `7` | 抓取时只保留最近 N 天；历史库不受影响 |
| `cleanup.enabled` | `false` | **默认禁用**；即便启用也只按 `created_at` 清理，绝不按公告日期删历史 |
| `download.prefetch` | `false` | 离线优先，默认不联网预取附件与快照 |
| `download.tiers.L1~L4` | 见配置 | 前后端共用的档位文案 |
| `publish.git_push` | `false` | mac 本地闭环不推送；键保留仅为兼容 Windows 备用入口 |
| `publish.sync_dir` | 空 | 仅 Windows 可选通道；`BIDDING_SYNC_DIR` 亦只属于该备用入口 |
| `offline.stale_days` | `2` | 数据截至超过该天数页面标黄 |
| `sources.*.enabled` | — | 数据源开关 |

---

## 安全与历史数据

- **通知链路已彻底移除**：配置、代码、脚本中的推送逻辑全部删除，仓库不再含明文推送凭据。
  **安全提醒**：历史 git 提交中曾出现过真实机器人凭据，仅删文件不能撤销泄露，
  需由仓库所有者在对应平台后台**作废该机器人凭据**。
- **843 条历史无损保留**：schema 自动迁移时一次性回填 `dedup_key`、地区标签与 `date_valid`，
  并加 `UNIQUE(dedup_key)`；清理默认禁用且只按 `created_at`。
- **XSS 防护**：内联数据经 `_json_for_script()` 转义 `< > &` 与 U+2028/2029，放在
  `<script type="application/json">` 中由 `JSON.parse(textContent)` 读取；
  页面渲染一律 `createElement` + `textContent`，不拼 `innerHTML`；外链仅 http/https 且带
  `rel="noopener noreferrer"`。

---

## 已知「需验证」项

1. 本机是 Windows 开发机，`.command` 只做了 `bash -n` 语法检查与文本契约校验，
   **mac 上双击运行、Gatekeeper 放行、launchd 定时触发均需在真实 mac 上验证**；
2. 各源当前可用性（老站 API、聚合站反爬、云南站接口）与 mac 直连可达性；
3. 乙方宝 0 条的确切成因与恢复情况；3 个休眠源复测后能否启用；
4. 官方 Python pkg / Homebrew 安装路径在用户具体 mac 机型上的差异；
5. `docs/PRD.md` 与 `docs/ARCHITECTURE.md` 仍保留早期跨系统选型的描述，
   运行时形态以本 README 与 `docs/使用说明.md` 为准。

---

## 许可证

GPL-3.0 License
