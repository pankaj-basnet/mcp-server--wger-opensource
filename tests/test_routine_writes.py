"""Routine and day creation against wger's actual field contract."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import respx
from mcp.server.fastmcp import FastMCP

from wger_mcp.config import Settings
from wger_mcp.tools import routines
from wger_mcp.wger_client import WgerClient

API = "https://wger.test/api/v2"


class _StubProvider:
    async def authorization_header(self) -> str:
        return "Token dev"

    async def aclose(self) -> None:
        pass


def _settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        wger_base_url="https://wger.test",
        mcp_auth="none",
        wger_dev_token="dev",
    )


def _register() -> FastMCP:
    mcp = FastMCP("test")
    routines.register(mcp, WgerClient(API, _StubProvider()), _settings())
    return mcp


def _payload(route: Any) -> dict[str, Any]:
    return json.loads(route.calls.last.request.content)


def _result(raw: Any) -> Any:
    return raw[1] if isinstance(raw, tuple) else raw


# ---------- create_routine ----------


async def test_end_is_always_sent() -> None:
    """wger marks end required; omitting it is a 400."""
    mcp = _register()
    with respx.mock(base_url=API) as mock:
        route = mock.post("/routine/").respond(json={"id": 1})
        await mcp.call_tool("create_routine", {"name": "Recomp", "start": "2026-08-24"})

    sent = _payload(route)
    assert sent["start"] == "2026-08-24"
    assert sent["end"] == (date(2026, 8, 24) + timedelta(weeks=12)).isoformat()


async def test_explicit_end_is_kept() -> None:
    mcp = _register()
    with respx.mock(base_url=API) as mock:
        route = mock.post("/routine/").respond(json={"id": 1})
        await mcp.call_tool(
            "create_routine",
            {"name": "Recomp", "start": "2026-08-24", "end": "2026-11-14"},
        )

    assert _payload(route)["end"] == "2026-11-14"


async def test_end_before_start_is_refused() -> None:
    mcp = _register()
    with respx.mock(base_url=API, assert_all_called=False) as mock:
        route = mock.post("/routine/").respond(json={"id": 1})
        out = _result(
            await mcp.call_tool(
                "create_routine",
                {"name": "Recomp", "start": "2026-08-24", "end": "2026-08-01"},
            )
        )

    assert not route.called
    assert "end" in json.dumps(out)


# ---------- add_routine_day ----------


async def test_default_day_type_is_accepted_by_wger() -> None:
    """The old default, "standard", is not in wger's DayType choices at all."""
    mcp = _register()
    with respx.mock(base_url=API) as mock:
        route = mock.post("/day/").respond(json={"id": 5})
        await mcp.call_tool(
            "add_routine_day", {"routine_id": "1", "name": "Upper Push", "order": 1}
        )

    sent = _payload(route)
    assert sent["type"] == "custom"
    assert sent["type"] in routines.DAY_TYPES


async def test_every_declared_day_type_is_sent_through() -> None:
    mcp = _register()
    for day_type in routines.DAY_TYPES:
        with respx.mock(base_url=API) as mock:
            route = mock.post("/day/").respond(json={"id": 5})
            await mcp.call_tool(
                "add_routine_day",
                {"routine_id": "1", "name": "D", "order": 1, "day_type": day_type},
            )
        assert _payload(route)["type"] == day_type


async def test_unknown_day_type_is_refused_locally() -> None:
    """Catch it here rather than spending a round trip on a 400 the model
    cannot read."""
    mcp = _register()
    with respx.mock(base_url=API, assert_all_called=False) as mock:
        route = mock.post("/day/").respond(json={"id": 5})
        out = _result(
            await mcp.call_tool(
                "add_routine_day",
                {
                    "routine_id": "1",
                    "name": "Upper Push",
                    "order": 1,
                    "day_type": "standard",
                },
            )
        )

    assert not route.called
    message = json.dumps(out)
    assert "standard" in message
    assert "custom" in message  # the error has to name the valid options
