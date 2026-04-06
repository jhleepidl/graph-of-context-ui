import unittest

from app.services.memory_graph import (
    build_memory_projection,
    detect_memory_conflicts,
    normalize_conflict_resolution,
    summarize_memory_conflicts,
)
from app.services.team_recommender import build_team_selection_dataset, serialize_team_selection_dataset_jsonl


class MemoryConflictLogicTests(unittest.TestCase):
    def test_detect_memory_conflicts_for_divergent_same_key_nodes_with_provenance_and_confidence(self):
        conflicts = detect_memory_conflicts(
            new_node={
                'id': 'n2',
                'surface_id': 'shared_evidence',
                'node_type': 'fact',
                'trust_tier': 'derived',
                'content': {'claim': 'service is healthy', 'conflict_key': 'service_health', 'confidence': 0.41},
                'provenance': {'source_id': 'probe_b', 'entity': 'service_health'},
            },
            existing_nodes=[
                {
                    'id': 'n1',
                    'surface_id': 'shared_evidence',
                    'node_type': 'fact',
                    'trust_tier': 'verified',
                    'content': {'claim': 'service is degraded', 'conflict_key': 'service_health', 'confidence': 0.92},
                    'provenance': {'source_id': 'probe_a', 'entity': 'service_health'},
                }
            ],
            existing_conflicts=[],
        )
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]['status'], 'pending')
        self.assertEqual(conflicts[0]['left_node_id'], 'n1')
        self.assertEqual(conflicts[0]['right_node_id'], 'n2')
        self.assertEqual(conflicts[0]['reason'], 'same_key_divergent_provenance_and_confidence')
        self.assertEqual(conflicts[0]['left_trust_tier'], 'verified')

    def test_build_memory_projection_includes_drilldown_and_block_reasons(self):
        projection = build_memory_projection(
            role_id='reviewer',
            surfaces=[
                {'surface_id': 'shared_evidence', 'target_roles': ['reviewer']},
                {'surface_id': 'private_working_memory', 'target_roles': ['builder']},
            ],
            nodes=[
                {'id': 'n1', 'surface_id': 'shared_evidence', 'node_type': 'fact', 'content_json': {'claim': 'ok'}, 'provenance_json': {'source_id': 'probe_a'}},
                {'id': 'n2', 'surface_id': 'private_working_memory', 'node_type': 'note', 'content_json': {'note': 'hidden'}},
            ],
        )
        self.assertEqual(len(projection['visible_nodes']), 1)
        self.assertEqual(len(projection['blocked_nodes']), 1)
        self.assertEqual(projection['blocked_nodes'][0]['blocked_reason'], 'role_not_allowed')

    def test_summarize_memory_conflicts_counts_statuses(self):
        summary = summarize_memory_conflicts([
            {'id': 'c1', 'surface_id': 'plan', 'left_node_id': 'n1', 'right_node_id': 'n2', 'status': 'pending', 'reason': 'divergent'},
            {'id': 'c2', 'surface_id': 'plan', 'left_node_id': 'n3', 'right_node_id': 'n4', 'status': 'resolved', 'reason': 'merged'},
        ])
        self.assertEqual(summary['count'], 2)
        self.assertEqual(summary['status_counts']['pending'], 1)
        self.assertEqual(summary['status_counts']['resolved'], 1)
        self.assertEqual(summary['reason_counts']['divergent'], 1)

    def test_normalize_conflict_resolution_keeps_winner_and_losers(self):
        resolution = normalize_conflict_resolution({
            'status': 'resolved',
            'winning_node_id': 'n2',
            'losing_node_ids': ['n1'],
            'summary': 'accept latest node',
        })
        self.assertEqual(resolution['winning_node_id'], 'n2')
        self.assertEqual(resolution['losing_node_ids'], ['n1'])

    def test_build_team_selection_dataset_normalizes_rows(self):
        dataset = build_team_selection_dataset([
            {
                'id': 'evt-1',
                'thread_id': 'thread-1',
                'run_id': 'run-1',
                'task_text': 'Implement a patch and review it',
                'selected_blueprint_id': 'impl_team',
                'recommendation': {
                    'candidates': [
                        {
                            'template_id': 'impl_team',
                            'task_archetype': 'implementation',
                            'score': 11,
                            'topology': {'pattern': 'review_loop', 'participant_count': 2, 'edge_count': 1},
                            'memory_fit': {'surface_count': 4, 'final_answer_surface_ready': True, 'shared_surface_count': 2},
                            'executable_definition': {'member_count': 2, 'role_ids': ['builder', 'reviewer'], 'executable_readiness': {'ready': True}, 'capability_contract': {'runtime_bound': True}},
                        }
                    ]
                },
                'outcome': {'success': True, 'quality_score': 0.9, 'token_cost': 1200, 'latency_ms': 8400},
                'created_at': '2026-04-06T00:00:00Z',
            }
        ])
        self.assertEqual(dataset['kind'], 'team_selection_dataset_v1')
        self.assertEqual(dataset['schema_version'], 2)
        self.assertEqual(dataset['count'], 1)
        self.assertEqual(dataset['rows'][0]['selected_topology_pattern'], 'review_loop')
        self.assertEqual(dataset['rows'][0]['selected_role_ids'], ['builder', 'reviewer'])
        self.assertEqual(dataset['archetype_counts']['implementation'], 1)

    def test_serialize_team_selection_dataset_jsonl(self):
        text = serialize_team_selection_dataset_jsonl([
            {
                'id': 'evt-1',
                'selected_blueprint_id': 'impl_team',
                'recommendation': {'candidates': [{'template_id': 'impl_team', 'task_archetype': 'implementation'}]},
            }
        ])
        self.assertIn('impl_team', text)
        self.assertEqual(len([line for line in text.splitlines() if line.strip()]), 1)


if __name__ == '__main__':
    unittest.main()
