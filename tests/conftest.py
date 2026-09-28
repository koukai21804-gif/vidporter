"""共享测试夹具：用 httpx.MockTransport 离线模拟各平台响应。"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from vidporter.config import Config
from vidporter.platforms.base import ExtractContext

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(out_dir=tmp_path / "downloads", cookies_dir=tmp_path / "cookies")


@pytest.fixture
def handler():
    """按 URL 前缀分发 fixture 的请求处理器。"""

    def handle(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "v.douyin.com" in url:
            return httpx.Response(
                302,
                headers={"Location": "https://www.douyin.com/video/7301234567890123456"},
            )
        if "iesdouyin.com/share/video/730999" in url:
            return httpx.Response(200, text=fixture("douyin_images.html"))
        if "iesdouyin.com/share" in url:
            return httpx.Response(200, text=fixture("douyin_video.html"))
        if "douyin.com" in url:
            # 重定向落地的页面内容不参与解析，仅要求可达
            return httpx.Response(200, text="<html></html>")
        if "xhslink.com" in url:
            return httpx.Response(
                302,
                headers={
                    "Location": "https://www.xiaohongshu.com/explore/6712345678901234567890ab?xsec_token=ABCtoken"
                },
            )
        if "xiaohongshu.com/explore/6712345678901234567890ab" in url:
            return httpx.Response(200, text=fixture("xhs_video.html"))
        if "xiaohongshu.com/explore/6712345678901234567890cd" in url:
            return httpx.Response(200, text=fixture("xhs_images.html"))
        if "kuaishou.com" in url:
            return httpx.Response(200, text=fixture("kuaishou.html"))
        return httpx.Response(404, text="not found")

    return handle


@pytest.fixture
def ctx(config: Config, handler) -> ExtractContext:
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return ExtractContext(config=config, client=client)
