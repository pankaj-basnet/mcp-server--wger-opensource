"""Exercise / ingredient catalog tools (read-only lookups), via the generated
``wger_api_client``."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field
from wger_api_client.api.exercisecategory import exercisecategory_list
from wger_api_client.api.exerciseinfo import exerciseinfo_list, exerciseinfo_retrieve
from wger_api_client.api.ingredient import ingredient_list, ingredient_retrieve
from wger_api_client.api.ingredientinfo import ingredientinfo_list
from wger_api_client.api.muscle import muscle_list
from wger_api_client.client import AuthenticatedClient
from wger_api_client.errors import UnexpectedStatus
from wger_api_client.types import UNSET

from ..api_client import api_err, paginate
from ..config import Settings
from .common import bad_request

_NUTRISCORE = r"^[A-Ea-e]$"


def _shape_images(images: Any) -> list[dict[str, Any]]:
    """Flatten an exercise's images, surfacing the 2.6 small/medium thumbnails."""
    out: list[dict[str, Any]] = []
    for img in images or []:
        if not isinstance(img, dict):
            continue
        out.append(
            {
                "image": img.get("image"),
                "is_main": img.get("is_main"),
                "thumbnails": img.get("thumbnails"),
            }
        )
    return out


def _shape_ingredient(ing: dict[str, Any], *, with_code: bool = False) -> dict[str, Any]:
    out = {
        "id": ing.get("id"),
        "uuid": ing.get("uuid"),
        "name": ing.get("name"),
        "energy": ing.get("energy"),
        "protein": ing.get("protein"),
        "carbohydrates": ing.get("carbohydrates"),
        "fat": ing.get("fat"),
        "brand": ing.get("brand"),
    }
    if with_code:
        out["code"] = ing.get("code")
    return out


