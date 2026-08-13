"""MCP tool modules, grouped by domain.

Each module exposes a ``register(mcp, <client>, settings)`` function;
``server.build_app`` calls them all. Migrated modules take the typed
``AuthenticatedClient``, the rest still the hand-written ``WgerClient``.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from wger_api_client.client import AuthenticatedClient

from ..config import Settings
from ..wger_client import WgerClient
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
    workout_logs.register,
    body_weight.register,
    measurements.register,
    equipment.register,
    exercises.register,
    analytics.register,
    off.register,
)

_TYPED_REGISTRARS = (
    routines.register,
    nutrition.register,
)


def register_all(
    mcp: FastMCP, client: WgerClient, api: AuthenticatedClient, settings: Settings
) -> None:
    """Register every tool module on the given FastMCP instance."""
    for register in _REGISTRARS:
        register(mcp, client, settings)
    for register in _TYPED_REGISTRARS:
        register(mcp, api, settings)


__all__ = ["register_all"]
