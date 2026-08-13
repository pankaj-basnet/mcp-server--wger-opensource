"""Workout log tools (per-set logging + legacy workouts)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..config import Settings
from ..wger_client import WgerClient, WgerError
from .common import bad_request, err


def register(mcp: FastMCP, client: WgerClient, settings: Settings) -> None:
    @mcp.tool()
    async def list_workouts(
        limit: Annotated[int, Field(ge=1, le=200)] = 20,
    ) -> list[dict[str, Any]]:
        """List legacy workout plans."""
        try:
            return await client.paginate("workout/", limit=limit)
        except WgerError as exc:
            return [err(exc)]

    @mcp.tool()
    async def log_set(
        exercise_id: str,
        reps: Annotated[int, Field(ge=1, le=1000)],
        weight_kg: Annotated[float, Field(ge=0, le=1000)],
        workout_log_date: date | None = None,
        rir: Annotated[float | None, Field(ge=0, le=10)] = None,
        routine_id: str | None = None,
        slot_entry_id: str | None = None,
        iteration: Annotated[int | None, Field(ge=1)] = None,
    ) -> dict[str, Any]:
        """Log a completed set (workoutlog). Uses today if no date given.

        Pass routine_id, slot_entry_id and iteration to attach the set to a
        planned routine entry. Get all three from get_workout_for_date. Without
        them the set is still logged, but as freestanding work that no routine
        report can attribute.
        """
        if slot_entry_id is not None and routine_id is None:
            return bad_request(
                "slot_entry_id needs routine_id; both come from get_workout_for_date"
            )
        payload: dict[str, Any] = {
            "exercise": exercise_id,
            "repetitions": reps,
            "weight": weight_kg,
            "date": (workout_log_date or date.today()).isoformat(),
        }
        if rir is not None:
            payload["rir"] = rir
        if routine_id is not None:
            payload["routine"] = routine_id
        if slot_entry_id is not None:
            payload["slot_entry"] = slot_entry_id
        if iteration is not None:
            payload["iteration"] = iteration
        try:
            return await client.post("workoutlog/", json=payload)
        except WgerError as exc:
            return err(exc)

    @mcp.tool()
    async def list_workout_logs(
        date_from: date | None = None,
        date_to: date | None = None,
        exercise_id: str | None = None,
        limit: Annotated[int, Field(ge=1, le=1000)] = 100,
    ) -> list[dict[str, Any]]:
        """List workout log entries (individual sets) with optional date/exercise filters."""
        params: dict[str, Any] = {"ordering": "-date"}
        if date_from is not None:
            params["date__gte"] = date_from.isoformat()
        if date_to is not None:
            params["date__lte"] = date_to.isoformat()
        if exercise_id is not None:
            params["exercise"] = exercise_id
        try:
            return await client.paginate("workoutlog/", params=params, limit=limit)
        except WgerError as exc:
            return [err(exc)]

    @mcp.tool()
    async def get_workout_log(log_id: str) -> dict[str, Any]:
        """Fetch one workout log entry."""
        try:
            return await client.get(f"workoutlog/{log_id}/")
        except WgerError as exc:
            return err(exc)

    @mcp.tool()
    async def update_workout_log(
        log_id: str,
        reps: Annotated[int | None, Field(ge=1, le=1000)] = None,
        weight_kg: Annotated[float | None, Field(ge=0, le=1000)] = None,
        rir: Annotated[float | None, Field(ge=0, le=10)] = None,
        when: date | None = None,
    ) -> dict[str, Any]:
        """Patch a workout log entry. Only provided fields are sent."""
        payload: dict[str, Any] = {}
        if reps is not None:
            payload["repetitions"] = reps
        if weight_kg is not None:
            payload["weight"] = weight_kg
        if rir is not None:
            payload["rir"] = rir
        if when is not None:
            payload["date"] = when.isoformat()
        if not payload:
            return bad_request("no fields to update")
        try:
            return await client.patch(f"workoutlog/{log_id}/", json=payload)
        except WgerError as exc:
            return err(exc)

    @mcp.tool()
    async def delete_workout_log(log_id: str) -> dict[str, Any]:
        """Delete a workout log entry."""
        try:
            await client.delete(f"workoutlog/{log_id}/")
            return {"deleted": True, "log_id": log_id}
        except WgerError as exc:
            return err(exc)
