# -*- coding: utf-8 -*-
"""协议测试共用夹具。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = ENGINE_ROOT / "ai_analyzer" / "schemas"
EXAMPLES_DIR = SCHEMAS_DIR / "examples"
ERROR_EXAMPLES_DIR = EXAMPLES_DIR / "errors"
ANDROID_HEADER = ENGINE_ROOT / "native" / "include" / "ipc" / "protocol_constants.h"


@pytest.fixture(scope="session")
def schemas_dir() -> Path:
    return SCHEMAS_DIR


@pytest.fixture(scope="session")
def examples_dir() -> Path:
    return EXAMPLES_DIR


@pytest.fixture(scope="session")
def android_header() -> Path:
    return ANDROID_HEADER


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def example_files() -> dict[str, dict]:
    """{样例名: 消息 dict}，含 errors/ 子目录。"""
    out: dict[str, dict] = {}
    for p in sorted(EXAMPLES_DIR.glob("*.json")):
        out[p.stem] = load_json(p)
    for p in sorted(ERROR_EXAMPLES_DIR.glob("*.json")):
        out[f"errors/{p.stem}"] = load_json(p)
    return out
