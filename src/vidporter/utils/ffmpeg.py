"""ffmpeg 检测与音频抽取。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from vidporter.utils.log import get_logger

log = get_logger("vidporter.ffmpeg")


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ffmpeg_version() -> str:
    try:
        out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        return out.stdout.splitlines()[0] if out.stdout else "ffmpeg"
    except Exception:
        return "ffmpeg"


def extract_audio(src: Path, dest: Path, bitrate: str = "192k") -> Path:
    """从视频文件抽取音频轨道，返回输出路径。"""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-c:a",
        "libmp3lame" if dest.suffix == ".mp3" else "copy",
        "-b:a",
        bitrate,
        str(dest),
    ]
    log.info("ffmpeg 抽取音频 -> %s", dest.name)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError(f"ffmpeg 音频抽取失败: {proc.stderr[-400:]}")
    return dest
