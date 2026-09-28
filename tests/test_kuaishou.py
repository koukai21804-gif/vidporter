from __future__ import annotations

import pytest

from vidporter.exceptions import ExtractionError, UnsupportedURLError
from vidporter.platforms.kuaishou import KuaishouExtractor


@pytest.fixture
def ks() -> KuaishouExtractor:
    return KuaishouExtractor()


def test_extract(ks, ctx):
    info = ks.extract("https://www.kuaishou.com/short-video/3xabc123def456", ctx)
    assert info.platform == "kuaishou"
    assert info.id == "3xabc123def456"
    assert info.title == "快手测试视频标题"
    assert info.formats[0].url.endswith(".mp4")
    assert info.duration == 22.0  # 毫秒 → 秒
    assert info.download_headers["Referer"] == "https://www.kuaishou.com/"


def test_unsupported_url(ks, ctx):
    with pytest.raises(UnsupportedURLError):
        ks.extract("https://www.kuaishou.com/profile/xyz", ctx)


def test_page_without_apollo(ks, ctx):
    def empty_handler(request):
        import httpx

        return httpx.Response(200, text="<html><body>no data</body></html>")

    import httpx

    ctx.client = httpx.Client(transport=httpx.MockTransport(empty_handler))
    with pytest.raises(ExtractionError):
        ks.extract("https://www.kuaishou.com/short-video/3xabc123def456", ctx)
