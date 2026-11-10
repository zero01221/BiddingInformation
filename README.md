<div align="center">

# 铁塔招标信息聚合

**离线优先 · 零安装 · 免翻墙 · Windows / macOS 双击即用**

[![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg?style=flat-square)](LICENSE)

</div>

---

## 它是什么

一份 **零构建、零框架的纯静态 HTML**（`output/index.html`），数据以安全内联 JSON 嵌在页面里。
用系统自带浏览器双击打开，即可按地区 / 日期 / 文件名检索铁塔招投标公告、看摘要、跳原文、取源文件。

- `file://` 下**零网络请求**，断网可用；
- 终端**不需要** Python / Node / 命令行 / 依赖安装，也不需要 VPN 或任何在线托管；
- 不依赖 GitHub Pages 或任何境外服务；终端访问全流程不请求在线地址；
- 每天在 Windows 生产端重新生成一次，把 `output/` 里的文件覆盖到终端并刷新即可看到新数据。

> 形态与技术选型的最终裁定见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，需求见 [docs/PRD.md](docs/PRD.md)，
> 分平台图文操作见 [docs/使用说明.md](docs/使用说明.md)。与 PRD 表述不一致处以 ARCHITECTURE 为准。

---

## 快速开始（终端用户，0 安装步骤）

| 平台 | 打开方式 | 说明 |
| --- | --- | --- |
| **Windows** | 双击 `output/index.html`，或 `output/win/铁塔招标信息.html` | 推荐 Chrome / Edge |
| **macOS** | 双击 `output/index.html`，或 `output/mac/铁塔招标信息.html`；也可双击 `打开_mac.command` | Safari / Chrome；本页数据已内联，`file://` 不会触发跨域报错 |

各平台目录内附有中文 `使用说明_win.txt` / `使用说明_mac.txt`，包含首次打开、Gatekeeper、下载行为的说明。

### 页面功能

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
中文文件名按操作系统分支处理：Windows Chrome/Edge 用 `download` 属性；macOS Safari 降级为
「新标签打开 + 引导另存为」，并给出 UTF-8 文件名与 RFC 5987 编码提示，避免乱码与点了没反应。

---

## 数据从哪来、每天怎么更新

```
Windows 生产机（任务计划 每日 08:00）
   └─ update.bat
        ├─ 抓取 4 个数据源 → 相关性校验 / 地区打标 / 去重 / 下载档位
        ├─ 落库 SQLite output/bidding_history.db（历史全量保留）
        ├─ 生成 output/index.html（数据内联）+ data.json + RSS + win/mac 快照包
        ├─ git push origin master（研发侧版本托管，失败仅告警）
        └─ 复制 output/ 到国内同步目录（同步盘 / 文件传输 / 局域网 / U 盘）
                    ↓
        macOS / Windows 终端覆盖同名文件 → 刷新浏览器（同步盘日常 0 步）
```

- **生产端唯一**：Windows（具备国内网络、Python 依赖与 git 凭据）。**终端 mac 不抓取、不生成、不装环境**。
- **每日更新**：把 `update.bat` 加入「Windows 任务计划程序」，触发器设为每日 08:00 (Asia/Shanghai)，
  「起始于」填项目根目录；也可以随时手动双击运行。详见 [docs/使用说明.md](docs/使用说明.md)。
- **版本托管**：`git push` 只用于研发侧代码/数据托管，与终端入口完全解耦；push 失败**仅告警不阻断**，
  本地产物与同步目录照常可用。
- **国内文件通道**：设置环境变量 `BIDDING_SYNC_DIR`（或配置 `publish.sync_dir`）指向同步盘目录，
  `update.bat` 会自动复制 `output/`；不设置则跳过，手动覆盖文件同样有效。
- **全失败降级**：产物先写临时文件，校验条数与内联 JSON 合法后才统一替换；异常或所有数据源
  本次均失败时**保留上一版** `index.html`，页面继续显示「数据截至」历史日期。

### 「数据截至」是什么意思

「数据更新时间」= 本次产物生成时刻；「数据截至」= 库中成功采集的最晚公告日。
离线 HTML 不会自己变新：想看最新数据，需要从 Windows 端或同步盘重新取一次
`output/index.html` 覆盖本地文件并刷新。**本期不做任何消息推送**，用户主动打开才看到更新。

---

## 数据源

| 层级 | 数据源 | 状态 | 备注 |
| --- | --- | --- | --- |
| 主源 P0 | 中国招标投标公共服务平台 `cebpubservice` | 启用 | 全国数据，地区只打标不过滤 |
| 辅源 P0 | 中国铁塔电子采购平台 `chinatowercom` | 启用 | 历史库 684 条 |
| 辅源 P0 | 乙方宝 `yfbzb` | 启用 | 历史长期 0 条，成因为反爬/页面结构，**需联网复测**；条数在页面数据源状态中如实可见 |
| 云南优先 P0 | 云南省公共资源交易中心 `ynggzy` | 启用 | 旧版实现完整但零注册，本版已补 `__init__.py` 导出与注册分支 |
| P1 | `ccgp` / `tower_com_cn` / `miit_txzbqy` | 禁用 | 分别为严格反爬 / 连接超时 / SPA 接口待逆向；本轮离线实施无法复测，保持禁用并写明结论，复测通过后把 `enabled` 改为 `true` 即可启用 |

