"""通过 Chrome DevTools 协议（CDP）从本机浏览器导出 cookie。

背景：新版 Edge / Chrome 的 cookie 采用 app-bound 加密（v20），第三方进程
读取本地数据库只会得到密文（yt-dlp 报 "Failed to decrypt with DPAPI"）。
而浏览器自己能拿到明文——以调试模式启动浏览器，用 CDP 的
``Network.getAllCookies`` 即可取到包括 HttpOnly（SESSDATA 等）在内的全部 cookie。

注意：Chromium 136 起（2025-04，Edge 同步跟进），``--remote-debugging-port``
在**默认用户数据目录**上会被静默忽略（防 debugger 滥用的安全加固），因此
这里使用 vidporter 专属 profile（持久化，登录状态跨次保留）；profile 初始
为空，需先导航到目标站点获取游客 cookie（如抖音 ttwid）。需要登录态时用
``--show`` 以有头模式跑一次并在窗口里登录。

只在需要时导入 websocket-client：``pip install "vidporter[cdp]"``。
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from vidporter.cookies import netscape
from vidporter.exceptions import MissingDependencyError
from vidporter.utils.log import get_logger

log = get_logger("vidporter.cookies.cdp")

DEBUG_PORT = 9222

# Windows / Linux / macOS 下各浏览器的常见安装路径
BROWSER_PATHS: dict[str, list[str]] = {
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/microsoft-edge",
        "/usr/bin/microsoft-edge-stable",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ],
}


def find_browser_executable(browser: str, explicit: Path | None = None) -> Path:
    if explicit:
        if not explicit.is_file():
            raise FileNotFoundError(f"指定的浏览器路径不存在: {explicit}")
        return explicit
    for candidate in BROWSER_PATHS.get(browser, []):
        p = Path(candidate)
        if p.is_file():
            return p
    which = shutil.which(browser)
    if which:
        return Path(which)
    raise FileNotFoundError(f"未找到 {browser}，请用 --browser-path 指定可执行文件路径")


def _cdp_profile_dir() -> Path:
    """CDP 导出专用 profile：独立于用户默认目录（Chromium 136+ 要求），且持久化。"""
    home = Path.home()
    if sys.platform == "darwin":
        base = home / "Library" / "Application Support" / "vidporter"
    elif sys.platform == "win32":
        base = home / "AppData" / "Local" / "vidporter"
    else:
        base = home / ".local" / "share" / "vidporter"
    return base / "cdp-profile"


def auto_navigate_url(domain_filter: str) -> str:
    """根据域名过滤器推导首次导航地址：游客 cookie 由目标站服务端下发。"""
    return f"https://www.{domain_filter}.com" if domain_filter else "about:blank"


class _CDPClient:
    """极简 CDP websocket 客户端，只做 request/response 调用。"""

    def __init__(self, ws_url: str, timeout: float = 25.0):
        try:
            import websocket
        except ImportError as e:  # pragma: no cover
            raise MissingDependencyError(
                "CDP 导出需要 websocket-client：pip install 'vidporter[cdp]'"
            ) from e
        self._ws = websocket.create_connection(ws_url, timeout=timeout, suppress_origin=True)
        self._next_id = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        mid = self._next_id
        msg: dict = {"id": mid, "method": method}
        if params:
            msg["params"] = params
        self._ws.send(json.dumps(msg))
        while True:
            reply = json.loads(self._ws.recv())
            if reply.get("id") == mid:
                if "error" in reply:
                    raise RuntimeError(f"CDP {method} 失败: {reply['error']}")
                return reply.get("result", {})

    def close(self) -> None:
        with contextlib.suppress(Exception):  # pragma: no cover
            self._ws.close()


def export_cookies(
    output: Path,
    browser: str = "edge",
    browser_path: Path | None = None,
    domain_filter: str = "",
    port: int = DEBUG_PORT,
    headless: bool = True,
    navigate_url: str | None = None,
    settle_seconds: float = 2.0,
) -> int:
    """导出浏览器 cookie 到 Netscape 文件，返回写入条数。

    使用 vidporter 专属 profile（Chromium 136+ 不允许在默认用户目录上开
    调试端口）；该 profile 初始无 cookie，``navigate_url`` 缺省时按
    ``domain_filter`` 先访问目标站点获取游客 cookie（ttwid 等）。

    ``domain_filter`` 非空时只保留包含该子串的域（如 ``bilibili``）。
    """
    exe = find_browser_executable(browser, browser_path)
    if navigate_url is None:
        navigate_url = auto_navigate_url(domain_filter)
    profile = _cdp_profile_dir()
    profile.mkdir(parents=True, exist_ok=True)

    flags = [
        str(exe),
        f"--remote-debugging-port={port}",
        # Chromium 111+ 拒绝带 Origin 头的 CDP WebSocket 连接（403）
        "--remote-allow-origins=*",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-popup-blocking",
        "--disable-features=Translate",
        navigate_url,
    ]
    if headless:
        flags.insert(1, "--headless=new")

    log.info("启动浏览器（调试端口 %d）: %s", port, exe.name)
    proc = subprocess.Popen(flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        targets = _wait_for_targets(port)
        page = next((t for t in targets if t.get("type") == "page"), None)
        if page is None:
            raise RuntimeError("未找到可用的页面 target")
        client = _CDPClient(page["webSocketDebuggerUrl"])
        try:
            client.call("Network.enable")
            if navigate_url != "about:blank":
                client.call("Page.enable")
                client.call("Page.navigate", {"url": navigate_url})
                time.sleep(max(settle_seconds, 3.0))
            result = client.call("Network.getAllCookies")
        finally:
            client.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    cookies = netscape.from_cdp(result.get("cookies", []))
    if domain_filter:
        cookies = netscape.filter_by_domain(cookies, domain_filter)
    if not cookies:
        raise RuntimeError(
            "没有取到 cookie——请检查本机能否访问目标站点，或网络是否被代理/防火墙拦截"
        )
    return netscape.write_netscape(output, cookies)


def _wait_for_targets(port: int, timeout_seconds: float = 40.0) -> list[dict]:
    deadline = time.monotonic() + timeout_seconds
    url = f"http://127.0.0.1:{port}/json/list"
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                targets = json.load(resp)
            if targets:
                return targets
        except Exception as e:
            last_err = e
        time.sleep(0.5)
    raise RuntimeError(f"调试端口 {port} 未就绪: {last_err}")
