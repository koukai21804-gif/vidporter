"""vidporter 本地网页控制台。

零额外依赖：标准库 ``http.server`` 提供 JSON API + 静态页面，
浏览器访问即可操作下载、扫码登录与字幕转换。

    from vidporter.web.server import serve
    serve()          # 启动并打开浏览器（阻塞直到 Ctrl+C）
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import vidporter
from vidporter.config import Config
from vidporter.download.engine import Engine
from vidporter.exceptions import CaptureRequiredError
from vidporter.models import DownloadOptions
from vidporter.utils.log import get_logger
from vidporter.web.tasks import Task, TaskManager

log = get_logger("vidporter.web")

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_PORT = 8765

tasks = TaskManager()


# -- API 处理函数 ------------------------------------------------------------


def api_version() -> dict:
    cfg = Config.load()
    return {
        "version": vidporter.__version__,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "out_dir": str(cfg.out_dir),
        "cookies_dir": str(cfg.cookies_dir),
        "ffmpeg": _ffmpeg_ok(),
    }


def _ffmpeg_ok() -> bool:
    import shutil

    return shutil.which("ffmpeg") is not None


def api_info(body: dict) -> dict:
    url = str(body.get("url", "")).strip()
    if not url:
        raise ValueError("缺少 url")
    engine = Engine(config=Config.load())
    media = engine.info(url)
    return {
        "platform": media.platform,
        "id": media.id,
        "title": media.title,
        "uploader": media.uploader,
        "duration": media.duration,
        "media_type": media.media_type,
        "images": len(media.images),
        "qualities": sorted({f.height for f in media.formats if f.height}, reverse=True)[:8],
        "subtitles": sorted({t.lang for t in media.subtitles})[:8],
    }


def _build_opts(body: dict) -> DownloadOptions:
    cfg = Config.load()
    out_dir = Path(str(body.get("out_dir") or cfg.out_dir)).expanduser()
    opts = DownloadOptions(
        out_dir=out_dir,
        max_height=int(body["quality"]) if body.get("quality") else None,
        audio_only=bool(body.get("audio_only")),
        download_subtitles=bool(body.get("subtitles")),
        proxy=cfg.proxy,
        rate_limit_sleep=cfg.rate_limit_sleep,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    return opts


def api_download(body: dict) -> dict:
    urls = [u.strip() for u in body.get("urls", []) if u and str(u).strip()]
    if not urls:
        raise ValueError("没有可下载的 URL")
    opts = _build_opts(body)
    title = urls[0] if len(urls) == 1 else f"{len(urls)} 个链接"

    def run(task: Task) -> None:
        engine = Engine(config=Config.load())
        task.log_line(f"开始处理 {len(urls)} 个链接…")
        ok = fail = 0
        for i, url in enumerate(urls, 1):
            task.log_line(f"[{i}/{len(urls)}] {url}")
            opts.progress_cb = lambda done, total, t=task: t.set_progress(done, total)

            def ydl_hook(d, t=task):
                t.set_progress(
                    d.get("downloaded_bytes") or 0,
                    d.get("total_bytes") or d.get("total_bytes_estimate"),
                )

            opts.progress_hook = ydl_hook
            try:
                result = engine.download(url, opts)
                ok += 1
                task.log_line(f"完成: {result.title}")
                for p in result.paths:
                    task.log_line(f"  → {p.name}")
            except CaptureRequiredError as e:
                fail += 1
                task.log_line("需要本地抓包（视频号），请用 vidporter channels 或嗅探工具")
                task.log_line(str(e.guidance).splitlines()[0] if e.guidance else "")
            except Exception as e:
                fail += 1
                task.log_line(f"失败: {e}")
        task.result = {"ok": ok, "failed": fail, "total": len(urls)}
        task.log_line(f"全部结束：成功 {ok}，失败 {fail}")

    task = tasks.submit("download", title, run)
    return {"task_id": task.id}


def api_login_bilibili(body: dict) -> dict:
    from vidporter.cookies.bilibili_qr import login

    cfg = Config.load()
    output = Path(str(body.get("out") or cfg.cookie_file_for("bilibili"))).expanduser()
    png = output.with_suffix(".qr.png")

    def run(task: Task) -> None:
        task.qr_png = png
        ok = login(
            output,
            png_path=png,
            status_cb=task.log_line,
        )
        task.result = {"logged_in": ok, "cookie_file": str(output)}

    task = tasks.submit("login", "B站扫码登录", run)
    return {"task_id": task.id}


def api_convert(body: dict) -> dict:
    from vidporter.subtitle.convert import convert_dir

    subs_dir = Path(str(body.get("subs_dir", ""))).expanduser()
    if not subs_dir.is_dir():
        raise ValueError(f"字幕目录不存在: {subs_dir}")
    out_dir = (
        Path(str(body["out"])).expanduser()
        if body.get("out")
        else subs_dir.parent / f"{subs_dir.name}_md"
    )
    title = str(body.get("title") or "逐字稿索引")
    recursive = bool(body.get("recursive"))

    def run(task: Task) -> None:
        task.log_line(f"转换 {subs_dir} → {out_dir}")
        summary = convert_dir(subs_dir, out_dir, index_title=title, recursive=recursive)
        task.result = {
            "written": summary["written"],
            "total_chars": summary["total_chars"],
            "index": str(summary["index"]),
        }
        task.log_line(f"完成：{summary['written']} 篇，约 {summary['total_chars']} 字")

    task = tasks.submit("convert", f"字幕转换 {subs_dir.name}", run)
    return {"task_id": task.id}


# -- HTTP 服务器 -------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = "vidporter/" + vidporter.__version__

    # 路由表
    POST_ROUTES = {
        "/api/info": api_info,
        "/api/download": api_download,
        "/api/login/bilibili": api_login_bilibili,
        "/api/convert": api_convert,
    }

    def log_message(self, fmt: str, *args: Any) -> None:  # 静默默认访问日志
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, path: Path) -> None:
        try:
            payload = path.read_bytes()
        except OSError:
            self._send_json({"error": "not found"}, 404)
            return
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".png": "image/png",
        }.get(path.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send_file(STATIC_DIR / "index.html")
        elif path == "/api/version":
            self._send_json(api_version())
        elif path == "/api/tasks":
            self._send_json({"tasks": tasks.list()})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        handler = self.POST_ROUTES.get(path)
        if handler is None:
            self._send_json({"error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        except json.JSONDecodeError:
            self._send_json({"error": "请求体不是合法 JSON"}, 400)
            return
        try:
            self._send_json(handler(body))
        except (ValueError, FileNotFoundError) as e:
            self._send_json({"error": str(e)}, 400)
        except CaptureRequiredError as e:
            self._send_json({"error": str(e), "guidance": e.guidance}, 409)
        except Exception as e:
            log.debug("API 内部错误: %s", e, exc_info=True)
            self._send_json({"error": f"处理失败: {e}"}, 500)


def _find_free_port(start: int, tries: int = 20) -> int:
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"{start} 起连续 {tries} 个端口均被占用")


def serve_ready(host: str = "127.0.0.1", port: int = 0, open_browser: bool = False):
    """创建并启动服务器，返回 (server, port, thread)；port=0 时自动分配。

    供 :func:`serve` 与测试使用。"""
    if port == 0:
        port = _find_free_port(DEFAULT_PORT)
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, name="vidporter-web", daemon=True)
    thread.start()
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    return server, port, thread


def serve(host: str = "127.0.0.1", port: int | None = None, open_browser: bool = True) -> None:
    """启动控制台服务器（阻塞），可选自动打开浏览器。"""
    server, port, _thread = serve_ready(
        host=host, port=port if port is not None else 0, open_browser=open_browser
    )
    url = f"http://{host}:{port}"
    print(f"vidporter 控制台: {url}  （Ctrl+C 退出）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
    finally:
        server.server_close()
