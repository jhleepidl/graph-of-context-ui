from app.services.claude_compatible_events import (
    build_claude_compatible_room_event,
    claude_event_to_room_usage_event,
    import_claude_compatible_manifest_preview,
    validate_claude_compatible_room_event,
)


def test_claude_compatible_event_sanitizes_raw_fields():
    event = build_claude_compatible_room_event({
        "source": "claude_code",
        "project_root": "/private/project",
        "event_type": "subagent used",
        "action": "Compare competitors",
        "subagent_name": "market_analyst",
        "metadata": {"prompt": "SECRET", "safe_note": "ok"},
        "outcome": {"signal": "accepted", "response": "RAW"},
    })
    assert event["kind"] == "claude_compatible_room_event_v1"
    assert event["event_type"] == "subagent_used"
    assert event["outcome"]["accepted"] is True
    assert event["metadata"]["safe_note"] == "ok"
    assert "prompt" not in event["metadata"]
    assert validate_claude_compatible_room_event(event) == (True, "ok")


def test_claude_event_to_room_usage_event():
    event = build_claude_compatible_room_event({"action": "run tests and review code", "subagent_name": "verifier", "outcome": {"signal": "retry"}})
    usage = claude_event_to_room_usage_event(event)
    assert usage["kind"] == "room_usage_event_v1"
    assert usage["goal"] == ""
    assert usage["recommendation"]["action"] == "review_component_or_schema"


def test_claude_manifest_import_preview_builds_candidate():
    preview = import_claude_compatible_manifest_preview("CLAUDE.md", "# Strategy Room\n\n## Workflow\n- Compare competitors\n")
    assert preview["kind"] == "claude_compatible_manifest_import_preview_v1"
    assert preview["room_package_candidate"]["kind"] == "shared_room_package_v1"
    assert preview["collection_policy"]["stores_raw_files_by_default"] is False
