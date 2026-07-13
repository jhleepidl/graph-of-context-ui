from app.services.recipe_catalog import (
    derive_recipe_evidence_status,
    get_collaboration_profile,
    get_recipe,
    list_collaboration_profiles,
    list_recipes,
    load_recipe_catalog,
)


def test_recipe_catalog_exposes_starter_kits_and_evidence_status():
    catalog = load_recipe_catalog()
    assert catalog["catalog_version"]
    assert len(catalog["recipes"]) >= 12
    small_change = get_recipe("coding.small_change")
    assert small_change is not None
    assert small_change["evidence_summary"]["status"] == "revalidation_needed"
    assert small_change["evidence_summary"]["live_runs"] == 4
    assert len(list_recipes(query="코드")) >= 1


def test_recipe_recommendation_requires_broad_evidence():
    status = derive_recipe_evidence_status(
        {"evaluation": {"evidence_scope": "representative", "evidence": [{"live_runs": 10, "passed_runs": 9, "policy_violations": 0}]}},
        {"status_policy": {"recommended": {"min_live_runs": 8, "min_success_rate": 0.85, "max_policy_violations": 0, "required_evidence_scope": ["representative"]}, "evaluated": {"min_live_runs": 3, "min_success_rate": 0.8, "max_policy_violations": 0}}},
    )
    assert status["status"] == "recommended"

import json

from sqlmodel import SQLModel, Session, create_engine

from app.models import HarnessEvaluationRun
from app.services.recipe_catalog import load_recipe_catalog_with_evidence


def test_recipe_catalog_uses_latest_synced_runtime_signature_as_current_evidence():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    payload = {
        "evaluation_id": "eval-recipe-current",
        "runs": [
            {
                "recipe_ids": ["coding.small_change"],
                "runtime_signature": "variant|codex|gpt-5.6-sol|high|codex-cli-0.144.0",
                "provider": "codex",
                "model": "gpt-5.6-sol",
                "reasoning_effort": "high",
                "cli_version": "codex-cli-0.144.0",
                "dry_run": False,
                "passed": True,
                "score": 1.0,
                "completed_at": "2026-07-12T01:00:00Z",
            },
            {
                "recipe_ids": ["coding.small_change"],
                "runtime_signature": "variant|codex|gpt-5.6-sol|high|codex-cli-0.144.0",
                "provider": "codex",
                "model": "gpt-5.6-sol",
                "reasoning_effort": "high",
                "cli_version": "codex-cli-0.144.0",
                "dry_run": False,
                "passed": True,
                "score": 1.0,
                "completed_at": "2026-07-12T01:01:00Z",
            },
            {
                "recipe_ids": ["coding.small_change"],
                "runtime_signature": "variant|codex|gpt-5.6-sol|high|codex-cli-0.144.0",
                "provider": "codex",
                "model": "gpt-5.6-sol",
                "reasoning_effort": "high",
                "cli_version": "codex-cli-0.144.0",
                "dry_run": False,
                "passed": True,
                "score": 0.9,
                "completed_at": "2026-07-12T01:02:00Z",
            },
        ],
    }
    with Session(engine) as session:
        session.add(HarnessEvaluationRun(
            evaluation_id="eval-recipe-current",
            payload_json=json.dumps(payload),
            total_run_count=3,
            passed_run_count=3,
        ))
        session.commit()
        catalog = load_recipe_catalog_with_evidence(session)
    recipe = next(item for item in catalog["recipes"] if item["id"] == "coding.small_change")
    summary = recipe["evidence_summary"]
    assert summary["status"] == "evaluated"
    assert summary["live_runs"] == 3
    assert summary["active_runtime_signature"] == "variant|codex|gpt-5.6-sol|high|codex-cli-0.144.0"
    assert any(row["current"] is True for row in summary["evidence"])


def test_recipe_catalog_exposes_diverse_generic_recipes_and_collaboration_profiles():
    for recipe_id in [
        "recommendation.contextual",
        "source.file_grounded",
        "thinking.parallel_ideas",
        "research.long_horizon",
        "artifact.prototype",
        "decision.risk_reviewed",
    ]:
        assert get_recipe(recipe_id) is not None

    profiles = list_collaboration_profiles()
    assert len(profiles) >= 7
    assert get_collaboration_profile("parallel_ideation")["runtime_support"] == "native"
    assert get_collaboration_profile("selective_panel")["runtime_support"] == "metadata_only"
    assert get_recipe("thinking.parallel_ideas")["recommended_collaboration_profile"] == "parallel_ideation"
