"""vidporter 命令行界面。"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

import vidporter
from vidporter.config import Config
from vidporter.download.engine import Engine
from vidporter.exceptions import CaptureRequiredError, VidporterError
from vidporter.models import DownloadOptions
from vidporter.utils.log import get_logger, setup_logging

app = typer.Typer(
    name="vidporter",
    help="统一的多平台视频提取工具：B站 / 抖音 / 快手 / 小红书 / 微信视频号 / 更多。",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)
subtitle_app = typer.Typer(help="字幕工具：批量抓取、转 Markdown 逐字稿", no_args_is_help=True)
cookies_app = typer.Typer(help="Cookie 管理：扫码登录、从浏览器导出", no_args_is_help=True)
app.add_typer(subtitle_app, name="subtitle")
app.add_typer(cookies_app, name="cookies")

console = Console()
log = get_logger()

VERSION_HELP = "输出路径；默认取配置或 ./downloads"
QUALITY_HELP = "最大高度（像素），如 1080；不填则取最佳"


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"vidporter {vidporter.__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="显示调试日志"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="只显示警告与错误"),
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="显示版本号"
    ),
) -> None:
    setup_logging(verbose=verbose, quiet=quiet)


def _load_config(config_file: Path | None) -> Config:
    try:
        return Config.load(config_file)
    except Exception as e:
        console.print(f"[yellow]配置文件解析失败，使用默认配置：{e}[/yellow]")
        return Config()


def _build_options(
    config: Config,
    out: Path | None,
    quality: int | None,
    audio_only: bool,
    audio_format: str | None,
    subtitles: bool,
    sub_langs: str | None,
    proxy: str | None,
    cookies: Path | None,
) -> DownloadOptions:
    opts = DownloadOptions(
        out_dir=out or config.out_dir,
        max_height=quality or config.quality,
        audio_only=audio_only,
        audio_format=audio_format or config.audio_format,
        download_subtitles=subtitles,
        subtitle_langs=sub_langs or config.subtitle_langs,
        proxy=proxy or config.proxy,
        cookies_file=cookies,
        rate_limit_sleep=config.rate_limit_sleep,
    )
    opts.out_dir.mkdir(parents=True, exist_ok=True)
    return opts


class _ProgressReporter:
    """同时适配 yt-dlp progress_hooks（dict）与内部 (done, total) 回调。"""

    def __init__(self, description: str) -> None:
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=True,
        )
        self._task = self._progress.add_task(description, total=None)
        self._context = None

    def __enter__(self):
        self._progress.start()
        return self

    def __exit__(self, *exc):
        self._progress.stop()

    def __call__(self, *args) -> None:
        if args and isinstance(args[0], dict):
            data = args[0]
            done = data.get("downloaded_bytes") or 0
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            self._update(done, total)
        elif len(args) == 2:
            done, total = args
            self._update(done, total)

    def _update(self, done, total) -> None:
        if total:
            self._progress.update(self._task, total=total, completed=done)
        else:
            self._progress.update(self._task, completed=done)


# -- download / info --------------------------------------------------------


@app.command()
def download(
    urls: list[str] = typer.Argument(..., help="视频链接（可多个）"),
    out: Path | None = typer.Option(None, "--out", "-o", help=VERSION_HELP),
    quality: int | None = typer.Option(None, "--quality", help=QUALITY_HELP),
    audio_only: bool = typer.Option(False, "--audio-only", "-a", help="只下载音频"),
    audio_format: str | None = typer.Option(
        None, "--audio-format", help="音频格式（mp3/m4a/flac…）"
    ),
    subtitles: bool = typer.Option(False, "--subtitles", "-s", help="同时下载字幕"),
    sub_langs: str | None = typer.Option(None, "--sub-langs", help="字幕语言，逗号分隔"),
    embed_subs: bool = typer.Option(False, "--embed-subs", help="字幕内嵌进视频（需 ffmpeg）"),
    proxy: str | None = typer.Option(None, "--proxy", help="HTTP/SOCKS 代理"),
    cookies: Path | None = typer.Option(None, "--cookies", help="Netscape cookie 文件"),
    platform: str | None = typer.Option(None, "--platform", "-p", help="强制指定平台"),
    no_fallback: bool = typer.Option(False, "--no-fallback", help="解析失败时不回退 yt-dlp"),
    config_file: Path | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """解析并下载视频 / 图集 / 音频。"""
    config = _load_config(config_file)
    opts = _build_options(
        config, out, quality, audio_only, audio_format, subtitles, sub_langs, proxy, cookies
    )
    opts.embed_subtitles = embed_subs
    engine = Engine(config=config)

    failed = 0
    for url in urls:
        name = _describe_url(url)
        try:
            with _ProgressReporter(f"下载 {name}") as reporter:
                opts.progress_hook = reporter
                opts.progress_cb = reporter
                result = engine.download(
                    url, opts, platform=platform, allow_fallback=not no_fallback
                )
            _print_result(result)
        except CaptureRequiredError as e:
            console.print(Panel(e.guidance or str(e), title="需要本地抓包", border_style="yellow"))
            failed += 1
        except VidporterError as e:
            console.print(f"[red]下载失败[/red] {url}\n  {e}")
            failed += 1
    if failed:
        raise typer.Exit(code=1)


@app.command()
def info(
    urls: list[str] = typer.Argument(..., help="视频链接（可多个）"),
    platform: str | None = typer.Option(None, "--platform", "-p", help="强制指定平台"),
    json_output: bool = typer.Option(False, "--json", help="以 JSON 输出"),
    config_file: Path | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """解析链接，显示标题、UP 主、清晰度等元信息（不下载）。"""
    config = _load_config(config_file)
    engine = Engine(config=config)
    for url in urls:
        try:
            media = engine.info(url, platform=platform)
        except CaptureRequiredError as e:
            console.print(Panel(e.guidance or str(e), title="需要本地抓包", border_style="yellow"))
            continue
        except VidporterError as e:
            console.print(f"[red]解析失败[/red] {url}\n  {e}")
            continue
        if json_output:
            console.print_json(json.dumps(_media_to_dict(media), ensure_ascii=False, indent=2))
        else:
            _print_media(media)


def _describe_url(url: str) -> str:
    return url if len(url) <= 60 else url[:57] + "…"


def _media_to_dict(media) -> dict:
    from dataclasses import asdict

    return asdict(media)


def _print_media(media) -> None:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_row("平台", media.platform)
    table.add_row("标题", media.title)
    if media.uploader:
        table.add_row("作者", media.uploader)
    if media.duration:
        m, s = divmod(int(media.duration), 60)
        table.add_row("时长", f"{m}:{s:02d}")
    if media.formats:
        heights = sorted({f.height for f in media.formats if f.height}, reverse=True)
        if heights:
            table.add_row("清晰度", ", ".join(f"{h}p" for h in heights[:8]))
    if media.subtitles:
        table.add_row("字幕", ", ".join(sorted({t.lang for t in media.subtitles})[:8]))
    if media.images:
        table.add_row("图集", f"{len(media.images)} 张")
    console.print(Panel(table, title=_describe_url(media.webpage_url), border_style="cyan"))


def _print_result(result) -> None:
    console.print(f"[green]✓[/green] {result.title}")
    for path in result.paths:
        size = ""
        try:
            if path.exists():
                size = f" ({path.stat().st_size / 1e6:.1f} MB)"
        except OSError:
            pass
        console.print(f"    {path}{size}")


# -- login / cookies --------------------------------------------------------


@cookies_app.command("login-bilibili")
def login_bilibili(
    out: Path | None = typer.Option(None, "--out", "-o", help="cookie 文件输出路径"),
    config_file: Path | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """扫码登录 B 站，生成 yt-dlp 可用的 cookie 文件。"""
    from vidporter.cookies.bilibili_qr import login

    config = _load_config(config_file)
    output = out or config.cookie_file_for("bilibili")
    png = output.with_suffix(".qr.png")
    console.print("[bold]B 站扫码登录[/bold]")
    try:
        ok = login(output, png_path=png, status_cb=lambda msg: console.print(msg))
    except VidporterError as e:
        console.print(f"[red]登录失败：{e}[/red]")
        raise typer.Exit(code=1) from e
    if not ok:
        console.print("[yellow]cookie 已写入，但登录校验未通过，请重试[/yellow]")
        raise typer.Exit(code=1)


@cookies_app.command("export")
def cookies_export(
    browser: str = typer.Option("edge", "--browser", "-b", help="edge / chrome"),
    browser_path: Path | None = typer.Option(None, "--browser-path", help="浏览器可执行文件路径"),
    domain: str = typer.Option("", "--domain", "-d", help="只保留包含该子串的域名，如 bilibili"),
    out: Path | None = typer.Option(None, "--out", "-o", help="输出文件"),
    show: bool = typer.Option(
        False, "--show", help="有头模式运行（专用 profile 可在窗口中登录，登录态会保留）"
    ),
    config_file: Path | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """以调试模式启动本机浏览器（专用 profile），经 CDP 导出 cookie（含 HttpOnly）。

    无头模式下会先访问目标站点获取游客 cookie（如抖音 ttwid）；
    需要登录态时加 --show 在弹出的窗口中登录后再导出。
    """
    from vidporter.cookies.browser_cdp import export_cookies

    config = _load_config(config_file)
    output = out or config.cookies_dir / f"{domain or 'browser'}.txt"
    console.print(f"正在从 {browser} 导出 cookie（期间请勿操作浏览器）…")
    try:
        count = export_cookies(
            output,
            browser=browser,
            browser_path=browser_path,
            domain_filter=domain,
            headless=not show,
        )
    except (VidporterError, FileNotFoundError, RuntimeError) as e:
        console.print(f"[red]导出失败：{e}[/red]")
        raise typer.Exit(code=1) from e
    console.print(f"[green]✓[/green] {count} 条 cookie → {output}")


# -- ui ---------------------------------------------------------------------


@app.command()
def ui(
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址"),
    port: int | None = typer.Option(None, "--port", help="端口（默认自动选择空闲端口）"),
    no_browser: bool = typer.Option(False, "--no-browser", help="不自动打开浏览器"),
) -> None:
    """启动本地网页控制台（浏览器操作下载 / 扫码登录 / 字幕转换）。"""
    from vidporter.web.server import serve

    serve(host=host, port=port, open_browser=not no_browser)


# -- channels ---------------------------------------------------------------


@app.command()
def channels(
    tool_path: Path | None = typer.Option(None, "--tool-path", help="嗅探工具可执行文件路径"),
    no_launch: bool = typer.Option(False, "--no-launch", help="只显示指引，不启动工具"),
) -> None:
    """微信视频号下载：启动本地嗅探工具并给出操作指引。"""
    from vidporter.platforms.channels import find_sniffer_tool, launch_sniffer_tool

    config = Config.load()
    exe = find_sniffer_tool(tool_path or config.channels_tool_path)
    if exe is None:
        console.print(
            Panel(
                "未检测到已安装的嗅探工具。请先安装其一：\n\n"
                "  res-downloader（推荐，持续维护）\n"
                "  https://github.com/putyy/res-downloader\n\n"
                "  WeChatVideoDownloader\n"
                "  https://github.com/lecepin/WeChatVideoDownloader\n\n"
                "安装后重新运行 vidporter channels，或用 --tool-path 指定路径。",
                title="缺少嗅探工具",
                border_style="yellow",
            )
        )
        raise typer.Exit(code=1)
    if no_launch:
        console.print(f"检测到嗅探工具：{exe}")
        return
    started = launch_sniffer_tool(exe)
    console.print(f"[green]✓[/green] 已启动 {started}")
    console.print(
        "\n下一步：\n"
        "  1. 在嗅探工具中开启代理监听；\n"
        "  2. 打开微信 PC 端，进入视频号播放目标视频；\n"
        "  3. 工具捕获到资源后点击下载，文件默认保存在工具的下载目录。"
    )


# -- batch ------------------------------------------------------------------


@app.command()
def batch(
    list_file: Path = typer.Argument(
        ..., exists=True, readable=True, help="URL 列表文件，每行一个，# 为注释"
    ),
    out: Path | None = typer.Option(None, "--out", "-o", help=VERSION_HELP),
    quality: int | None = typer.Option(None, "--quality", help=QUALITY_HELP),
    audio_only: bool = typer.Option(False, "--audio-only", "-a", help="只下载音频"),
    platform: str | None = typer.Option(None, "--platform", "-p", help="强制指定平台"),
    proxy: str | None = typer.Option(None, "--proxy", help="HTTP/SOCKS 代理"),
    config_file: Path | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """批量下载：列表文件驱动，自动断点续跑，失败清单落盘。"""
    config = _load_config(config_file)
    opts = _build_options(config, out, quality, audio_only, None, False, None, proxy, None)
    engine = Engine(config=config)
    results = engine.batch(list_file, opts, platform=platform, status_cb=console.print)
    ok = sum(1 for st in results.values() if st in ("ok", "cached"))
    fail = sum(1 for st in results.values() if st.startswith("failed"))
    console.print(f"\n合计 {len(results)} 项：成功/缓存 {ok}，失败 {fail}")
    if fail:
        raise typer.Exit(code=1)


# -- subtitle ---------------------------------------------------------------


@subtitle_app.command("fetch")
def subtitle_fetch(
    urls: list[str] = typer.Argument(None, help="B站视频链接或 BV 号（可多个）"),
    list_file: Path | None = typer.Option(None, "--list", "-l", help="URL/BV 列表文件"),
    out: Path = typer.Option(Path("subs"), "--out", "-o", help="字幕输出目录"),
    langs: str | None = typer.Option(None, "--langs", help="字幕语言，逗号分隔，如 ai-zh,zh-Hans"),
    cookies: Path | None = typer.Option(None, "--cookies", help="Netscape cookie 文件"),
    proxy: str | None = typer.Option(None, "--proxy", help="HTTP/SOCKS 代理"),
    config_file: Path | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """批量下载字幕（AI 字幕 / CC 字幕），已有字幕自动跳过。"""
    from vidporter.subtitle.fetch import fetch as fetch_subs
    from vidporter.subtitle.fetch import load_url_list, write_failure_report

    config = _load_config(config_file)
    if not urls and list_file is None:
        console.print("[red]请提供 URL 或 --list 文件[/red]")
        raise typer.Exit(code=1)
    all_urls = list(urls or [])
    if list_file:
        all_urls += load_url_list(list_file)
    cookie_file = cookies or config.cookie_file_for("bilibili")
    results = fetch_subs(
        all_urls,
        out_dir=out,
        langs=langs or config.subtitle_langs,
        cookies_file=cookie_file if Path(cookie_file).is_file() else None,
        proxy=proxy or config.proxy,
        sleep=config.rate_limit_sleep,
        status_cb=console.print,
    )
    failed = write_failure_report(results, Path("subs_failures.txt"))
    ok = sum(1 for st in results.values() if st in ("ok", "cached"))
    console.print(f"\n合计 {len(results)} 项：成功/缓存 {ok}，失败 {failed}")


@subtitle_app.command("convert")
def subtitle_convert(
    subs_dir: Path = typer.Argument(..., exists=True, help="srt 字幕目录"),
    out: Path | None = typer.Option(None, "--out", "-o", help="Markdown 输出目录"),
    index_title: str = typer.Option("逐字稿索引", "--title", help="索引标题"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="递归子目录"),
) -> None:
    """把 SRT 字幕转为 Markdown 逐字稿（去重、按停顿分段、生成索引）。"""
    from vidporter.subtitle.convert import convert_dir

    out_dir = out or subs_dir.parent / f"{subs_dir.name}_md"
    summary = convert_dir(subs_dir, out_dir, index_title=index_title, recursive=recursive)
    console.print(
        f"[green]✓[/green] 已生成 {summary['written']} 篇逐字稿"
        f"（约 {summary['total_chars']} 字）→ {out_dir}"
    )
    console.print(f"  索引：{summary['index']}")


def main() -> None:
    """包入口（pyproject console_scripts 指向这里）。"""
    app()


if __name__ == "__main__":
    app()
