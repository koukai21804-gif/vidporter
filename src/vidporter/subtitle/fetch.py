"""字幕批量抓取（B站 AI 字幕工作流）。

从批量脚本迁移而来：可断点续传（跳过已有 srt）、对 412/频繁限流退避重试、
失败清单落盘供重跑。
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path

from vidporter.platforms.ytdlp_backend import ytdlp_fetch_subtitles
from vidporter.utils.log import get_logger

log = get_logger("vidporter.subtitle.fetch")

_BV_RE = re.compile(r"(BV[0-9A-Za-z]{10})")


def bv_from_url(url: str) -> str | None:
    m = _BV_RE.search(url)
    return m.group(1) if m else None


def find_existing(out_dir: Path, bv: str) -> Path | None:
    """该 BV 是否已有字幕文件（任意语言后缀）。"""
    try:
        for name in out_dir.iterdir():
            if name.name.startswith(bv) and name.suffix.lower() in (".srt", ".vtt", ".json3"):
                return name
    except FileNotFoundError:
        pass
    return None


def load_url_list(list_file: Path) -> list[str]:
    """读取 URL/BV 列表文件；支持 BV 号直接书写、# 注释、空行。"""
    urls = []
    for line in list_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(
            line
            if line.lower().startswith(("http://", "https://"))
            else f"https://www.bilibili.com/video/{line}"
        )
    return urls


def fetch(
    urls: list[str],
    out_dir: Path,
    langs: str = "ai-zh,zh-Hans",
    cookies_file: Path | None = None,
    proxy: str | None = None,
    sleep: float = 1.0,
    max_retries: int = 3,
    status_cb: Callable[[str], None] | None = None,
) -> dict[str, str]:
    """批量抓取字幕，返回 {url: status}。"""
    log_cb = status_cb or (lambda msg: log.info("%s", msg))

    def existing_check(url: str) -> Path | None:
        bv = bv_from_url(url)
        return find_existing(out_dir, bv) if bv else None

    return ytdlp_fetch_subtitles(
        urls,
        out_dir=out_dir,
        langs=langs,
        cookies_file=cookies_file,
        proxy=proxy,
        sleep=sleep,
        existing_check=existing_check,
        max_retries=max_retries,
        status_cb=log_cb,
    )


def write_failure_report(results: dict[str, str], out_file: Path) -> int:
    """把失败项写回文件，便于下一轮重跑；返回失败数。"""
    failures = [url for url, st in results.items() if st.startswith("failed")]
    if failures:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text("\n".join(failures) + "\n", encoding="utf-8")
    elif out_file.exists():
        os.remove(out_file)
    return len(failures)
