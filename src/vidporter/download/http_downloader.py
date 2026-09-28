"""支持断点续传的 HTTP 流式下载。"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import httpx

from vidporter.exceptions import DownloadError
from vidporter.utils.log import get_logger

log = get_logger("vidporter.download.http")

CHUNK_SIZE = 64 * 1024
ProgressCallback = Callable[[int, int | None], None]  # (已下载字节, 总字节或 None)


def download_file(
    client: httpx.Client,
    url: str,
    dest: Path,
    headers: dict[str, str] | None = None,
    progress_cb: ProgressCallback | None = None,
    resume: bool = True,
    max_retries: int = 3,
) -> Path:
    """下载 ``url`` 到 ``dest``，带 .part 临时文件与 Range 断点续传。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    done = part.stat().st_size if (resume and part.exists()) else 0
    headers = dict(headers or {})

    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return _attempt(client, url, dest, part, headers, progress_cb, resume, done)
        except (httpx.HTTPError, OSError) as e:
            last_err = e
            log.warning("下载中断（第 %d/%d 次）: %s", attempt, max_retries, e)
            done = part.stat().st_size if part.exists() else 0
            time.sleep(min(2**attempt, 10))
    raise DownloadError(f"下载失败 {url}: {last_err}")


def _attempt(
    client: httpx.Client,
    url: str,
    dest: Path,
    part: Path,
    headers: dict[str, str],
    progress_cb: ProgressCallback | None,
    resume: bool,
    done: int,
) -> Path:
    req_headers = dict(headers)
    if done > 0:
        req_headers["Range"] = f"bytes={done}-"
    with client.stream("GET", url, headers=req_headers) as resp:
        if resume and done > 0 and resp.status_code == 200:
            # 服务器不支持 Range，从头开始
            done = 0
        resp.raise_for_status()

        total: int | None = None
        if resp.status_code == 206:
            # "bytes 100-999/1234" → 完整大小是斜杠后的数字
            content_range = resp.headers.get("Content-Range", "")
            if "/" in content_range:
                try:
                    total = int(content_range.rsplit("/", 1)[1])
                except ValueError:
                    total = None
        elif resp.headers.get("Content-Length"):
            total = int(resp.headers["Content-Length"])

        mode = "ab" if (resp.status_code == 206 and done > 0) else "wb"
        received = 0
        with open(part, mode) as f:
            for chunk in resp.iter_bytes(CHUNK_SIZE):
                f.write(chunk)
                received += len(chunk)
                if progress_cb:
                    progress_cb(done + received, total)
    part.replace(dest)
    return dest
