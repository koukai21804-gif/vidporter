from __future__ import annotations

import httpx

from vidporter.cookies import netscape


def _sample_cookies():
    return [
        netscape.Cookie("SESSDATA", "abc,def", ".bilibili.com", http_only=True, expires=1900000000),
        netscape.Cookie("buvid3", "xyz123", ".bilibili.com", http_only=False),
        netscape.Cookie("other", "v", ".example.com", http_only=False),
    ]


def test_write_and_parse_roundtrip(tmp_path):
    path = tmp_path / "cookies.txt"
    count = netscape.write_netscape(path, _sample_cookies())
    assert count == 3
    assert "# Netscape HTTP Cookie File" in path.read_text(encoding="utf-8")

    parsed = netscape.load_file(path)
    by_name = {c.name: c for c in parsed}
    assert by_name["SESSDATA"].value == "abc,def"
    assert by_name["SESSDATA"].http_only is True
    assert by_name["buvid3"].http_only is False
    assert by_name["SESSDATA"].domain == ".bilibili.com"


def test_filter_and_merge():
    a = [netscape.Cookie("k", "from_a", ".a.com")]
    b = [netscape.Cookie("k", "from_b", ".b.com"), netscape.Cookie("x", "vx", ".b.com")]
    merged = netscape.merge(a, b)
    assert {c.name: c.value for c in merged} == {"k": "from_a", "x": "vx"}
    merged_rev = netscape.merge(a, b, prefer_first=False)
    assert {c.name: c.value for c in merged_rev}["k"] == "from_b"


def test_filter_by_domain():
    cookies = netscape.filter_by_domain(_sample_cookies(), "bilibili")
    assert len(cookies) == 2
    assert all("bilibili" in c.domain for c in cookies)


def test_header_string():
    header = netscape.header_string(
        [netscape.Cookie("a", "1", ".x.com"), netscape.Cookie("b", "2", ".x.com")]
    )
    assert header == "a=1; b=2"


def test_cdp_mapping():
    cdp_cookies = [
        {
            "name": "SESSDATA",
            "value": "s",
            "domain": ".bilibili.com",
            "path": "/",
            "expires": 1900000000,
            "secure": True,
            "httpOnly": True,
        },
        {
            "name": "sid",
            "value": "t",
            "domain": "bilibili.com",
            "path": "/",
            "expires": -1,
            "secure": False,
            "httpOnly": False,
        },
    ]
    cookies = netscape.from_cdp(cdp_cookies)
    assert cookies[0].http_only and cookies[0].secure
    assert cookies[1].expires == 0  # 会话 cookie


def test_expired_cookies_filtered(tmp_path):
    path = tmp_path / "c.txt"
    netscape.write_netscape(
        path,
        [
            netscape.Cookie("old", "v", ".x.com", expires=1000),  # 已过期
            netscape.Cookie("live", "v", ".x.com", expires=3_000_000_000),
        ],
    )
    live = netscape.cookies_for_domain(path, "x.com")
    assert [c.name for c in live] == ["live"]


def test_http_downloader_resume(tmp_path):
    from vidporter.download.http_downloader import download_file

    data = b"0123456789" * 100  # 1000 字节

    def handler(request: httpx.Request):
        rng = request.headers.get("range")
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            return httpx.Response(
                206,
                content=data[start:],
                headers={"Content-Range": f"bytes {start}-{len(data) - 1}/{len(data)}"},
            )
        return httpx.Response(200, content=data, headers={"Content-Length": str(len(data))})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dest = tmp_path / "video.mp4"

    events = []
    path = download_file(
        client,
        "https://cdn.example.com/video.mp4",
        dest,
        progress_cb=lambda d, t: events.append((d, t)),
    )
    assert path == dest
    assert dest.read_bytes() == data
    assert not dest.with_suffix(".mp4.part").exists()
    assert events  # 进度回调被调用


def test_http_downloader_resume_from_part(tmp_path):
    from vidporter.download.http_downloader import download_file

    data = b"0123456789" * 100
    dest = tmp_path / "video.mp4"
    part = dest.with_suffix(".mp4.part")
    part.write_bytes(data[:400])  # 模拟上次下载到 40%

    def handler(request: httpx.Request):
        rng = request.headers.get("range")
        start = int(rng.split("=")[1].split("-")[0]) if rng else 0
        assert start == 400, "应从断点继续"
        if rng:
            return httpx.Response(
                206,
                content=data[start:],
                headers={"Content-Range": f"bytes {start}-{len(data) - 1}/{len(data)}"},
            )
        return httpx.Response(200, content=data, headers={"Content-Length": str(len(data))})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    path = download_file(client, "https://cdn.example.com/video.mp4", dest)
    assert path.read_bytes() == data


def test_http_downloader_ignores_unsupported_range(tmp_path):
    from vidporter.download.http_downloader import download_file

    data = b"abcdef" * 10

    def handler(request: httpx.Request):
        # 服务器不支持 Range：带 Range 头也返回 200 全量
        return httpx.Response(200, content=data, headers={"Content-Length": str(len(data))})

    dest = tmp_path / "v.mp4"
    dest.with_suffix(".mp4.part").write_bytes(data[:10])
    client = httpx.Client(transport=httpx.MockTransport(handler))
    download_file(client, "https://cdn.example.com/v.mp4", dest)
    assert dest.read_bytes() == data


def test_auto_navigate_url():
    from vidporter.cookies.browser_cdp import auto_navigate_url

    assert auto_navigate_url("douyin") == "https://www.douyin.com"
    assert auto_navigate_url("") == "about:blank"
