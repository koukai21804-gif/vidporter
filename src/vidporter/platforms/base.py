"""平台适配器基类。

每个平台实现 :meth:`BaseExtractor.extract`，把 URL 解析成
:class:`~vidporter.models.MediaInfo`；下载默认走基类的 HTTP 直链下载，
yt-dlp 支持的平台通过 :class:`YtdlpMixin` 覆盖为 yt-dlp 下载。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import urlparse

from vidporter.exceptions import ExtractionError
from vidporter.models import DownloadOptions, DownloadResult, MediaInfo
from vidporter.utils.log import get_logger

if TYPE_CHECKING:
    import httpx

    from vidporter.config import Config

log = get_logger("vidporter.platforms")


@dataclass
class ExtractContext:
    """解析与下载过程中各平台共用的上下文。"""

    config: Config
    client: httpx.Client | None = None
    verbose: bool = False

    def get_client(self, user_agent: str | None = None, **kwargs) -> httpx.Client:
        if self.client is not None:
            return self.client
        from vidporter.utils.net import DESKTOP_UA, make_client

        return make_client(
            proxy=self.config.proxy,
            user_agent=user_agent or DESKTOP_UA,
            **kwargs,
        )

    def cookies_for(self, platform: str) -> Path | None:
        path = self.config.cookie_file_for(platform)
        return path if path.is_file() else None


class BaseExtractor(ABC):
    #: 短名，用于 CLI --platform、日志与输出目录命名
    name: ClassVar[str] = "generic"
    #: 展示名（中文）
    display_name: ClassVar[str] = "通用"
    #: 匹配的域名后缀（不含 www.）；空表示兜底平台
    domains: ClassVar[tuple[str, ...]] = ()
    #: True 表示必须本地抓包才能拿到资源（如视频号）
    capture_required: ClassVar[bool] = False

    @classmethod
    def can_handle(cls, url: str) -> bool:
        if not cls.domains:
            return False
        try:
            host = urlparse(url).hostname or ""
        except ValueError:
            return False
        host = host.lower().removeprefix("www.")
        return any(host == d or host.endswith("." + d) for d in cls.domains)

    @abstractmethod
    def extract(self, url: str, ctx: ExtractContext) -> MediaInfo:
        """解析 URL，返回媒体信息。失败抛 UnsupportedURLError / ExtractionError。"""

    # -- 下载 ---------------------------------------------------------------

    def download(self, url: str, ctx: ExtractContext, opts: DownloadOptions) -> DownloadResult:
        info = self.extract(url, ctx)
        if opts.audio_only and info.media_type == "video":
            return self._download_audio_from_video(info, ctx, opts)
        if info.media_type == "images":
            return self._download_images(info, ctx, opts)
        return self._download_single_stream(info, ctx, opts)

    def _download_single_stream(
        self, info: MediaInfo, ctx: ExtractContext, opts: DownloadOptions
    ) -> DownloadResult:
        from vidporter.download.http_downloader import download_file
        from vidporter.utils.net import make_client

        stream = info.best_stream(opts.max_height)
        if stream is None:
            raise ExtractionError("解析成功但没有可下载的媒体流")

        out_dir = opts.out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_title = _safe_filename(info.title) or info.id
        dest = out_dir / f"{safe_title}.{stream.ext}"
        client = (
            ctx.get_client()
            if ctx.client is not None
            else make_client(proxy=opts.proxy or ctx.config.proxy)
        )
        headers = dict(info.download_headers)
        path = download_file(
            client, stream.url, dest, headers=headers, progress_cb=opts.progress_cb
        )
        paths = [path]
        paths += self._save_subtitles(info, opts)
        return DownloadResult(True, info.webpage_url, self.name, paths, info.title)

    def _download_images(
        self, info: MediaInfo, ctx: ExtractContext, opts: DownloadOptions
    ) -> DownloadResult:
        from vidporter.download.http_downloader import download_file
        from vidporter.utils.net import make_client

        out_dir = opts.out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_title = _safe_filename(info.title) or info.id
        client = (
            ctx.get_client()
            if ctx.client is not None
            else make_client(proxy=opts.proxy or ctx.config.proxy)
        )
        paths = []
        for i, img_url in enumerate(info.images, 1):
            ext = _guess_image_ext(img_url)
            dest = out_dir / f"{safe_title}_{i:02d}.{ext}"
            paths.append(
                download_file(
                    client,
                    img_url,
                    dest,
                    headers=info.download_headers,
                    progress_cb=opts.progress_cb,
                )
            )
        paths += self._save_subtitles(info, opts)
        return DownloadResult(True, info.webpage_url, self.name, paths, info.title)

    def _download_audio_from_video(
        self, info: MediaInfo, ctx: ExtractContext, opts: DownloadOptions
    ) -> DownloadResult:
        """短视频平台通常不单独给音频流：优先找音频流，否则借助 ffmpeg 抽取。"""
        audio = next((f for f in info.formats if f.is_audio_only and f.url), None)
        if audio is None:
            video = info.best_stream(opts.max_height)
            if video is None:
                raise ExtractionError("没有可用的媒体流")
            downloaded = self._download_single_stream(info, ctx, opts)
            return _extract_audio(downloaded, opts)
        from vidporter.download.http_downloader import download_file
        from vidporter.utils.net import make_client

        out_dir = opts.out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_title = _safe_filename(info.title) or info.id
        client = (
            ctx.get_client()
            if ctx.client is not None
            else make_client(proxy=opts.proxy or ctx.config.proxy)
        )
        raw = out_dir / f"{safe_title}_raw.{audio.ext}"
        path = download_file(client, audio.url, raw, headers=info.download_headers)
        return DownloadResult(True, info.webpage_url, self.name, [path], info.title)

    def _save_subtitles(self, info: MediaInfo, opts: DownloadOptions) -> list[Path]:
        if not opts.download_subtitles or not info.subtitles:
            return []
        import httpx

        wanted = [s.strip() for s in opts.subtitle_langs.split(",") if s.strip()]
        saved = []
        for track in info.subtitles:
            if wanted and not any(w and track.lang.startswith(w) for w in wanted):
                continue
            stem = _safe_filename(info.title) or info.id
            dest = opts.out_dir / f"{stem}.{track.lang}.{track.ext}"
            try:
                resp = httpx.get(track.url, timeout=30, follow_redirects=True)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
                saved.append(dest)
            except httpx.HTTPError as e:
                log.warning("字幕下载失败 %s: %s", track.lang, e)
        return saved


# -- 模块级工具函数 ---------------------------------------------------------

_FILENAME_BAD = re.compile(r'[\\/:*?"<>|\r\n\t]')


def _safe_filename(name: str, max_len: int = 80) -> str:
    cleaned = _FILENAME_BAD.sub("_", name).strip(" ._")
    return cleaned[:max_len]


def _guess_image_ext(url: str) -> str:
    lower = url.lower().split("?")[0]
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if lower.endswith(ext):
            return ext.lstrip(".")
    return "jpg"


def _extract_audio(result: DownloadResult, opts: DownloadOptions) -> DownloadResult:
    """用 ffmpeg 把已下载的视频抽成音频。"""
    from vidporter.exceptions import FFmpegNotFoundError
    from vidporter.utils.ffmpeg import extract_audio, ffmpeg_available

    if not ffmpeg_available():
        raise FFmpegNotFoundError("转音频需要 ffmpeg，请安装并加入 PATH，或直接下载视频")
    audio_paths = []
    for path in result.paths:
        if path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".srt", ".vtt"):
            continue
        dest = path.with_suffix(f".{opts.audio_format}")
        audio_paths.append(extract_audio(path, dest))
    return DownloadResult(
        result.ok, result.url, result.platform, audio_paths or result.paths, result.title
    )
