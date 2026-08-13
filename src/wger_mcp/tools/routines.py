"""Routine / day / slot / slot-entry tools (the training-plan tree), via the
generated ``wger_api_client``. Resource ids stay opaque strings at the tool
boundary (ADR 0002)."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Annotated, Any, NamedTuple

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from wger_api_client import models as api_models
from wger_api_client.api.day import (
    day_create,
    day_destroy,
    day_list,
    day_partial_update,
    day_retrieve,
)
from wger_api_client.api.max_repetitions_config import (
    max_repetitions_config_create,
    max_repetitions_config_destroy,
    max_repetitions_config_list,
    max_repetitions_config_partial_update,
)
from wger_api_client.api.max_rest_config import (
    max_rest_config_create,
    max_rest_config_destroy,
    max_rest_config_list,
    max_rest_config_partial_update,
)
from wger_api_client.api.max_rir_config import (
    max_rir_config_create,
    max_rir_config_destroy,
    max_rir_config_list,
    max_rir_config_partial_update,
)
from wger_api_client.api.max_sets_config import (
    max_sets_config_create,
    max_sets_config_destroy,
    max_sets_config_list,
    max_sets_config_partial_update,
)
from wger_api_client.api.max_weight_config import (
    max_weight_config_create,
    max_weight_config_destroy,
    max_weight_config_list,
    max_weight_config_partial_update,
)
from wger_api_client.api.repetitions_config import (
    repetitions_config_create,
    repetitions_config_destroy,
    repetitions_config_list,
    repetitions_config_partial_update,
)
from wger_api_client.api.rest_config import (
    rest_config_create,
    rest_config_destroy,
    rest_config_list,
    rest_config_partial_update,
)
from wger_api_client.api.rir_config import (
    rir_config_create,
    rir_config_destroy,
    rir_config_list,
    rir_config_partial_update,
)
from wger_api_client.api.routine import (
    routine_create,
    routine_destroy,
    routine_list,
    routine_partial_update,
    routine_retrieve,
)
from wger_api_client.api.sets_config import (
    sets_config_create,
    sets_config_destroy,
    sets_config_list,
    sets_config_partial_update,
)
from wger_api_client.api.slot import (
    slot_create,
    slot_destroy,
    slot_list,
    slot_partial_update,
)
from wger_api_client.api.slot_entry import (
    slot_entry_create,
    slot_entry_destroy,
    slot_entry_list,
    slot_entry_partial_update,
    slot_entry_retrieve,
)
from wger_api_client.api.weight_config import (
    weight_config_create,
    weight_config_destroy,
    weight_config_list,
    weight_config_partial_update,
)
from wger_api_client.client import AuthenticatedClient
from wger_api_client.errors import UnexpectedStatus
from wger_api_client.models.day_type_enum import DAY_TYPE_ENUM_VALUES
from wger_api_client.models.operation_enum import OPERATION_ENUM_VALUES
from wger_api_client.models.step_enum import STEP_ENUM_VALUES
from wger_api_client.types import UNSET

from ..api_client import paginate
from ..config import Settings
from .common import (
    ToolInputError,
    api_err,
    api_list_tool,
    api_tool,
    as_decimal,
    as_int,
    bad_request,
    opt,
    require_fields,
)


class _ConfigApi(NamedTuple):
    list_mod: Any
    create_mod: Any
    update_mod: Any
    destroy_mod: Any
    request: type
    patched: type
    int_value: bool


# Per-iteration config endpoints. Each kind lives on its own resource linked
# by slot_entry; the entry itself only stores the exercise binding.
CONFIG_KINDS: dict[str, _ConfigApi] = {
    "sets": _ConfigApi(
        sets_config_list,
        sets_config_create,
        sets_config_partial_update,
        sets_config_destroy,
        api_models.SetNrConfigRequest,
        api_models.PatchedSetNrConfigRequest,
        True,
    ),
    "reps": _ConfigApi(
        repetitions_config_list,
        repetitions_config_create,
        repetitions_config_partial_update,
        repetitions_config_destroy,
        api_models.RepetitionsConfigRequest,
        api_models.PatchedRepetitionsConfigRequest,
        False,
    ),
    "weight": _ConfigApi(
        weight_config_list,
        weight_config_create,
        weight_config_partial_update,
        weight_config_destroy,
        api_models.WeightConfigRequest,
        api_models.PatchedWeightConfigRequest,
        False,
    ),
    "rir": _ConfigApi(
        rir_config_list,
        rir_config_create,
        rir_config_partial_update,
        rir_config_destroy,
        api_models.RiRConfigRequest,
        api_models.PatchedRiRConfigRequest,
        False,
    ),
    "rest": _ConfigApi(
        rest_config_list,
        rest_config_create,
        rest_config_partial_update,
        rest_config_destroy,
        api_models.RestConfigRequest,
        api_models.PatchedRestConfigRequest,
        True,
    ),
    "max_sets": _ConfigApi(
        max_sets_config_list,
        max_sets_config_create,
        max_sets_config_partial_update,
        max_sets_config_destroy,
        api_models.MaxSetNrConfigRequest,
        api_models.PatchedMaxSetNrConfigRequest,
        True,
    ),
    "max_reps": _ConfigApi(
        max_repetitions_config_list,
        max_repetitions_config_create,
        max_repetitions_config_partial_update,
        max_repetitions_config_destroy,
        api_models.MaxRepetitionsConfigRequest,
        api_models.PatchedMaxRepetitionsConfigRequest,
        False,
    ),
    "max_weight": _ConfigApi(
        max_weight_config_list,
        max_weight_config_create,
        max_weight_config_partial_update,
        max_weight_config_destroy,
        api_models.MaxWeightConfigRequest,
        api_models.PatchedMaxWeightConfigRequest,
        False,
    ),
    "max_rir": _ConfigApi(
        max_rir_config_list,
        max_rir_config_create,
        max_rir_config_partial_update,
        max_rir_config_destroy,
        api_models.MaxRiRConfigRequest,
        api_models.PatchedMaxRiRConfigRequest,
        False,
    ),
    "max_rest": _ConfigApi(
        max_rest_config_list,
        max_rest_config_create,
        max_rest_config_partial_update,
        max_rest_config_destroy,
        api_models.MaxRestConfigRequest,
        api_models.PatchedMaxRestConfigRequest,
        True,
    ),
}

DAY_TYPES = tuple(sorted(DAY_TYPE_ENUM_VALUES))
OPERATIONS = tuple(sorted(OPERATION_ENUM_VALUES))
STEPS = tuple(sorted(STEP_ENUM_VALUES))

# wger requires an end date on every routine; twelve weeks is a conventional
# training block.
DEFAULT_ROUTINE_WEEKS = 12

# Model field limits, so the caller is told before the server refuses
ROUTINE_NAME_MAX = 25
DAY_NAME_MAX = 20


def _config_value(cfg: _ConfigApi, kind: str, value: float) -> int | str:
    """The wire value for a config kind: whole numbers for sets and rest
    seconds, decimal strings for the rest."""
    if not cfg.int_value:
        return as_decimal(value)
    if value != int(value):
        raise ToolInputError(f"{kind} must be a whole number, got {value}")
    return int(value)


def _unknown_kind(kind: str) -> dict[str, Any]:
    return bad_request(f"unknown kind '{kind}'; expected one of {sorted(CONFIG_KINDS)}")


def register(mcp: FastMCP, api: AuthenticatedClient, settings: Settings) -> None:
    @mcp.tool()
    @api_list_tool
    async def list_routines(
        limit: Annotated[int, Field(ge=1, le=200)] = 20,
    ) -> list[dict[str, Any]]:
        """List the user's training routines (new wger model)."""
        return await paginate(routine_list.asyncio, client=api, limit=limit)

    @mcp.tool()
    @api_tool
    async def get_routine(routine_id: str) -> dict[str, Any]:
        """Fetch a single routine with its day structure."""
        routine = await routine_retrieve.asyncio(id=as_int(routine_id, "routine_id"), client=api)
        return routine.to_dict()

    @mcp.tool()
    @api_list_tool
    async def list_routine_days(
        routine_id: str,
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
    ) -> list[dict[str, Any]]:
        """List training days of a routine."""
        return await paginate(
            day_list.asyncio,
            client=api,
            limit=limit,
            routine=as_int(routine_id, "routine_id"),
            ordering="order",
        )

    @mcp.tool()
    @api_tool
    async def get_routine_day(day_id: str) -> dict[str, Any]:
        """Fetch a single training day."""
        day = await day_retrieve.asyncio(id=as_int(day_id, "day_id"), client=api)
        return day.to_dict()

    @mcp.tool()
    @api_list_tool
    async def list_slots(
        day_id: str,
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
    ) -> list[dict[str, Any]]:
        """List slots in a training day."""
        return await paginate(
            slot_list.asyncio,
            client=api,
            limit=limit,
            day=as_int(day_id, "day_id"),
            ordering="order",
        )

    @mcp.tool()
    @api_list_tool
    async def list_slot_entries(
        slot_id: str,
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
    ) -> list[dict[str, Any]]:
        """List exercise entries in a slot."""
        return await paginate(
            slot_entry_list.asyncio,
            client=api,
            limit=limit,
            slot=as_int(slot_id, "slot_id"),
            ordering="order",
        )

    @mcp.tool()
    @api_tool
    async def get_slot_entry(entry_id: str) -> dict[str, Any]:
        """Fetch a slot entry. Note: per-set sets/reps/weight/rir/rest are stored
        on separate *-config endpoints linked by slot_entry, not on the entry
        itself. Use list_slot_entry_configs to read them."""
        entry = await slot_entry_retrieve.asyncio(id=as_int(entry_id, "entry_id"), client=api)
        return entry.to_dict()

    @mcp.tool()
    @api_tool
    async def list_slot_entry_configs(
        slot_entry_id: str,
        kinds: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch per-iteration configs for a slot entry. kinds filters which
        ones to read (e.g. ['sets','reps','weight']); default = all 10."""
        try:
            entry_id = as_int(slot_entry_id, "slot_entry_id")
        except ValueError as exc:
            return bad_request(str(exc))
        targets = kinds or list(CONFIG_KINDS)

        async def _fetch(kind: str) -> tuple[str, Any]:
            cfg = CONFIG_KINDS.get(kind)
            if cfg is None:
                return kind, bad_request(f"unknown kind '{kind}'")
            try:
                return kind, await paginate(
                    cfg.list_mod.asyncio,
                    client=api,
                    limit=200,
                    slot_entry=entry_id,
                    ordering="iteration",
                )
            except (UnexpectedStatus, httpx.HTTPError) as exc:
                return kind, api_err(exc)

        results = await asyncio.gather(*[_fetch(k) for k in targets])
        out: dict[str, Any] = {"slot_entry_id": slot_entry_id}
        for kind, value in results:
            out[kind] = value
        return out

    @mcp.tool()
    @api_tool
    async def create_routine(
        name: Annotated[str, Field(min_length=1, max_length=ROUTINE_NAME_MAX)],
        description: str = "",
        start: date | None = None,
        end: date | None = None,
        fit_in_week: bool = False,
    ) -> dict[str, Any]:
        """Create a training routine.

        Start defaults to today. wger requires an end date, so one is derived
        from the start when not given (12 weeks).
        """
        start_date = start or date.today()
        end_date = end or start_date + timedelta(weeks=DEFAULT_ROUTINE_WEEKS)
        if end_date <= start_date:
            return bad_request("end must be after start")
        body = api_models.RoutineRequest(
            start=start_date,
            end=end_date,
            name=name,
            description=description,
            fit_in_week=fit_in_week,
        )
        created = await routine_create.asyncio(client=api, body=body)
        return created.to_dict()

    @mcp.tool()
    @api_tool
    async def update_routine(
        routine_id: str,
        name: Annotated[str | None, Field(max_length=ROUTINE_NAME_MAX)] = None,
        description: str | None = None,
        start: date | None = None,
        end: date | None = None,
        fit_in_week: bool | None = None,
    ) -> dict[str, Any]:
        """Patch a routine. Only provided fields are sent."""
        body = api_models.PatchedRoutineRequest(
            name=opt(name),
            description=opt(description),
            start=opt(start),
            end=opt(end),
            fit_in_week=opt(fit_in_week),
        )
        require_fields(body)
        updated = await routine_partial_update.asyncio(
            id=as_int(routine_id, "routine_id"), client=api, body=body
        )
        return updated.to_dict()

    @mcp.tool()
    @api_tool
    async def add_routine_day(
        routine_id: str,
        name: Annotated[str, Field(min_length=1, max_length=DAY_NAME_MAX)],
        order: Annotated[int, Field(ge=1, le=100)],
        description: str = "",
        is_rest: bool = False,
        day_type: str = "custom",
    ) -> dict[str, Any]:
        """Add a training day to a routine.

        day_type is one of: custom, enom, amrap, hiit, tabata, edt, rft, afap.
        Leave it alone for ordinary strength training.
        """
        if day_type not in DAY_TYPE_ENUM_VALUES:
            return bad_request(
                f"unknown day type '{day_type}'; expected one of {', '.join(DAY_TYPES)}"
            )
        body = api_models.DayRequest(
            routine=as_int(routine_id, "routine_id"),
            order=order,
            name=name,
            description=description,
            is_rest=is_rest,
            type_=day_type,
        )
        created = await day_create.asyncio(client=api, body=body)
        return created.to_dict()

    @mcp.tool()
    @api_tool
    async def add_slot_to_day(
        day_id: str,
        order: Annotated[int, Field(ge=1, le=100)],
        comment: str = "",
    ) -> dict[str, Any]:
        """Add an exercise slot (grouping) to a day. Sets/reps/weight live on
        the *-config records of its entries, not on the slot."""
        body = api_models.SlotRequest(day=as_int(day_id, "day_id"), order=order, comment=comment)
        created = await slot_create.asyncio(client=api, body=body)
        return created.to_dict()

    @mcp.tool()
    @api_tool
    async def update_routine_day(
        day_id: str,
        name: Annotated[str | None, Field(max_length=DAY_NAME_MAX)] = None,
        order: Annotated[int | None, Field(ge=1, le=100)] = None,
        description: str | None = None,
        is_rest: bool | None = None,
        day_type: str | None = None,
    ) -> dict[str, Any]:
        """Patch a training day. Only provided fields are sent."""
        if day_type is not None and day_type not in DAY_TYPE_ENUM_VALUES:
            return bad_request(
                f"unknown day type '{day_type}'; expected one of {', '.join(DAY_TYPES)}"
            )
        body = api_models.PatchedDayRequest(
            name=opt(name),
            order=opt(order),
            description=opt(description),
            is_rest=opt(is_rest),
            type_=opt(day_type),
        )
        require_fields(body)
        updated = await day_partial_update.asyncio(
            id=as_int(day_id, "day_id"), client=api, body=body
        )
        return updated.to_dict()

    @mcp.tool()
    @api_tool
    async def update_slot(
        slot_id: str,
        order: Annotated[int | None, Field(ge=1, le=100)] = None,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """Patch a slot."""
        body = api_models.PatchedSlotRequest(
            order=opt(order),
            comment=opt(comment),
        )
        require_fields(body)
        updated = await slot_partial_update.asyncio(
            id=as_int(slot_id, "slot_id"), client=api, body=body
        )
        return updated.to_dict()

    @mcp.tool()
    @api_tool
    async def update_slot_entry(
        slot_entry_id: str,
        exercise_id: str | None = None,
        order: Annotated[int | None, Field(ge=1, le=100)] = None,
        comment: str | None = None,
        repetition_unit: int | None = None,
        weight_unit: int | None = None,
    ) -> dict[str, Any]:
        """Patch a slot entry (the exercise binding)."""
        body = api_models.PatchedSlotEntryRequest(
            exercise=(as_int(exercise_id, "exercise_id") if exercise_id is not None else UNSET),
            order=opt(order),
            comment=opt(comment),
            repetition_unit=opt(repetition_unit),
            weight_unit=opt(weight_unit),
        )
        require_fields(body)
        updated = await slot_entry_partial_update.asyncio(
            id=as_int(slot_entry_id, "slot_entry_id"), client=api, body=body
        )
        return updated.to_dict()

    @mcp.tool()
    @api_tool
    async def update_slot_entry_config(
        kind: str,
        config_id: str,
        value: float | None = None,
        iteration: Annotated[int | None, Field(ge=1, le=1000)] = None,
        operation: str | None = None,
        step: str | None = None,
        repeat: bool | None = None,
    ) -> dict[str, Any]:
        """Patch an existing per-iteration config record.
        kind selects the endpoint (sets, reps, weight, rir, rest, max_*).
        Use this to bump weight when progressing."""
        cfg = CONFIG_KINDS.get(kind)
        if cfg is None:
            return _unknown_kind(kind)
        if operation is not None and operation not in OPERATION_ENUM_VALUES:
            return bad_request(f"operation must be one of {OPERATIONS}")
        if step is not None and step not in STEP_ENUM_VALUES:
            return bad_request(f"step must be one of {STEPS}")
        body = cfg.patched(
            value=_config_value(cfg, kind, value) if value is not None else UNSET,
            iteration=opt(iteration),
            operation=opt(operation),
            step=opt(step),
            repeat=opt(repeat),
        )
        require_fields(body)
        updated = await cfg.update_mod.asyncio(
            id=as_int(config_id, "config_id"), client=api, body=body
        )
        return updated.to_dict()

    @mcp.tool()
    @api_tool
    async def delete_slot_entry_config(kind: str, config_id: str) -> dict[str, Any]:
        """Delete a per-iteration config record."""
        cfg = CONFIG_KINDS.get(kind)
        if cfg is None:
            return _unknown_kind(kind)
        await cfg.destroy_mod.asyncio_detailed(id=as_int(config_id, "config_id"), client=api)
        return {"deleted": True, "kind": kind, "config_id": config_id}

    @mcp.tool()
    @api_tool
    async def delete_routine(routine_id: str) -> dict[str, Any]:
        """Delete a routine and its entire day/slot/entry tree."""
        await routine_destroy.asyncio_detailed(id=as_int(routine_id, "routine_id"), client=api)
        return {"deleted": True, "routine_id": routine_id}

    @mcp.tool()
    @api_tool
    async def delete_routine_day(day_id: str) -> dict[str, Any]:
        """Delete a training day (cascades to its slots and entries)."""
        await day_destroy.asyncio_detailed(id=as_int(day_id, "day_id"), client=api)
        return {"deleted": True, "day_id": day_id}

    @mcp.tool()
    @api_tool
    async def delete_slot(slot_id: str) -> dict[str, Any]:
        """Delete a slot (cascades to its entries and configs)."""
        await slot_destroy.asyncio_detailed(id=as_int(slot_id, "slot_id"), client=api)
        return {"deleted": True, "slot_id": slot_id}

    @mcp.tool()
    @api_tool
    async def delete_slot_entry(slot_entry_id: str) -> dict[str, Any]:
        """Delete a slot entry (the exercise binding) and its configs."""
        await slot_entry_destroy.asyncio_detailed(
            id=as_int(slot_entry_id, "slot_entry_id"), client=api
        )
        return {"deleted": True, "slot_entry_id": slot_entry_id}

    @mcp.tool()
    @api_tool
    async def attach_exercise_to_slot(
        slot_id: str,
        exercise_id: str,
        order: Annotated[int, Field(ge=1, le=100)] = 1,
        repetition_unit: int | None = None,
        weight_unit: int | None = None,
        comment: str = "",
    ) -> dict[str, Any]:
        """Attach an exercise to a slot. exercise_id is the numeric wger PK
        (same id used in log_set / exerciseinfo). Per-set reps/weight live on
        sets-config / repetitions-config / weight-config records, not here."""
        body = api_models.SlotEntryRequest(
            slot=as_int(slot_id, "slot_id"),
            exercise=as_int(exercise_id, "exercise_id"),
            order=order,
            comment=comment,
            repetition_unit=opt(repetition_unit),
            weight_unit=opt(weight_unit),
        )
        created = await slot_entry_create.asyncio(client=api, body=body)
        return created.to_dict()

    @mcp.tool()
    @api_tool
    async def set_slot_entry_config(
        slot_entry_id: str,
        kind: str,
        value: float,
        iteration: Annotated[int, Field(ge=1, le=1000)] = 1,
        operation: str = "r",
        step: str = "abs",
        repeat: bool = False,
    ) -> dict[str, Any]:
        """Create a per-iteration config record for a slot entry.
        kind: one of sets, reps, weight, rir, rest, max_sets, max_reps,
        max_weight, max_rir, max_rest. operation 'r' = replace, '+' = add,
        '-' = subtract. step 'abs', 'percent' or 'na'."""
        cfg = CONFIG_KINDS.get(kind)
        if cfg is None:
            return _unknown_kind(kind)
        if operation not in OPERATION_ENUM_VALUES:
            return bad_request(f"operation must be one of {OPERATIONS}")
        if step not in STEP_ENUM_VALUES:
            return bad_request(f"step must be one of {STEPS}")
        body = cfg.request(
            slot_entry=as_int(slot_entry_id, "slot_entry_id"),
            iteration=iteration,
            value=_config_value(cfg, kind, value),
            operation=operation,
            step=step,
            repeat=repeat,
        )
        created = await cfg.create_mod.asyncio(client=api, body=body)
        return created.to_dict()

    @mcp.tool()
    @api_tool
    async def add_exercise_with_sets(
        day_id: str,
        exercise_id: str,
        sets: Annotated[int, Field(ge=1, le=50)],
        reps: Annotated[int, Field(ge=1, le=1000)],
        weight_kg: Annotated[float, Field(ge=0, le=1000)],
        slot_order: Annotated[int, Field(ge=1, le=100)] = 1,
    ) -> dict[str, Any]:
        """High-level convenience: create slot + slot-entry + sets/reps/weight
        configs in one call. Returns the created ids. Partial failures are
        reported in the response."""
        # Parsed up front: the slot must not be created if a later id is bad
        day = as_int(day_id, "day_id")
        exercise = as_int(exercise_id, "exercise_id")
        values = [
            (kind, _config_value(CONFIG_KINDS[kind], kind, value))
            for kind, value in (("sets", sets), ("reps", reps), ("weight", weight_kg))
        ]

        result: dict[str, Any] = {}
        try:
            slot = await slot_create.asyncio(
                client=api, body=api_models.SlotRequest(day=day, order=slot_order)
            )
        except (UnexpectedStatus, httpx.HTTPError) as exc:
            return api_err(exc) | {"stage": "slot"}
        result["slot"] = slot.to_dict()

        try:
            entry = await slot_entry_create.asyncio(
                client=api,
                body=api_models.SlotEntryRequest(
                    slot=slot.id, exercise=exercise, order=1, comment=""
                ),
            )
        except (UnexpectedStatus, httpx.HTTPError) as exc:
            return result | api_err(exc) | {"stage": "slot-entry"}
        result["slot_entry"] = entry.to_dict()

        # The three configs only depend on the entry, so they go out together
        async def _config(kind: str, value: int | str) -> Any:
            cfg = CONFIG_KINDS[kind]
            return await cfg.create_mod.asyncio(
                client=api,
                body=cfg.request(
                    slot_entry=entry.id,
                    iteration=1,
                    value=value,
                    operation="r",
                    step="abs",
                    repeat=False,
                ),
            )

        created = await asyncio.gather(
            *[_config(kind, value) for kind, value in values], return_exceptions=True
        )
        failed = None
        for (kind, _), outcome in zip(values, created, strict=True):
            if isinstance(outcome, BaseException):
                failed = failed or (kind, outcome)
                continue
            result[f"{kind}_config"] = outcome.to_dict()
        if failed is not None:
            kind, exc = failed
            if not isinstance(exc, UnexpectedStatus | httpx.HTTPError):
                raise exc
            return result | api_err(exc) | {"stage": f"{kind}-config"}

        return result
