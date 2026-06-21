import unittest

from app.services.room_evolution import propose_room_evolution, public_room_evolution_export
from app.services.room_learning import build_room_learning_snapshot


def learning_item(text, *, command='/ask', signal=None):
    signal = signal or {}
    return {
        'event_type': 'room_learning_signal',
        'command': command,
        'domain_label': 'emergent',
        'payload': {
            'signal_pack': {
                'work_mode': 'ask' if command == '/ask' else 'team_task',
                'candidate_object_types': signal.get('objects', []),
                'domain_hints': signal.get('domains', []),
                'preference_signal': signal.get('preference', False),
                'observation_event_signal': signal.get('observation', False),
                'aggregate_query_signal': signal.get('aggregate', False),
                'image_input_signal': signal.get('image', False),
                'external_search_signal': signal.get('external', False),
                'database_need_signal': signal.get('database', False),
                'gateway_need_signal': signal.get('gateway', False),
                'uncertainty_or_confirmation_signal': signal.get('confirm', False),
            },
            'goal': text,
        },
    }


class RoomEvolutionLogicTest(unittest.TestCase):
    def test_dynamic_room_evolution_proposes_schema_agents_materialization_and_gateway(self):
        items = [
            learning_item('menu ask', signal={'objects': ['meal_or_intake_event'], 'domains': ['meal_like'], 'preference': True}),
            learning_item('meal record', signal={'objects': ['meal_or_intake_event'], 'domains': ['meal_like'], 'observation': True}),
            learning_item('image estimate', signal={'objects': ['meal_or_intake_event'], 'domains': ['meal_like'], 'image': True, 'confirm': True}),
            learning_item('recent pattern and db query', signal={'objects': ['meal_or_intake_event'], 'domains': ['meal_like'], 'aggregate': True, 'database': True}),
            learning_item('nearby search', signal={'objects': ['restaurant_candidate'], 'domains': ['meal_like'], 'external': True}),
        ]
        snapshot = propose_room_evolution(items)
        self.assertEqual(snapshot['governance']['ai_role'], 'architect_advisor_proposer_not_controller')
        self.assertFalse(snapshot['governance']['auto_apply'])
        proposal_ids = {p['proposal_id'] for p in snapshot['proposals']}
        proposal_types = {p['proposal_type'] for p in snapshot['proposals']}
        self.assertIn('schema:meal_or_intake_event', proposal_ids)
        self.assertIn('agent:image_interpreter', proposal_ids)
        self.assertIn('agent:local_info_scout', proposal_ids)
        self.assertIn('memory_materialization', proposal_types)
        self.assertIn('gateway_or_board', proposal_types)

    def test_public_export_contains_only_aggregate_structure(self):
        items = [learning_item('private text 김치찌개', signal={'objects': ['meal_or_intake_event'], 'observation': True})]
        exported = public_room_evolution_export(propose_room_evolution(items))
        self.assertFalse(exported['privacy']['includes_raw_text'])
        self.assertFalse(exported['privacy']['includes_private_memory'])
        self.assertNotIn('김치찌개', str(exported))

    def test_room_learning_snapshot_includes_room_evolution(self):
        snapshot = build_room_learning_snapshot([
            learning_item('first', signal={'objects': ['observed_event'], 'observation': True}),
            learning_item('second', signal={'objects': ['observed_event'], 'observation': True}),
        ])
        self.assertEqual(snapshot['room_evolution']['kind'], 'room_evolution_snapshot_v1')
        self.assertIn('public_evolution_export', snapshot)
        self.assertFalse(snapshot['public_evolution_export']['privacy']['includes_private_memory'])


if __name__ == '__main__':
    unittest.main()
