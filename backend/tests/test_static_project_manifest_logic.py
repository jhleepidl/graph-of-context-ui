from app.services.static_project_manifest import (
    build_room_package_candidate,
    build_static_manifest_context_block,
    parse_project_manifest,
)

SAMPLE = """# Project Guide

## Overview
- Track enterprise competitors and customer needs.

## Commands
- pytest

## Review Checklist
- Verify claims before memory promotion.

## Do Not
- Do not copy credentials.
"""


def test_parse_static_project_manifest_and_package_candidate():
    manifest = parse_project_manifest("CLAUDE.md", SAMPLE)
    assert manifest["kind"] == "static_project_manifest_v1"
    assert manifest["manifest_type"] == "claude_md"
    assert manifest["import_boundary"]["copies_private_memory"] is False
    assert manifest["policies"]["commands"]
    package = build_room_package_candidate(manifest)
    assert package["kind"] == "shared_room_package_v1"
    assert package["safety_report"]["copies_private_memory"] is False
    block = build_static_manifest_context_block(manifest)
    assert "static_project_manifest" in block
