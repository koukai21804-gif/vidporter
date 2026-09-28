# Changelog

本项目的版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-09-28

首个公开版本。

### 新增

- 核心架构：平台适配器（`BaseExtractor`）+ 注册表分发 + 下载引擎，
  解析失败自动回退 yt-dlp 通用引擎
- 平台支持：
  - 哔哩哔哩（yt-dlp 内置提取器，支持登录 cookie、AI 字幕）
  - 抖音（分享链接无水印解析、图集、yt-dlp 兜底）
  - 快手（Apollo State 解析、yt-dlp 兜底）
  - 小红书（`__INITIAL_STATE__` 解析，视频与图集）
  - 微信视频号（外部嗅探工具桥接：res-downloader / WeChatVideoDownloader）
  - 通用：yt-dlp 支持的 1800+ 站点
- Cookie 工具：B站扫码登录；经 Chrome DevTools 协议从 Edge/Chrome 导出
  cookie（绕过 app-bound 加密）；Netscape 格式读写
- 字幕工作流：批量抓取（断点续传、限流退避、失败清单）；
  SRT → Markdown 逐字稿（去重、停顿分段、索引生成）
- CLI：`download` / `info` / `batch` / `channels` / `cookies` / `subtitle`
  子命令，rich 进度条，TOML 配置文件
- HTTP 下载器：流式下载、Range 断点续传、重试
- 完整离线测试（httpx MockTransport）与 CI（三平台 × Python 3.10–3.13）
