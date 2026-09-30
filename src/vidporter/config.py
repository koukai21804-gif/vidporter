"""配置加载：内置默认值 ← 用户配置文件（TOML）。

配置文件查找顺序（第一个存在的生效）：
  1. ``--config`` 显式指定
  2. ``./vidporter.toml``（当前目录）
  3. ``%APPDATA%/vidporter/config.toml``（Windows）
     ``~/.config/vidporter/config.toml``（Linux / macOS）
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python < 3.11
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:  # pragma: no cover - 未安装 tomli 时降级为忽略配置文件
        tomllib = None  # type: ignore[assignment]


def user_config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "vidporter"
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "vidporter"


def default_cookies_dir() -> Path:
    return user_config_dir() / "cookies"


def find_config_file(explicit: Path | None = None) -> Path | None:
    candidates = []
    if explicit:
        candidates.append(explicit)
    candidates.append(Path.cwd() / "vidporter.toml")
    candidates.append(user_config_dir() / "config.toml")
    for c in candidates:
        if c.is_file():
            return c
    return None


@dataclass
class Config:
    """全局配置。CLI 参数会以不可变方式覆盖这里给出的值。"""

    out_dir: Path = field(default_factory=lambda: Path("downloads"))
    quality: int | None = None
    audio_format: str = "mp3"
    subtitle_langs: str = "ai-zh,zh-Hans"
    proxy: str | None = None
    cookies_dir: Path = field(default_factory=default_cookies_dir)
    # 各平台 cookie 文件；None 表示用 cookies_dir 下的默认名
    bilibili_cookies: Path | None = None
    douyin_cookies: Path | None = None
    kuaishou_cookies: Path | None = None
    xiaohongshu_cookies: Path | None = None
    # 微信视频号外部嗅探工具的可执行文件路径（res-downloader / wx_video_download）
    channels_tool_path: Path | None = None
    rate_limit_sleep: float = 1.0

    def cookie_file_for(self, platform: str) -> Path:
        custom = getattr(self, f"{platform}_cookies", None)
        if custom:
            return Path(custom)
        return self.cookies_dir / f"{platform}.txt"

    @classmethod
    def load(cls, explicit: Path | None = None) -> Config:
        cfg = cls()
        path = find_config_file(explicit)
        if path is None:
            return cfg
        if tomllib is None:  # pragma: no cover
            return cfg
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cfg._apply_mapping(data.get("vidporter", data))

    def _apply_mapping(self, data: dict) -> Config:
        kwargs = {}
        path_keys = {
            "out_dir",
            "cookies_dir",
            "bilibili_cookies",
            "douyin_cookies",
            "kuaishou_cookies",
            "xiaohongshu_cookies",
            "channels_tool_path",
        }
        for key, value in data.items():
            if not hasattr(self, key):
                continue
            if key in path_keys and value is not None:
                value = Path(str(value)).expanduser()
            kwargs[key] = value
        return replace(self, **kwargs)
