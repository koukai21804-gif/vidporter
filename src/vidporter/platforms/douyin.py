"""抖音适配器。

思路：分享链接（v.douyin.com/xxx 或 www.douyin.com/video/{id}）→
请求 iesdouyin 移动分享页 → 解析 ``window._ROUTER_DATA`` 中的作品数据 →
得到无水印播放地址（playwm → play）。该路径是社区公开的通行做法，
平台随时可能调整，失败时下载引擎会自动回退到 yt-dlp。
"""

from __future__ import annotations

import re
from typing import ClassVar

from vidporter.exceptions import ExtractionError, UnsupportedURLError
from vidporter.models import MediaInfo, StreamFormat
from vidporter.platforms.base import BaseExtractor, ExtractContext
from vidporter.utils.log import get_logger
from vidporter.utils.net import MOBILE_UA, extract_json_after_marker, resolve_url

log = get_logger("vidporter.platforms.douyin")

_ID_RE = re.compile(r"/(?:video|note|slidelayout)/(\d+)")
_MODAL_ID_RE = re.compile(r"[?&]modal_id=(\d+)")


class DouyinExtractor(BaseExtractor):
    name = "douyin"
    display_name = "抖音"
    domains: ClassVar[tuple[str, ...]] = ("douyin.com", "iesdouyin.com")

    def extract(self, url: str, ctx: ExtractContext) -> MediaInfo:
        client = ctx.get_client(user_agent=MOBILE_UA)
        canonical = self._canonical_url(client, url)
        item_id = self._parse_item_id(canonical)
        if not item_id:
            raise UnsupportedURLError(f"无法从 URL 中解析出抖音作品 id: {url}")

        item = self._fetch_item(client, item_id, canonical)
        return self._build_info(item, item_id, canonical)

    # -- URL 处理 -----------------------------------------------------------

    def _canonical_url(self, client, url: str) -> str:
        if "v.douyin.com" in url or "iesdouyin.com/share" in url:
            return resolve_url(client, url)
        return url

    @staticmethod
    def _parse_item_id(url: str) -> str | None:
        m = _ID_RE.search(url) or _MODAL_ID_RE.search(url)
        return m.group(1) if m else None

    # -- 数据获取 -----------------------------------------------------------

    def _fetch_item(self, client, item_id: str, canonical_url: str) -> dict:
        share_url = f"https://www.iesdouyin.com/share/video/{item_id}/"
        try:
            resp = client.get(share_url)
            resp.raise_for_status()
        except Exception as e:
            raise ExtractionError(f"抖音分享页请求失败: {e}") from e

        try:
            router_data = extract_json_after_marker(resp.text, "window._ROUTER_DATA")
        except ExtractionError:
            raise ExtractionError(
                "分享页中没有作品数据（可能需要登录 cookie 或页面已改版）；"
                "请尝试 vidporter cookies export 导出抖音 cookie 后重试"
            ) from None

        item = self._find_item(router_data, item_id)
        if not item:
            raise ExtractionError("作品数据为空，作品可能已删除或私密")
        return item

    @staticmethod
    def _find_item(router_data: dict, item_id: str) -> dict | None:
        loader = router_data.get("loaderData", {})
        for page in loader.values():
            info_res = page.get("videoInfoRes") or page.get("noteInfoRes") or {}
            item_list = info_res.get("item_list", [])
            if item_list:
                # 分享页只承载一个作品
                return item_list[0]
        return None

    # -- 数据映射 -----------------------------------------------------------

    def _build_info(self, item: dict, item_id: str, canonical_url: str) -> MediaInfo:
        desc = (item.get("desc") or "").strip() or item_id
        video = item.get("video") or {}
        images = item.get("images") or []

        headers = {
            "Referer": "https://www.douyin.com/",
            "User-Agent": MOBILE_UA,
        }
        info = MediaInfo(
            platform=self.name,
            id=item_id,
            title=desc,
            webpage_url=f"https://www.douyin.com/video/{item_id}",
            description=desc,
            uploader=(item.get("author") or {}).get("nickname", ""),
            duration=(item.get("video") or {}).get("duration")
            or ((item.get("video") or {}).get("duration_precise")),
            thumbnail=(video.get("cover") or {}).get("url_list", [""])[0],
            download_headers=headers,
        )

        if images:
            info.media_type = "images"
            info.images = [
                (img.get("url_list") or [""])[-1] for img in images if img.get("url_list")
            ]
            if not info.images:
                raise ExtractionError("图集数据中没有可下载的图片")
            return info

        play_addr = (video.get("play_addr") or {}).get("url_list") or []
        if not play_addr:
            raise ExtractionError("作品中没有可下载的视频地址")
        # playwm 是带水印地址，替换为无水印的 play 接口
        no_wm = play_addr[0].replace("/playwm/", "/play/")
        info.formats.append(
            StreamFormat(
                format_id="no-watermark",
                url=no_wm,
                ext=(video.get("play_addr") or {}).get("uri_ext") or "mp4",
                height=((video.get("play_addr") or {}).get("height")),
                width=((video.get("play_addr") or {}).get("width")),
                vcodec="avc1",
                acodec="mp4a",
            )
        )
        return info
