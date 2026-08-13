"""Attaching logged sets to a routine: get_workout_for_date + log_set linkage."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import respx
from mcp.server.fastmcp import FastMCP

from wger_mcp.config import Settings
from wger_mcp.tools import routines, workout_logs
from wger_mcp.wger_client import WgerClient

API = "https://wger.test/api/v2"
TODAY = date.today().isoformat()


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


def _register(module: Any) -> FastMCP:
    mcp = FastMCP("test")
    module.register(mcp, WgerClient(API, _StubProvider()), _settings())
    return mcp


def _payload(route: Any) -> dict[str, Any]:
    return json.loads(route.calls.last.request.content)


def _result(raw: Any) -> Any:
    """FastMCP returns (content, structured); take the structured payload."""
    return raw[1] if isinstance(raw, tuple) else raw


def _gym_sequence(day_date: str = TODAY, *, is_rest: bool = False) -> list[dict[str, Any]]:
    return [
        {
            "iteration": 3,
            "date": day_date,
            "label": "Week 3",
            "day": {"id": 11, "name": "Push", "is_rest": is_rest},
            "slots": [
                {
                    "comment": "",
                    "is_superset": False,
                    "exercises": [73],
                    "sets": [
                        {
                            "slot_entry_id": 501,
                            "exercise": 73,
                            "sets": 5,
                            "repetitions": 5,
                            "weight": 61.23,
                            "weight_unit": 1,
                            "rir": 2,
                            "rest": 180,
                            "text_repr": "5 x 5 @ 61.23 kg",
                        }
                    ],
                }
            ],
        }
    ]


# ---------- get_workout_for_date ----------


def _mock_names(mock: Any) -> None:
    """Names live on translations; the plan endpoints carry only ids."""
    mock.get("/language/").respond(
        json={"count": 1, "next": None, "results": [{"id": 2, "short_name": "en"}]}
    )
    mock.get("/exercise-translation/").respond(
        json={
            "count": 2,
            "next": None,
            "results": [
                {"exercise": 73, "language": 1, "name": "Bankdrucken"},
                {"exercise": 73, "language": 2, "name": "Bench Press"},
            ],
        }
    )


async def test_returns_slot_entry_ids_for_today() -> None:
    mcp = _register(routines)
    with respx.mock(base_url=API) as mock:
        mock.get("/routine/7/date-sequence-gym/").respond(json=_gym_sequence())
        _mock_names(mock)
        out = _result(await mcp.call_tool("get_workout_for_date", {"routine_id": "7"}))

    assert out["iteration"] == 3
    assert out["day_name"] == "Push"
    assert out["is_rest_day"] is False
    assert len(out["planned"]) == 1
    entry = out["planned"][0]
    # These three are what log_set needs; without them the linkage is guesswork.
    assert entry["slot_entry_id"] == 501
    assert entry["exercise_id"] == 73
    assert entry["repetitions"] == 5
    # A name, not a bare id: reading the plan should not require a second lookup.
    assert entry["exercise_name"] == "Bench Press"


async def test_date_outside_the_routine_is_not_an_error() -> None:
    """A date the routine does not cover reports a rest day, not a failure."""
    mcp = _register(routines)
    with respx.mock(base_url=API) as mock:
        mock.get("/routine/7/date-sequence-gym/").respond(json=_gym_sequence("1999-01-01"))
        out = _result(await mcp.call_tool("get_workout_for_date", {"routine_id": "7"}))

    assert out["is_rest_day"] is True
    assert out["planned"] == []
    assert out["iteration"] is None
    assert "note" in out


async def test_rest_day_reports_no_planned_work() -> None:
    mcp = _register(routines)
    sequence = _gym_sequence(is_rest=True)
    sequence[0]["slots"] = []
    with respx.mock(base_url=API) as mock:
        mock.get("/routine/7/date-sequence-gym/").respond(json=sequence)
        out = _result(await mcp.call_tool("get_workout_for_date", {"routine_id": "7"}))

    assert out["is_rest_day"] is True
    assert out["planned"] == []
    assert out["day_name"] == "Push"


# ---------- log_set linkage ----------


async def test_log_set_attaches_to_the_plan() -> None:
    mcp = _register(workout_logs)
    with respx.mock(base_url=API) as mock:
        route = mock.post("/workoutlog/").respond(json={"id": "abc"})
        await mcp.call_tool(
            "log_set",
            {
                "exercise_id": "73",
                "reps": 5,
                "weight_kg": 61.23,
                "routine_id": "7",
                "slot_entry_id": "501",
                "iteration": 3,
            },
        )

    sent = _payload(route)
    assert sent["routine"] == "7"
    assert sent["slot_entry"] == "501"
    assert sent["iteration"] == 3
    assert sent["repetitions"] == 5


async def test_log_set_without_linkage_is_unchanged() -> None:
    """Freestanding logging must keep working exactly as before."""
    mcp = _register(workout_logs)
    with respx.mock(base_url=API) as mock:
        route = mock.post("/workoutlog/").respond(json={"id": "abc"})
        await mcp.call_tool(
            "log_set", {"exercise_id": "73", "reps": 5, "weight_kg": 61.23}
        )

    sent = _payload(route)
    assert set(sent) == {"exercise", "repetitions", "weight", "date"}


async def test_slot_entry_without_routine_is_rejected() -> None:
    """wger ties a slot entry to its routine; sending one alone logs it wrong."""
    mcp = _register(workout_logs)
    # assert_all_called=False: the point of this test is that the POST never happens.
    with respx.mock(base_url=API, assert_all_called=False) as mock:
        route = mock.post("/workoutlog/").respond(json={"id": "abc"})
        out = _result(
            await mcp.call_tool(
                "log_set",
                {
                    "exercise_id": "73",
                    "reps": 5,
                    "weight_kg": 61.23,
                    "slot_entry_id": "501",
                },
            )
        )

    assert not route.called
    assert "routine_id" in json.dumps(out)
