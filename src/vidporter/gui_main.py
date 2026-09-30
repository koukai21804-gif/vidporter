"""vidporter GUI 启动器 —— PyInstaller 打包入口（pyproject [build] / vidporter.spec）。

用法（打包后）::

    vidporter-gui.exe            # 启动控制台并自动打开浏览器
    vidporter-gui.exe --no-browser
    vidporter-gui.exe 8788       # 指定端口
"""

from __future__ import annotations

import sys

from vidporter.utils.log import setup_logging
from vidporter.web.server import serve


def main() -> None:
    setup_logging()
    args = [a for a in sys.argv[1:] if a != "--no-browser"]
    open_browser = "--no-browser" not in sys.argv
    port = int(args[0]) if args and args[0].isdigit() else None
    serve(port=port, open_browser=open_browser)


if __name__ == "__main__":
    main()
