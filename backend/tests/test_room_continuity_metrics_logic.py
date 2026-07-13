from app.services.room_usage import summarize_room_usage_events


def test_room_usage_summary_includes_continuity_signals():
    summary = summarize_room_usage_events([
        {'event_type': 'room_continuation_requested', 'domain_label': 'research'},
        {'event_type': 'room_continuation_completed', 'domain_label': 'research'},
        {'event_type': 'room_continuity_brief_view', 'domain_label': 'research'},
        {'event_type': 'room_source_boundary_view', 'domain_label': 'research'},
        {'event_type': 'room_rules_view', 'domain_label': 'research'},
        {'event_type': 'room_branch_proposed', 'domain_label': 'research'},
    ])
    continuity = summary['continuity']
    assert continuity['continuation_attempt_count'] == 1
    assert continuity['continuation_completion_count'] == 1
    assert continuity['continuation_completion_rate'] == 1
    assert continuity['brief_view_count'] == 1
    assert continuity['branch_proposal_count'] == 1
