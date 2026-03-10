# 📕 xhs-auto-cy — 小红书自动化技能

使用 Playwright 驱动**真实 Chrome 浏览器**，自动执行小红书平台各类操作。

## 功能特性

- **图文/视频发布** — 自动填写标题、正文、话题，上传本地或远程图片/视频
- **笔记搜索** — 按关键词搜索，支持排序和类型筛选，返回结构化 JSON
- **笔记详情** — 抓取指定笔记的完整信息
- **自动评论** — 对指定笔记发布评论
- **通知抓取** — 获取点赞、评论、@提及、新增关注等通知
- **数据看板** — 导出创作者数据，支持 CSV 导出
- **实时监控** — 持续监控笔记数据变化
- **多账号管理** — 独立 Chrome Profile，Cookie 与登录态完全隔离
- **反检测策略** — playwright-stealth 注入 + 随机化操作时序，模拟真人行为

## 安装

### 1. 安装依赖

```bash
cd xhs-auto-cy
pip install -r requirements.txt
python3 -m playwright install chromium
```

### 2. 配置

首次运行自动生成配置文件 `~/.xhs-auto-cy/config.toml`：

```toml
[default]
profile = "default"
headless = false
chrome_channel = "chrome"

[timing]
min_action_delay_ms = 1000
max_action_delay_ms = 3000
typing_delay_ms = 120
```

## 命令速查

所有命令通过 `python3 scripts/xhs.py` 调用（在 `xhs-auto-cy/` 目录下）。

### 浏览器管理

```bash
python3 scripts/xhs.py browser launch [--profile default] [--headless]
python3 scripts/xhs.py browser restart [--profile default]
python3 scripts/xhs.py browser kill [--profile default]
python3 scripts/xhs.py browser status
```

### 登录

```bash
python3 scripts/xhs.py login [--profile default]          # QR 扫码登录
python3 scripts/xhs.py login --check [--profile default]   # 检查登录状态
```

### 发布图文

```bash
python3 scripts/xhs.py publish-image \
  --title "标题" --content "正文内容" \
  --images "img1.jpg" "img2.jpg" \
  [--image-urls "URL1" "URL2"] \
  [--topics "话题1" "话题2"] \
  [--preview] [--private] [--profile default]
```

### 发布视频

```bash
python3 scripts/xhs.py publish-video \
  --title "标题" --content "正文内容" \
  --video "video.mp4" \
  [--video-url "URL"] [--cover "cover.jpg"] \
  [--topics "话题1" "话题2"] \
  [--preview] [--private] [--profile default]
```

### 搜索笔记

```bash
python3 scripts/xhs.py search \
  --keyword "搜索关键词" \
  [--sort latest|popular|relevant] \
  [--type all|image|video] \
  [--limit 20] [--profile default]
```

### 笔记详情 / 评论

```bash
python3 scripts/xhs.py detail --url "https://www.xiaohongshu.com/explore/xxx"
python3 scripts/xhs.py comment --url "..." --text "评论内容"
```

### 通知 / 看板

```bash
python3 scripts/xhs.py notifications [--type mentions|likes|comments|follows] [--limit 50]
python3 scripts/xhs.py dashboard [--period 7d|30d] [--export-csv "./metrics.csv"]
```

### 账号管理

```bash
python3 scripts/xhs.py profile list
python3 scripts/xhs.py profile add <name> [--display-name "显示名"]
python3 scripts/xhs.py profile remove <name>
python3 scripts/xhs.py profile set-default <name>
```

## 项目结构

```
xhs-auto-cy/
├── SKILL.md                    # Claude Code 技能定义
├── README.md
├── requirements.txt
├── references/                 # 参考资料
└── scripts/
    ├── xhs.py                  # CLI 入口
    ├── actions/                # 各功能模块
    │   ├── auth.py             # 登录 & QR 扫码
    │   ├── publish_image.py    # 图文发布
    │   ├── publish_video.py    # 视频发布
    │   ├── search.py           # 搜索
    │   ├── note_detail.py      # 笔记详情
    │   ├── note_management.py  # 笔记管理（编辑/删除）
    │   ├── comment.py          # 评论
    │   ├── notifications.py    # 通知抓取
    │   ├── dashboard.py        # 数据看板
    │   └── monitor.py          # 实时监控
    ├── core/                   # 核心组件
    │   ├── browser_pool.py     # 浏览器实例管理
    │   ├── config_store.py     # 配置读写
    │   └── navigator.py        # 页面导航
    └── utils/                  # 工具函数
        ├── log.py              # 日志
        ├── media.py            # 图片/视频下载
        └── timing.py           # 随机延迟
```

## 反检测策略

- **playwright-stealth** 注入 — 隐藏 WebDriver 指纹
- **随机化操作时序** — 每次操作间加入 1-3 秒随机延迟，模拟真人节奏
- **打字延迟** — 逐字输入，每字约 120ms
- **持久化 Session** — 使用独立 Chrome Profile，保留登录态，避免频繁登录触发风控

## 注意事项

- 默认有头模式运行，需要 headless 请加 `--headless`
- 所有操作前自动检查登录状态，未登录时启动 QR 扫码流程
- 命令输出均为 JSON 格式，便于程序化处理
- 加 `--debug` 参数可查看详细日志
- 请合理控制操作频率，避免触发平台风控

## 依赖

- **Python 3.10+**
- **Playwright** — 浏览器自动化
- **playwright-stealth** — 反检测
- **httpx** — HTTP 客户端（下载远程图片/视频）
- **tomli_w** — TOML 配置读写

## 许可证

MIT License

---

<div align="center">
  <h3>联系作者</h3>
  <p>扫码加微信，交流反馈</p>
  <img src="assets/wechat-qr.jpg" alt="WeChat QR Code" width="200">
</div>
