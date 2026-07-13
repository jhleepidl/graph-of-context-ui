from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlmodel import Session

from app.auth import get_current_principal
from app.db import engine
from app.services.recipe_catalog import (
    get_collaboration_profile,
    get_recipe,
    list_collaboration_profiles,
    list_recipes,
    load_collaboration_profile_catalog,
    load_recipe_catalog_with_evidence,
)


router = APIRouter(prefix="/api/recipes", tags=["recipes"])


@router.get("")
def read_recipes(query: str = "", category: str = "", status: str = ""):
    get_current_principal()
    with Session(engine) as session:
        catalog = load_recipe_catalog_with_evidence(session)
        items = list_recipes(query=query, category=category, status=status, catalog=catalog)
        return {
            "schema_version": catalog.get("schema_version"),
            "catalog_version": catalog.get("catalog_version"),
            "count": len(items),
            "items": items,
            "status_policy": catalog.get("status_policy", {}),
            "collaboration_profile_catalog_version": load_collaboration_profile_catalog().get("catalog_version"),
            "collaboration_profiles": list_collaboration_profiles(),
        }


@router.get("/collaboration-profiles")
def read_collaboration_profiles(query: str = "", include_preview: bool = True):
    get_current_principal()
    catalog = load_collaboration_profile_catalog()
    items = list_collaboration_profiles(query=query, include_preview=include_preview)
    return {
        "schema_version": catalog.get("schema_version"),
        "catalog_version": catalog.get("catalog_version"),
        "count": len(items),
        "items": items,
    }


@router.get("/collaboration-profiles/{profile_id}")
def read_collaboration_profile(profile_id: str):
    get_current_principal()
    profile = get_collaboration_profile(profile_id)
    if not profile:
        raise HTTPException(404, "collaboration profile not found")
    return profile


@router.get("/{recipe_id}")
def read_recipe(recipe_id: str):
    get_current_principal()
    with Session(engine) as session:
        catalog = load_recipe_catalog_with_evidence(session)
        recipe = get_recipe(recipe_id, catalog=catalog)
        if not recipe:
            raise HTTPException(404, "recipe not found")
        return recipe
