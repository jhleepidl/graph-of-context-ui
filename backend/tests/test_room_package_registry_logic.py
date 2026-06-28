from app.services.room_package_registry import (
    build_room_package_export_preview,
    build_room_package_lifecycle_preview,
    build_room_package_registry,
    build_room_package_registry_card,
)


def _item():
    return {
        "package_id": "strategy_room",
        "title": "Strategy Room",
        "description": "Competitive research and product strategy room.",
        "visibility": "public",
        "status": "candidate",
        "source": "test",
        "package": {
            "kind": "shared_room_package_v1",
            "package_id": "strategy_room",
            "title": "Strategy Room",
            "description": "Competitive research and product strategy room.",
            "visibility": "public",
            "status": "candidate",
            "version": "0.2.0",
            "domain_label": "enterprise_strategy",
            "agents": ["market_analyst", "competitor_reviewer"],
            "memory_schema": {
                "object_types": ["competitor", "customer_need", "product_gap"],
                "private_memory_export": "never_by_default",
            },
            "context_policy": {"private_memory": "least_privilege", "cross_room_memory": "ask_before_use"},
            "approval_policy": {"install": "required", "external_side_effects": "approval_required"},
            "tags": ["strategy", "enterprise"],
        },
        "updated_at": "2026-06-23T00:00:00",
    }


def test_registry_card_exposes_governance_and_compatibility():
    card = build_room_package_registry_card(_item())
    assert card["kind"] == "room_package_registry_card_v1"
    assert card["domain_label"] == "enterprise_strategy"
    assert card["privacy_guardrail"]["clone_safe"] is True
    assert "claude_md" in card["compatibility"]["exports"]
    assert card["governance"]["private_memory_never_exported"] is True


def test_registry_summary_groups_packages():
    registry = build_room_package_registry([_item()], query="strategy")
    assert registry["ok"] is True
    assert registry["summary"]["package_count"] == 1
    assert registry["summary"]["by_domain"]["enterprise_strategy"] == 1


def test_export_preview_generates_claude_compatible_markdown_without_private_memory():
    preview = build_room_package_export_preview(_item(), target_format="claude_md")
    assert preview["target_format"] == "claude_md"
    assert "# CLAUDE.md" in preview["content"]
    assert "Strategy Room" in preview["content"]
    assert preview["privacy"]["raw_private_memory_included"] is False


def test_lifecycle_preview_blocks_unsafe_publish():
    item = _item()
    item["package"]["safety_report"] = {"copies_private_memory": True}
    preview = build_room_package_lifecycle_preview(item, action="approve_publish")
    assert preview["ok"] is False
    assert preview["blockers"]
