"""Bilibili 扫码登录，产出 yt-dlp 可用的 Netscape cookie 文件。

为什么不用浏览器 cookie：新版 Edge/Chrome 使用 app-bound 加密（v20），
从外部复制或读取的 profile 无法解密。扫码登录直接从 passport 接口拿到
会话 cookie（SESSDATA / bili_jct / DedeUserID 等），一步到位。

用法::

    from vidporter.cookies.bilibili_qr import login
    login(Path("cookies.txt"))  # 终端会打印二维码并等待确认
"""

from __future__ import annotations

import contextlib
import http.cookiejar
import json
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

import segno

from vidporter.cookies import netscape
from vidporter.exceptions import VidporterError
from vidporter.utils.log import get_logger

log = get_logger("vidporter.cookies.bilibili")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"

# 外层 code 恒为 0，真实状态在 data.code
CODE_OK = 0
CODE_EXPIRED = 86038


class BiliQRLoginError(VidporterError):
    pass


def _request(
    opener: urllib.request.OpenerDirector,
    url: str,
    referer: str | None = None,
    as_json: bool = False,
):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json, text/plain, */*")
    req.add_header("Referer", referer or "https://passport.bilibili.com/login")
    resp = opener.open(req, timeout=25)
    return json.load(resp) if as_json else resp


def _show_qr(url: str, png_path: Path | None) -> None:
    qr = segno.make(url)
    if png_path is not None:
        png_path.parent.mkdir(parents=True, exist_ok=True)
        qr.save(str(png_path), scale=8, border=4)
        log.info("二维码已保存: %s", png_path)
    with contextlib.suppress(Exception):  # 终端不支持时仅用 PNG
        qr.terminal(compact=True, border=1)


def login(
    output: Path,
    png_path: Path | None = None,
    poll_interval: float = 3.0,
    timeout_seconds: float = 180.0,
    status_cb: Callable[[str], None] | None = None,
) -> bool:
    """执行扫码登录，成功时把 cookie 写入 ``output`` 并返回 True。

    ``status_cb`` 用于把过程状态交给 CLI 展示；缺省打印到日志。
    """
    log_cb = status_cb or (lambda msg: log.info("%s", msg))
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    log_cb("正在初始化会话…")
    try:
        _request(opener, "https://www.bilibili.com/")
    except Exception as e:  # 网络可达性弱提示，不阻断
        log_cb("提示：初始化访问失败（%s），继续尝试。" % e)

    log_cb("正在获取二维码…")
    data = _request(opener, GENERATE_URL, as_json=True)
    if data.get("code") != 0:
        raise BiliQRLoginError(f"获取二维码失败: {data}")
    qrcode_key = data["data"]["qrcode_key"]
    _show_qr(data["data"]["url"], png_path)
    log_cb("请使用 B 站 App 扫描二维码并确认登录（限时 3 分钟）…")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        try:
            poll = _request(opener, f"{POLL_URL}?qrcode_key={qrcode_key}", as_json=True)
        except Exception as e:
            log_cb(f"轮询出错，继续: {e}")
            continue
        pd = poll.get("data", {})
        code = pd.get("code")
        if code == CODE_OK:
            params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(pd.get("url", "")).query))
            return _write_cookies(output, cj, opener, params, log_cb)
        if code == CODE_EXPIRED:
            raise BiliQRLoginError("二维码已过期，请重新运行登录命令")
        log_cb("等待扫码确认…(%s)" % pd.get("message", ""))
    raise BiliQRLoginError("扫码超时，请重试")


def _write_cookies(
    output: Path,
    cj: http.cookiejar.CookieJar,
    opener: urllib.request.OpenerDirector,
    session_params: dict[str, str],
    log_cb: Callable[[str], None],
) -> bool:
    far = int(time.time()) + 180 * 86400
    domain = ".bilibili.com"

    cookies: list[netscape.Cookie] = [
        netscape.Cookie(
            name=c.name,
            value=c.value or "",
            domain=c.domain if c.domain.startswith(".") else "." + c.domain.lstrip("."),
            path=c.path or "/",
            expires=c.expires or far,
            secure=bool(c.secure),
            http_only=False,
        )
        for c in cj
        if "bilibili" in c.domain
    ]
    # 扫码返回的会话参数是登录态的关键
    for name, value in session_params.items():
        if value:
            cookies.append(
                netscape.Cookie(
                    name=name,
                    value=value,
                    domain=domain,
                    path="/",
                    expires=far,
                    secure=name != "DedeUserID",
                    http_only=name not in ("DedeUserID", "sid"),
                )
            )
    count = netscape.write_netscape(output, cookies)
    log_cb("cookie 已写入 %s（%d 条）" % (output, count))

    logged_in, uname = _verify(opener)
    if logged_in:
        log_cb("登录成功，欢迎 %s" % uname)
    else:
        log_cb("警告：cookie 已写入，但 nav 接口显示未登录，请稍后重试")
    return logged_in


def _verify(opener: urllib.request.OpenerDirector) -> tuple[bool, str]:
    try:
        data = _request(opener, NAV_URL, referer="https://www.bilibili.com/", as_json=True)
        d = data.get("data", {})
        return bool(d.get("isLogin")), d.get("uname", "")
    except Exception:
        return False, ""
