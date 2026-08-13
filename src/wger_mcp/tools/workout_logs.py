"""Workout log tools (per-set logging), via the generated ``wger_api_client``.

The legacy ``list_workouts`` tool is gone; its ``/workout/`` endpoint no
longer exists on wger >= 2.6.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Annotated, Any

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

from ..api_client import paginate
from ..config import Settings
from .common import (
    api_list_tool,
    api_tool,
    as_decimal,
    as_int,
    as_uuid,
    as_weight_unit,
    at_noon,
    opt,
    require_fields,
)


def register(mcp: FastMCP, api: AuthenticatedClient, settings: Settings) -> None:
    @mcp.tool()
    @api_tool
    async def log_set(
        exercise_id: str,
        reps: Annotated[int, Field(ge=1, le=1000)],
        weight: Annotated[float, Field(ge=0, le=2000)],
        workout_log_date: date | datetime | None = None,
        rir: Annotated[float | None, Field(ge=0, le=10)] = None,
        weight_unit: str = "kg",
    ) -> dict[str, Any]:
        """Log a completed set (workoutlog). Without a date, wger stamps the
        entry with the current time; a bare date lands at 12:00.

        weight_unit is 'kg' or 'lb'. The weight is stored in the unit given, so
        a trainee who works in pounds gets pounds back out, with no rounding
        drift from converting twice.

        rir records Reps In Reserve for the set: how many good repetitions were
        left. It is how wger tracks set effort.
        """
        body = api_models.WorkoutLogRequest(
            exercise=as_int(exercise_id, "exercise_id"),
            repetitions=str(reps),
            weight=as_decimal(weight),
            weight_unit=as_weight_unit(weight_unit),
            date=opt(at_noon(workout_log_date)),
            rir=opt(as_decimal(rir) if rir is not None else None),
        )
        created = await workoutlog_create.asyncio(client=api, body=body)
        return created.to_dict()

    @mcp.tool()
    @api_list_tool
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
            filters["exercise"] = as_int(exercise_id, "exercise_id")
        return await paginate(workoutlog_list.asyncio, client=api, limit=limit, **filters)

    @mcp.tool()
    @api_tool
    async def get_workout_log(log_id: str) -> dict[str, Any]:
        """Fetch one workout log entry."""
        log = await workoutlog_retrieve.asyncio(id=as_uuid(log_id, "log_id"), client=api)
        return log.to_dict()

    @mcp.tool()
    @api_tool
    async def update_workout_log(
        log_id: str,
        reps: Annotated[int | None, Field(ge=1, le=1000)] = None,
        weight: Annotated[float | None, Field(ge=0, le=2000)] = None,
        rir: Annotated[float | None, Field(ge=0, le=10)] = None,
        when: date | datetime | None = None,
        weight_unit: str | None = None,
    ) -> dict[str, Any]:
        """Patch a workout log entry. Only provided fields are sent.

        weight_unit ('kg' or 'lb') is only sent when given, so correcting reps
        alone leaves the recorded unit untouched.
        """
        log = as_uuid(log_id, "log_id")
        body = api_models.PatchedWorkoutLogRequest(
            repetitions=opt(str(reps) if reps is not None else None),
            weight=opt(as_decimal(weight) if weight is not None else None),
            weight_unit=opt(as_weight_unit(weight_unit)),
            rir=opt(as_decimal(rir) if rir is not None else None),
            date=opt(at_noon(when)),
        )
        require_fields(body)
        updated = await workoutlog_partial_update.asyncio(id=log, client=api, body=body)
        return updated.to_dict()

    @mcp.tool()
    @api_tool
    async def delete_workout_log(log_id: str) -> dict[str, Any]:
        """Delete a workout log entry."""
        await workoutlog_destroy.asyncio_detailed(id=as_uuid(log_id, "log_id"), client=api)
        return {"deleted": True, "log_id": log_id}
