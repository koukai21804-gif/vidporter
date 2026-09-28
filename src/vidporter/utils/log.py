from __future__ import annotations

import logging
import sys

from rich.logging import RichHandler

_format = "%(message)s"


def setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    level = logging.DEBUG if verbose else (logging.WARNING if quiet else logging.INFO)
    handler = RichHandler(rich_tracebacks=True, show_path=False, markup=False)
    handler.setFormatter(logging.Formatter(_format, datefmt="[%X]"))
    root = logging.getLogger("vidporter")
    root.setLevel(level)
    root.handlers[:] = [handler]
    # 压掉 httpx 等第三方库的 DEBUG 输出
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if sys.platform == "win32":
        # 避免部分终端 GBK 编码报错
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
            sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover
            pass


def get_logger(name: str = "vidporter") -> logging.Logger:
    return logging.getLogger(name)
