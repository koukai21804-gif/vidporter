"""SRT 字幕 → Markdown 逐字稿转换。

从个人工作流脚本泛化而来：
- 原文逐字保留（不插入标点、不改写），仅去掉连续重复行；
- 按停顿（默认 >1s）与长度（默认 420 字）切成自然段；
- 目录内有 yt-dlp 的 ``*.info.json`` 时自动读取标题 / 时长 / 链接；
- 生成索引 ``00_索引.md``。
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path

_TS_RE = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


# -- 解析与段落切分 ---------------------------------------------------------


def parse_srt(path: Path) -> list[tuple[float, float, str]]:
    """返回 [(start_sec, end_sec, text)]。"""
    raw = path.read_text(encoding="utf-8", errors="replace")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    segments = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [line for line in block.split("\n") if line.strip()]
        if len(lines) < 2:
            continue
        ts_idx = next((i for i, line in enumerate(lines[:4]) if _TS_RE.search(line)), None)
        if ts_idx is None:
            continue
        m = _TS_RE.search(lines[ts_idx])
        h, mi, s, ms, h2, mi2, s2, ms2 = (int(x) for x in m.groups())
        start = h * 3600 + mi * 60 + s + ms / 1000.0
        end = h2 * 3600 + mi2 * 60 + s2 + ms2 / 1000.0
        # 中文字幕去掉字内空格
        text = re.sub(r"\s+", "", " ".join(line.strip() for line in lines[ts_idx + 1 :]))
        if text:
            segments.append((start, end, text))
    return segments


def dedupe(segments: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    """去掉相邻重复（ASR 常见的整行重复 / 重复后缀）。"""
    out = []
    for st, en, tx in segments:
        if out and out[-1][2] == tx:
            continue
        if out and len(tx) >= 4 and out[-1][2].endswith(tx):
            continue
        out.append((st, en, tx))
    return out


def to_paragraphs(
    segments: list[tuple[float, float, str]], gap: float = 1.0, max_len: int = 420
) -> list[str]:
    """按停顿或长度切段。"""
    paragraphs: list[str] = []
    current = ""
    prev_end: float | None = None
    for start, end, text in segments:
        if current and prev_end is not None and (start - prev_end) > gap and len(current) >= 60:
            paragraphs.append(current)
            current = text
            prev_end = end
            continue
        if current and len(current) + len(text) > max_len:
            paragraphs.append(current)
            current = text
        else:
            current = (current + text) if current else text
        prev_end = end
        if len(current) > max_len + 200:
            paragraphs.append(current)
            current = ""
    if current:
        paragraphs.append(current)
    return paragraphs


def fmt_duration(seconds: float | None) -> str:
    if not seconds:
        return "-"
    sec = int(round(seconds))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# -- 元数据与输出 ------------------------------------------------------------


def load_meta(info_json_path: Path) -> dict:
    try:
        data = json.loads(info_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    upload = data.get("upload_date") or ""
    return {
        "id": data.get("id") or "",
        "title": data.get("title") or "",
        "duration": data.get("duration"),
        "uploader": data.get("uploader") or "",
        "url": data.get("webpage_url") or "",
        "date": (f"{upload[:4]}-{upload[4:6]}-{upload[6:]}" if len(upload) == 8 else ""),
    }


def convert_one(
    srt_path: Path,
    out_path: Path,
    meta: dict | None = None,
    heading_level: int = 1,
) -> int:
    """转换单个 srt；返回正文字数。"""
    meta = meta or {}
    segments = dedupe(parse_srt(srt_path))
    body = "\n\n".join(to_paragraphs(segments))
    chars = len(body.replace("\n", ""))
    title = meta.get("title") or srt_path.stem

    lines = [f"{'#' * heading_level} {title}", ""]
    if meta.get("date"):
        lines += [f"- 发布日期：{meta['date']}"]
    if meta.get("duration"):
        lines += [f"- 时长：{fmt_duration(meta['duration'])}"]
    if meta.get("uploader"):
        lines += [f"- UP 主：{meta['uploader']}"]
    if meta.get("id"):
        lines += [f"- ID：{meta['id']}"]
    if meta.get("url"):
        lines += [f"- 链接：{meta['url']}"]
    if len(lines) > 2:
        lines += ["", f"- 字数：约 {chars} 字", "", "---", ""]
    lines += ["## 文字稿", "", body, ""]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return chars


def convert_dir(
    subs_dir: Path,
    out_dir: Path,
    index_title: str = "逐字稿索引",
    recursive: bool = False,
) -> dict:
    """批量转换目录中的 .srt 并生成索引。"""
    pattern = "**/*.srt" if recursive else "*.srt"
    srt_files = sorted(Path(p) for p in glob.glob(str(Path(subs_dir) / pattern)))
    out_dir.mkdir(parents=True, exist_ok=True)

    rows, missing_meta = [], 0
    total_chars = 0
    written = 0
    for srt in srt_files:
        meta = load_meta(srt.with_suffix(".info.json"))
        if not meta.get("title"):
            missing_meta += 1
        stem = srt.stem
        out_name = f"{stem}.md"
        chars = convert_one(srt, out_dir / out_name, meta)
        total_chars += chars
        written += 1
        rows.append((out_name, meta, chars))

    index_path = out_dir / "00_索引.md"
    lines = [f"# {index_title}", "", f"- 共 {written} 篇，约 {total_chars} 字", ""]
    lines += ["| 文件 | 标题 | 字数 |", "|---|---|---|"]
    for out_name, meta, chars in rows:
        title = (meta.get("title") or "-").replace("|", "\\|")
        lines.append(f"| [{out_name}]({out_name}) | {title} | 约{chars}字 |")
    lines.append("")
    index_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "written": written,
        "total_chars": total_chars,
        "index": index_path,
        "missing_meta": missing_meta,
    }
