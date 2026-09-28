"""yt-dlp 支持平台的共享实现。

B站、以及 1800+ 个「其它站点」都由 yt-dlp 承担解析与下载；这里把
vidporter 的 :class:`DownloadOptions` 翻译成 yt-dlp 选项，并把解析结果
映射回 :class:`MediaInfo` 以便 ``info`` 命令和统一展示。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vidporter.exceptions import ExtractionError
from vidporter.models import DownloadOptions, DownloadResult, MediaInfo, StreamFormat, SubtitleTrack
from vidporter.platforms.base import _safe_filename
from vidporter.utils.log import get_logger

log = get_logger("vidporter.platforms.ytdlp")


def build_ydl_opts(
    ctx, opts: DownloadOptions | None = None, download: bool = True
) -> dict[str, Any]:
    """构造 yt-dlp 选项字典。"""
    ydl: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 30,
        "retries": 3,
        "noplaylist": True,
        "outtmpl": {
            "default": (
                str(Path(opts.out_dir) / opts.out_template)
                if opts
                else "%(title).80s [%(id)s].%(ext)s"
            )
        },
    }
    cookie_file = None
    if opts and opts.cookies_file:
        cookie_file = opts.cookies_file
    elif ctx is not None:
        cookie_file = ctx.cookies_for(getattr(ctx, "_platform", "bilibili"))
    if cookie_file and Path(cookie_file).is_file():
        ydl["cookiefile"] = str(cookie_file)
    proxy = (opts.proxy if opts else None) or (ctx.config.proxy if ctx else None)
    if proxy:
        ydl["proxy"] = proxy
    if opts:
        if opts.max_height:
            ydl["format"] = (
                f"bv*[height<={opts.max_height}]+ba/b[height<={opts.max_height}]/bv*+ba/b"
            )
        if opts.audio_only:
            ydl["format"] = "bestaudio/best"
            ydl["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": opts.audio_format,
                    "preferredquality": "0",
                }
            ]
        if opts.download_subtitles or opts.embed_subtitles:
            ydl["writesubtitles"] = True
            ydl["writeautomaticsub"] = True
            ydl["subtitleslangs"] = [s.strip() for s in opts.subtitle_langs.split(",") if s.strip()]
            ydl["convertsubtitles"] = "srt"
            if opts.embed_subtitles:
                ydl["postprocessors"] = ydl.get("postprocessors", []) + [
                    {"key": "FFmpegEmbedSubtitle"}
                ]
        if opts.rate_limit_sleep:
            ydl["sleep_interval_requests"] = opts.rate_limit_sleep
        if opts.progress_hook:
            ydl["progress_hooks"] = [opts.progress_hook]
    return ydl


def info_dict_to_media(info: dict, platform: str) -> MediaInfo:
    """把 yt-dlp 的 info 字典映射为 MediaInfo（只保留常用字段）。"""

    def _fmt(f: dict) -> StreamFormat:
        return StreamFormat(
            format_id=str(f.get("format_id", "")),
            url=f.get("url") or "",
            ext=f.get("ext") or "mp4",
            height=f.get("height"),
            width=f.get("width"),
            vcodec=f.get("vcodec"),
            acodec=f.get("acodec"),
            filesize=f.get("filesize") or f.get("filesize_approx"),
            protocol=f.get("protocol") or "https",
            note=f.get("format_note") or "",
        )

    subtitles: list[SubtitleTrack] = []
    for lang, tracks in (info.get("subtitles") or {}).items():
        for t in tracks or []:
            if t.get("ext") in ("srt", "vtt", "json3", "srv3", "ass"):
                subtitles.append(
                    SubtitleTrack(lang=lang, url=t["url"], ext=t["ext"], name=t.get("name") or "")
                )
                break
    auto = info.get("automatic_captions") or {}
    for lang, tracks in auto.items():
        if any(s.lang == lang for s in subtitles):
            continue
        if lang.startswith("ai-zh") or lang.startswith("zh"):
            for t in tracks or []:
                if t.get("ext") in ("srt", "vtt"):
                    subtitles.append(SubtitleTrack(lang=lang, url=t["url"], ext=t["ext"]))
                    break

    return MediaInfo(
        platform=platform,
        id=str(info.get("id", "")),
        title=info.get("title") or info.get("id") or "untitled",
        webpage_url=info.get("webpage_url") or "",
        media_type="images" if info.get("_type") == "playlist" and info.get("gallery") else "video",
        description=(info.get("description") or "")[:2000],
        uploader=info.get("uploader") or info.get("uploader_id") or "",
        duration=info.get("duration"),
        thumbnail=info.get("thumbnail") or "",
        formats=[_fmt(f) for f in (info.get("formats") or []) if f.get("url")],
        subtitles=subtitles,
        extra={"raw_formats": len(info.get("formats") or [])},
    )


class YtdlpMixin:
    """给 :class:`BaseExtractor` 子类混入 yt-dlp 的解析与下载能力。"""

    def ytdlp_extract(self, url: str, ctx, platform: str | None = None) -> MediaInfo:
        from yt_dlp import YoutubeDL

        ydl_opts = build_ydl_opts(ctx, download=False)
        platform = platform or self.name  # type: ignore[attr-defined]
        try:
            with YoutubeDL(ydl_opts) as ydl:
                raw = ydl.extract_info(url, download=False)
        except Exception as e:
            raise ExtractionError(f"yt-dlp 解析失败: {_short_err(e)}") from e
        if raw is None:
            raise ExtractionError("yt-dlp 未返回结果")
        return info_dict_to_media(raw, platform)

    def ytdlp_download(
        self, url: str, ctx, opts: DownloadOptions, platform: str | None = None
    ) -> DownloadResult:
        from yt_dlp import YoutubeDL

        opts.out_dir.mkdir(parents=True, exist_ok=True)
        ydl_opts = build_ydl_opts(ctx, opts, download=True)
        platform = platform or self.name  # type: ignore[attr-defined]
        try:
            with YoutubeDL(ydl_opts) as ydl:
                raw = ydl.extract_info(url, download=True)
                if raw is None:
                    raise ExtractionError("yt-dlp 未返回结果")
                raw = ydl.sanitize_info(raw)
        except Exception as e:
            raise ExtractionError(f"yt-dlp 下载失败: {_short_err(e)}") from e

        paths = _collect_paths(raw)
        title = raw.get("title") or raw.get("id") or ""
        return DownloadResult(True, url, platform, paths, str(title))

    def ytdlp_info(self, url: str, ctx) -> MediaInfo:
        return self.ytdlp_extract(url, ctx)


def _collect_paths(raw: dict) -> list[Path]:
    """从下载完成后的 info 字典收集落盘文件路径（含旁边的字幕文件）。"""
    paths: list[Path] = []
    entries = raw.get("entries") or [raw]
    for entry in entries:
        if not entry:
            continue
        for req in entry.get("requested_downloads") or []:
            fp = req.get("filepath") or req.get("filename")
            if not fp:
                continue
            base = Path(fp)
            paths.append(base)
            # yt-dlp 把字幕写在视频文件旁边（同主干不同后缀）
            for sub_path in base.parent.glob(base.stem + ".*"):
                if sub_path.suffix.lower() in (".srt", ".vtt", ".ass", ".json3"):
                    paths.append(sub_path)
    # 去重保序
    seen: set[Path] = set()
    unique = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _short_err(e: Exception) -> str:
    text = str(e)
    return text[-300:] if len(text) > 300 else text


def ytdlp_fetch_subtitles(
    urls: list[str],
    out_dir: Path,
    langs: str,
    cookies_file: Path | None,
    proxy: str | None = None,
    sleep: float = 1.0,
    existing_check=None,
    max_retries: int = 3,
    status_cb=None,
) -> dict[str, str]:
    """批量抓取字幕（B站 AI 字幕工作流的核心）。

    ``existing_check(url)`` 返回已存在输出路径时跳过该项，实现断点续传。
    返回 {url: status}，status ∈ {"ok", "cached", "failed: <原因>"}。
    """
    from yt_dlp import YoutubeDL

    log_cb = status_cb or (lambda msg: log.info("%s", msg))
    out_dir.mkdir(parents=True, exist_ok=True)
    statuses: dict[str, str] = {}

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": [s.strip() for s in langs.split(",") if s.strip()],
        "convertsubtitles": "srt",
        "outtmpl": {"default": str(out_dir / "%(id)s.%(ext)s")},
        "sleep_interval_requests": sleep,
        "socket_timeout": 60,
        "retries": max_retries,
    }
    if cookies_file and Path(cookies_file).is_file():
        ydl_opts["cookiefile"] = str(cookies_file)
    if proxy:
        ydl_opts["proxy"] = proxy

    import time as _time

    for i, url in enumerate(urls, 1):
        if existing_check and (cached := existing_check(url)):
            statuses[url] = "cached"
            log_cb("[%d/%d] 跳过（已有）: %s" % (i, len(urls), cached.name))
            continue
        got = False
        last_err = ""
        for attempt in range(1, max_retries + 1):
            try:
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(url, download=True)
                got = True
                break
            except Exception as e:
                last_err = _short_err(e)
                # B 站风控（-412 / 频繁）退避后重试
                if any(sig in last_err for sig in ("412", "799", "频繁")):
                    wait = 25 * attempt
                    log_cb("触发限流，等待 %ds 后重试 (%d/%d)" % (wait, attempt, max_retries))
                    _time.sleep(wait)
                else:
                    _time.sleep(2)
        statuses[url] = "ok" if got else f"failed: {last_err}"
        log_cb("[%d/%d] %s %s" % (i, len(urls), "OK" if got else "FAIL", url))
    return statuses


__all__ = [
    "YtdlpMixin",
    "build_ydl_opts",
    "info_dict_to_media",
    "ytdlp_fetch_subtitles",
    "_safe_filename",
]
