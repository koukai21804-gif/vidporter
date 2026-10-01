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


_SHELL_HTML = """<!doctype html><html><head><script>
window._ROUTER_DATA = {"loaderData":{"video_layout":null,"video_(id)/page":
{"ua":"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)","isSpider":false,
"query":{},"renderInSSR":1,"lastPath":"/share/video/7301234567890123456/",
"itemId":"7301234567890123456","abParams":{}}}}
</script></head><body><div id="root"></div></body></html>"""


def test_shell_page_with_null_loader_entry(douyin, ctx):
    # 2025+ 分享页改为客户端渲染壳：loaderData 含 video_layout: null 占位键。
    # 旧版对每个值直接 .get，会抛 AttributeError('NoneType' object has no attribute 'get')
    def shell_handler(request: httpx.Request):
        return httpx.Response(200, text=_SHELL_HTML)

    ctx.client = httpx.Client(transport=httpx.MockTransport(shell_handler), follow_redirects=True)
    with pytest.raises(ExtractionError, match="cookie"):
        douyin.extract("https://www.douyin.com/video/7301234567890123456", ctx)


def test_find_item_tolerates_null_pages():
    router_data = {
        "loaderData": {
            "video_layout": None,
            "video_(id)/page": {"videoInfoRes": {"item_list": [{"desc": "ok"}]}},
        }
    }
    assert DouyinExtractor._find_item(router_data, "7301234567890123456") == {"desc": "ok"}
    # loaderData 缺失 / 值全为 null 时安全返回 None，而不是抛 AttributeError
    assert DouyinExtractor._find_item({"loaderData": None}, "x") is None
    assert DouyinExtractor._find_item({"loaderData": {"a": None}}, "x") is None
    assert DouyinExtractor._find_item({}, "x") is None


def test_douyin_cookies_attached(douyin, ctx):
    from vidporter.cookies import netscape

    cookie_file = ctx.config.cookie_file_for("douyin")
    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    netscape.write_netscape(
        cookie_file,
        [netscape.Cookie(name="ttwid", value="1%7Cabc", domain=".douyin.com")],
    )
    seen: dict[str, str] = {}

    def cookie_handler(request: httpx.Request):
        seen["cookie"] = request.headers.get("cookie", "")
        return httpx.Response(200, text=_SHELL_HTML)

    ctx.client = httpx.Client(transport=httpx.MockTransport(cookie_handler), follow_redirects=True)
    with pytest.raises(ExtractionError):
        douyin.extract("https://www.douyin.com/video/7301234567890123456", ctx)
    assert "ttwid=1%7Cabc" in seen["cookie"]


_VIDEO_HTML = (
    '<html><head><script>window._ROUTER_DATA = {"loaderData":{'
    '"video_layout":null,"video_(id)/page":{"videoInfoRes":{"item_list":[{'
    '"desc":"测试视频","video":{"play_addr":{"uri_ext":"mp4",'
    '"url_list":["https://aweme.snssdk.com/playwm/?video_id=x"]}}}]}}}}'
    "</script></head><body></body></html>"
)


def test_ttwid_minted_and_persisted(douyin, ctx):
    # cookie 文件里没有 ttwid（如 CDP 导出只拿到 __ac_*）→ 自动申请并写回
    def handler(request: httpx.Request):
        url = str(request.url)
        if "ttwid.bytedance.com" in url:
            return httpx.Response(
                200,
                json={"status_code": 0},
                headers={"Set-Cookie": "ttwid=1%7Cminted; Path=/; Domain=bytedance.com"},
            )
        if "iesdouyin.com/share" in url:
            assert "ttwid=1%7Cminted" in request.headers.get("cookie", "")
            return httpx.Response(200, text=_VIDEO_HTML)
        return httpx.Response(404, text="not found")

    ctx.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    info = douyin.extract("https://www.douyin.com/video/7301234567890123456", ctx)
    assert info.title == "测试视频"

    from vidporter.cookies import netscape

    cookie_file = ctx.config.cookie_file_for("douyin")
    assert cookie_file.is_file()
    assert "ttwid" in [c.name for c in netscape.load_file(cookie_file)]


def test_ttwid_not_minted_when_present(douyin, ctx):
    from vidporter.cookies import netscape

    cookie_file = ctx.config.cookie_file_for("douyin")
    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    netscape.write_netscape(
        cookie_file,
        [netscape.Cookie(name="ttwid", value="1%7Cexisting", domain=".douyin.com")],
    )

    def handler(request: httpx.Request):
        url = str(request.url)
        if "ttwid.bytedance.com" in url:
            raise AssertionError("已有 ttwid 时不应再申请")
        if "iesdouyin.com/share" in url:
            assert "ttwid=1%7Cexisting" in request.headers.get("cookie", "")
            return httpx.Response(200, text=_VIDEO_HTML)
        return httpx.Response(404, text="not found")

    ctx.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    douyin.extract("https://www.douyin.com/video/7301234567890123456", ctx)
