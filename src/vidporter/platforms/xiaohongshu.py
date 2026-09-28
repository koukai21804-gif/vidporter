"""小红书（XiaoHongShu / RedNote）适配器。

思路：分享短链（xhslink.com/xxx）→ 跳转到笔记页（带 xsec_token）→
解析 ``window.__INITIAL_STATE__`` 中的笔记数据 → 视频（videoStream.h264
直链）或图集（imageList）。部分笔记需要登录 cookie 才可见。
"""

from __future__ import annotations

import re
from typing import ClassVar

from vidporter.exceptions import ExtractionError, UnsupportedURLError
from vidporter.models import MediaInfo, StreamFormat
from vidporter.platforms.base import BaseExtractor, ExtractContext
from vidporter.utils.log import get_logger
from vidporter.utils.net import extract_json_after_marker, parse_state_json, resolve_url

log = get_logger("vidporter.platforms.xiaohongshu")

_NOTE_ID_RE = re.compile(r"/(?:explore|discovery/item|user/profile)/([0-9a-f]{24})")


class XiaohongshuExtractor(BaseExtractor):
    name = "xiaohongshu"
    display_name = "小红书"
    domains: ClassVar[tuple[str, ...]] = ("xiaohongshu.com", "xhslink.com")

    def extract(self, url: str, ctx: ExtractContext) -> MediaInfo:
        client = ctx.get_client()
        canonical = resolve_url(client, url) if "xhslink.com" in url else url
        note_id = self._parse_note_id(canonical)
        if not note_id:
            raise UnsupportedURLError(f"无法从 URL 中解析出小红书笔记 id: {url}")

        state = self._fetch_state(client, canonical, ctx)
        note = self._find_note(state, note_id)
        if not note:
            raise ExtractionError(
                "页面中没有笔记数据——该笔记可能需要登录 cookie，或已删除；"
                "可尝试导出小红书 cookie 后重试"
            )
        return self._build_info(note, note_id, canonical)

    @staticmethod
    def _parse_note_id(url: str) -> str | None:
        m = _NOTE_ID_RE.search(url)
        return m.group(1) if m else None

    def _fetch_state(self, client, canonical_url: str, ctx: ExtractContext) -> dict:
        cookie_path = ctx.cookies_for("xiaohongshu")
        request_cookies = None
        if cookie_path:
            from vidporter.cookies import netscape

            cookies = netscape.cookies_for_domain(cookie_path, "xiaohongshu")
            request_cookies = {c.name: c.value for c in cookies} or None
        try:
            resp = client.get(canonical_url, cookies=request_cookies)
            resp.raise_for_status()
        except Exception as e:
            raise ExtractionError(f"小红书页面请求失败: {e}") from e
        # __INITIAL_STATE__ 常含 undefined 字面量：先尝试严格解析，
        # 失败则取文本块把 undefined 替换为 null 后再解析
        try:
            raw = extract_json_after_marker(resp.text, "window.__INITIAL_STATE__")
            if isinstance(raw, dict):
                return raw
        except ExtractionError:
            pass
        return parse_state_json(extract_state_text(resp.text, "window.__INITIAL_STATE__"))

    @staticmethod
    def _find_note(state: dict, note_id: str) -> dict | None:
        note_root = state.get("note") or state.get("noteData") or {}
        detail_map = note_root.get("noteDetailMap") or {}
        entry = detail_map.get(note_id) or next(iter(detail_map.values()), None)
        if entry and isinstance(entry, dict):
            return entry.get("note") or entry
        return None

    def _build_info(self, note: dict, note_id: str, canonical_url: str) -> MediaInfo:
        title = (note.get("title") or note.get("desc") or note_id).strip()[:80]
        info = MediaInfo(
            platform=self.name,
            id=note_id,
            title=title,
            webpage_url=canonical_url,
            description=(note.get("desc") or "")[:2000],
            uploader=(note.get("user") or {}).get("nickname", ""),
            duration=((note.get("video") or {}).get("media") or {}).get("videoDuration"),
            thumbnail=((note.get("imageList") or [{}])[0].get("urlDefault")) or "",
            download_headers={"Referer": "https://www.xiaohongshu.com/"},
        )

        video = note.get("video") or {}
        media = video.get("media") or {}
        streams = media.get("videoStream") or {}
        h264 = streams.get("h264") or streams.get("avc") or []
        h265 = streams.get("h265") or streams.get("hev") or []
        candidates = h264 + h265
        # 优先高清（masterUrl 优先于 backupUrls）
        for stream in sorted(candidates, key=lambda s: s.get("videoBitrate", 0) or 0, reverse=True):
            url = stream.get("masterUrl") or stream.get("backupUrls", [""])[0]
            if url:
                info.formats.append(
                    StreamFormat(
                        format_id=stream.get("streamType") or "video",
                        url=url,
                        ext="mp4",
                        height=stream.get("height"),
                        width=stream.get("width"),
                        vcodec=stream.get("videoCodec") or "avc1",
                        acodec=stream.get("audioCodec") or "mp4a",
                    )
                )
        if info.formats:
            return info

        image_list = note.get("imageList") or []
        images = []
        for img in image_list:
            url = img.get("urlDefault") or ""
            if not url:
                info_urls = img.get("infoList") or []
                if info_urls:
                    url = info_urls[-1].get("url", "")
            if url:
                images.append(url)
        if images:
            info.media_type = "images"
            info.images = images
            return info

        raise ExtractionError("笔记中既没有视频也没有图片数据")


def extract_state_text(html: str, marker: str) -> str:
    """取出 marker 之后到 </script> 之前的原始文本（处理 undefined 等非法 JSON）。"""
    idx = html.find(marker)
    if idx < 0:
        raise ExtractionError(f"页面中未找到 {marker!r}")
    end = html.find("</script>", idx)
    if end < 0:
        raise ExtractionError(f"{marker!r} 数据块未闭合")
    start = html.find("{", idx)
    return html[start:end]
