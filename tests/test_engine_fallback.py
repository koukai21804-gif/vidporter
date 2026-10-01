"""引擎回退行为：平台解析失败后 yt-dlp 兜底应携带该平台的 cookie。"""

from __future__ import annotations

import httpx
import pytest

from vidporter.download.engine import Engine
from vidporter.exceptions import ExtractionError
from vidporter.models import DownloadOptions
from vidporter.platforms.base import ExtractContext

_SHELL_HTML = (
    '<html><head><script>window._ROUTER_DATA = {"loaderData":'
    '{"video_layout":null,"video_(id)/page":{"itemId":"7301234567890123456"}}}'
    "</script></head><body></body></html>"
)


def _shell_ctx(config) -> ExtractContext:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_SHELL_HTML)

    return ExtractContext(
        config=config,
        client=httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True),
    )


def _write_douyin_cookies(config) -> None:
    from vidporter.cookies import netscape

    cookie_file = config.cookie_file_for("douyin")
    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    netscape.write_netscape(
        cookie_file,
        [netscape.Cookie(name="ttwid", value="test", domain=".douyin.com")],
    )


def test_fallback_passes_platform_cookies(config, monkeypatch):
    _write_douyin_cookies(config)
    engine = Engine(config=config)
    engine.ctx = _shell_ctx(config)

    captured: dict[str, object] = {}

    def fake_generic_download(url, ctx, opts):
        captured["cookies_file"] = opts.cookies_file
        raise ExtractionError("stop here")

    monkeypatch.setattr(engine.registry.generic, "download", fake_generic_download)
    opts = DownloadOptions(out_dir=config.out_dir)
    with pytest.raises(ExtractionError, match="stop here"):
        engine.download("https://www.douyin.com/video/7301234567890123456", opts)
    assert captured["cookies_file"] == config.cookie_file_for("douyin")
    # 不污染调用方复用的 opts（批处理场景）
    assert opts.cookies_file is None


def test_fallback_without_cookies_stays_none(config, monkeypatch):
    engine = Engine(config=config)
    engine.ctx = _shell_ctx(config)

    captured: dict[str, object] = {}

    def fake_generic_download(url, ctx, opts):
        captured["cookies_file"] = opts.cookies_file
        raise ExtractionError("stop here")

    monkeypatch.setattr(engine.registry.generic, "download", fake_generic_download)
    with pytest.raises(ExtractionError, match="stop here"):
        engine.download("https://www.douyin.com/video/7301234567890123456", DownloadOptions())
    assert captured["cookies_file"] is None
