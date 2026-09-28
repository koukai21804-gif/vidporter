from __future__ import annotations

import json

from vidporter.models import MediaInfo, StreamFormat
from vidporter.subtitle import convert


def _write_srt(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_parse_and_dedupe(tmp_path):
    srt = tmp_path / "BV1test.srt"
    _write_srt(
        srt,
        [
            "1",
            "00:00:00,000 --> 00:00:02,000",
            "大家好 今天讲一个新话题",
            "",
            "2",
            "00:00:02,000 --> 00:00:04,000",
            "大家好 今天讲一个新话题",  # 完全重复 → 去掉
            "",
            "3",
            "00:00:05,500 --> 00:00:08,000",
            "然后我们再来看第二个例子",
            "",
        ],
    )
    segs = convert.parse_srt(srt)
    assert len(segs) == 3
    assert segs[0][2] == "大家好今天讲一个新话题"  # 内部空格被移除
    deduped = convert.dedupe(segs)
    assert len(deduped) == 2


def test_paragraph_split_on_gap(tmp_path):
    srt = tmp_path / "gap.srt"
    long_a = "第一句话内容比较长一些一些" * 5  # ≥60 字，满足停顿切分阈值
    long_b = "第二句话紧跟着第一句话来说" * 5
    _write_srt(
        srt,
        [
            "1",
            "00:00:00,000 --> 00:00:01,500",
            long_a,
            "",
            "2",
            "00:00:01,600 --> 00:00:03,000",
            long_b,
            "",
            "3",
            "00:00:10,000 --> 00:00:11,000",
            "停顿之后开始一个新的话题",
            "",
        ],
    )
    segs = convert.dedupe(convert.parse_srt(srt))
    paras = convert.to_paragraphs(segs, gap=1.0)
    assert len(paras) == 2
    assert "新的话题" in paras[1]


def test_convert_one_with_meta(tmp_path):
    srt = tmp_path / "BV1meta.srt"
    _write_srt(
        srt,
        [
            "1",
            "00:00:00,000 --> 00:00:02,000",
            "内容",
            "",
            "2",
            "00:00:02,200 --> 00:00:04,000",
            "更多内容",
        ],
    )
    meta = {
        "id": "BV1meta",
        "title": "测试标题",
        "duration": 125,
        "uploader": "某人",
        "url": "https://www.bilibili.com/video/BV1meta",
        "date": "2026-01-01",
    }
    out = tmp_path / "out.md"
    chars = convert.convert_one(srt, out, meta)
    text = out.read_text(encoding="utf-8")
    assert "# 测试标题" in text
    assert "- 时长：2:05" in text
    assert "- 发布日期：2026-01-01" in text
    assert "## 文字稿" in text
    assert chars > 0


def test_convert_dir_generates_index(tmp_path):
    subs = tmp_path / "subs"
    subs.mkdir()
    _write_srt(subs / "BV1a.srt", ["1", "00:00:00,000 --> 00:00:02,000", "甲视频内容"])
    _write_srt(subs / "BV1b.srt", ["1", "00:00:00,000 --> 00:00:02,000", "乙视频内容"])
    # 模拟 yt-dlp 的 info.json
    (subs / "BV1a.info.json").write_text(
        json.dumps({"id": "BV1a", "title": "甲视频", "duration": 60, "webpage_url": "u1"}),
        encoding="utf-8",
    )

    out = tmp_path / "md"
    summary = convert.convert_dir(subs, out, index_title="测试索引")
    assert summary["written"] == 2
    index = (out / "00_索引.md").read_text(encoding="utf-8")
    assert "# 测试索引" in index
    assert "[BV1a.md](BV1a.md)" in index
    assert "甲视频" in index
    assert (out / "BV1a.md").exists()


def test_best_stream_selection():
    info = MediaInfo(
        platform="test",
        id="1",
        title="t",
        webpage_url="u",
        formats=[
            StreamFormat("360", "u360", height=360, vcodec="avc1"),
            StreamFormat("1080", "u1080", height=1080, vcodec="avc1"),
            StreamFormat("720", "u720", height=720, vcodec="avc1"),
        ],
    )
    assert info.best_stream().height == 1080
    assert info.best_stream(max_height=720).height == 720
    # 上限内没有流时取可用的最佳流
    assert info.best_stream(max_height=480).height == 360
