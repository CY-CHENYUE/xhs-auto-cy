---
name: xhs-auto-cy
description: >-
  小红书自动化工具，通过 Playwright 驱动真实 Chrome 浏览器执行小红书平台操作。
  当用户需要对小红书执行实际操作时使用，包括：
  (1) 发布——"发小红书"、"发布到小红书"、"帮我发一篇小红书笔记"、"上传图文/视频到小红书"；
  (2) 搜索——"搜小红书"、"在小红书搜一下"、"小红书上搜XX"、"查找小红书笔记"；
  (3) 互动——"帮我评论这条小红书"、"回复小红书评论"；
  (4) 数据——"看看小红书数据"、"导出小红书看板"、"小红书通知有哪些"；
  (5) 账号——"登录小红书"、"切换小红书账号"。
  注意：仅撰写小红书文案但不需要发布时，不要触发此技能。
version: 1.0.0
tools: Bash, Read
metadata: {"clawdbot":{"emoji":"📕","homepage":"https://github.com/CY-CHENYUE/xhs-auto-cy","requires":{"bins":["python3"],"packages":["playwright","playwright-stealth","httpx","tomli_w"]}}}
---

# 小红书自动化 (xhs-auto-cy)

使用 Playwright 驱动真实 Chrome 浏览器，自动执行小红书各类操作。

## 首次使用

首次运行时会自动安装依赖和浏览器。如依赖未安装，先执行：

```bash
pip install -r {baseDir}/requirements.txt && python3 -m playwright install chromium
```

## 命令速查

所有命令通过 `python3 {baseDir}/scripts/xhs.py` 调用。

### 1. 浏览器管理

```bash
# 启动浏览器
python3 {baseDir}/scripts/xhs.py browser launch [--profile default] [--headless]

# 重启 / 关闭 / 查看状态
python3 {baseDir}/scripts/xhs.py browser restart [--profile default]
python3 {baseDir}/scripts/xhs.py browser kill [--profile default]
python3 {baseDir}/scripts/xhs.py browser status
```

### 2. 登录

```bash
# QR 扫码登录（有头模式下直接在浏览器扫码）
python3 {baseDir}/scripts/xhs.py login [--profile default]

# 检查登录状态
python3 {baseDir}/scripts/xhs.py login --check [--profile default]
```

### 3. 发布图文

```bash
python3 {baseDir}/scripts/xhs.py publish-image \
  --title "标题" --content "正文内容" \
  --images "img1.jpg" "img2.jpg" \
  [--image-urls "URL1" "URL2"] \
  [--topics "话题1" "话题2"] \
  [--preview] [--private] [--profile default]
```

- `--preview`: 填充表单但不提交，用于确认内容
- `--private`: 发布为仅自己可见（私密笔记），确认无误后可手动改为公开
- `--image-urls`: 自动下载远程图片后上传

### 4. 发布视频

```bash
python3 {baseDir}/scripts/xhs.py publish-video \
  --title "标题" --content "正文内容" \
  --video "video.mp4" \
  [--video-url "URL"] \
  [--cover "cover.jpg"] \
  [--topics "话题1" "话题2"] \
  [--preview] [--private] [--profile default]
```

- `--private`: 发布为仅自己可见（私密笔记）

### 5. 搜索笔记

```bash
python3 {baseDir}/scripts/xhs.py search \
  --keyword "搜索关键词" \
  [--sort latest|popular|relevant] \
  [--type all|image|video] \
  [--limit 20] [--profile default]
```

返回 JSON 数组，包含笔记 ID、标题、作者、互动数据。

### 6. 笔记详情

```bash
python3 {baseDir}/scripts/xhs.py detail \
  --url "https://www.xiaohongshu.com/explore/xxx" \
  [--xsec-token "TOKEN"] [--profile default]
```

注意：搜索结果中的 url 字段已包含 xsec_token 参数，直接使用即可。如单独传入 `--xsec-token`，会自动拼接到 URL。

### 7. 自动评论

```bash
python3 {baseDir}/scripts/xhs.py comment \
  --url "https://www.xiaohongshu.com/explore/xxx" \
  --text "评论内容" \
  [--profile default]
```

### 8. 通知抓取

```bash
python3 {baseDir}/scripts/xhs.py notifications \
  [--type mentions|likes|comments|follows] \
  [--limit 50] [--profile default]
```

### 9. 数据看板

```bash
python3 {baseDir}/scripts/xhs.py dashboard \
  [--period 7d|30d] \
  [--export-csv "./metrics.csv"] \
  [--profile default]
```

### 10. 账号管理

```bash
python3 {baseDir}/scripts/xhs.py profile list
python3 {baseDir}/scripts/xhs.py profile add <name> [--display-name "显示名"]
python3 {baseDir}/scripts/xhs.py profile remove <name>
python3 {baseDir}/scripts/xhs.py profile set-default <name>
```

## 多账号支持

每个 profile 对应独立的 Chrome 用户目录，Cookie 和登录态完全隔离。

```bash
# 添加新账号
python3 {baseDir}/scripts/xhs.py profile add work --display-name "工作号"

# 用指定账号发布
python3 {baseDir}/scripts/xhs.py publish-image --profile work --title "..." --content "..." --images "..."
```

## 配置文件

配置保存在 `~/.xhs-auto-cy/config.toml`，首次运行自动生成。支持的配置项：

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

## 注意事项

- 默认有头模式运行，需要 headless 请加 `--headless`
- 所有操作前会自动检查登录状态，未登录时启动 QR 扫码流程
- detail/comment 遇到安全拦截时会自动探测会话是否过期，过期则触发扫码重新登录并重试（最多 1 次）
- detail 内置限速（3-8 秒随机间隔）和自动重试（最多 4 次，指数退避 5s/12s/25s）
- comment 内置自动重试（最多 2 次，退避 10s）
- 命令输出均为 JSON 格式，便于程序化处理
- 加 `--debug` 参数可查看详细日志

## 批量操作指引

当需要批量抓取笔记详情（如 search → 逐条 detail）时，遵循以下流程：

1. **开始前**：执行 `login --check` 确认登录状态，失败则先扫码登录
2. **固定会话**：整个批量任务使用同一 `--profile`，不要中途切换
3. **逐条执行**：单线程串行调用 detail，代码内置了 3-8 秒随机间隔，无需额外等待
4. **失败处理**：
   - detail 内置自动重试（最多 4 次尝试，指数退避），无需手动重试
   - 单条失败不中断批量任务，继续处理下一条
   - 失败的笔记保留 search 摘要（标题/作者/热度/URL），标记为"⚠️ 详情获取失败"
5. **最终汇总**：报告中区分"完整详情"和"仅摘要（详情获取失败）"的笔记
