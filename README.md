<div align="center">

# vidporter · 视频搬运工

**English** | [简体中文](README.md)

**统一的多平台视频提取工具** —— 一个程序，覆盖 B站 / 抖音 / 快手 / 小红书 / 微信视频号，以及 yt-dlp 支持的 1800+ 站点。

[![CI](https://github.com/koukai21804-gif/vidporter/actions/workflows/ci.yml/badge.svg)](https://github.com/koukai21804-gif/vidporter/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![Release](https://img.shields.io/github/v/release/koukai21804-gif/vidporter)](https://github.com/koukai21804-gif/vidporter/releases)

命令行 · 网页图形界面 · 免安装单文件 exe

</div>

---

## 特性

- **一个入口下载所有平台**：自动按 URL 识别平台，分发到对应解析器
- **多形态内容**：视频、无水印短视频、图集、音频（`--audio-only`）、字幕
- **字幕工作流**：B站 AI 字幕批量抓取（断点续传、限流退避）+ SRT 转 Markdown 逐字稿
- **Cookie 全家桶**：B站扫码登录、从 Edge/Chrome 经 CDP 导出（绕过 app-bound 加密）
- **图形界面**：`vidporter ui` 网页控制台，或免 Python 环境的单文件 exe
- **批处理**：URL 列表驱动、状态文件断点续跑、失败清单落盘
- **可扩展架构**：实现一个 `BaseExtractor` 即可接入新平台

## 支持矩阵

| 平台 | 视频 | 图集 | 音频 | 字幕 | 登录后增强 | 实现方式 |
|---|:-:|:-:|:-:|:-:|:-:|---|
| 哔哩哔哩 | ✅ | — | ✅ | ✅ | 高清/AI字幕 | yt-dlp 内置提取器 |
| 抖音 | ✅ 无水印 | ✅ | ✅ | — | 私密作品 | 原生解析 + yt-dlp 兜底 |
| 快手 | ✅ | — | ✅ | — | 更稳 | 原生解析 + yt-dlp 兜底 |
| 小红书 | ✅ | ✅ | ✅ | — | 需登录笔记 | 原生解析 |
| 微信视频号 | ⚠️ 见下方说明 | — | — | — | — | 外部嗅探工具桥接 |
| 其它站点 | ✅ | — | ✅ | ✅ | — | yt-dlp（1800+ 站点） |

> **关于微信视频号**：视频号的流经加密域名分发、密钥随客户端会话下发，
> 无法像其它平台一样直接解析，必须本地抓包。`vidporter channels` 命令会
> 检测并启动本机已安装的开源嗅探工具（[res-downloader](https://github.com/putyy/res-downloader)
> 或 [WeChatVideoDownloader](https://github.com/lecepin/WeChatVideoDownloader)），
> 并给出操作指引。欢迎社区贡献纯 Python 的嗅探后端（见 `platforms/channels.py` 的扩展点）。

## 安装

```bash
# 推荐：pipx / uv 隔离安装
pipx install vidporter

# 或
pip install vidporter

# 开发版
git clone https://github.com/koukai21804-gif/vidporter.git
cd vidporter
pip install -e ".[dev]"
```

下载视频封装、转音频需要系统安装 [ffmpeg](https://ffmpeg.org) 并加入 `PATH`。

## 快速上手

```bash
# 自动识别平台并下载（视频）
vidporter download "https://www.bilibili.com/video/BV1xx411c7mD"
vidporter download "https://v.douyin.com/iRNBho5/"          # 抖音，无水印
vidporter download "https://www.xiaohongshu.com/explore/xxx" # 小红书视频
vidporter download "https://xhslink.com/xxx"                 # 小红书图集
vidporter download "https://www.youtube.com/watch?v=..."     # 任意 yt-dlp 支持的站点

# 常用选项
vidporter download <url> --quality 1080        # 限制最大清晰度
vidporter download <url> --audio-only          # 只取音频（mp3）
vidporter download <url> --subtitles           # 连字幕一起下载
vidporter download <url> --out D:/myvideos     # 指定输出目录

# 只看信息不下载
vidporter info <url>
vidporter info <url> --json

# 启动本地网页控制台（浏览器图形界面）
vidporter ui
```

### 图形界面（网页控制台 / 免安装 exe）

不想敲命令？两种方式：

```bash
# 方式一：任意已安装环境直接启动，自动打开浏览器
vidporter ui [--port 8765] [--no-browser]

# 方式二：PyInstaller 打包的单文件 exe，双击即用（无需 Python 环境）
pyinstaller vidporter.spec --noconfirm     # 产出 dist/vidporter-gui.exe（约 20MB）
```

网页控制台功能：粘贴链接批量下载（实时进度条与日志）、解析预览、
B站扫码登录（二维码直接显示在页面上）、SRT 转 Markdown 逐字稿。
服务器只监听 `127.0.0.1`，不对外暴露端口。

### 微信视频号

```bash
vidporter channels   # 检测/启动嗅探工具，按指引在微信 PC 端播放即可
```

### Cookie 管理

B站高清与 AI 字幕、部分私密内容需要登录态：

```bash
# 方式一：扫码登录（推荐，不依赖浏览器）
vidporter cookies login-bilibili

# 方式二：从本机 Edge/Chrome 导出（CDP 方式，含 HttpOnly，绕过 app-bound 加密）
vidporter cookies export --browser edge --domain bilibili
```

### 批量下载

```bash
# urls.txt 每行一个链接，# 开头是注释
vidporter batch urls.txt --quality 1080
# 中断后重跑同一命令即自动续跑（状态文件 <list>.state.json）
```

### 字幕工作流（B站 AI 字幕 → Markdown 逐字稿）

```bash
# 1. 批量抓取字幕（BV 号或链接均可；已有字幕自动跳过；限流自动退避重试）
vidporter subtitle fetch --list bvs.txt --out subs/

# 2. 转 Markdown 逐字稿：去重、按停顿分段、生成索引
vidporter subtitle convert subs/ --out transcripts/
```

### 配置文件

CLI 参数 > 配置文件 > 内置默认值。配置路径：`./vidporter.toml` 或
`%APPDATA%/vidporter/config.toml`（Windows）、`~/.config/vidporter/config.toml`（Linux/macOS）。

```toml
[vidporter]
out_dir = "D:/videos"          # 默认输出目录
quality = 1080                 # 默认清晰度上限
subtitle_langs = "ai-zh,zh-Hans"
proxy = "http://127.0.0.1:7890"
# 视频号嗅探工具路径（未安装到 PATH 时需要）
channels_tool_path = "D:/tools/res-downloader/res-downloader.exe"
```

## 架构

```
CLI (typer + rich) / Web 控制台 (http.server + 单文件 HTML)
 └─ Engine（编排：分发 → 解析 → 下载 → 失败回退）
     ├─ Registry（URL → 平台适配器）
     │    ├─ BilibiliExtractor ──┐
     │    ├─ DouyinExtractor     │  原生解析器：
     │    ├─ KuaishouExtractor   │  请求分享页 → 解析 SSR JSON → 直链
     │    ├─ XiaohongshuExtractor│
     │    ├─ WechatChannelsExtractor → 嗅探工具桥接
     │    └─ GenericExtractor ───┴─ yt-dlp（B站 + 1800+ 站点兜底）
     ├─ HTTP downloader（断点续传 / 进度回调）
     ├─ Cookie 模块（Netscape 读写 / B站扫码 / CDP 导出）
     └─ 字幕工具链（批量抓取 / SRT→Markdown）
```

### 添加新平台

1. 在 `src/vidporter/platforms/` 新建适配器，继承 `BaseExtractor`：
   - 填 `name` / `display_name` / `domains`
   - 实现 `extract(url, ctx) -> MediaInfo`
   - 有独立下载逻辑时覆写 `download()`（参考 `YtdlpMixin`）
2. 在 `registry.py` 注册
3. 在 `tests/fixtures/` 放一份脱敏的页面样本，写离线解析测试

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 已知与相关项目

vidporter 的实现站在这些优秀开源项目的肩膀上：

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)（Unlicense）— 核心下载引擎
- [putyy/res-downloader](https://github.com/putyy/res-downloader)（Apache-2.0）— 视频号等嗅探类下载的实现参照
- [lecepin/WeChatVideoDownloader](https://github.com/lecepin/WeChatVideoDownloader) — 视频号下载工具
- [JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader)（GPL-3.0）、[JoeanAmier/XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader)（GPL-3.0）— 平台解析思路参照（未复用代码）
- [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)（Apache-2.0）— 数据接口参照
- [nexmoe/VidBee](https://github.com/nexmoe/VidBee)、[iawia002/lux](https://github.com/iawia002/lux) — 同类整合工具

## 免责声明

本工具仅供个人学习、备份与研究使用。请遵守目标平台的用户协议与当地法律法规，
尊重内容创作者的版权；下载内容请勿用于商业用途或二次分发。使用本工具产生的
任何问题由使用者自行承担。详见 [DISCLAIMER.md](DISCLAIMER.md)。

## License

[MIT](LICENSE)
