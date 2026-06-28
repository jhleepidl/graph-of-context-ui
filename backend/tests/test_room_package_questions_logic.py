from app.services.room_package_questions import (
    classify_room_package_question_signals,
    plan_room_package_questions,
    summarize_question_plans,
)


def test_does_not_ask_for_ordinary_room_memory_paper_discussion():
    plan = plan_room_package_questions(
        task_text="Room별 specialized memory structure를 paper 4 topic으로 삼고 schema를 학습하자.",
        room_package={"domain_label": "research_paper", "memory_schema": {"object_types": ["paper_claim"]}},
    )
    assert plan["kind"] == "room_package_question_plan_v1"
    assert plan["should_ask"] is False
    assert plan["policy"]["ask_only_when_confirmation_is_required"] is True


def test_export_question_is_triggered_by_explicit_package_and_private_ambiguity():
    signals = classify_room_package_question_signals(task_text="handoff bundle에 private pricing note를 넣어도 될까?")
    assert signals["has_room_package"] is True
    assert signals["has_privacy_risk"] is True
    assert signals["has_export_decision_request"] is True
    plan = plan_room_package_questions(task_text="handoff bundle에 private pricing note를 넣어도 될까?")
    assert plan["questions"][0]["question_type"] == "exportability_confirmation"
    assert plan["questions"][0]["requires_user_confirmation"] is True


def test_resolved_private_export_policy_is_not_reasked():
    plan = plan_room_package_questions(task_text="handoff bundle에는 private notes를 넣지 말자.")
    assert plan["signals"]["has_resolved_negative_policy"] is True
    assert plan["should_ask"] is False


def test_question_summary_counts_questions_and_suppressed_plans():
    plans = [
        plan_room_package_questions(task_text="앞으로 전체 workflow 기본으로 해줘."),
        plan_room_package_questions(task_text="zip handoff bundle에 private pricing을 포함해도 되는지 애매해."),
    ]
    summary = summarize_question_plans(plans)
    assert summary["question_count"] == 1
    assert summary["suppressed_plan_count"] == 1
    assert "exportability_confirmation" in summary["by_question_type"]
