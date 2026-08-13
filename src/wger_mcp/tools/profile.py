"""User-profile tools, via the generated ``wger_api_client``."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from wger_api_client.api.userprofile import userprofile_list
from wger_api_client.client import AuthenticatedClient
from wger_api_client.errors import UnexpectedStatus

from ..api_client import api_err
from ..config import Settings


def register(mcp: FastMCP, api: AuthenticatedClient, settings: Settings) -> None:
    @mcp.tool()
    async def whoami() -> dict[str, Any]:
        """Return the wger user profile of the authenticated caller."""
        try:
            profile = await userprofile_list.asyncio(client=api)
            return profile.to_dict()
        except UnexpectedStatus as exc:
            return api_err(exc)
