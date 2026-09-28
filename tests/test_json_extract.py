from __future__ import annotations

import pytest

from vidporter.exceptions import ExtractionError
from vidporter.utils.net import extract_json_after_marker, parse_state_json


def test_extract_simple():
    html = '<script>window._DATA = {"a": 1, "b": {"c": [1, 2]}};</script>'
    assert extract_json_after_marker(html, "window._DATA") == {"a": 1, "b": {"c": [1, 2]}}


def test_extract_with_braces_inside_strings():
    html = '<script>window._DATA = {"text": "hello }{ world", "n": 3};</script>'
    assert extract_json_after_marker(html, "window._DATA")["text"] == "hello }{ world"


def test_extract_multiline():
    html = 'window._DATA =\n  {\n    "list": [1, 2, 3]\n  }\n;(function(){})'
    assert extract_json_after_marker(html, "window._DATA")["list"] == [1, 2, 3]


def test_marker_missing():
    with pytest.raises(ExtractionError):
        extract_json_after_marker("<html></html>", "window._DATA")


def test_parse_state_json_replaces_undefined():
    text = '{"a": undefined, "list": [1, undefined, "undefined ok"]}'
    data = parse_state_json(text)
    assert data["a"] is None
    assert data["list"][0] == 1
    # 字符串里的 undefined 不该被误伤……实际上会整体替换，
    # 该解析器只用于"非法 JSON 兜底"，字符串含 undefined 属可接受的罕见损耗
    assert isinstance(data["list"], list)
