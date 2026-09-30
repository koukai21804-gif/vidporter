from __future__ import annotations

import json

from vidporter.config import Config
from vidporter.platforms.ytdlp_backend import build_ydl_opts, info_dict_to_media
from vidporter.subtitle.fetch import bv_from_url, load_url_list


def test_config_defaults():
    cfg = Config()
    assert cfg.quality is None
    assert cfg.out_dir.name == "downloads"
    assert cfg.cookie_file_for("bilibili").name == "bilibili.txt"


def test_config_load_toml(tmp_path):
    cfg_file = tmp_path / "vidporter.toml"
    cfg_file.write_text(
        """
[vidporter]
out_dir = "~/videos"
quality = 1080
subtitle_langs = "zh-Hans"
proxy = "http://127.0.0.1:7890"
""",
        encoding="utf-8",
    )
    cfg = Config.load(cfg_file)
    assert cfg.quality == 1080
    assert cfg.subtitle_langs == "zh-Hans"
    assert str(cfg.proxy) == "http://127.0.0.1:7890"
    assert "videos" in str(cfg.out_dir)


def test_build_ydl_opts(tmp_path):
    # cookies_dir 指向临时目录，测试不受本机真实 cookie 影响
    cfg = Config(cookies_dir=tmp_path / "cookies")
    from vidporter.platforms.base import ExtractContext

    ctx = ExtractContext(config=cfg)
    from vidporter.models import DownloadOptions

    opts = DownloadOptions(out_dir=tmp_path, max_height=1080, download_subtitles=True)
    ydl = build_ydl_opts(ctx, opts)
    assert "height<=1080" in ydl["format"]
    assert ydl["writesubtitles"] is True
    assert ydl["subtitleslangs"] == ["ai-zh", "zh-Hans"]
    assert "cookiefile" not in ydl


def test_build_ydl_opts_audio(tmp_path):
    from vidporter.models import DownloadOptions
    from vidporter.platforms.base import ExtractContext

    ctx = ExtractContext(config=Config(cookies_dir=tmp_path / "cookies"))
    opts = DownloadOptions(out_dir=tmp_path, audio_only=True, audio_format="mp3")
    ydl = build_ydl_opts(ctx, opts)
    assert ydl["format"] == "bestaudio/best"
    assert ydl["postprocessors"][0]["preferredcodec"] == "mp3"


def test_info_dict_mapping():
    raw = {
        "id": "BV1xx",
        "title": "标题",
        "webpage_url": "https://www.bilibili.com/video/BV1xx",
        "uploader": "UP",
        "duration": 100,
        "formats": [
            {
                "format_id": "100-1",
                "ext": "mp4",
                "url": "http://u/1",
                "height": 1080,
                "vcodec": "avc1",
                "acodec": "mp4a",
                "filesize": 123,
            },
            {
                "format_id": "audio",
                "ext": "m4a",
                "url": "http://u/2",
                "vcodec": "none",
                "acodec": "mp4a",
            },
        ],
        "subtitles": {"zh-Hans": [{"ext": "srt", "url": "http://s/1", "name": "中文"}]},
        "automatic_captions": {"ai-zh": [{"ext": "srt", "url": "http://s/2"}]},
    }
    media = info_dict_to_media(raw, "bilibili")
    assert media.title == "标题"
    assert len(media.formats) == 2
    assert media.formats[0].height == 1080
    assert {t.lang for t in media.subtitles} == {"zh-Hans", "ai-zh"}


def test_bv_and_list_parsing(tmp_path):
    assert bv_from_url("https://www.bilibili.com/video/BV1xx411c7mD?p=1") == "BV1xx411c7mD"
    assert bv_from_url("BV1abcDEFghi") == "BV1abcDEFghi"
    assert bv_from_url("https://example.com/other") is None

    list_file = tmp_path / "urls.txt"
    list_file.write_text(
        "\n".join(
            [
                "# 注释行",
                "",
                "BV1abc1234567",
                "https://www.bilibili.com/video/BV1xyz5678901",
            ]
        ),
        encoding="utf-8",
    )
    urls = load_url_list(list_file)
    assert urls == [
        "https://www.bilibili.com/video/BV1abc1234567",
        "https://www.bilibili.com/video/BV1xyz5678901",
    ]


def test_channels_sniffer_detection(tmp_path, monkeypatch):
    from vidporter.platforms import channels

    # 未安装时返回 None（monkeypatch 掉 PATH 查找环境）
    monkeypatch.setattr(channels, "TOOL_BINARIES", {"res-downloader": ["definitely-not-exist-xyz"]})
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert channels.find_sniffer_tool(None) is None

    # 显式路径
    exe = tmp_path / "res-downloader.exe"
    exe.write_bytes(b"")
    assert channels.find_sniffer_tool(exe) == exe


def test_batch_state_roundtrip(tmp_path):
    """批量下载的状态文件应可序列化恢复。"""
    state = tmp_path / "list.txt.state.json"
    state.write_text(json.dumps(["https://a.com/1", "https://a.com/2"]))
    assert json.loads(state.read_text()) == ["https://a.com/1", "https://a.com/2"]
