"""通用兜底适配器 — yt-dlp 支持的 1800+ 站点都走这里。"""

from __future__ import annotations

from typing import ClassVar

from vidporter.models import DownloadOptions, DownloadResult, MediaInfo
from vidporter.platforms.base import BaseExtractor, ExtractContext
from vidporter.platforms.ytdlp_backend import YtdlpMixin


class GenericExtractor(YtdlpMixin, BaseExtractor):
    name = "generic"
    display_name = "通用（yt-dlp）"
    domains: ClassVar[tuple[str, ...]] = ()  # 空 = 兜底

    def extract(self, url: str, ctx: ExtractContext) -> MediaInfo:
        return self.ytdlp_extract(url, ctx, platform=self.name)

    def download(self, url: str, ctx: ExtractContext, opts: DownloadOptions) -> DownloadResult:
        return self.ytdlp_download(url, ctx, opts, platform=self.name)
