"""平台注册表：URL → 适配器的分发中枢。"""

from __future__ import annotations

from vidporter.platforms.base import BaseExtractor
from vidporter.platforms.bilibili import BilibiliExtractor
from vidporter.platforms.channels import WechatChannelsExtractor
from vidporter.platforms.douyin import DouyinExtractor
from vidporter.platforms.generic import GenericExtractor
from vidporter.platforms.kuaishou import KuaishouExtractor
from vidporter.platforms.xiaohongshu import XiaohongshuExtractor

PLATFORM_NAMES = (
    "bilibili",
    "douyin",
    "kuaishou",
    "xiaohongshu",
    "wechat-channels",
    "generic",
)


class Registry:
    def __init__(self, extractors: list[BaseExtractor] | None = None) -> None:
        if extractors is None:
            extractors = [
                BilibiliExtractor(),
                DouyinExtractor(),
                KuaishouExtractor(),
                XiaohongshuExtractor(),
                WechatChannelsExtractor(),
            ]
        self.specific = extractors
        self.generic = GenericExtractor()

    def resolve(self, url: str) -> BaseExtractor:
        for extractor in self.specific:
            if extractor.can_handle(url):
                return extractor
        return self.generic

    def by_name(self, name: str) -> BaseExtractor:
        for extractor in self.specific:
            if extractor.name == name:
                return extractor
        if name == "generic":
            return self.generic
        raise KeyError(f"未知平台: {name}")


def default_registry() -> Registry:
    return Registry()
