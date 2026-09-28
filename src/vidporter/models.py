"""核心数据模型。

平台适配器从各自的页面 / 接口解析出 :class:`MediaInfo`，下载引擎根据
:class:`DownloadOptions` 挑选流并落盘。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StreamFormat:
    """一条可下载的媒体流。

    对原生解析的平台（抖音 / 小红书 / 快手），通常是单个已封装好的
    mp4 直链；对 yt-dlp 支持的平台，直接沿用 yt-dlp 的 format 字典。
    """

    format_id: str
    url: str
    ext: str = "mp4"
    height: int | None = None
    width: int | None = None
    vcodec: str | None = None
    acodec: str | None = None
    filesize: int | None = None
    protocol: str = "https"
    note: str = ""

    @property
    def is_audio_only(self) -> bool:
        return bool(self.vcodec) and self.vcodec == "none"

    @property
    def is_video(self) -> bool:
        return bool(self.vcodec) and self.vcodec != "none"


@dataclass
class SubtitleTrack:
    lang: str
    url: str
    ext: str = "srt"
    name: str = ""


@dataclass
class MediaInfo:
    """一次成功解析的结果。"""

    platform: str
    id: str
    title: str
    webpage_url: str
    media_type: str = "video"  # "video" | "images"
    description: str = ""
    uploader: str = ""
    duration: float | None = None  # 秒
    thumbnail: str = ""
    formats: list[StreamFormat] = field(default_factory=list)
    subtitles: list[SubtitleTrack] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    # 下载直链时需要携带的请求头（防盗链 Referer 等），由平台适配器给出
    download_headers: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def best_stream(self, max_height: int | None = None) -> StreamFormat | None:
        """按清晰度上限挑选最佳视频流；不含视频流时退回唯一可用流。"""
        candidates = [f for f in self.formats if f.is_video and f.url]
        if not candidates:
            candidates = [f for f in self.formats if f.url]
        if not candidates:
            return None
        if max_height:
            within = [f for f in candidates if f.height and f.height <= max_height]
            if within:
                candidates = within
        # 高度未知视为最低优先，其余按高度降序
        return max(candidates, key=lambda f: f.height or 0)


@dataclass
class DownloadOptions:
    out_dir: Path = Path("downloads")
    out_template: str = "%(title).80s [%(id)s].%(ext)s"
    max_height: int | None = None  # 例如 1080
    audio_only: bool = False
    audio_format: str = "mp3"
    download_subtitles: bool = False
    subtitle_langs: str = "ai-zh,zh-Hans"
    embed_subtitles: bool = False
    proxy: str | None = None
    cookies_file: Path | None = None
    rate_limit_sleep: float = 1.0
    # 进度回调（由 CLI 注入；hook 收到 yt-dlp 的进度字典，cb 收到 (done, total)）
    progress_hook: Any | None = None
    progress_cb: Any | None = None

    def resolve_path(self, name: str) -> Path:
        d = self.out_dir / name if name else self.out_dir
        d.mkdir(parents=True, exist_ok=True)
        return d


@dataclass
class DownloadResult:
    ok: bool
    url: str
    platform: str
    paths: list[Path] = field(default_factory=list)
    title: str = ""
    message: str = ""
