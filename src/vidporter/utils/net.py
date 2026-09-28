"""共享 HTTP 客户端与 JSON 提取工具。"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from vidporter.exceptions import ExtractionError

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


def make_client(
    proxy: str | None = None,
    user_agent: str = DESKTOP_UA,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    cookies_file: str | None = None,
) -> httpx.Client:
    base_headers = {"User-Agent": user_agent, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5"}
    if headers:
        base_headers.update(headers)
    kwargs: dict[str, Any] = {
        "follow_redirects": True,
        "timeout": timeout,
        "headers": base_headers,
    }
    if proxy:
        kwargs["proxy"] = proxy
    if cookies_file:
        kwargs["cookies"] = _load_netscape_cookies(cookies_file)
    return httpx.Client(**kwargs)


def _load_netscape_cookies(path: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    # #HttpOnly_ 前缀行也是有效 cookie
                    if line.startswith("#HttpOnly_"):
                        line = line[len("#HttpOnly_") :]
                    else:
                        continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    cookies[parts[5]] = parts[6]
    except OSError:
        pass
    return cookies


def resolve_url(client: httpx.Client, url: str) -> str:
    """跟随重定向，返回最终 URL（保留查询串，例如小红书的 xsec_token）。"""
    resp = client.get(url)
    resp.raise_for_status()
    return str(resp.url)


def extract_json_after_marker(html: str, marker: str) -> Any:
    """在 HTML 中定位 ``marker`` 之后第一个 JSON 值并解析。

    页面里常见 ``window.__INITIAL_STATE__={...}`` / ``window.__APOLLO_STATE__={...}``，
    用正则匹配到 ``</script>`` 容易被字符串内容干扰；这里从 marker 位置直接用
    ``raw_decode`` 消费一个完整 JSON 值，鲁棒得多。未找到或解析失败抛
    :class:`ExtractionError`。
    """
    idx = html.find(marker)
    if idx < 0:
        raise ExtractionError(f"页面中未找到 {marker!r}")
    start = html.find("{", idx + len(marker))
    if start < 0:
        raise ExtractionError(f"{marker!r} 后未找到 JSON 数据")
    try:
        value, _ = json.JSONDecoder().raw_decode(html[start:])
    except json.JSONDecodeError as e:
        raise ExtractionError(f"{marker!r} JSON 解析失败: {e}") from e
    return value


def sanitize_state(value: Any) -> Any:
    """把 ``undefined`` 字面量替换为 ``null`` 后再解析的预处理。

    部分站点的 SSR 状态是未严格合法的 JSON（包含 ``undefined``），
    在调用方先对文本做文本级替换，这里提供递归遍历的兜底。
    """
    if isinstance(value, dict):
        return {k: sanitize_state(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_state(v) for v in value]
    return value


_UNDEFINED_RE = re.compile(r"\bundefined\b")


def parse_state_json(text: str) -> Any:
    """解析可能包含 ``undefined`` 字面量、且后面跟着 ``;`` 等尾随内容的 JSON 文本。"""
    start = text.find("{")
    if start < 0:
        raise ExtractionError("状态文本中没有 JSON 数据")
    cleaned = _UNDEFINED_RE.sub("null", text[start:])
    try:
        value, _ = json.JSONDecoder().raw_decode(cleaned)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"状态 JSON 解析失败: {e}") from e
    return value
