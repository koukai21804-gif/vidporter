<div align="center">

# vidporter · 视频搬运工

English | [简体中文](README.md)

**One unified video extractor for everything** — Bilibili, Douyin (TikTok CN), Kuaishou, Xiaohongshu (RedNote), WeChat Channels, plus 1800+ more sites powered by yt-dlp.

[![CI](https://github.com/koukai21804-gif/vidporter/actions/workflows/ci.yml/badge.svg)](https://github.com/koukai21804-gif/vidporter/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![Release](https://img.shields.io/github/v/release/koukai21804-gif/vidporter)](https://github.com/koukai21804-gif/vidporter/releases)

CLI · Local Web Console · Single-file executable

</div>

---

## Features

- **One entry point for every platform**: URLs are auto-detected and routed to the right extractor
- **Every content form**: videos, watermark-free short videos, image galleries, audio (`--audio-only`), subtitles
- **Subtitle workflow**: bulk Bilibili AI-subtitle fetching (resumable, rate-limit backoff) + SRT-to-Markdown transcripts
- **Full cookie toolkit**: Bilibili QR-code login, CDP export from Edge/Chrome (bypasses app-bound encryption)
- **GUI**: `vidporter ui` local web console, or a single-file exe that needs no Python
- **Batch mode**: URL-list driven, resumable via state file, failures written to a report
- **Extensible by design**: implement one `BaseExtractor` class to add a platform

## Support Matrix

| Platform | Video | Gallery | Audio | Subtitles | Enhanced w/ login | Implementation |
|---|:-:|:-:|:-:|:-:|:-:|---|
| Bilibili | ✅ | — | ✅ | ✅ | HD / AI subtitles | yt-dlp built-in extractor |
| Douyin | ✅ no watermark | ✅ | ✅ | — | private posts | native parser + yt-dlp fallback |
| Kuaishou | ✅ | — | ✅ | — | more reliable | native parser + yt-dlp fallback |
| Xiaohongshu | ✅ | ✅ | ✅ | — | login-only notes | native parser |
| WeChat Channels | ⚠️ see below | — | — | — | — | external sniffer bridge |
| Everything else | ✅ | — | ✅ | ✅ | — | yt-dlp (1800+ sites) |

> **About WeChat Channels**: video streams are served through encrypted domains with
> per-session keys, so they cannot be resolved like other platforms — local traffic
> capture is required. The `vidporter channels` command detects and launches an
> installed open-source sniffer ([res-downloader](https://github.com/putyy/res-downloader)
> or [WeChatVideoDownloader](https://github.com/lecepin/WeChatVideoDownloader)) and
> guides you from there. Contributions toward a pure-Python sniffer backend are welcome
> (see the extension point in `platforms/channels.py`).

## Installation

```bash
# Recommended: isolated install via pipx / uv
pipx install vidporter

# or
pip install vidporter

# from source
git clone https://github.com/koukai21804-gif/vidporter.git
cd vidporter
pip install -e ".[dev]"
```

Muxing videos and extracting audio require [ffmpeg](https://ffmpeg.org) on your `PATH`.

## Quick Start

```bash
# Auto-detects the platform and downloads
vidporter download "https://www.bilibili.com/video/BV1xx411c7mD"
vidporter download "https://v.douyin.com/iRNBho5/"           # Douyin, no watermark
vidporter download "https://www.xiaohongshu.com/explore/xxx" # Xiaohongshu video
vidporter download "https://xhslink.com/xxx"                 # Xiaohongshu gallery
vidporter download "https://www.youtube.com/watch?v=..."     # any yt-dlp site

# Common options
vidporter download <url> --quality 1080        # cap resolution
vidporter download <url> --audio-only          # audio only (mp3)
vidporter download <url> --subtitles           # fetch subtitles too
vidporter download <url> --out D:/myvideos     # output directory

# Inspect without downloading
vidporter info <url>
vidporter info <url> --json

# Launch the local web console (browser GUI)
vidporter ui
```

### Graphical Interface (web console / standalone exe)

```bash
# Option 1: start from any installed environment, browser opens automatically
vidporter ui [--port 8765] [--no-browser]

# Option 2: build a single-file exe with PyInstaller — double-click to run, no Python needed
pyinstaller vidporter.spec --noconfirm     # produces dist/vidporter-gui.exe (~20MB)
```

The web console supports pasting multiple links for batch download (live progress bars
and logs), metadata preview, Bilibili QR login (the QR code is displayed right on the
page), and SRT-to-Markdown conversion. The server listens on `127.0.0.1` only.

### WeChat Channels

```bash
vidporter channels   # detects / launches a sniffer tool, then follows the guide
```

### Cookie Management

Bilibili HD streams and AI subtitles, plus some private content, require a login:

```bash
# Option 1: QR login (recommended, browser-independent)
vidporter cookies login-bilibili

# Option 2: export from local Edge/Chrome over CDP (incl. HttpOnly, bypasses app-bound encryption)
vidporter cookies export --browser edge --domain bilibili
```

### Batch Download

```bash
# one URL per line in urls.txt, lines starting with # are comments
vidporter batch urls.txt --quality 1080
# re-running the same command resumes automatically (state file <list>.state.json)
```

### Subtitle Workflow (Bilibili AI subtitles → Markdown transcripts)

```bash
# 1. Bulk-fetch subtitles (BV ids or links; existing files are skipped; rate limits retried with backoff)
vidporter subtitle fetch --list bvs.txt --out subs/

# 2. Convert to Markdown transcripts: dedupe, split on pauses, generate an index
vidporter subtitle convert subs/ --out transcripts/
```

### Configuration

CLI flags > config file > built-in defaults. Config locations: `./vidporter.toml` or
`%APPDATA%/vidporter/config.toml` (Windows), `~/.config/vidporter/config.toml` (Linux/macOS).

```toml
[vidporter]
out_dir = "D:/videos"          # default output directory
quality = 1080                 # default resolution cap
subtitle_langs = "ai-zh,zh-Hans"
proxy = "http://127.0.0.1:7890"
# path to the WeChat Channels sniffer tool (needed when not on PATH)
channels_tool_path = "D:/tools/res-downloader/res-downloader.exe"
```

## Architecture

```
CLI (typer + rich) / Web console (http.server + single-file HTML)
 └─ Engine (dispatch → extract → download → fallback)
     ├─ Registry (URL → platform extractor)
     │    ├─ BilibiliExtractor ──┐
     │    ├─ DouyinExtractor     │  native parsers:
     │    ├─ KuaishouExtractor   │  share page → SSR JSON → direct link
     │    ├─ XiaohongshuExtractor│
     │    ├─ WechatChannelsExtractor → external sniffer bridge
     │    └─ GenericExtractor ───┴─ yt-dlp (Bilibili + 1800+ site fallback)
     ├─ HTTP downloader (range resume / progress callbacks)
     ├─ Cookie toolkit (Netscape I/O / Bilibili QR / CDP export)
     └─ Subtitle toolchain (bulk fetch / SRT→Markdown)
```

### Adding a New Platform

1. Create an adapter in `src/vidporter/platforms/` extending `BaseExtractor`:
   - fill in `name` / `display_name` / `domains`
   - implement `extract(url, ctx) -> MediaInfo`
   - override `download()` if the platform needs custom logic (see `YtdlpMixin`)
2. Register it in `registry.py`
3. Add a sanitized page fixture to `tests/fixtures/` and write an offline parsing test

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Acknowledgements

vidporter stands on the shoulders of these projects:

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense) — the core download engine
- [putyy/res-downloader](https://github.com/putyy/res-downloader) (Apache-2.0) — reference for sniffer-style capture
- [lecepin/WeChatVideoDownloader](https://github.com/lecepin/WeChatVideoDownloader) — WeChat Channels downloader
- [JoeanAmier/TikTokDownloader](https://github.com/JoeanAmier/TikTokDownloader) (GPL-3.0), [JoeanAmier/XHS-Downloader](https://github.com/JoeanAmier/XHS-Downloader) (GPL-3.0) — parsing ideas referenced, no code reused
- [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) (Apache-2.0) — API reference
- [nexmoe/VidBee](https://github.com/nexmoe/VidBee), [iawia002/lux](https://github.com/iawia002/lux) — similar all-in-one tools

## Disclaimer

This tool is for personal learning, backup, and research only. Please respect the
terms of service of each platform, local laws and regulations, and content creators'
copyright. Downloaded content must not be used commercially or redistributed. See
[DISCLAIMER.md](DISCLAIMER.md).

## License

[MIT](LICENSE)
