"""Bridge between the generated ``wger_api_client`` and this server's auth.

The generated :class:`~wger_api_client.client.AuthenticatedClient` expects one
fixed token, but this server resolves the outbound wger credential *per
request* from the caller's identity (see ``auth/exchange.py``). The bridge is
an :class:`httpx.Auth` that asks the :class:`WgerTokenProvider` for the
``Authorization`` header on every request, injected via
``set_async_httpx_client`` so all requests share one connection pool.

Also provides the two helpers the tool modules need on top of the generated
functions: offset pagination over ``*_list`` endpoints and shaping
:class:`~wger_api_client.errors.UnexpectedStatus` into the error dict the
tools return (same shape as ``tools.common.err``).

Tool modules are being migrated from the hand-written ``wger_client`` to this
typed client one by one; both coexist until the migration is complete.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, Protocol

import httpx
from wger_api_client.client import AuthenticatedClient
from wger_api_client.errors import UnexpectedStatus

from .auth.exchange import WgerTokenProvider
from .config import Settings

# One request per page; matches wger's maximum API page size.
_PAGE_LIMIT = 100


class _ProviderAuth(httpx.Auth):
    """Resolves the Authorization header per request from the token provider.

    The provider reads the caller's identity off the request context, so the
    header differs between concurrent requests of different users.
    """

    def __init__(self, provider: WgerTokenProvider) -> None:
        self._provider = provider

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        request.headers["Authorization"] = await self._provider.authorization_header()
        yield request


def build_api_client(settings: Settings, provider: WgerTokenProvider) -> AuthenticatedClient:
    """One shared typed client; auth is per-request via ``_ProviderAuth``.

    The ``token`` attribute is never sent — ``set_async_httpx_client`` replaces
    the client the generated code would otherwise build from it.
    """
    base_url = str(settings.wger_base_url).rstrip("/")
    api = AuthenticatedClient(
        base_url=base_url,
        token="unused-per-request-auth",
        raise_on_unexpected_status=True,
    )
    api.set_async_httpx_client(
        httpx.AsyncClient(
            base_url=base_url,
            auth=_ProviderAuth(provider),
            timeout=20.0,
            headers={
                "Accept": "application/json",
                "User-Agent": "wger-mcp/0.1",
            },
        )
    )
    return api


def api_err(exc: UnexpectedStatus) -> dict[str, Any]:
    """Shape an UnexpectedStatus as the tool-response error dict."""
    try:
        detail: Any = json.loads(exc.content)
    except ValueError:
        detail = exc.content.decode(errors="replace")
    return {"error": True, "status": exc.status_code, "detail": detail}


class _Page(Protocol):
    count: Any
    results: Any


async def paginate(
    list_fn: Callable[..., Awaitable[_Page | None]],
    *,
    client: AuthenticatedClient,
    limit: int,
    **filters: Any,
) -> list[dict[str, Any]]:
    """Collect up to ``limit`` items from a generated ``*_list.asyncio``.

    Requests ``limit`` directly (the server caps a page at its own maximum)
    and follows with offset requests while the server returns fewer items
    than asked for but reports more available.
    """
    results: list[dict[str, Any]] = []
    while len(results) < limit:
        page = await list_fn(
            client=client,
            limit=min(limit - len(results), _PAGE_LIMIT),
            offset=len(results) or None,
            **filters,
        )
        items = page.results if page and isinstance(page.results, list) else []
        if not items:
            break
        results.extend(item.to_dict() for item in items)
        count = page.count if isinstance(page.count, int) else None
        if count is not None and len(results) >= count:
            break
    return results[:limit]
