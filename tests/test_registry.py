from __future__ import annotations

import pytest

from vidporter.exceptions import CaptureRequiredError
from vidporter.platforms.channels import WechatChannelsExtractor
from vidporter.platforms.douyin import DouyinExtractor
from vidporter.platforms.xiaohongshu import XiaohongshuExtractor
from vidporter.registry import Registry


@pytest.fixture
def registry() -> Registry:
    return Registry()


@pytest.mark.parametrize(
    "url,expected_name",
    [
        ("https://www.bilibili.com/video/BV1xx411c7mD", "bilibili"),
        ("https://b23.tv/abc123", "bilibili"),
        ("https://v.douyin.com/iRNBho5/", "douyin"),
        ("https://www.douyin.com/video/7301234567890123456", "douyin"),
        ("https://v.kuaishou.com/7g8hj2", "kuaishou"),
        ("https://www.kuaishou.com/short-video/3xabc123", "kuaishou"),
        ("http://xhslink.com/aBcDeF", "xiaohongshu"),
        ("https://www.xiaohongshu.com/explore/6712345678901234567890ab", "xiaohongshu"),
        ("https://channels.weixin.qq.com/share/5KGk00XxmM86", "wechat-channels"),
        # 伪装成平台路径的其它站点应落到通用引擎
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "generic"),
        ("https://example.com/video/123", "generic"),
        ("https://fakebilibili.com/video/BV1xx", "generic"),
    ],
)
def test_resolve_dispatch(registry: Registry, url: str, expected_name: str):
    assert registry.resolve(url).name == expected_name


def test_by_name(registry: Registry):
    assert registry.by_name("bilibili").name == "bilibili"
    assert registry.by_name("generic").name == "generic"
    with pytest.raises(KeyError):
        registry.by_name("nope")


def test_subdomain_matching():
    assert DouyinExtractor.can_handle("https://www.iesdouyin.com/share/video/1/")
    assert XiaohongshuExtractor.can_handle("https://www.xiaohongshu.com/explore/x")
    assert not DouyinExtractor.can_handle("https://douyin.evil.com/video/1")


def test_wechat_channels_raises_capture(registry: Registry):
    ex = registry.resolve("https://channels.weixin.qq.com/share/abc")
    assert ex.capture_required is True
    with pytest.raises(CaptureRequiredError):
        WechatChannelsExtractor().extract("https://channels.weixin.qq.com/x", None)


def test_douyin_rejects_non_video_url():
    ex = DouyinExtractor()
    # 非作品页解析不出 id
    assert ex._parse_item_id("https://www.douyin.com/user/MS4wLjABAAAA") is None
    assert ex._parse_item_id("https://www.douyin.com/discover") is None
    assert (
        ex._parse_item_id("https://www.douyin.com/video/7301234567890123456")
        == "7301234567890123456"
    )
    assert (
        ex._parse_item_id("https://www.douyin.com/discover?modal_id=7301234567890123456")
        == "7301234567890123456"
    )
