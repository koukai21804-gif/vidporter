"""微信视频号适配器。

视频号的视频流经加密域名分发、密钥随客户端会话下发，**无法**像其它平台
那样通过公开网页直接解析，必须本地抓包（嗅探）。本项目对视频号采取
「外部工具桥接」策略：``vidporter channels`` 命令检测 / 启动本机已安装的
开源嗅探工具（res-downloader、WeChatVideoDownloader），下载完成后文件
仍由用户管理。架构上保留 :class:`CaptureRequiredError`，欢迎社区贡献
纯 Python 的嗅探后端。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

from vidporter.exceptions import CaptureRequiredError
from vidporter.platforms.base import BaseExtractor, ExtractContext

GUIDANCE = """\
微信视频号的视频流是加密分发的，需要在客户端播放时由本地代理抓包。
两种方式：
  1. 运行 `vidporter channels`，自动启动已安装的嗅探工具；
  2. 手动使用开源工具：
     - res-downloader（Apache-2.0，活跃维护）
       https://github.com/putyy/res-downloader
     - WeChatVideoDownloader
       https://github.com/lecepin/WeChatVideoDownloader
在工具开启代理后，于微信 PC 端打开并播放目标视频号内容，
工具会捕获真实播放地址并下载。"""

# 各平台下嗅探工具的常见可执行文件名
TOOL_BINARIES = {
    "res-downloader": ["res-downloader"],
    "wx-video-download": ["wx_video_download", "wx-video-download"],
}


class WechatChannelsExtractor(BaseExtractor):
    name = "wechat-channels"
    display_name = "微信视频号"
    domains: ClassVar[tuple[str, ...]] = ("channels.weixin.qq.com",)
    capture_required: ClassVar[bool] = True

    def extract(self, url: str, ctx: ExtractContext) -> None:
        raise CaptureRequiredError(
            "微信视频号需要本地抓包获取视频流，无法直接解析。", guidance=GUIDANCE
        )


def find_sniffer_tool(config_path: Path | None = None) -> Path | None:
    """按顺序查找本机嗅探工具：显式配置 → PATH → 常见安装位置。"""
    if config_path and Path(config_path).is_file():
        return Path(config_path)
    for names in TOOL_BINARIES.values():
        for name in names:
            which = shutil.which(name)
            if which:
                return Path(which)
    candidates = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        local_appdata = Path(local_appdata)
        candidates += [
            local_appdata / "Programs" / "res-downloader" / "res-downloader.exe",
            local_appdata / "res-downloader" / "res-downloader.exe",
        ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def launch_sniffer_tool(tool_path: Path | None = None) -> Path | None:
    """启动嗅探工具（不阻塞），返回所用可执行文件路径；找不到返回 None。"""
    exe = find_sniffer_tool(tool_path)
    if exe is None:
        return None
    if sys.platform == "win32":
        subprocess.Popen([str(exe)], creationflags=subprocess.DETACHED_PROCESS)  # type: ignore[attr-defined]
    else:
        subprocess.Popen([str(exe)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return exe
