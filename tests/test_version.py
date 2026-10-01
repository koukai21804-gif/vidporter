"""发布一致性：两处版本号必须同步。"""

from __future__ import annotations

import sys
from pathlib import Path

import vidporter

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_version_matches_pyproject():
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    assert vidporter.__version__ == data["project"]["version"]
