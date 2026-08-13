"""Shared helpers for tool modules."""

from __future__ import annotations

import functools
import json
from collections.abc import Awaitable, Callable
from datetime import date, datetime, time
from typing import Any, Protocol, TypeVar
from uuid import UUID

import httpx
from wger_api_client.errors import UnexpectedStatus
from wger_api_client.types import UNSET, Unset

T = TypeVar("T")

# A bare date has to land somewhere on the day wger stores as a timestamp;
# noon keeps it on the intended day in either direction of a timezone shift.
_BARE_DATE_TIME = time(12, 0)


class ToolInputError(Exception):
    """An argument wger cannot accept. Reported to the caller as a 400."""


def bad_request(detail: str) -> dict[str, Any]:
    """Shape a 400-style validation error as a tool-response dict."""
    return {"error": True, "status": 400, "detail": detail}


def api_err(exc: UnexpectedStatus | httpx.HTTPError) -> dict[str, Any]:
    """Shape an upstream failure as a tool-response dict."""
    if isinstance(exc, UnexpectedStatus):
        try:
            detail: Any = json.loads(exc.content)
        except ValueError:
            detail = exc.content.decode(errors="replace")
        return {"error": True, "status": exc.status_code, "detail": detail}
    return {"error": True, "status": 503, "detail": f"wger is unreachable: {exc}"}


def opt(value: T | None) -> T | Unset:
    """What the caller left out stays out of the request."""
    return UNSET if value is None else value


def as_uuid(value: str, field: str) -> UUID:
    """Parse an opaque id from the tool boundary into the UUID the API wants."""
    try:
        return UUID(value)
    except ValueError:
        raise ToolInputError(f"{field} must be a UUID, got {value!r}") from None


def as_int(value: str, field: str) -> int:
    """Parse an opaque id from the tool boundary into the int the API wants."""
    try:
        return int(value)
    except ValueError:
        raise ToolInputError(f"{field} must be a numeric id, got {value!r}") from None


def as_decimal(value: float) -> str:
    """Decimal fields travel as strings in the API."""
    return f"{value:g}"


def at_noon(when: date | datetime | None) -> datetime | None:
    """Anchor a bare date at :data:`_BARE_DATE_TIME`.

    A ``datetime`` passes through unchanged, offset included, and ``None``
    stays ``None`` so the caller can leave the field to wger. Note ``datetime``
    is a subclass of ``date``, so the subclass is checked first.
    """
    if when is None or isinstance(when, datetime):
        return when
    return datetime.combine(when, _BARE_DATE_TIME)


class _Body(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


def require_fields(body: _Body) -> None:
    """Refuse a patch that would send nothing."""
    if not body.to_dict():
        raise ToolInputError("no fields to update")


def api_tool(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Turn a rejected argument or an upstream failure into an error dict.

    Only :class:`ToolInputError` counts as an argument problem, so a parse
    error on the response is not mistaken for one.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except ToolInputError as exc:
            return bad_request(str(exc))
        except (UnexpectedStatus, httpx.HTTPError) as exc:
            return api_err(exc)

    return wrapper


def api_list_tool(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """:func:`api_tool` for tools whose result is a list."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except ToolInputError as exc:
            return [bad_request(str(exc))]
        except (UnexpectedStatus, httpx.HTTPError) as exc:
            return [api_err(exc)]

    return wrapper
