from app.services.room_concierge import classify_room_concierge_route, score_linear_room_concierge_model


def test_direct_short_ask():
    decision = classify_room_concierge_route("오늘 저녁 메뉴 추천해줘")
    assert decision["route"] == "concierge_direct_answer"
    assert decision["should_bypass_workbench"] is True
    assert decision["should_show_plan_preview"] is False


def test_search_ask_not_direct():
    decision = classify_room_concierge_route("실제로 메뉴판을 검색해서 추천해줘")
    assert decision["route"] == "concierge_search_answer"
    assert decision["should_bypass_workbench"] is False


def test_code_patch_uses_workbench():
    decision = classify_room_concierge_route("첨부 zip을 보고 코드 패치하고 테스트 돌려줘")
    assert decision["route"] == "standard_workbench"
    assert "needs_workspace_or_artifact" in decision["blockers"]


def test_score_linear_room_concierge_model_prefers_workbench_under_governance_pressure():
    decision = classify_room_concierge_route("오늘 저녁 메뉴 추천해줘")
    model = {
        "version": "unit-linear",
        "route_weights": {
            "concierge_direct_answer": {"bias": 0.5, "signal_simple_qa": 0.3},
            "standard_workbench": {"bias": 0.0, "room_governance_pressure": 3.0},
        },
    }
    scored = score_linear_room_concierge_model(decision, model, room_footprint={"governance_pressure": 1.0})
    assert scored["ok"] is True
    assert scored["route"] == "standard_workbench"
    assert scored["features"]["signal_simple_qa"] == 1.0
