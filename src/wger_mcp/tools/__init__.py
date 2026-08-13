"""MCP tool modules, grouped by domain.

Each wger-facing module exposes ``register(mcp, api, settings)`` on the typed
``wger_api_client``; ``off`` talks to Open Food Facts through its own httpx
client. ``server.build_app`` calls them all.
"""

from __future__ import annotations

import httpx
from mcp.server.fastmcp import FastMCP
from wger_api_client.client import AuthenticatedClient

from ..config import Settings
from . import (
    analytics,
    body_weight,
    equipment,
    exercises,
    measurements,
    nutrition,
    off,
    profile,
    routines,
    workout_logs,
)

_REGISTRARS = (
    profile.register,
    routines.register,
    workout_logs.register,
    body_weight.register,
    measurements.register,
    equipment.register,
    nutrition.register,
    exercises.register,
    analytics.register,
)


def register_all(
    mcp: FastMCP, api: AuthenticatedClient, off_http: httpx.AsyncClient, settings: Settings
) -> None:
    """Register every tool module on the given FastMCP instance."""
    for register in _REGISTRARS:
        register(mcp, api, settings)
    off.register(mcp, off_http, settings)


__all__ = ["register_all"]
