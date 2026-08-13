"""Body-weight tracking tools, via the generated ``wger_api_client``."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field
from wger_api_client import models as api_models
from wger_api_client.api.weightentry import (
    weightentry_create,
    weightentry_destroy,
    weightentry_list,
    weightentry_partial_update,
)
from wger_api_client.client import AuthenticatedClient
from wger_api_client.errors import UnexpectedStatus
from wger_api_client.types import UNSET

from ..api_client import api_err, paginate
from ..config import Settings
from .common import bad_request

# Bare dates land at noon so the entry stays on the intended day across
# timezone shifts.
_BARE_DATE_TIME = time(12, 0)


def _entry_datetime(when: date | datetime | None) -> datetime:
    if when is None:
        return datetime.now(UTC)
    if isinstance(when, datetime):
        return when
    return datetime.combine(when, _BARE_DATE_TIME)


def register(mcp: FastMCP, api: AuthenticatedClient, settings: Settings) -> None:
    @mcp.tool()
    async def log_body_weight(
        weight_kg: Annotated[float, Field(gt=0, le=500)],
        when: date | datetime | None = None,
    ) -> dict[str, Any]:
        """Log a body-weight entry. Defaults to now; a bare date lands at 12:00."""
        body = api_models.WeightEntryRequest(
            date=_entry_datetime(when),
            weight=f"{weight_kg:g}",
        )
        try:
            created = await weightentry_create.asyncio(client=api, body=body)
            return created.to_dict()
        except UnexpectedStatus as exc:
            return api_err(exc)

    @mcp.tool()
    async def get_body_weight_history(
        limit: Annotated[int, Field(ge=1, le=500)] = 30,
    ) -> list[dict[str, Any]]:
        """Return recent body-weight entries (newest first)."""
        try:
            return await paginate(
                weightentry_list.asyncio, client=api, limit=limit, ordering="-date"
            )
        except UnexpectedStatus as exc:
            return [api_err(exc)]

    @mcp.tool()
    async def update_body_weight_entry(
        entry_id: str,
        weight_kg: Annotated[float | None, Field(gt=0, le=500)] = None,
        when: date | datetime | None = None,
    ) -> dict[str, Any]:
        """Patch a body-weight entry."""
        body = api_models.PatchedWeightEntryRequest(
            weight=f"{weight_kg:g}" if weight_kg is not None else UNSET,
            date=_entry_datetime(when) if when is not None else UNSET,
        )
        if not body.to_dict():
            return bad_request("no fields to update")
        try:
            updated = await weightentry_partial_update.asyncio(
                id=int(entry_id), client=api, body=body
            )
            return updated.to_dict()
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError:
            return bad_request(f"entry_id must be a numeric id, got {entry_id!r}")

    @mcp.tool()
    async def delete_body_weight_entry(entry_id: str) -> dict[str, Any]:
        """Delete a body-weight entry."""
        try:
            await weightentry_destroy.asyncio_detailed(id=int(entry_id), client=api)
            return {"deleted": True, "entry_id": entry_id}
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError:
            return bad_request(f"entry_id must be a numeric id, got {entry_id!r}")
