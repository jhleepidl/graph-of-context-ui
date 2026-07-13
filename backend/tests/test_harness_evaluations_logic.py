from sqlmodel import Session, SQLModel, create_engine

from app.services.harness_evaluations import (
    aggregate_variant_performance,
    ingest_harness_evaluation,
    list_harness_evaluation_runs,
    list_variant_results,
    serialize_harness_evaluation_run,
)


def test_harness_evaluation_ingest_is_idempotent_and_aggregates_variants():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    payload = {
        "evaluation_id": "eval_1",
        "suite": "coding_live_v1",
        "status": "passed",
        "scenario_count": 2,
        "total_run_count": 4,
        "passed_run_count": 4,
        "failed_run_count": 0,
        "recommendation": {"harness_variant_id": "codex.high.v1", "runtime_signature": "codex.high.v1|codex|model-a|high|cli-1"},
        "variant_results": [
            {"runtime_signature": "codex.high.v1|codex|model-a|high|cli-1", "harness_variant_id": "codex.high.v1", "provider": "codex", "model": "model-a", "reasoning_effort": "high", "cli_version": "cli-1", "run_count": 4, "passed_run_count": 4, "success_rate": 1.0, "average_score": 0.95, "average_duration_ms": 1000},
        ],
    }
    with Session(engine) as session:
        row, variants, created = ingest_harness_evaluation(session, payload)
        session.commit()
        assert created is True
        assert row.recommendation_variant_id == "codex.high.v1"
        assert row.recommendation_runtime_signature == "codex.high.v1|codex|model-a|high|cli-1"
        assert serialize_harness_evaluation_run(row)["quality_run_count"] == 4
        payload["variant_results"][0]["average_score"] = 0.97
        row2, variants2, created2 = ingest_harness_evaluation(session, payload)
        session.commit()
        assert created2 is False
        assert row2.id == row.id
        assert len(list_harness_evaluation_runs(session)) == 1
        results = list_variant_results(session)
        assert len(results) == 1
        aggregate = aggregate_variant_performance(results)
        assert aggregate[0]["success_rate"] == 1.0
        assert aggregate[0]["average_score"] == 0.97



def test_same_variant_is_separated_when_model_or_cli_version_changes():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for evaluation_id, signature, model, cli in [
            ("eval_a", "shared.v1|codex|model-a|high|cli-1", "model-a", "cli-1"),
            ("eval_b", "shared.v1|codex|model-b|high|cli-2", "model-b", "cli-2"),
        ]:
            ingest_harness_evaluation(session, {
                "evaluation_id": evaluation_id,
                "variant_results": [{
                    "runtime_signature": signature,
                    "harness_variant_id": "shared.v1",
                    "provider": "codex",
                    "model": model,
                    "reasoning_effort": "high",
                    "cli_version": cli,
                    "run_count": 1,
                    "passed_run_count": 1,
                    "success_rate": 1.0,
                    "average_score": 1.0,
                }],
            })
        session.commit()
        aggregate = aggregate_variant_performance(list_variant_results(session))
        assert len(aggregate) == 2
        assert {row["runtime_signature"] for row in aggregate} == {
            "shared.v1|codex|model-a|high|cli-1",
            "shared.v1|codex|model-b|high|cli-2",
        }


def test_execution_ineligible_variants_remain_visible_as_runs_but_do_not_pollute_leaderboard():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    payload = {
        "evaluation_id": "eval_access_denied",
        "status": "completed_with_execution_errors",
        "total_run_count": 1,
        "passed_run_count": 0,
        "failed_run_count": 0,
        "execution_error_run_count": 1,
        "quality_run_count": 0,
        "variant_results": [{
            "runtime_signature": "v|codex|gpt-5-codex|high|cli-1",
            "harness_variant_id": "v",
            "provider": "codex",
            "model": "gpt-5-codex",
            "run_count": 1,
            "quality_run_count": 0,
            "execution_error_run_count": 1,
            "success_rate": None,
            "average_score": None,
        }],
    }
    with Session(engine) as session:
        row, variants, created = ingest_harness_evaluation(session, payload)
        session.commit()
        assert created is True
        assert variants == []
        assert list_variant_results(session) == []
        serialized = serialize_harness_evaluation_run(row)
        assert serialized["execution_error_run_count"] == 1
        assert serialized["quality_run_count"] == 0



def test_corrected_resync_removes_previously_ranked_execution_ineligible_variant():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    signature = "v|codex|gpt-5-codex|high|cli-1"
    with Session(engine) as session:
        ingest_harness_evaluation(session, {
            "evaluation_id": "eval_repair",
            "status": "completed_with_failures",
            "total_run_count": 1,
            "passed_run_count": 0,
            "failed_run_count": 1,
            "variant_results": [{
                "runtime_signature": signature,
                "harness_variant_id": "v",
                "provider": "codex",
                "model": "gpt-5-codex",
                "run_count": 1,
                "passed_run_count": 0,
                "failed_run_count": 1,
                "success_rate": 0.0,
                "average_score": 0.4,
            }],
        })
        session.commit()
        assert len(list_variant_results(session)) == 1

        row, variants, created = ingest_harness_evaluation(session, {
            "evaluation_id": "eval_repair",
            "status": "completed_with_execution_errors",
            "total_run_count": 1,
            "passed_run_count": 0,
            "failed_run_count": 0,
            "quality_run_count": 0,
            "execution_error_run_count": 1,
            "variant_results": [{
                "runtime_signature": signature,
                "harness_variant_id": "v",
                "provider": "codex",
                "model": "gpt-5-codex",
                "run_count": 1,
                "quality_run_count": 0,
                "execution_error_run_count": 1,
                "success_rate": None,
                "average_score": None,
            }],
        })
        session.commit()
        assert created is False
        assert variants == []
        assert list_variant_results(session) == []
        serialized = serialize_harness_evaluation_run(row)
        assert serialized["quality_run_count"] == 0
        assert serialized["execution_error_run_count"] == 1


def test_authoritative_resync_removes_stale_variant_missing_from_payload():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ingest_harness_evaluation(session, {
            "evaluation_id": "eval_authoritative",
            "variant_results": [
                {
                    "runtime_signature": "keep|codex|model-a|high|cli-1",
                    "harness_variant_id": "keep",
                    "provider": "codex",
                    "model": "model-a",
                    "run_count": 1,
                    "passed_run_count": 1,
                    "success_rate": 1.0,
                    "average_score": 1.0,
                },
                {
                    "runtime_signature": "stale|codex|model-b|high|cli-1",
                    "harness_variant_id": "stale",
                    "provider": "codex",
                    "model": "model-b",
                    "run_count": 1,
                    "passed_run_count": 0,
                    "failed_run_count": 1,
                    "success_rate": 0.0,
                    "average_score": 0.2,
                },
            ],
        })
        session.commit()
        assert len(list_variant_results(session)) == 2

        ingest_harness_evaluation(session, {
            "evaluation_id": "eval_authoritative",
            "variant_results": [
                {
                    "runtime_signature": "keep|codex|model-a|high|cli-1",
                    "harness_variant_id": "keep",
                    "provider": "codex",
                    "model": "model-a",
                    "run_count": 1,
                    "passed_run_count": 1,
                    "success_rate": 1.0,
                    "average_score": 0.99,
                },
            ],
        })
        session.commit()
        results = list_variant_results(session)
        assert len(results) == 1
        assert results[0].runtime_signature == "keep|codex|model-a|high|cli-1"
        assert results[0].average_score == 0.99
