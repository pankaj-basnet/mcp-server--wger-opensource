"""The typed-client bridge: per-request auth, pagination, error shaping."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
import respx
from wger_api_client.errors import UnexpectedStatus

from wger_mcp import api_client
from wger_mcp.api_client import build_api_client, paginate
from wger_mcp.config import Settings
from wger_mcp.tools.common import api_err


class _StubProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def authorization_header(self) -> str:
        self.calls += 1
        return f"Token call-{self.calls}"

    async def aclose(self) -> None:
        pass


def _api(provider: _StubProvider):
    settings = Settings(  # type: ignore[call-arg]
        wger_base_url="https://wger.test",
        mcp_auth="none",
        wger_dev_token="dev",
    )
    return build_api_client(settings, provider)


# ---------- _ProviderAuth ----------


@pytest.mark.asyncio
async def test_authorization_header_is_resolved_per_request() -> None:
    """Every request asks the provider anew — that is what makes the shared
    client safe for multiple users."""
    provider = _StubProvider()
    api = _api(provider)
    with respx.mock(base_url="https://wger.test") as router:
        route = router.get("/api/v2/version/").respond(json="2.7.0")
        client = api.get_async_httpx_client()
        await client.get("/api/v2/version/")
        await client.get("/api/v2/version/")
    headers = [call.request.headers["Authorization"] for call in route.calls]
    assert headers == ["Token call-1", "Token call-2"]


# ---------- paginate ----------


def _item(n: int) -> Any:
    return SimpleNamespace(to_dict=lambda n=n: {"id": n})


def _fake_list(total: int, *, count: int | None = None):
    """A stand-in for a generated ``*_list.asyncio``.

    Serves like the real endpoint: exactly as many items as asked for, until
    the data runs out. ``count`` defaults to the true total; pass None for a
    server that does not report one.
    """
    calls: list[dict[str, Any]] = []

    async def fn(*, client: Any = None, limit: int, offset: int | None = None, **kwargs: Any):
        calls.append({"limit": limit, "offset": offset, **kwargs})
        start = offset or 0
        items = [_item(n) for n in range(start + 1, min(start + limit, total) + 1)]
        return SimpleNamespace(count=total if count is None else count, results=items)

    fn.calls = calls  # type: ignore[attr-defined]
    return fn


@pytest.mark.asyncio
async def test_paginate_single_page() -> None:
    fn = _fake_list(2)
    result = await paginate(fn, client=None, limit=10)
    assert result == [{"id": 1}, {"id": 2}]
    assert len(fn.calls) == 1


@pytest.mark.asyncio
async def test_paginate_follows_offsets_up_to_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """More rows than fit in a page are collected over several offsets."""
    monkeypatch.setattr(api_client, "_PAGE_LIMIT", 2)
    fn = _fake_list(5)
    result = await paginate(fn, client=None, limit=5)
    assert [r["id"] for r in result] == [1, 2, 3, 4, 5]
    assert [c["offset"] for c in fn.calls] == [None, 2, 4]


@pytest.mark.asyncio
async def test_paginate_stops_on_a_short_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """A page shorter than asked for is the last one, so nothing follows it."""
    monkeypatch.setattr(api_client, "_PAGE_LIMIT", 2)
    fn = _fake_list(3, count=None)
    result = await paginate(fn, client=None, limit=100)
    assert len(result) == 3
    assert len(fn.calls) == 2


@pytest.mark.asyncio
async def test_paginate_never_asks_for_more_than_the_limit() -> None:
    fn = _fake_list(50)
    await paginate(fn, client=None, limit=3)
    assert fn.calls[0]["limit"] == 3


@pytest.mark.asyncio
async def test_paginate_passes_filters_through() -> None:
    fn = _fake_list(0)
    await paginate(fn, client=None, limit=10, ordering="-datetime", plan="x")
    assert fn.calls[0]["ordering"] == "-datetime"
    assert fn.calls[0]["plan"] == "x"


# ---------- api_err ----------


def test_api_err_parses_json_bodies() -> None:
    exc = UnexpectedStatus(400, b'{"name": ["required"]}')
    assert api_err(exc) == {"error": True, "status": 400, "detail": {"name": ["required"]}}


def test_api_err_falls_back_to_text() -> None:
    exc = UnexpectedStatus(502, b"Bad Gateway")
    assert api_err(exc) == {"error": True, "status": 502, "detail": "Bad Gateway"}
