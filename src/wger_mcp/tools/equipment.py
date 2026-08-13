"""Equipment catalog tools, via the generated ``wger_api_client``.

The catalog is global and read-only in wger; the earlier create/update/delete
tools could never succeed and are gone.
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field
from wger_api_client.api.equipment import equipment_list, equipment_retrieve
from wger_api_client.client import AuthenticatedClient
from wger_api_client.errors import UnexpectedStatus

from ..api_client import api_err, paginate
from ..config import Settings
from .common import bad_request


def register(mcp: FastMCP, api: AuthenticatedClient, settings: Settings) -> None:
    @mcp.tool()
    async def list_gym_equipment(
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
    ) -> list[dict[str, Any]]:
        """List the equipment catalog (barbell, dumbbell, ...)."""
        try:
            return await paginate(equipment_list.asyncio, client=api, limit=limit)
        except UnexpectedStatus as exc:
            return [api_err(exc)]

    @mcp.tool()
    async def get_gym_equipment(equipment_id: str) -> dict[str, Any]:
        """Fetch a single equipment entry by ID."""
        try:
            item = await equipment_retrieve.asyncio(id=int(equipment_id), client=api)
            return item.to_dict()
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError:
            return bad_request(f"equipment_id must be a numeric id, got {equipment_id!r}")
