"""MCP tool modules, grouped by domain.

Each module exposes a ``register(mcp, <client>, settings)`` function that
attaches its tools to the given FastMCP instance; ``server.build_app`` calls
them all. Modules that need no configuration simply ignore ``settings``.

Modules are being migrated from the hand-written ``WgerClient`` to the typed
``wger_api_client`` (see ``api_client.py``); migrated ones take the
``AuthenticatedClient`` instead.
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
    routines.register,
    workout_logs.register,
    body_weight.register,
    measurements.register,
    equipment.register,
    exercises.register,
    analytics.register,
    off.register,
)

_TYPED_REGISTRARS = (nutrition.register,)


def register_all(
    mcp: FastMCP, client: WgerClient, api: AuthenticatedClient, settings: Settings
) -> None:
    """Register every tool module on the given FastMCP instance."""
    for register in _REGISTRARS:
        register(mcp, client, settings)
    for register in _TYPED_REGISTRARS:
        register(mcp, api, settings)


__all__ = ["register_all"]
