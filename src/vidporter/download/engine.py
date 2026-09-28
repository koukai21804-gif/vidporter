"""下载引擎：URL 分发 → 解析 → 下载，含跨平台回退与批处理。"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from vidporter.config import Config
from vidporter.exceptions import CaptureRequiredError, ExtractionError, VidporterError
from vidporter.models import DownloadOptions, DownloadResult, MediaInfo
from vidporter.platforms.base import ExtractContext
from vidporter.platforms.channels import GUIDANCE as CHANNELS_GUIDANCE
from vidporter.registry import Registry, default_registry
from vidporter.utils.log import get_logger

log = get_logger("vidporter.engine")


@dataclass
class Engine:
    """一次会话的下载引擎。"""

    config: Config
    registry: Registry = None  # type: ignore[assignment]
    ctx: ExtractContext | None = None

    def __post_init__(self) -> None:
        if self.registry is None:
            self.registry = default_registry()
        if self.ctx is None:
            self.ctx = ExtractContext(config=self.config)

    # -- 解析 ---------------------------------------------------------------

    def info(self, url: str, platform: str | None = None) -> MediaInfo:
        extractor = self.registry.by_name(platform) if platform else self.registry.resolve(url)
        if extractor.capture_required:
            raise CaptureRequiredError(
                "微信视频号需要本地抓包获取视频流，无法直接解析。",
                guidance=CHANNELS_GUIDANCE,
            )
        return extractor.extract(url, self.ctx)

    # -- 下载 ---------------------------------------------------------------

    def download(
        self,
        url: str,
        opts: DownloadOptions,
        platform: str | None = None,
        allow_fallback: bool = True,
    ) -> DownloadResult:
        extractor = self.registry.by_name(platform) if platform else self.registry.resolve(url)
        if extractor.capture_required:
            raise CaptureRequiredError(
                "微信视频号需要本地抓包获取视频流，无法直接解析。",
                guidance=CHANNELS_GUIDANCE,
            )
        try:
            return extractor.download(url, self.ctx, opts)
        except (ExtractionError, VidporterError) as e:
            if not allow_fallback or extractor.name == "generic":
                raise
            log.warning("%s 平台解析失败（%s），回退到 yt-dlp 通用引擎…", extractor.name, e)
            return self.registry.generic.download(url, self.ctx, opts)

    # -- 批处理 -------------------------------------------------------------

    def batch(
        self,
        list_file: Path,
        opts: DownloadOptions,
        platform: str | None = None,
        status_cb: Callable[[str], None] | None = None,
        fail_file: Path | None = None,
    ) -> dict[str, str]:
        """逐行下载 URL 列表；状态文件支持中断续跑。

        状态文件 ``<list>.state.json`` 记录已完成的 URL；失败清单写入
        ``fail_file``（缺省 <list>.failures.txt）。
        """
        log_cb = status_cb or (lambda msg: log.info("%s", msg))
        urls = [
            line.strip()
            for line in list_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        state_path = list_file.with_suffix(list_file.suffix + ".state.json")
        done: set[str] = set()
        if state_path.exists():
            done = set(json.loads(state_path.read_text(encoding="utf-8")))
        failures_path = fail_file or list_file.with_suffix(".failures.txt")

        results: dict[str, str] = {}
        total = len(urls)
        for i, url in enumerate(urls, 1):
            if url in done:
                results[url] = "cached"
                log_cb("[%d/%d] 跳过（已完成）: %s" % (i, total, url))
                continue
            try:
                result = self.download(url, opts, platform=platform)
                results[url] = "ok"
                log_cb("[%d/%d] OK  %s → %s" % (i, total, result.title[:40], url))
                done.add(url)
            except CaptureRequiredError:
                results[url] = "capture-required"
                log_cb("[%d/%d] 需抓包（视频号），跳过: %s" % (i, total, url))
            except Exception as e:
                results[url] = f"failed: {e}"
                log_cb("[%d/%d] FAIL %s (%s)" % (i, total, url, e))
                with open(failures_path, "a", encoding="utf-8") as f:
                    f.write(url + "\n")
            state_path.write_text(json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8")
            if i < total and self.config.rate_limit_sleep:
                time.sleep(self.config.rate_limit_sleep)
        return results
