from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

COMPANION_CONTROL_SCHEMA_VERSION = "goc.companion_control_manifest/v1"

_COMPANIONS: List[Dict[str, Any]] = [
    {
        "id": "research",
        "label": "Research Companion",
        "purpose": "Research framing, prior art, experiment analysis, and docs alignment.",
        "best_for": ["paper direction", "prior art", "experiment interpretation", "docs trajectory"],
        "memory_connections": [
            {"source": "project_docs", "mode": "read", "strictness": "source_required"},
            {"source": "experiment_summaries", "mode": "read", "strictness": "balanced"},
            {"source": "accepted_decisions", "mode": "read", "strictness": "source_required"},
        ],
        "excluded_by_default": ["private_raw_traces", "unreviewed_other_room_raw_chat"],
        "agent_mode": "balanced",
        "action_policy": "draft_and_patch_only",
        "branch_policy": "branch_for_speculation",
    },
    {
        "id": "implementation",
        "label": "Implementation Companion",
        "purpose": "Code patches, targeted tests, source-bundle hygiene, and implementation handoff.",
        "best_for": ["patching", "targeted tests", "source bundle", "CLI/docs consistency"],
        "memory_connections": [
            {"source": "implementation_status", "mode": "read", "strictness": "source_required"},
            {"source": "project_docs", "mode": "read", "strictness": "balanced"},
            {"source": "test_results", "mode": "read", "strictness": "balanced"},
        ],
        "excluded_by_default": ["private_raw_traces", "unreviewed_product_branches"],
        "agent_mode": "implementation",
        "action_policy": "patch_allowed_external_actions_confirmed",
        "branch_policy": "branch_for_speculation",
    },
    {
        "id": "product",
        "label": "Product Companion",
        "purpose": "UX, room/companion entrypoints, fuzzy memory tolerance, and control-surface design.",
        "best_for": ["user experience", "companion design", "memory controls", "entrypoint design"],
        "memory_connections": [
            {"source": "product_docs", "mode": "read", "strictness": "balanced"},
            {"source": "accepted_decisions", "mode": "read", "strictness": "balanced"},
        ],
        "excluded_by_default": ["private_raw_traces", "implementation_debug_logs"],
        "agent_mode": "product",
        "action_policy": "draft_and_patch_only",
        "branch_policy": "suggest_branch_for_large_changes",
    },
    {
        "id": "concierge",
        "label": "Best Companion / Concierge",
        "purpose": "Route ambiguous requests and suggest the safest companion/context bundle.",
        "best_for": ["which companion?", "ambiguous task", "context bundle choice", "safe routing"],
        "memory_connections": [
            {"source": "companion_profiles", "mode": "read", "strictness": "balanced"},
            {"source": "project_docs_index", "mode": "read", "strictness": "balanced"},
        ],
        "excluded_by_default": ["private_raw_traces", "sensitive_memory"],
        "agent_mode": "router",
        "action_policy": "suggest_only",
        "branch_policy": "ask_before_cross_room_context",
    },
]

_CONTEXT_MODES: List[Dict[str, Any]] = [
    {
        "id": "project-only",
        "label": "Project-only",
        "description": "Use project-scoped docs/decisions and avoid unrelated personal/global memory.",
        "telegram_command": "/context project-only",
        "risk": "low",
    },
    {
        "id": "clean-slate",
        "label": "Clean slate",
        "description": "Answer without existing room/personal assumptions except the current request.",
        "telegram_command": "/context clean-slate",
        "risk": "medium",
    },
    {
        "id": "exclude",
        "label": "Exclude source or assumption",
        "description": "Exclude a named memory source, assumption, branch, or prior hypothesis.",
        "telegram_command": "/context exclude <source-or-assumption>",
        "risk": "low",
    },
    {
        "id": "reset",
        "label": "Reset context controls",
        "description": "Clear room-session context overrides and return to the companion default.",
        "telegram_command": "/context reset",
        "risk": "low",
    },
]

_AGENT_MODES: List[Dict[str, Any]] = [
    {"id": "fast", "label": "Fast", "description": "Proceed through low-risk ambiguity with brief assumptions.", "telegram_command": "/agent mode fast"},
    {"id": "balanced", "label": "Balanced", "description": "Default: proceed on low-risk ambiguity, ask on high-risk actions.", "telegram_command": "/agent mode balanced"},
    {"id": "strict", "label": "Strict", "description": "Ask more often before changing durable memory, scope, or external actions.", "telegram_command": "/agent mode strict"},
]

_USER_FLOWS: List[Dict[str, Any]] = [
    {
        "id": "room_continuity",
        "label": "Resume the Room without re-explaining",
        "description": "Review the active goal, source boundaries, rules, corrections, and next action before continuing or branching.",
        "commands": ["/brief", "/continue", "/sources", "/rules", "/branch <new direction>"],
    },
    {
        "id": "choose_companion",
        "label": "Choose who to talk to",
        "description": "Pick a specialized companion instead of manually wiring memory sources.",
        "commands": ["/companions", "/companion switch <id>", "/companion profile"],
    },
    {
        "id": "control_context",
        "label": "Choose what context is allowed",
        "description": "Start from project-only or exclude a stale assumption before asking.",
        "commands": ["/context project-only", "/context exclude <source>", "/context reset"],
    },
    {
        "id": "correct_and_repair",
        "label": "Correct once, avoid repeated mistakes",
        "description": "Record a correction; durable corrections become reviewable merge proposals, and accepted proposals expose branchable materialization candidates rather than silent global memory.",
        "commands": ["/correct <text>", "/correct proposals", "/correct approve latest", "/correct materialize-preview", "/correct reject latest <reason>", "/correct promote latest"],
    },
]

_RUNTIME_STATUS: Dict[str, Any] = {
    "telegram_runtime": "implemented_thin_surface",
    "goc_web_runtime": "manifest_and_hub_scaffold",
    "write_model": "web hub currently guides/copies safe commands; durable writes still happen through runtime commands",
    "next_runtime_step": "connect GoC hub actions to authenticated companion-control write endpoints after accepted-proposal materialization candidates are reviewed",
}


def get_companion_control_manifest() -> Dict[str, Any]:
    return {
        "schema_version": COMPANION_CONTROL_SCHEMA_VERSION,
        "product_positioning": {
            "external_language": "Persistent AI Room",
            "internal_language": "AI Room substrate",
            "principle": "The model can change. The Room remembers.",
        },
        "companions": deepcopy(_COMPANIONS),
        "context_modes": deepcopy(_CONTEXT_MODES),
        "agent_modes": deepcopy(_AGENT_MODES),
        "user_flows": deepcopy(_USER_FLOWS),
        "runtime_status": deepcopy(_RUNTIME_STATUS),
        "ux_notes": [
            "Prefer Room goal, source boundaries, rules, corrections, and continuation controls over Agent/model configuration on the first screen.",
            "Low-risk context repair should be fuzzy and recoverable; high-risk memory/tool actions stay strict.",
            "Do not silently promote corrections to project-shared memory; create reviewable proposals and branchable materialization candidates.",
        ],
        "non_goals": [
            "Do not position multi-model or multi-agent execution as the primary product value.",
            "Do not make one global best friend that always sees every memory.",
            "Do not force users to manage raw memory graphs before asking a question.",
            "Do not rewrite the whole GoC Studio before validating the simplified Companion Hub.",
        ],
    }
