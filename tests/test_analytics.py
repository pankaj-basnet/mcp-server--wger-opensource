"""Analytics aggregation: log timestamps collapse onto calendar days."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

from wger_mcp.api_client import build_api_client
from wger_mcp.config import Settings
from wger_mcp.tools import analytics


class _StubProvider:
    async def authorization_header(self) -> str:
        return "Token dev"

    async def aclose(self) -> None:
        pass


def _register() -> FastMCP:
    mcp = FastMCP("test")
    settings = Settings(  # type: ignore[call-arg]
        wger_base_url="https://wger.test",
        mcp_auth="none",
        wger_dev_token="dev",
    )
    api = build_api_client(settings, _StubProvider())
    analytics.register(mcp, api, settings)
    return mcp


def _log(day: str, hour: int, reps: str = "8.00", weight: str = "50.00") -> Any:
    entry = {
        "id": f"{day}-{hour}",
        "exercise": 1,
        "date": f"{day}T{hour:02d}:00:00+00:00",
        "repetitions": reps,
        "weight": weight,
    }
    return SimpleNamespace(to_dict=lambda entry=entry: entry)


def _listing(entries: list[Any]):
    async def fn(**kwargs: Any) -> Any:
        return SimpleNamespace(count=len(entries), results=entries)

    return fn


def _result(raw: Any) -> Any:
    return raw[1] if isinstance(raw, tuple) else raw


@pytest.mark.asyncio
async def test_sessions_group_by_day_not_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    """wger stamps each set with a full timestamp; sets of one workout still
    form a single session."""
    mcp = _register()
    day = (date.today() - timedelta(days=1)).isoformat()
    logs = [_log(day, 10), _log(day, 10), _log(day, 11)]
    monkeypatch.setattr(analytics.workoutlog_list, "asyncio", _listing(logs))
    out = _result(await mcp.call_tool("exercise_history", {"exercise_id": "1"}))
    assert len(out["sessions"]) == 1
    assert out["sessions"][0]["date"] == day
    assert out["sessions"][0]["sets"] == 3


@pytest.mark.asyncio
async def test_volume_trend_buckets_timestamped_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = _register()
    day = date.today() - timedelta(days=1)
    logs = [_log(day.isoformat(), 10), _log(day.isoformat(), 18)]
    monkeypatch.setattr(analytics.workoutlog_list, "asyncio", _listing(logs))
    out = _result(await mcp.call_tool("volume_trend", {"days": 7, "bucket": "day"}))
    assert len(out["series"]) == 1
    assert out["series"][0]["bucket_start"] == day.isoformat()
    assert out["series"][0]["sets"] == 2


@pytest.mark.asyncio
async def test_weekly_summary_counts_active_days(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = _register()
    d1 = (date.today() - timedelta(days=1)).isoformat()
    d2 = (date.today() - timedelta(days=2)).isoformat()
    logs = [_log(d1, 9), _log(d1, 10), _log(d2, 9)]
    monkeypatch.setattr(analytics.workoutlog_list, "asyncio", _listing(logs))
    out = _result(await mcp.call_tool("weekly_summary", {"days": 7}))
    assert out["exercises"][0]["active_days"] == 2
    assert out["total_sets"] == 3
