"""导入、统计与配置的单元测试：不需要数据库即可运行。"""

import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = BACKEND.parent / "fixtures"
os.environ.setdefault("PUBLIC_ORIGIN", "http://localhost:8080")
sys.path.insert(0, str(BACKEND))


@pytest.fixture(scope="session")
def fixtures():
    return FIXTURES


@pytest.fixture(scope="session")
def sample_snapshot(fixtures):
    import json

    return json.loads((fixtures / "sample-snapshot.json").read_text(encoding="utf-8"))
