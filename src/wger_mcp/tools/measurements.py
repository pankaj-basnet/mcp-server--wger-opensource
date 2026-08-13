"""Body measurement tools (categories + entries), via the generated
``wger_api_client``."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated, Any
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from pydantic import Field
from wger_api_client import models as api_models
from wger_api_client.api.measurement import (
    measurement_create,
    measurement_destroy,
    measurement_list,
    measurement_partial_update,
    measurement_retrieve,
)
from wger_api_client.api.measurement_category import (
    measurement_category_create,
    measurement_category_destroy,
    measurement_category_list,
    measurement_category_partial_update,
    measurement_category_retrieve,
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


def _uuid(value: str, field: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise ValueError(f"{field} must be a UUID, got {value!r}") from None


def register(mcp: FastMCP, api: AuthenticatedClient, settings: Settings) -> None:
    # ── Categories ──────────────────────────────────────────────────────────

    @mcp.tool()
    async def list_measurement_categories(
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
    ) -> list[dict[str, Any]]:
        """List all body measurement categories (e.g. Waist, Chest, Bicep)."""
        try:
            return await paginate(measurement_category_list.asyncio, client=api, limit=limit)
        except UnexpectedStatus as exc:
            return [api_err(exc)]

    @mcp.tool()
    async def create_measurement_category(
        name: Annotated[str, Field(min_length=1, max_length=100)],
        unit: Annotated[str, Field(min_length=1, max_length=30)] = "cm",
    ) -> dict[str, Any]:
        """Create a body measurement category (e.g. name='Bicep', unit='cm')."""
        try:
            created = await measurement_category_create.asyncio(
                client=api, body=api_models.CategoryRequest(name=name, unit=unit)
            )
            return created.to_dict()
        except UnexpectedStatus as exc:
            return api_err(exc)

    @mcp.tool()
    async def get_measurement_category(category_id: str) -> dict[str, Any]:
        """Fetch a single measurement category by ID."""
        try:
            category = await measurement_category_retrieve.asyncio(
                id=_uuid(category_id, "category_id"), client=api
            )
            return category.to_dict()
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError as exc:
            return bad_request(str(exc))

    @mcp.tool()
    async def update_measurement_category(
        category_id: str,
        name: str | None = None,
        unit: Annotated[str | None, Field(max_length=30)] = None,
    ) -> dict[str, Any]:
        """Rename or change the unit of a measurement category."""
        body = api_models.PatchedCategoryRequest(
            name=name if name is not None else UNSET,
            unit=unit if unit is not None else UNSET,
        )
        if not body.to_dict():
            return bad_request("no fields to update")
        try:
            updated = await measurement_category_partial_update.asyncio(
                id=_uuid(category_id, "category_id"), client=api, body=body
            )
            return updated.to_dict()
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError as exc:
            return bad_request(str(exc))

    @mcp.tool()
    async def delete_measurement_category(category_id: str) -> dict[str, Any]:
        """Delete a measurement category and all its entries."""
        try:
            await measurement_category_destroy.asyncio_detailed(
                id=_uuid(category_id, "category_id"), client=api
            )
            return {"deleted": True, "category_id": category_id}
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError as exc:
            return bad_request(str(exc))

    # ── Entries ──────────────────────────────────────────────────────────────

    @mcp.tool()
    async def list_measurements(
        category_id: str | None = None,
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
    ) -> list[dict[str, Any]]:
        """List body measurement entries, optionally filtered by category."""
        filters: dict[str, Any] = {"ordering": "-date"}
        if category_id is not None:
            try:
                filters["category"] = _uuid(category_id, "category_id")
            except ValueError as exc:
                return [bad_request(str(exc))]
        try:
            return await paginate(measurement_list.asyncio, client=api, limit=limit, **filters)
        except UnexpectedStatus as exc:
            return [api_err(exc)]

    @mcp.tool()
    async def log_measurement(
        category_id: str,
        value: Annotated[float, Field(gt=0)],
        when: date | datetime | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Add a body measurement entry to a category. Defaults to now; a bare
        date lands at 12:00."""
        try:
            body = api_models.MeasurementRequest(
                category=_uuid(category_id, "category_id"),
                value=value,
                date=(
                    when
                    if isinstance(when, datetime)
                    else datetime.combine(when, _BARE_DATE_TIME)
                    if when is not None
                    else UNSET
                ),
                notes=notes if notes is not None else UNSET,
            )
            created = await measurement_create.asyncio(client=api, body=body)
            return created.to_dict()
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError as exc:
            return bad_request(str(exc))

    @mcp.tool()
    async def get_measurement(measurement_id: str) -> dict[str, Any]:
        """Fetch a single body measurement entry by ID."""
        try:
            entry = await measurement_retrieve.asyncio(
                id=_uuid(measurement_id, "measurement_id"), client=api
            )
            return entry.to_dict()
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError as exc:
            return bad_request(str(exc))

    @mcp.tool()
    async def update_measurement(
        measurement_id: str,
        value: Annotated[float | None, Field(gt=0)] = None,
        when: date | datetime | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Patch a body measurement entry."""
        body = api_models.PatchedMeasurementRequest(
            value=value if value is not None else UNSET,
            date=(
                when
                if isinstance(when, datetime)
                else datetime.combine(when, _BARE_DATE_TIME)
                if when is not None
                else UNSET
            ),
            notes=notes if notes is not None else UNSET,
        )
        if not body.to_dict():
            return bad_request("no fields to update")
        try:
            updated = await measurement_partial_update.asyncio(
                id=_uuid(measurement_id, "measurement_id"), client=api, body=body
            )
            return updated.to_dict()
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError as exc:
            return bad_request(str(exc))

    @mcp.tool()
    async def delete_measurement(measurement_id: str) -> dict[str, Any]:
        """Delete a body measurement entry."""
        try:
            await measurement_destroy.asyncio_detailed(
                id=_uuid(measurement_id, "measurement_id"), client=api
            )
            return {"deleted": True, "measurement_id": measurement_id}
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError as exc:
            return bad_request(str(exc))
