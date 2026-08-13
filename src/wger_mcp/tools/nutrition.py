"""Nutrition plan / meal / diary tools, via the generated ``wger_api_client``.

Resource ids stay opaque strings at the tool boundary (ADR 0002); they are
parsed into the client's id types internally.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Annotated, Any

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from wger_api_client import models as api_models
from wger_api_client.api.ingredient import ingredient_retrieve
from wger_api_client.api.meal import meal_create, meal_retrieve
from wger_api_client.api.mealitem import mealitem_create
from wger_api_client.api.nutritiondiary import (
    nutritiondiary_create,
    nutritiondiary_destroy,
    nutritiondiary_list,
    nutritiondiary_partial_update,
)
from wger_api_client.api.nutritionplan import (
    nutritionplan_create,
    nutritionplan_destroy,
    nutritionplan_list,
    nutritionplan_partial_update,
    nutritionplan_retrieve,
)
from wger_api_client.api.userprofile import userprofile_partial_update, userprofile_retrieve
from wger_api_client.api.weightentry import weightentry_list
from wger_api_client.client import AuthenticatedClient
from wger_api_client.errors import UnexpectedStatus
from wger_api_client.types import UNSET

from ..api_client import paginate
from ..config import Settings
from .common import (
    api_err,
    api_list_tool,
    api_tool,
    as_decimal,
    as_int,
    as_uuid,
    at_noon,
    bad_request,
    opt,
    require_fields,
)

_INGREDIENT_CONCURRENCY = 8

# Model field limits, so the caller is told before the server refuses
PLAN_DESCRIPTION_MAX = 80
MEAL_NAME_MAX = 25


def register(mcp: FastMCP, api: AuthenticatedClient, settings: Settings) -> None:
    @mcp.tool()
    @api_list_tool
    async def list_nutrition_plans(
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
    ) -> list[dict[str, Any]]:
        """List your nutrition plans."""
        return await paginate(nutritionplan_list.asyncio, client=api, limit=limit)

    @mcp.tool()
    @api_tool
    async def get_nutrition_plan(plan_id: str) -> dict[str, Any]:
        """Fetch one nutrition plan with meals and items."""
        plan = await nutritionplan_retrieve.asyncio(id=as_uuid(plan_id, "plan_id"), client=api)
        return plan.to_dict()

    @mcp.tool()
    @api_tool
    async def create_nutrition_plan(
        description: Annotated[str, Field(max_length=PLAN_DESCRIPTION_MAX)] = "",
        only_logging: bool = False,
        goal_energy: Annotated[float | None, Field(ge=0, le=20000)] = None,
        goal_protein: Annotated[float | None, Field(ge=0, le=2000)] = None,
        goal_carbohydrates: Annotated[float | None, Field(ge=0, le=2000)] = None,
        goal_fat: Annotated[float | None, Field(ge=0, le=2000)] = None,
    ) -> dict[str, Any]:
        """Create a nutrition plan. Returns the new plan including its id."""
        body = api_models.NutritionPlanRequest(
            description=description,
            only_logging=only_logging,
            goal_energy=int(goal_energy) if goal_energy is not None else UNSET,
            goal_protein=int(goal_protein) if goal_protein is not None else UNSET,
            goal_carbohydrates=(
                int(goal_carbohydrates) if goal_carbohydrates is not None else UNSET
            ),
            goal_fat=int(goal_fat) if goal_fat is not None else UNSET,
        )
        created = await nutritionplan_create.asyncio(client=api, body=body)
        return created.to_dict()

    @mcp.tool()
    @api_tool
    async def update_nutrition_plan(
        plan_id: str,
        description: Annotated[str | None, Field(max_length=PLAN_DESCRIPTION_MAX)] = None,
        only_logging: bool | None = None,
        goal_energy: Annotated[float | None, Field(ge=0, le=20000)] = None,
        goal_protein: Annotated[float | None, Field(ge=0, le=2000)] = None,
        goal_carbohydrates: Annotated[float | None, Field(ge=0, le=2000)] = None,
        goal_fat: Annotated[float | None, Field(ge=0, le=2000)] = None,
    ) -> dict[str, Any]:
        """Patch a nutrition plan. Only provided fields are sent."""
        body = api_models.PatchedNutritionPlanRequest(
            description=opt(description),
            only_logging=opt(only_logging),
            goal_energy=int(goal_energy) if goal_energy is not None else UNSET,
            goal_protein=int(goal_protein) if goal_protein is not None else UNSET,
            goal_carbohydrates=(
                int(goal_carbohydrates) if goal_carbohydrates is not None else UNSET
            ),
            goal_fat=int(goal_fat) if goal_fat is not None else UNSET,
        )
        require_fields(body)
        updated = await nutritionplan_partial_update.asyncio(
            id=as_uuid(plan_id, "plan_id"), client=api, body=body
        )
        return updated.to_dict()

    @mcp.tool()
    @api_tool
    async def delete_nutrition_plan(plan_id: str) -> dict[str, Any]:
        """Delete a nutrition plan (cascades to its meals and diary entries)."""
        await nutritionplan_destroy.asyncio_detailed(id=as_uuid(plan_id, "plan_id"), client=api)
        return {"deleted": True, "plan_id": plan_id}

    @mcp.tool()
    @api_tool
    async def create_meal(
        plan_id: str,
        name: Annotated[str, Field(min_length=1, max_length=MEAL_NAME_MAX)],
        time: str | None = None,
    ) -> dict[str, Any]:
        """Create a meal in a nutrition plan (e.g. Breakfast, Lunch).
        time is 'HH:MM' or 'HH:MM:SS'; omit for an unscheduled meal.
        wger orders meals by time itself."""
        body = api_models.MealRequest(
            plan=as_uuid(plan_id, "plan_id"),
            name=name,
            time=opt(time),
        )
        meal = await meal_create.asyncio(client=api, body=body)
        return meal.to_dict()

    # Recipes — wger has no dedicated Recipe entity, so a "recipe" is modelled
    # as a Meal inside a NutritionPlan, with its MealItems acting as the
    # recipe's ingredients. create_recipe / get_recipe / add_ingredient_to_recipe
    # are semantic aliases over the meal + mealitem endpoints.

    @mcp.tool()
    @api_tool
    async def create_recipe(
        plan_id: str,
        name: Annotated[str, Field(min_length=1, max_length=MEAL_NAME_MAX)],
    ) -> dict[str, Any]:
        """Create a recipe (a named Meal inside a plan). Wger has no separate
        Recipe model, so this is a thin alias over POST /meal/ — the returned
        id is a meal_id, usable wherever meal_id is expected."""
        body = api_models.MealRequest(plan=as_uuid(plan_id, "plan_id"), name=name)
        meal = await meal_create.asyncio(client=api, body=body)
        return meal.to_dict()

    @mcp.tool()
    @api_tool
    async def get_recipe(recipe_id: str) -> dict[str, Any]:
        """Fetch a recipe (Meal) with its items. recipe_id = meal id."""
        meal = await meal_retrieve.asyncio(id=as_uuid(recipe_id, "recipe_id"), client=api)
        return meal.to_dict()

    @mcp.tool()
    @api_tool
    async def add_ingredient_to_recipe(
        recipe_id: str,
        ingredient_id: str,
        amount_g: Annotated[float, Field(gt=0, le=10000)],
        weight_unit_id: str | None = None,
    ) -> dict[str, Any]:
        """Add an ingredient to a recipe (POST /mealitem/). amount_g is in
        grams unless weight_unit_id is supplied (custom unit)."""
        body = api_models.MealItemRequest(
            meal=as_uuid(recipe_id, "recipe_id"),
            ingredient=as_int(ingredient_id, "ingredient_id"),
            amount=as_decimal(amount_g),
            weight_unit=(
                as_int(weight_unit_id, "weight_unit_id") if weight_unit_id is not None else UNSET
            ),
        )
        item = await mealitem_create.asyncio(client=api, body=body)
        return item.to_dict()

    # Note: wger's REST /ingredient/ endpoint is read-only (ReadOnlyModelViewSet).
    # Custom-ingredient submission previously went through wger's Django web form
    # with username/password session auth; that path was removed when the server
    # moved to the multi-user SSO model (no per-user password). See
    # docs/adr/0001-multi-user-auth-via-oidc-token-exchange.md.

    @mcp.tool()
    @api_tool
    async def log_ingredient(
        plan_id: str,
        ingredient_id: str,
        amount_g: Annotated[float, Field(gt=0, le=10000)],
        when: date | datetime | None = None,
        meal_id: str | None = None,
    ) -> dict[str, Any]:
        """Log eaten food against a plan (logitem).

        ``when`` accepts either a full timestamp or a bare date:

        - ``"2026-07-21T07:30:00+02:00"`` — logged at exactly that instant, the
          offset preserved. Use this to record when a meal was actually eaten.
        - ``"2026-07-21"`` — a date with no time, anchored at 12:00 local.
        - omitted — wger timestamps the entry with the current time.

        ``meal_id`` optionally attributes the entry to a specific meal of the
        plan; omit it for a standalone diary entry.
        """
        body = api_models.LogItemRequest(
            plan=as_uuid(plan_id, "plan_id"),
            ingredient=as_int(ingredient_id, "ingredient_id"),
            amount=as_decimal(amount_g),
            datetime_=opt(at_noon(when)),
            meal=as_uuid(meal_id, "meal_id") if meal_id is not None else UNSET,
        )
        entry = await nutritiondiary_create.asyncio(client=api, body=body)
        return entry.to_dict()

    @mcp.tool()
    @api_tool
    async def update_log_item(
        log_item_id: str,
        amount_g: Annotated[float | None, Field(gt=0, le=10000)] = None,
        when: date | datetime | None = None,
        ingredient_id: str | None = None,
        meal_id: str | None = None,
    ) -> dict[str, Any]:
        """Patch an existing nutrition-diary entry.

        Use this to correct an entry's time or amount in place. ``when`` takes
        the same forms as in ``log_ingredient``; only the fields you pass are
        changed.
        """
        body = api_models.PatchedLogItemRequest(
            amount=as_decimal(amount_g) if amount_g is not None else UNSET,
            datetime_=opt(at_noon(when)),
            ingredient=(
                as_int(ingredient_id, "ingredient_id") if ingredient_id is not None else UNSET
            ),
            meal=as_uuid(meal_id, "meal_id") if meal_id is not None else UNSET,
        )
        require_fields(body)
        updated = await nutritiondiary_partial_update.asyncio(
            id=as_uuid(log_item_id, "log_item_id"), client=api, body=body
        )
        return updated.to_dict()

    @mcp.tool()
    @api_list_tool
    async def list_log_items(
        when: date | None = None,
        plan_id: str | None = None,
        limit: Annotated[int, Field(ge=1, le=500)] = 200,
    ) -> list[dict[str, Any]]:
        """List nutrition-diary log items. Defaults to today; pass when=None
        with plan_id to scope by plan only."""
        filters: dict[str, Any] = {"ordering": "-datetime"}
        if when is not None:
            filters["datetime_date"] = when
        if plan_id is not None:
            try:
                filters["plan"] = as_uuid(plan_id, "plan_id")
            except ValueError as exc:
                return [bad_request(str(exc))]
        if when is None and plan_id is None:
            filters["datetime_date"] = date.today()
        return await paginate(nutritiondiary_list.asyncio, client=api, limit=limit, **filters)

    @mcp.tool()
    @api_tool
    async def delete_log_item(log_item_id: str) -> dict[str, Any]:
        """Delete a nutrition-diary log item (a logged ingredient entry)."""
        await nutritiondiary_destroy.asyncio_detailed(
            id=as_uuid(log_item_id, "log_item_id"), client=api
        )
        return {"deleted": True, "log_item_id": log_item_id}

    @mcp.tool()
    @api_tool
    async def calculate_daily_calories(
        weight_kg: Annotated[float | None, Field(gt=20, le=400)] = None,
        height_cm: Annotated[float | None, Field(gt=80, le=260)] = None,
        age: Annotated[int | None, Field(ge=10, le=100)] = None,
        sex: Annotated[str | None, Field(pattern=r"^(male|female)$")] = None,
        activity_level: str = "moderate",
        goal: str = "maintain",
        protein_g_per_kg: Annotated[float, Field(ge=0.8, le=3.5)] = 1.8,
        fat_pct_of_kcal: Annotated[float, Field(ge=15, le=45)] = 25.0,
        apply_to_profile: bool = False,
    ) -> dict[str, Any]:
        """Compute daily kcal target and macro split.

        Uses the Mifflin-St Jeor BMR formula x activity multiplier x goal
        adjustment. Macro split: protein from g/kg bodyweight, fat from % of
        target kcal, carbs from the remainder.

        Any of weight_kg / height_cm / age / sex left as None are auto-filled:
        height/age/sex from /userprofile/ (gender "1"=male, "2"=female),
        weight from the latest /weightentry/. If apply_to_profile=True, the
        resulting target_kcal is written into userprofile.calories.

        activity_level: sedentary (1.2), light (1.375), moderate (1.55),
        active (1.725), very_active (1.9).
        goal: cut (-500 kcal), maintain (0), bulk (+300 kcal).
        """
        activity_multipliers = {
            "sedentary": 1.2,
            "light": 1.375,
            "moderate": 1.55,
            "active": 1.725,
            "very_active": 1.9,
        }
        goal_deltas = {"cut": -500.0, "maintain": 0.0, "bulk": 300.0}
        if activity_level not in activity_multipliers:
            return bad_request(f"activity_level must be one of {sorted(activity_multipliers)}")
        if goal not in goal_deltas:
            return bad_request(f"goal must be one of {sorted(goal_deltas)}")

        source: dict[str, str] = {}
        for key, val in (
            ("weight_kg", weight_kg),
            ("height_cm", height_cm),
            ("age", age),
            ("sex", sex),
        ):
            if val is not None:
                source[key] = "argument"

        need_profile = any(v is None for v in (height_cm, age, sex))
        need_weight = weight_kg is None
        if need_profile or need_weight:
            try:
                profile, latest_weights = await asyncio.gather(
                    userprofile_retrieve.asyncio(client=api) if need_profile else _none(),
                    weightentry_list.asyncio(client=api, limit=1, ordering="-date")
                    if need_weight
                    else _none(),
                )
            except (UnexpectedStatus, httpx.HTTPError) as exc:
                return api_err(exc)

            if profile is not None:
                if height_cm is None and isinstance(profile.height, int):
                    height_cm = float(profile.height)
                    source["height_cm"] = "userprofile"
                if age is None and isinstance(profile.age, int):
                    age = profile.age
                    source["age"] = "userprofile"
                if sex is None:
                    gender = profile.gender if isinstance(profile.gender, str) else None
                    if gender == "1":
                        sex = "male"
                        source["sex"] = "userprofile"
                    elif gender == "2":
                        sex = "female"
                        source["sex"] = "userprofile"
            if (
                weight_kg is None
                and latest_weights is not None
                and isinstance(latest_weights.results, list)
                and latest_weights.results
            ):
                try:
                    weight_kg = float(latest_weights.results[0].weight) or None
                    if weight_kg is not None:
                        source["weight_kg"] = "weightentry"
                except (TypeError, ValueError):
                    pass

        missing = [
            name
            for name, val in (
                ("weight_kg", weight_kg),
                ("height_cm", height_cm),
                ("age", age),
                ("sex", sex),
            )
            if val is None
        ]
        if missing:
            return bad_request(
                "missing required fields (not found in wger profile / weight history): "
                + ", ".join(missing)
            )

        # Mifflin-St Jeor
        base = 10 * weight_kg + 6.25 * height_cm - 5 * age
        bmr = base + (5 if sex == "male" else -161)
        tdee = bmr * activity_multipliers[activity_level]
        target = tdee + goal_deltas[goal]

        protein_g = protein_g_per_kg * weight_kg
        fat_g = (fat_pct_of_kcal / 100.0) * target / 9.0
        carbs_kcal = target - (protein_g * 4 + fat_g * 9)
        carbs_g = max(carbs_kcal / 4.0, 0.0)

        target_kcal = round(target, 0)
        result: dict[str, Any] = {
            "bmr_kcal": round(bmr, 0),
            "tdee_kcal": round(tdee, 0),
            "target_kcal": target_kcal,
            "macros": {
                "protein_g": round(protein_g, 1),
                "fat_g": round(fat_g, 1),
                "carbs_g": round(carbs_g, 1),
            },
            "inputs": {
                "weight_kg": weight_kg,
                "height_cm": height_cm,
                "age": age,
                "sex": sex,
                "activity_level": activity_level,
                "goal": goal,
                "protein_g_per_kg": protein_g_per_kg,
                "fat_pct_of_kcal": fat_pct_of_kcal,
            },
            "input_sources": source,
            "formula": "Mifflin-St Jeor",
        }

        if apply_to_profile:
            try:
                patched = await userprofile_partial_update.asyncio(
                    client=api,
                    body=api_models.PatchedUserprofileRequest(calories=int(target_kcal)),
                )
                result["profile_update"] = {"applied": True, "calories": patched.calories}
            except (UnexpectedStatus, httpx.HTTPError) as exc:
                result["profile_update"] = {"applied": False, "error": api_err(exc)}

        return result

    @mcp.tool()
    @api_tool
    async def update_user_profile(
        calories: Annotated[int | None, Field(ge=800, le=10000)] = None,
        height_cm: Annotated[int | None, Field(gt=80, le=260)] = None,
        birthdate: date | None = None,
        gender: Annotated[str | None, Field(pattern=r"^(1|2)$")] = None,
        sleep_hours: Annotated[int | None, Field(ge=0, le=24)] = None,
        work_hours: Annotated[int | None, Field(ge=0, le=24)] = None,
        work_intensity: Annotated[str | None, Field(pattern=r"^[123]$")] = None,
        sport_hours: Annotated[int | None, Field(ge=0, le=24)] = None,
        sport_intensity: Annotated[str | None, Field(pattern=r"^[123]$")] = None,
        freetime_hours: Annotated[int | None, Field(ge=0, le=24)] = None,
        freetime_intensity: Annotated[str | None, Field(pattern=r"^[123]$")] = None,
    ) -> dict[str, Any]:
        """Update the wger user profile. gender: '1'=male, '2'=female.
        intensity fields: '1'=low, '2'=moderate, '3'=high."""
        # gender/intensity are Literal types in the client; the Field patterns
        # above already restrict the values, so the strings pass through as-is
        body = api_models.PatchedUserprofileRequest(
            calories=opt(calories),
            height=opt(height_cm),
            birthdate=opt(birthdate),
            gender=opt(gender),
            sleep_hours=opt(sleep_hours),
            work_hours=opt(work_hours),
            work_intensity=opt(work_intensity),
            sport_hours=opt(sport_hours),
            sport_intensity=opt(sport_intensity),
            freetime_hours=opt(freetime_hours),
            freetime_intensity=opt(freetime_intensity),
        )
        require_fields(body)
        updated = await userprofile_partial_update.asyncio(client=api, body=body)
        return updated.to_dict()

    @mcp.tool()
    @api_tool
    async def nutrition_summary(
        when: date | None = None,
        plan_id: str | None = None,
    ) -> dict[str, Any]:
        """Sum kcal/protein/carbs/fat from diary entries for a date. Per entry,
        fetches the ingredient's macros (per 100 g) and scales by amount_g."""
        target = when or date.today()
        filters: dict[str, Any] = {"datetime_date": target}
        if plan_id is not None:
            try:
                filters["plan"] = as_uuid(plan_id, "plan_id")
            except ValueError as exc:
                return bad_request(str(exc))
        entries = await paginate(nutritiondiary_list.asyncio, client=api, limit=500, **filters)

        # Fan out distinct ingredient fetches concurrently.
        ing_ids: set[int] = set()
        for entry in entries:
            ing_id = entry.get("ingredient")
            if ing_id and float(entry.get("amount") or 0) > 0:
                ing_ids.add(ing_id)

        sem = asyncio.Semaphore(_INGREDIENT_CONCURRENCY)

        async def _fetch(iid: int) -> tuple[int, dict[str, Any]]:
            async with sem:
                try:
                    ing = await ingredient_retrieve.asyncio(id=iid, client=api)
                    return iid, ing.to_dict()
                except (UnexpectedStatus, httpx.HTTPError) as exc:
                    return iid, {"_err": api_err(exc)}

        cache: dict[int, dict[str, Any]] = dict(await asyncio.gather(*[_fetch(i) for i in ing_ids]))

        totals = {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
        items: list[dict[str, Any]] = []
        for entry in entries:
            ing_id = entry.get("ingredient")
            amount = float(entry.get("amount") or 0)
            if not ing_id or amount <= 0:
                continue
            ing = cache.get(ing_id) or {}
            if "_err" in ing:
                items.append(
                    {
                        "entry_id": entry.get("id"),
                        "ingredient_id": ing_id,
                        "error": ing["_err"],
                    }
                )
                continue
            factor = amount / 100.0
            kcal = float(ing.get("energy") or 0) * factor
            prot = float(ing.get("protein") or 0) * factor
            carb = float(ing.get("carbohydrates") or 0) * factor
            fat = float(ing.get("fat") or 0) * factor
            totals["kcal"] += kcal
            totals["protein_g"] += prot
            totals["carbs_g"] += carb
            totals["fat_g"] += fat
            items.append(
                {
                    "entry_id": entry.get("id"),
                    "ingredient_id": ing_id,
                    "ingredient_name": ing.get("name"),
                    "amount_g": amount,
                    "kcal": round(kcal, 1),
                    "protein_g": round(prot, 1),
                    "carbs_g": round(carb, 1),
                    "fat_g": round(fat, 1),
                }
            )
        return {
            "date": target.isoformat(),
            "totals": {k: round(v, 1) for k, v in totals.items()},
            "items": items,
        }


async def _none() -> None:
    """Placeholder coroutine for optional branches of asyncio.gather."""
    return None
