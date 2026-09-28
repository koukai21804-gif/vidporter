from __future__ import annotations

import httpx
import pytest

from vidporter.exceptions import ExtractionError, UnsupportedURLError
from vidporter.platforms.douyin import DouyinExtractor


@pytest.fixture
def douyin() -> DouyinExtractor:
    return DouyinExtractor()


def test_video_extract(douyin, ctx):
    info = douyin.extract("https://v.douyin.com/iRNBho5/", ctx)
    assert info.platform == "douyin"
    assert info.id == "7301234567890123456"
    assert info.title == "这是一条测试视频标题"
    assert info.uploader == "测试UP主"
    assert info.media_type == "video"
    # 无水印替换
    assert "/play/" in info.formats[0].url
    assert "/playwm/" not in info.formats[0].url
    # 防盗链请求头
    assert info.download_headers["Referer"] == "https://www.douyin.com/"


def test_images_extract(douyin, ctx):
    info = douyin.extract("https://www.douyin.com/note/7309991234567890123", ctx)
    assert info.media_type == "images"
    assert len(info.images) == 2
    # 图集取 url_list 的最后一个（通常是大图）
    assert info.images[0].endswith("big=1")


def test_unsupported_url(douyin, ctx):
    with pytest.raises(UnsupportedURLError):
        douyin.extract("https://www.douyin.com/discover?modal_id=", ctx)


def test_page_without_data(douyin, ctx):
    # 404 分支返回 not found 页面 → 无 _ROUTER_DATA
    def bad_handler(request: httpx.Request):
        return httpx.Response(200, text="<html>no data</html>")

    import httpx as _httpx

    ctx.client = _httpx.Client(transport=_httpx.MockTransport(bad_handler))
    with pytest.raises(ExtractionError):
        douyin.extract("https://www.douyin.com/video/7301234567890123456", ctx)
