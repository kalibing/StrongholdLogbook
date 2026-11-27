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


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """限速计数是进程内全局状态，每个用例前清空，避免用例之间互相影响。"""
    from logbook import api

    counters = [api.login_throttle, api.register_ip_quota, api.register_failures, api.register_global_quota]
    counters += [counter for counter, _ in api.user_quotas.values()]
    for counter in counters:
        counter._failures.clear()
    yield
