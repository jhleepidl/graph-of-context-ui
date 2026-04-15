from __future__ import annotations



RUNTIME_MEMBER_ID_KEYS = ("agent_id", "runtime_instance_id", "instance_id", "id", "member_id")
RUNTIME_MEMBER_HINT_KEYS = (
    "role_label",
    "role",
    "role_id",
    "title",
    "name",
    "display_name",
    "display_label",
    "displayLabel",
    "label",
    "slot_id",
    "slotId",
    "preset_id",
    "presetId",
    "authority_profile_id",
    "authorityProfileId",
    "template_id",
    "agent_template_id",
    "provider",
    "llm_provider",
    "model",
    "model_name",
    "runtime_status",
    "status",
    "state",
    "capability_tags",
    "capabilities",
    "responsibilities",
    "responsibility",
    "ephemeral",
    "transient",
    "selection_reason",
    "selectionReason",
    "synthesized",
    "attached_skill_ids",
    "attachedSkillIds",
    "context_pack_id",
    "contextPackId",
)
RUNTIME_NESTED_BLOCK_KEYS = ("runtime", "meta", "result", "output", "state", "data")
TASK_INTERPRETATION_KEYS = ("task_interpretation", "taskInterpretation")
TEAM_PLAN_KEYS = ("team_plan", "teamPlan")
ACTION_SOURCE_KEYS = ("action_source", "actionSource")
COLLABORATION_CELL_KEYS = ("collaboration_cells", "collaborationCells")
AUTHORITY_GRAPH_KEYS = ("authority_graph", "authorityGraph")
CHECKPOINT_KEYS = ("checkpoints",)
EXECUTION_GRAPH_KEYS = ("execution_graph", "executionGraph")
SELECTION_EXPLANATION_KEYS = ("selection_explanations", "selectionExplanations")
EXECUTION_INSIGHT_KEYS = ("execution_insights", "executionInsights")
EXECUTION_FEEDBACK_KEYS = ("execution_feedback", "executionFeedback")
SCOPE_SPEC_KEYS = ("scope_specs", "scopeSpecs")
MATERIALIZED_SCOPE_KEYS = ("materialized_scopes", "materializedScopes")
VISIBILITY_GRAPH_KEYS = ("visibility_graph", "visibilityGraph")
CONTEXT_RUNTIME_MODE_KEYS = ("context_runtime_mode", "contextRuntimeMode")
CONVERSATION_PREFERENCE_KEYS = ("conversation_preferences", "conversationPreferences")
TEAM_PLAN_V2_HINT_KEYS = (
    *TASK_INTERPRETATION_KEYS,
    *COLLABORATION_CELL_KEYS,
    *AUTHORITY_GRAPH_KEYS,
    *CHECKPOINT_KEYS,
    *EXECUTION_GRAPH_KEYS,
    *SELECTION_EXPLANATION_KEYS,
    *SCOPE_SPEC_KEYS,
    *MATERIALIZED_SCOPE_KEYS,
    *VISIBILITY_GRAPH_KEYS,
    *CONTEXT_RUNTIME_MODE_KEYS,
    *CONVERSATION_PREFERENCE_KEYS,
    "slots",
    "supervisor_runtime",
    "supervisorRuntime",
)


