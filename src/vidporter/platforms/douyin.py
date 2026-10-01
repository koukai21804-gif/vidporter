"""抖音适配器。

思路：分享链接（v.douyin.com/xxx 或 www.douyin.com/video/{id}）→
请求 iesdouyin 移动分享页 → 解析 ``window._ROUTER_DATA`` 中的作品数据 →
得到无水印播放地址（playwm → play）。该路径是社区公开的通行做法，
平台随时可能调整，失败时下载引擎会自动回退到 yt-dlp。

注意：分享页正逐步改为客户端渲染，必须有 ``ttwid`` cookie 才能拿到 SSR
作品数据；cookie 文件里没有 ttwid 时会自动向字节签发接口申请一个并写回
（游客级，长期有效），``vidporter cookies export --domain douyin`` 导出的
其余 cookie（登录态等）也会按请求附带。仍失败时下载引擎自动回退 yt-dlp。
"""

from __future__ import annotations

import re
import time
from typing import ClassVar

from vidporter.exceptions import ExtractionError, UnsupportedURLError
from vidporter.models import MediaInfo, StreamFormat
from vidporter.platforms.base import BaseExtractor, ExtractContext
from vidporter.utils.log import get_logger
from vidporter.utils.net import MOBILE_UA, extract_json_after_marker, resolve_url

log = get_logger("vidporter.platforms.douyin")

_ID_RE = re.compile(r"/(?:video|note|slidelayout)/(\d+)")
_MODAL_ID_RE = re.compile(r"[?&]modal_id=(\d+)")

# 字节系游客 ttwid 签发接口（社区通行做法）：分享页 SSR 数据必须有 ttwid，
# 而无头浏览器访问 douyin.com 首页只能拿到 __ac_* 验证 cookie，拿不到 ttwid
_TTWID_REGISTER_URL = "https://ttwid.bytedance.com/ttwid/union/register/"
_TTWID_BODY = {
    "region": "cn",
    "aid": 1768,
    "needFid": False,
    "service": "www.ixigua.com",
    "migrate_info": {"ticket": "", "source": "node"},
    "cbUrlProtocol": "https",
    "union": True,
}


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

        item = self._fetch_item(client, item_id, canonical, ctx)
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

    def _fetch_item(self, client, item_id: str, canonical_url: str, ctx: ExtractContext) -> dict:
        share_url = f"https://www.iesdouyin.com/share/video/{item_id}/"
        cookies = self._request_cookies(ctx) or {}
        if "ttwid" not in cookies:
            ttwid = self._mint_ttwid(client)
            if ttwid:
                cookies["ttwid"] = ttwid
                self._persist_ttwid(ctx, ttwid)
        if cookies:
            client.cookies.update(cookies)
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
                "可尝试 vidporter cookies export --domain douyin 导出 cookie 后重试"
            ) from None

        item = self._find_item(router_data, item_id)
        if not item:
            # 分享页已是客户端渲染壳时同样走这里（loaderData 只有占位键）
            raise ExtractionError(
                "分享页中没有作品数据：作品可能已删除或私密，也可能被风控拦截；"
                "可尝试 vidporter cookies export --domain douyin 导出 cookie 后重试"
            )
        return item

    @staticmethod
    def _request_cookies(ctx: ExtractContext) -> dict[str, str] | None:
        """导出的抖音 cookie 存在时按请求附带（ttwid 等是拿到 SSR 数据的关键）。"""
        cookie_path = ctx.cookies_for("douyin")
        if not cookie_path:
            return None
        from vidporter.cookies import netscape

        cookies = netscape.cookies_for_domain(cookie_path, "douyin")
        return {c.name: c.value for c in cookies} or None

    @staticmethod
    def _mint_ttwid(client) -> str | None:
        """向字节签发接口申请游客 ttwid；失败返回 None（回退 yt-dlp 兜底）。"""
        try:
            resp = client.post(_TTWID_REGISTER_URL, json=_TTWID_BODY)
            resp.raise_for_status()
            ttwid = resp.cookies.get("ttwid")
            if ttwid:
                log.debug("已申请游客 ttwid")
            return ttwid
        except Exception as e:
            log.warning("申请 ttwid 失败: %s", e)
            return None

    @staticmethod
    def _persist_ttwid(ctx: ExtractContext, ttwid: str) -> None:
        """把游客 ttwid 写回 cookie 文件（一次申请长期有效），yt-dlp 兜底也能用。"""
        from vidporter.cookies import netscape

        path = ctx.config.cookie_file_for("douyin")
        existing = netscape.load_file(path) if path.is_file() else []
        keep = [c for c in existing if c.name != "ttwid"]
        keep.append(
            netscape.Cookie(
                name="ttwid",
                value=ttwid,
                domain=".douyin.com",
                expires=int(time.time()) + 365 * 86400,
            )
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        netscape.write_netscape(path, keep)
        log.debug("游客 ttwid 已缓存 → %s", path)

    @staticmethod
    def _find_item(router_data: dict, item_id: str) -> dict | None:
        loader = router_data.get("loaderData")
        if not isinstance(loader, dict):
            return None
        for page in loader.values():
            if not isinstance(page, dict):
                # loaderData 里 video_layout 等占位键恒为 null
                continue
            info_res = page.get("videoInfoRes") or page.get("noteInfoRes") or {}
            item_list = info_res.get("item_list") or []
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
