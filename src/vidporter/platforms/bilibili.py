"""Bilibili（B站）适配器 — 由 yt-dlp 内置提取器承担。"""

from __future__ import annotations

from typing import ClassVar

from vidporter.models import DownloadOptions, DownloadResult, MediaInfo
from vidporter.platforms.base import BaseExtractor, ExtractContext
from vidporter.platforms.ytdlp_backend import YtdlpMixin


class BilibiliExtractor(YtdlpMixin, BaseExtractor):
    name = "bilibili"
    display_name = "哔哩哔哩"
    domains: ClassVar[tuple[str, ...]] = ("bilibili.com", "b23.tv")

    def extract(self, url: str, ctx: ExtractContext) -> MediaInfo:
        return self.ytdlp_extract(url, ctx, platform=self.name)

    def download(self, url: str, ctx: ExtractContext, opts: DownloadOptions) -> DownloadResult:
        if not opts.cookies_file:
            # B 站高清晰度与 AI 字幕普遍需要登录态，自动挂上默认 cookie
            opts.cookies_file = ctx.cookies_for("bilibili")
        return self.ytdlp_download(url, ctx, opts, platform=self.name)
