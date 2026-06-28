from app.services.room_memory_data_capture import build_room_memory_goc_event, validate_room_memory_goc_event


def test_room_memory_trials_goc_event_hashes_ids_and_strips_text():
    event = build_room_memory_goc_event(
        thread_id='thread-1',
        route={'depth': 'ask', 'raw_text': 'must not leak'},
        evolution_snapshot={
            'maturity': 'soft_typed_memory_candidate',
            'aggregate': {'counts': {'total_events': 3}, 'top_objects': [{'id': 'strategy_note'}]},
            'room_memory_trial_plan': {'candidate_object_types': ['strategy_note'], 'treatments': ['raw_tail']},
        },
    )
    assert event['ids']['thread_id_hash'] != 'thread-1'
    assert 'must not leak' not in str(event)
    ok, reason = validate_room_memory_goc_event(event)
    assert ok is True
    assert reason == ''
