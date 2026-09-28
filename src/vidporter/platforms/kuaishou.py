"""快手适配器。

思路：短链（v.kuaishou.com/xxx）→ 跳转到 photo 页 → 解析
``window.__APOLLO_STATE__`` 中的作品数据得到 photoUrl。快手网页对
未登录请求限制较松但结构常变，失败时回退 yt-dlp。
"""

from __future__ import annotations

import re
from typing import ClassVar

from vidporter.exceptions import ExtractionError, UnsupportedURLError
from vidporter.models import MediaInfo, StreamFormat
from vidporter.platforms.base import BaseExtractor, ExtractContext
from vidporter.utils.log import get_logger
from vidporter.utils.net import extract_json_after_marker, resolve_url

log = get_logger("vidporter.platforms.kuaishou")

_PHOTO_ID_RE = re.compile(r"/(?:short-video|photo)/([\w-]+)")


class KuaishouExtractor(BaseExtractor):
    name = "kuaishou"
    display_name = "快手"
    domains: ClassVar[tuple[str, ...]] = ("kuaishou.com", "gifshow.com", "chenzhongtech.com")

    def extract(self, url: str, ctx: ExtractContext) -> MediaInfo:
        client = ctx.get_client()
        canonical = resolve_url(client, url) if "v.kuaishou.com" in url else url
        photo_id = self._parse_photo_id(canonical)
        if not photo_id:
            raise UnsupportedURLError(f"无法从 URL 中解析出快手作品 id: {url}")

        payload = self._fetch_payload(client, canonical, ctx)
        photo = self._find_photo(payload)
        if not photo:
            raise ExtractionError(
                "页面中没有作品数据（可能需要登录 cookie 或已改版）；可尝试导出快手 cookie 后重试"
            )
        return self._build_info(photo, photo_id)

    @staticmethod
    def _parse_photo_id(url: str) -> str | None:
        m = _PHOTO_ID_RE.search(url)
        return m.group(1) if m else None

    def _fetch_payload(self, client, canonical_url: str, ctx: ExtractContext) -> dict:
        cookie_path = ctx.cookies_for("kuaishou")
        request_cookies = None
        if cookie_path:
            from vidporter.cookies import netscape

            cookies = netscape.cookies_for_domain(cookie_path, "kuaishou")
            request_cookies = {c.name: c.value for c in cookies} or None
        try:
            resp = client.get(canonical_url, cookies=request_cookies)
            resp.raise_for_status()
        except Exception as e:
            raise ExtractionError(f"快手页面请求失败: {e}") from e
        try:
            return extract_json_after_marker(resp.text, "window.__APOLLO_STATE__")
        except ExtractionError as e:
            raise ExtractionError(f"快手页面解析失败: {e}") from e

    @staticmethod
    def _find_photo(payload: dict) -> dict | None:
        # __APOLLO_STATE__ 形如 {"defaultClient": {"VisionVideoDetailPhoto:xxx": {...}}}
        # 为兼容结构变化，直接遍历找含 photoUrl 的节点
        stack = [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("photoUrl"):
                    return node
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
        return None

    def _build_info(self, photo: dict, photo_id: str) -> MediaInfo:
        caption = (photo.get("caption") or "").strip() or photo_id
        photo_url = photo["photoUrl"]
        ext = "mp4"
        m = re.search(r"\.(mp4|flv|mov)(?:[?#]|$)", photo_url.lower())
        if m:
            ext = m.group(1)
        duration_ms = photo.get("duration")
        return MediaInfo(
            platform=self.name,
            id=photo_id,
            title=caption,
            webpage_url=f"https://www.kuaishou.com/short-video/{photo_id}",
            description=caption,
            duration=duration_ms / 1000 if duration_ms else None,
            thumbnail=photo.get("posterUrl") or photo.get("thumbnailUrl") or "",
            formats=[
                StreamFormat(
                    format_id="photo",
                    url=photo_url,
                    ext=ext,
                    height=photo.get("height"),
                    width=photo.get("width"),
                    vcodec="avc1",
                    acodec="mp4a",
                )
            ],
            download_headers={"Referer": "https://www.kuaishou.com/"},
        )
