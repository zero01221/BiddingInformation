## 项目概述

铁塔招标信息推送（IronTowerInformation），基于 [TrendRadar](https://github.com/sansan0/TrendRadar) 二次开发。自动监控全国/区域铁塔招标信息，支持关键词筛选和多渠道推送（企业微信、飞书、钉钉、Telegram、邮件）。

## 技术栈

- **语言**: Python 3.12+
- **包管理**: uv（pyproject.toml + uv.lock）
- **核心依赖**: requests, PyYAML, feedparser, boto3, litellm, fastmcp, json-repair, tenacity
- **构建系统**: hatchling
- **MCP 服务**: fastmcp + websockets（HTTP 模式，端口 3333）

## 目录结构

```
/workspace/projects/
├── trendradar/           # 主包
│   ├── __main__.py       # CLI 主入口（python -m trendradar）
│   ├── context.py        # 应用上下文
│   ├── core/             # 配置加载、分析、调度
│   ├── crawler/          # 数据抓取模块
│   ├── notification/     # 多渠道推送（企微/飞书/钉钉/TG/邮件）
│   ├── report/           # 报告生成
│   ├── storage/          # 数据存储
│   ├── ai/               # AI 分析模块
│   └── utils/            # 工具函数
├── mcp_server/           # MCP 服务端
├── config/               # 配置文件
│   ├── config.yaml       # 主配置
│   ├── frequency_words.txt # 关键词列表
│   ├── timeline.yaml     # 时间线配置
│   └── ai_filter/        # AI 过滤配置
├── scripts/              # 脚本
│   ├── bidding_scraper.py  # 招标抓取
│   ├── coze-deploy-setup.sh # 部署依赖安装
│   └── coze-deploy-run.sh   # 部署服务启动（端口 5000）
├── output/               # 输出目录
├── docker/               # Docker 配置
├── index.html            # 报告模板（静态 HTML）
├── start-http.sh         # MCP HTTP 服务启动脚本
├── pyproject.toml        # 项目配置
└── requirements.txt      # 依赖清单
```

## 关键入口 / 核心模块

- **CLI 入口**: `python -m trendradar` 或 `trendradar`（安装后）
- **MCP 服务**: `python -m mcp_server.server` 或 `trendradar-mcp`
- **HTTP 模式**: `bash start-http.sh`（端口 3333）
- **招标抓取脚本**: `scripts/bidding_scraper.py`
- **主配置**: `config/config.yaml`

## 运行与预览

- 本项目为后端/CLI 工具，无可预览的 Web 界面
- 运行方式：`uv run python -m trendradar`
- MCP 服务：`uv run python -m mcp_server.server --transport http --host 0.0.0.0 --port 3333`

## 部署配置

- 部署类型：service（HTTP 服务）
- 部署入口：MCP HTTP 服务
- 部署端口：5000
- 构建脚本：`scripts/coze-deploy-setup.sh`（安装依赖）
- 运行脚本：`scripts/coze-deploy-run.sh -p 5000`（启动 MCP HTTP 服务）

## 用户偏好与长期约束

- Python 项目必须使用 uv 管理依赖和虚拟环境
- 禁止使用 npm/yarn
- 配置文件位于 config/ 目录

## 常见问题和预防

- 虚拟环境未创建时需先运行 `uv sync`
- MCP HTTP 服务默认端口 3333，注意不要与系统端口冲突
- 推送渠道需在 GitHub Secrets 或环境变量中配置 Webhook/凭据

## 招标爬虫功能说明

`scripts/bidding_scraper.py` 是招标信息爬虫脚本，主要功能：

### 数据源
1. **中国政府采购网** - 使用搜索 API，通过 URL 参数限制地区为云南（displayZone=云南&zoneId=53）
2. **中国采购与招标网** - POST 搜索，关键词"铁塔"
3. **云南省公共资源交易中心** - 专用 API，网站本身全是云南省信息，只需匹配铁塔关键词
4. **乙方宝（全国招标采购信息平台）** - 搜索全国数据，过滤云南地区

### 过滤逻辑
- **核心关键词**：铁塔、塔桅、通信铁塔等相关词汇
- **地区过滤**：
  - 云南省公共资源交易中心：网站本身全是云南信息，无需检查地区
  - 中国政府采购网：通过 URL 参数限制地区，无需检查地区
  - 其他网站：检查标题/描述/地区信息是否包含云南相关关键词
- **正文匹配**：支持访问详情页提取正文中的地区信息（用于标题无地区信息的情况）

### 运行方式
```bash
# 生成 RSS feed
python scripts/bidding_scraper.py

# 只打印结果，不写文件
python scripts/bidding_scraper.py --dry-run

# 指定输出文件
python scripts/bidding_scraper.py --output output/bidding_feed.xml
```
