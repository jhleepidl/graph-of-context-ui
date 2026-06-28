from app.services.room_skill_discovery import build_room_skill_discovery_bundle


def test_room_skill_discovery_generates_room_memory_trial_plan():
    snapshot = {
        'aggregate': {
            'counts': {'total_events': 5, 'image_input': 1, 'confirmation_need': 1},
            'top_objects': [{'id': 'meal_or_intake_event', 'count': 4}],
        }
    }
    bundle = build_room_skill_discovery_bundle(snapshot)
    assert bundle['kind'] == 'room_skill_discovery_bundle_v1'
    assert bundle['probe_suite']['probes']
    assert bundle['room_memory_schema_trial_plan']['unit_of_treatment'] == 'room_specific_memory_package_or_schema_projection'
    assert bundle['governance']['direct_memory_write'] is False
