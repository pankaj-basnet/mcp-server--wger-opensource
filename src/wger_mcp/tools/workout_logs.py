"""Workout log tools (per-set logging), via the generated ``wger_api_client``.

The legacy ``list_workouts`` tool is gone; its ``/workout/`` endpoint no
longer exists on wger >= 2.6.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Annotated, Any
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from pydantic import Field
from wger_api_client import models as api_models
from wger_api_client.api.workoutlog import (
    workoutlog_create,
    workoutlog_destroy,
    workoutlog_list,
    workoutlog_partial_update,
    workoutlog_retrieve,
)
from wger_api_client.client import AuthenticatedClient
from wger_api_client.errors import UnexpectedStatus
from wger_api_client.types import UNSET, Unset

from ..api_client import api_err, paginate
from ..config import Settings
from .common import bad_request

# Bare dates land at noon so the entry stays on the intended day across
# timezone shifts.
_BARE_DATE_TIME = time(12, 0)


def _log_datetime(when: date | datetime | None) -> datetime | Unset:
    if when is None:
        return UNSET
    if isinstance(when, datetime):
        return when
    return datetime.combine(when, _BARE_DATE_TIME)


def register(mcp: FastMCP, api: AuthenticatedClient, settings: Settings) -> None:
    @mcp.tool()
    async def log_set(
        exercise_id: str,
        reps: Annotated[int, Field(ge=1, le=1000)],
        weight_kg: Annotated[float, Field(ge=0, le=1000)],
        workout_log_date: date | datetime | None = None,
        rir: Annotated[float | None, Field(ge=0, le=10)] = None,
    ) -> dict[str, Any]:
        """Log a completed set (workoutlog). Without a date, wger stamps the
        entry with the current time; a bare date lands at 12:00."""
        try:
            body = api_models.WorkoutLogRequest(
                exercise=int(exercise_id),
                repetitions=str(reps),
                weight=f"{weight_kg:g}",
                date=_log_datetime(workout_log_date),
                rir=f"{rir:g}" if rir is not None else UNSET,
            )
            created = await workoutlog_create.asyncio(client=api, body=body)
            return created.to_dict()
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError:
            return bad_request(f"exercise_id must be a numeric id, got {exercise_id!r}")

    @mcp.tool()
    async def list_workout_logs(
        date_from: date | None = None,
        date_to: date | None = None,
        exercise_id: str | None = None,
        limit: Annotated[int, Field(ge=1, le=1000)] = 100,
    ) -> list[dict[str, Any]]:
        """List workout log entries (individual sets) with optional date/exercise filters."""
        filters: dict[str, Any] = {"ordering": "-date"}
        if date_from is not None:
            filters["date_gte"] = datetime.combine(date_from, time.min)
        if date_to is not None:
            filters["date_lt"] = datetime.combine(date_to + timedelta(days=1), time.min)
        if exercise_id is not None:
            try:
                filters["exercise"] = int(exercise_id)
            except ValueError:
                return [bad_request(f"exercise_id must be a numeric id, got {exercise_id!r}")]
        try:
            return await paginate(workoutlog_list.asyncio, client=api, limit=limit, **filters)
        except UnexpectedStatus as exc:
            return [api_err(exc)]

    @mcp.tool()
    async def get_workout_log(log_id: str) -> dict[str, Any]:
        """Fetch one workout log entry."""
        try:
            log = await workoutlog_retrieve.asyncio(id=UUID(log_id), client=api)
            return log.to_dict()
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError:
            return bad_request(f"log_id must be a UUID, got {log_id!r}")

    @mcp.tool()
    async def update_workout_log(
        log_id: str,
        reps: Annotated[int | None, Field(ge=1, le=1000)] = None,
        weight_kg: Annotated[float | None, Field(ge=0, le=1000)] = None,
        rir: Annotated[float | None, Field(ge=0, le=10)] = None,
        when: date | datetime | None = None,
    ) -> dict[str, Any]:
        """Patch a workout log entry. Only provided fields are sent."""
        body = api_models.PatchedWorkoutLogRequest(
            repetitions=str(reps) if reps is not None else UNSET,
            weight=f"{weight_kg:g}" if weight_kg is not None else UNSET,
            rir=f"{rir:g}" if rir is not None else UNSET,
            date=_log_datetime(when),
        )
        if not body.to_dict():
            return bad_request("no fields to update")
        try:
            updated = await workoutlog_partial_update.asyncio(
                id=UUID(log_id), client=api, body=body
            )
            return updated.to_dict()
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError:
            return bad_request(f"log_id must be a UUID, got {log_id!r}")

    @mcp.tool()
    async def delete_workout_log(log_id: str) -> dict[str, Any]:
        """Delete a workout log entry."""
        try:
            await workoutlog_destroy.asyncio_detailed(id=UUID(log_id), client=api)
            return {"deleted": True, "log_id": log_id}
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError:
            return bad_request(f"log_id must be a UUID, got {log_id!r}")
