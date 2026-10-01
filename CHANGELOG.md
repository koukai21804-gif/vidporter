# Changelog

本项目的版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.2.1] - 2026-10-01

### 修复

- **抖音**：分享页改版（`loaderData` 恒含 `video_layout: null` 占位键）导致
  `AttributeError: 'NoneType' object has no attribute 'get'`，且裸异常绕过
  yt-dlp 回退机制；现在安全跳过空占位键，失败转为可触发回退的干净错误
- **抖音**：分享页改为客户端渲染后，无 `ttwid` cookie 只能拿到空壳页面；
  现在自动向字节签发接口申请游客 ttwid 并写回 cookie 文件——零配置即可
  解析下载（实测含图集在内的短链与直达链接）
- **抖音**：导出的抖音 cookie 之前从未被请求携带；现在自研解析与 yt-dlp
  回退均会附带（引擎兜底时透传失败平台的 cookie，且不污染批处理复用的
  下载选项）
- **cookie 导出**：Chromium 136+ 禁止在默认用户目录上开调试端口，导致
  「调试端口 9222 未就绪: timed out」；改用 vidporter 专属持久化 profile，
  并补 `--remote-allow-origins` 修复 CDP WebSocket 握手 403；无头模式会先
  访问目标站点获取游客 cookie；新增 `--show` 有头模式（专用 profile 保留
  登录态）

### 新增

- 应用图标（exe 资源 + 网页 favicon）；`build` 依赖组加入 pillow

## [0.2.0] - 2026-10-01

### 新增

- **网页图形界面**：`vidporter ui` 启动本地控制台（仅监听 127.0.0.1），
  支持链接批量下载（实时进度条与日志）、解析预览、B站扫码登录
  （二维码显示在页面上）、SRT → Markdown 逐字稿转换
- **单文件可执行程序**：PyInstaller 打包配置（`vidporter.spec`），
  `pyinstaller vidporter.spec` 产出约 20MB 的 `vidporter-gui.exe`，
  免 Python 环境双击即用；新增 `build` 可选依赖组
- 新增 `src/vidporter/web/`（任务管理器 + 标准 HTTP 服务端）与
  `gui_main.py`（打包入口）；8 个离线测试覆盖任务管理与 API

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
