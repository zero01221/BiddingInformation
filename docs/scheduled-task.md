# 定时任务配置说明

## 功能说明

本项目支持通过 GitHub Actions 实现每日定时抓取招标信息，并自动发送到飞书机器人。

## 配置步骤

### 1. 创建飞书机器人

1. 打开飞书，进入需要接收通知的群聊
2. 点击群设置 → 群机器人 → 添加机器人
3. 选择"自定义机器人"
4. 填写机器人名称（如"招标信息助手"）
5. 复制 Webhook 地址（格式：`https://open.feishu.cn/open-apis/bot/v2/hook/xxx`）

### 2. 配置 GitHub Secrets

1. 打开 GitHub 仓库页面
2. 进入 Settings → Secrets and variables → Actions
3. 点击 "New repository secret"
4. 添加以下 Secret：
   - Name: `FEISHU_WEBHOOK`
   - Value: 你复制的飞书 Webhook 地址

### 3. 启用 GitHub Actions

1. 打开 GitHub 仓库页面
2. 进入 Actions 标签页
3. 找到 "招标信息每日抓取" 工作流
4. 点击 "Enable workflow"

### 4. 手动触发测试

1. 进入 Actions → "招标信息每日抓取"
2. 点击 "Run workflow"
3. 选择分支（通常是 main 或 master）
4. 点击 "Run workflow" 按钮

## 定时规则

默认配置为每天北京时间 8:00 自动运行。

如需修改时间，编辑 `.github/workflows/daily-crawl.yml`：

```yaml
on:
  schedule:
    # cron 格式：分 时 日 月 周（UTC时间）
    # 北京时间 8:00 = UTC 0:00
    - cron: '0 0 * * *'
```

常用时间参考：
- 每天 8:00：`0 0 * * *`
- 每天 9:00：`0 1 * * *`
- 每周一 8:00：`0 0 * * 1`
- 每天 8:00 和 18:00：`0 0,10 * * *`

## 本地定时任务（可选）

如果不想使用 GitHub Actions，也可以使用本地定时任务：

### Windows 任务计划程序

1. 打开"任务计划程序"
2. 创建基本任务
3. 触发器：每天 8:00
4. 操作：启动程序
   - 程序：`python`
   - 参数：`-m scripts.bidding_scraper --output output/bidding_feed.xml`
   - 起始于：`D:\my-project\IronTowerInformation`

### Linux/Mac cron

```bash
# 编辑 crontab
crontab -e

# 添加以下行（每天 8:00 运行）
0 8 * * * cd /path/to/IronTowerInformation && python -m scripts.bidding_scraper --output output/bidding_feed.xml
```

## 通知内容

飞书通知包含以下信息：
- 标题：今日新增招标信息数量
- 每条信息包含：来源、日期、标题、详情链接
- 最多显示 20 条

## 注意事项

1. GitHub Actions 免费额度：每月 2000 分钟
2. 飞书机器人有频率限制，建议每天最多发送 1-2 次
3. 如果长时间没有新信息，通知会自动跳过
4. 数据库保留 90 天内的记录（可在配置中修改）
