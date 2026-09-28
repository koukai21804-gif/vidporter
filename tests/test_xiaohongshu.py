from __future__ import annotations

import pytest

from vidporter.exceptions import ExtractionError, UnsupportedURLError
from vidporter.platforms.xiaohongshu import XiaohongshuExtractor


@pytest.fixture
def xhs() -> XiaohongshuExtractor:
    return XiaohongshuExtractor()


def test_video_extract(xhs, ctx):
    info = xhs.extract("http://xhslink.com/aBcDeF", ctx)
    assert info.platform == "xiaohongshu"
    assert info.id == "6712345678901234567890ab"
    assert info.title == "测试笔记标题"
    assert info.media_type == "video"
    # h264 多码率时选 bitrate 最高的
    assert "1080p" in info.formats[0].url
    assert info.download_headers["Referer"] == "https://www.xiaohongshu.com/"


def test_images_extract(xhs, ctx):
    info = xhs.extract(
        "https://www.xiaohongshu.com/explore/6712345678901234567890cd?xsec_token=T", ctx
    )
    assert info.media_type == "images"
    assert info.images == [
        "https://sns-img-hw.xhscdn.com/img1.jpg",
        "https://sns-img-hw.xhscdn.com/img2.jpg",
    ]


def test_unsupported_url(xhs, ctx):
    with pytest.raises(UnsupportedURLError):
        xhs.extract("https://www.xiaohongshu.com/user/profile/abc", ctx)


def test_note_missing_raises(xhs, ctx, handler, monkeypatch):
    # 页面存在但笔记数据缺失 → ExtractionError
    def empty_handler(request):
        return __import__("httpx").Response(
            200, text='<script>window.__INITIAL_STATE__={"note":{"noteDetailMap":{}}};</script>'
        )

    import httpx

    ctx.client = httpx.Client(transport=httpx.MockTransport(empty_handler))
    with pytest.raises(ExtractionError):
        xhs.extract(
            "https://www.xiaohongshu.com/explore/6712345678901234567890ab?xsec_token=T", ctx
        )


def test_undefined_literal_fallback(xhs, ctx):
    # 含 undefined 的非严格 JSON 应通过文本替换兜底解析
    import json

    state = {
        "note": {
            "noteDetailMap": {
                "6712345678901234567890ab": {
                    "note": {
                        "noteId": "6712345678901234567890ab",
                        "type": "video",
                        "title": "兜底标题",
                        "video": {
                            "media": {
                                "videoStream": {
                                    "h264": [
                                        {
                                            "masterUrl": "https://sns-video-hw.xhscdn.com/stream/v.mp4",
                                            "videoBitrate": 800,
                                        }
                                    ]
                                }
                            }
                        },
                    }
                }
            }
        },
        "x": None,
    }
    # 用合法 JSON 生成页面文本，再把 null 换成 undefined 模拟非严格 JSON
    page = (
        "<script>window.__INITIAL_STATE__="
        + json.dumps(state).replace(": null", ": undefined")
        + ";</script>"
    )

    def weird_handler(request):
        import httpx

        return httpx.Response(200, text=page)

    import httpx

    ctx.client = httpx.Client(transport=httpx.MockTransport(weird_handler))
    info = xhs.extract(
        "https://www.xiaohongshu.com/explore/6712345678901234567890ab?xsec_token=T", ctx
    )
    assert info.title == "兜底标题"
    assert info.formats[0].url.endswith(".mp4")
