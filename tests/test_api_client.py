"""The typed-client bridge: per-request auth, pagination, error shaping."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
import respx
from wger_api_client.errors import UnexpectedStatus

from wger_mcp.api_client import api_err, build_api_client, paginate
from wger_mcp.config import Settings


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


def _fake_list(pages: list[tuple[int, list[Any]]]):
    """A stand-in for a generated ``*_list.asyncio``; pops one page per call."""
    calls: list[dict[str, Any]] = []

    async def fn(*, client: Any = None, **kwargs: Any):
        calls.append(kwargs)
        count, items = pages.pop(0)
        return SimpleNamespace(count=count, results=items)

    fn.calls = calls  # type: ignore[attr-defined]
    return fn


@pytest.mark.asyncio
async def test_paginate_single_page() -> None:
    fn = _fake_list([(2, [_item(1), _item(2)])])
    result = await paginate(fn, client=None, limit=10)
    assert result == [{"id": 1}, {"id": 2}]
    assert len(fn.calls) == 1


@pytest.mark.asyncio
async def test_paginate_follows_offsets_up_to_limit() -> None:
    """A server page smaller than the requested limit triggers offset requests."""
    fn = _fake_list([(5, [_item(1), _item(2)]), (5, [_item(3), _item(4)])])
    result = await paginate(fn, client=None, limit=4)
    assert [r["id"] for r in result] == [1, 2, 3, 4]
    assert fn.calls[1]["offset"] == 2


@pytest.mark.asyncio
async def test_paginate_stops_at_count() -> None:
    """count says there is nothing more, so no request is wasted on it."""
    fn = _fake_list([(2, [_item(1), _item(2)])])
    result = await paginate(fn, client=None, limit=100)
    assert len(result) == 2
    assert len(fn.calls) == 1


@pytest.mark.asyncio
async def test_paginate_passes_filters_through() -> None:
    fn = _fake_list([(0, [])])
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