def register(mcp: FastMCP, api: AuthenticatedClient, settings: Settings) -> None:
    default_language = settings.default_language

    @mcp.tool()
    async def search_exercises(
        query: Annotated[str, Field(min_length=2)],
        language: Annotated[str | None, Field(pattern=r"^[a-z]{2}$")] = None,
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
    ) -> list[dict[str, Any]]:
        """Search the wger exercise database by name.

        ``language`` is an ISO 639-1 code ('en', 'pl', 'de', ...); it defaults to
        the server's ``DEFAULT_LANGUAGE``.
        """
        try:
            results = await paginate(
                exerciseinfo_list.asyncio,
                client=api,
                limit=limit,
                name_search=query,
                language_code=language or default_language,
            )
        except UnexpectedStatus as exc:
            return [api_err(exc)]
        q_lower = query.lower()
        shaped: list[dict[str, Any]] = []
        for ex in results:
            translations = [
                t for t in (ex.get("translations") or []) if isinstance(t, dict) and t.get("name")
            ]
            match = next(
                (t for t in translations if q_lower in (t.get("name") or "").lower()),
                translations[0] if translations else None,
            )
            shaped.append(
                {
                    "id": ex.get("id"),
                    "uuid": ex.get("uuid"),
                    "name": (match or {}).get("name"),
                    "category": (ex.get("category") or {}).get("name"),
                    "equipment": [e.get("name") for e in (ex.get("equipment") or [])],
                    "images": _shape_images(ex.get("images")),
                    "translations": [
                        {"language": t.get("language"), "name": t.get("name")} for t in translations
                    ],
                }
            )
        return shaped

    @mcp.tool()
    async def get_exercise(exercise_id: str) -> dict[str, Any]:
        """Fetch full exercise detail (instructions, muscles, equipment, images).

        Since wger 2.6 each image also carries ``thumbnails`` with ``small`` and
        ``medium`` URLs (returned verbatim in the raw detail)."""
        try:
            exercise = await exerciseinfo_retrieve.asyncio(id=int(exercise_id), client=api)
            return exercise.to_dict()
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError:
            return bad_request(f"exercise_id must be a numeric id, got {exercise_id!r}")

    @mcp.tool()
    async def search_ingredients(
        query: Annotated[str, Field(min_length=2)],
        language: Annotated[str | None, Field(pattern=r"^[a-z]{2}$")] = None,
        limit: Annotated[int, Field(ge=1, le=50)] = 10,
        nutriscore: Annotated[str | None, Field(pattern=_NUTRISCORE)] = None,
        nutriscore_better_than: Annotated[str | None, Field(pattern=_NUTRISCORE)] = None,
        nutriscore_at_worst: Annotated[str | None, Field(pattern=_NUTRISCORE)] = None,
    ) -> list[dict[str, Any]]:
        """Search wger's ingredient database (foods with macros).

        Nutri-Score grades run A (best) → E (worst). Optional filters (wger 2.6):
        ``nutriscore`` exact grade; ``nutriscore_better_than='C'`` returns A/B
        only (strictly better); ``nutriscore_at_worst='C'`` returns A/B/C
        (C or better). Pass at most one of the three.

        ``language`` is an ISO 639-1 code; it defaults to the server's
        ``DEFAULT_LANGUAGE``.
        """
        chosen = [v for v in (nutriscore, nutriscore_better_than, nutriscore_at_worst) if v]
        if len(chosen) > 1:
            return [bad_request("pass at most one nutriscore filter")]
        try:
            results = await paginate(
                ingredientinfo_list.asyncio,
                client=api,
                limit=limit,
                name_search=query,
                language_code=language or default_language,
                nutriscore=nutriscore.upper() if nutriscore else UNSET,
                nutriscore_lt=(nutriscore_better_than.upper() if nutriscore_better_than else UNSET),
                nutriscore_lte=nutriscore_at_worst.upper() if nutriscore_at_worst else UNSET,
            )
        except UnexpectedStatus as exc:
            return [api_err(exc)]
        return [_shape_ingredient(ing) for ing in results]

    @mcp.tool()
    async def get_ingredient(ingredient_id: str) -> dict[str, Any]:
        """Fetch full ingredient detail (macros per 100 g, brand, etc.)."""
        try:
            ingredient = await ingredient_retrieve.asyncio(id=int(ingredient_id), client=api)
            return ingredient.to_dict()
        except UnexpectedStatus as exc:
            return api_err(exc)
        except ValueError:
            return bad_request(f"ingredient_id must be a numeric id, got {ingredient_id!r}")

    @mcp.tool()
    async def search_ingredient_by_barcode(
        barcode: Annotated[str, Field(min_length=4, max_length=32)],
        limit: Annotated[int, Field(ge=1, le=20)] = 5,
    ) -> list[dict[str, Any]]:
        """Look up ingredients by EAN/UPC barcode (exact match on the wger
        `code` field). Typically returns 0 or 1 result — much more precise
        than name search."""
        try:
            results = await paginate(ingredient_list.asyncio, client=api, limit=limit, code=barcode)
        except UnexpectedStatus as exc:
            return [api_err(exc)]
        return [_shape_ingredient(ing, with_code=True) for ing in results]

    @mcp.tool()
    async def list_categories(
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
    ) -> list[dict[str, Any]]:
        """List exercise categories (Chest, Back, …)."""
        try:
            return await paginate(exercisecategory_list.asyncio, client=api, limit=limit)
        except UnexpectedStatus as exc:
            return [api_err(exc)]

    @mcp.tool()
    async def list_muscles(
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
    ) -> list[dict[str, Any]]:
        """List muscles."""
        try:
            return await paginate(muscle_list.asyncio, client=api, limit=limit)
        except UnexpectedStatus as exc:
            return [api_err(exc)]

    @mcp.tool()
    async def search_exercises_by_filter(
        equipment_id: str | None = None,
        muscle_id: str | None = None,
        category_id: str | None = None,
        language: Annotated[str | None, Field(pattern=r"^[a-z]{2}$")] = None,
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
    ) -> list[dict[str, Any]]:
        """Find exercises by structured filters (e.g. Dumbbell + Back).

        ``language`` is an ISO 639-1 code; it defaults to the server's
        ``DEFAULT_LANGUAGE``.
        """
        try:
            results = await paginate(
                exerciseinfo_list.asyncio,
                client=api,
                limit=limit,
                language_code=language or default_language,
                equipment=int(equipment_id) if equipment_id is not None else UNSET,
                muscles=int(muscle_id) if muscle_id is not None else UNSET,
                category=int(category_id) if category_id is not None else UNSET,
            )
        except UnexpectedStatus as exc:
            return [api_err(exc)]
        except ValueError:
            return [bad_request("equipment_id/muscle_id/category_id must be numeric ids")]
        shaped: list[dict[str, Any]] = []
        for ex in results:
            translations = [
                t for t in (ex.get("translations") or []) if isinstance(t, dict) and t.get("name")
            ]
            shaped.append(
                {
                    "id": ex.get("id"),
                    "uuid": ex.get("uuid"),
                    "name": (translations[0].get("name") if translations else None),
                    "category": (ex.get("category") or {}).get("name"),
                    "equipment": [e.get("name") for e in (ex.get("equipment") or [])],
                    "muscles": [m.get("name") for m in (ex.get("muscles") or [])],
                }
            )
        return shaped
