"""The shared tool helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from wger_api_client.types import UNSET

from wger_mcp.tools.common import (
    ToolInputError,
    as_decimal,
    as_int,
    as_uuid,
    at_noon,
    opt,
    require_fields,
)

# ---------- at_noon ----------


def test_none_stays_none() -> None:
    """Omitting the field lets wger apply its own timezone.now default."""
    assert at_noon(None) is None


def test_bare_date_is_anchored_at_noon() -> None:
    assert at_noon(date(2026, 7, 21)) == datetime(2026, 7, 21, 12, 0)


def test_datetime_offset_is_preserved() -> None:
    """The reporter's case in issue #5: an explicit offset survives verbatim."""
    tz = timezone(timedelta(hours=2))
    stamp = at_noon(datetime(2026, 7, 21, 7, 0, tzinfo=tz))
    assert stamp == datetime(2026, 7, 21, 7, 0, tzinfo=tz)


def test_naive_datetime_keeps_its_time() -> None:
    assert at_noon(datetime(2026, 7, 21, 7, 30)) == datetime(2026, 7, 21, 7, 30)


def test_datetime_checked_before_date() -> None:
    """datetime subclasses date, so a naive isinstance order would truncate."""
    assert at_noon(datetime(2026, 7, 21, 23, 45)) != datetime(2026, 7, 21, 12, 0)


# ---------- opt ----------


def test_only_none_becomes_unset() -> None:
    """0 and False are values the caller chose, not omissions."""
    assert opt(None) is UNSET
    assert opt(0) == 0
    assert opt(False) is False
    assert opt("") == ""


# ---------- ids and decimals ----------


def test_ids_are_parsed_or_refused() -> None:
    assert as_int("42", "log_id") == 42
    assert str(as_uuid("018f6f30-0000-7000-8000-000000000001", "plan_id")).startswith("018f6f30")
    with pytest.raises(ToolInputError, match="plan_id"):
        as_uuid("nope", "plan_id")
    with pytest.raises(ToolInputError, match="numeric id"):
        as_int("nope", "exercise_id")


def test_decimals_travel_without_trailing_zeros() -> None:
    assert as_decimal(82.5) == "82.5"
    assert as_decimal(90) == "90"


# ---------- require_fields ----------


def test_empty_patch_is_refused() -> None:
    class _Body:
        def __init__(self, data: dict) -> None:
            self._data = data

        def to_dict(self) -> dict:
            return self._data

    require_fields(_Body({"name": "x"}))
    with pytest.raises(ToolInputError, match="no fields to update"):
        require_fields(_Body({}))