地区词表单一事实源为 `config/regions.json`（全国省份 + 地州市 + 云南 16 州市），Python 打标与前端下拉共用。

---

## win / mac 版本区分（用户可感知）

| 维度 | Windows | macOS |
| --- | --- | --- |
| 一键入口 | `update.bat`（生产端：抓取+生成+推送+同步复制） | `打开_mac.command`（仅 `open`，零依赖不调用 Python） |
| 离线包 | `output/win/铁塔招标信息.html` + `使用说明_win.txt` | `output/mac/铁塔招标信息.html` + `使用说明_mac.txt` |
| 中文名下载 | `<a download>` 直接保存 | Safari 降级新标签 + 引导另存为，附 UTF-8 文件名 |
| 首次打开 | 直接双击 | `.command` 需 `chmod +x`；Gatekeeper 拦截时「右键 → 打开」；**最稳是直接双击 HTML** |

数据、模板与逻辑完全同源，只是入口与下载行为按平台分支，避免维护两份二进制。

---

## 开发 / 维护（仅 Windows 生产端）

环境：Python 3.13+。`pip install -r requirements.txt`；开发测试用 `pip install -e ".[dev]"`。

```bash
# 完整流程：抓取 → 处理 → 落库 → 导出 → 构建（原子写）
python -m scripts.bidding_scraper.main

# 不联网，只用现有数据库重建全部产物（离线验证）
python -m scripts.bidding_scraper.main --no-crawl

# 只打印不写产物 / 统计 / 列出记录
python -m scripts.bidding_scraper.main --dry-run
python -m scripts.bidding_scraper.main --stats
python -m scripts.bidding_scraper.main --list --days 7

# 静态构建薄封装 / 本地预览（127.0.0.1:8080，仅调试）
python scripts/serve_web.py --output output/index.html
python scripts/serve_web.py

# QA 回归（测试由 QA 阶段独立维护）
pytest
```

### 项目结构

```
BiddingInformation/
├── config/
│   ├── bidding_scraper.yaml       # 数据源 / 关键词 / 下载档位 / 发布 / 离线策略
│   └── regions.json               # 全国省份·地州市映射（Python 与前端共用）
├── scripts/
│   ├── bidding_scraper/
│   │   ├── crawlers/              # 7 个数据源爬虫（4 启用 / 3 休眠）
│   │   ├── config.py  models.py  database.py  filters.py  base_crawler.py
│   │   ├── dedup.py  relevance.py  region_tagger.py
│   │   ├── download_resolver.py  snapshot.py
│   │   ├── exporter.py  builder.py  pipeline.py  output.py  utils.py  logger.py
│   │   └── main.py
│   └── serve_web.py               # 本地预览 / 静态构建薄封装
├── web/                           # index.template.html · app.js · styles.css（内联进产物）
├── output/
│   ├── index.html                 # 单文件离线页（数据已安全内联，入库）
│   ├── data.json                  # 分离数据产物（入库）
│   ├── bidding_feed.xml           # RSS
│   ├── bidding_history.db         # SQLite 历史库（入库，请勿删除）
│   ├── win/  mac/                 # 平台专属离线包 + 中文使用说明
│   └── snapshots/  attachments/   # L2/L3 产物（按 dedup_key 命名，忽略入库）
├── update.bat                     # Windows 每日更新入口
├── 打开_mac.command               # macOS 零依赖一键打开
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
| `publish.sync_dir` | 空 | 国内同步目录；`update.bat` 优先读环境变量 `BIDDING_SYNC_DIR` |
| `offline.stale_days` | `2` | 数据截至超过该天数页面标黄 |
| `sources.*.enabled` | — | 数据源开关 |

---

## 安全与历史数据

- **通知链路已彻底移除**：配置、代码、脚本与部署 workflow 中的推送逻辑全部删除，
  仓库不再含明文推送凭据。**安全提醒**：历史 git 提交中曾出现过真实机器人凭据，
  仅删文件不能撤销泄露，需由仓库所有者在对应平台后台**作废该机器人凭据**。
- **843 条历史无损保留**：schema 自动迁移时一次性回填 `dedup_key`、地区标签与 `date_valid`，
  并加 `UNIQUE(dedup_key)`；清理默认禁用且只按 `created_at`。
- **XSS 防护**：内联数据经 `_json_for_script()` 转义 `< > &` 与 U+2028/2029，放在
  `<script type="application/json">` 中由 `JSON.parse(textContent)` 读取；
  页面渲染一律 `createElement` + `textContent`，不拼 `innerHTML`；外链仅 http/https 且带
  `rel="noopener noreferrer"`。

---

## 已知「需验证」项（本轮离线实施未联网）

1. 各源当前可用性（老站 API、聚合站反爬、云南站接口）；
2. 乙方宝 0 条的确切成因与恢复情况；
3. 3 个休眠源复测后能否启用；
4. GitHub 仓库真实写权限（`update.bat` 会尝试 push，失败仅告警）；
5. 用户最终选择哪一个国内文件通道（不影响任何代码）。

---

## 许可证

GPL-3.0 License
