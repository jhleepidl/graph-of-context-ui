import unittest

from app.services.memory_graph import (
    append_conflict_history,
    build_memory_projection,
    detect_memory_conflicts,
    normalize_conflict_history_entry,
    normalize_conflict_resolution,
    summarize_memory_conflict,
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

    def test_build_memory_projection_includes_governance_reasons_for_private_quarantined_low_confidence_and_conflicts(self):
        projection = build_memory_projection(
            role_id='reviewer',
            surfaces=[
                {'surface_id': 'shared_evidence', 'target_roles': ['reviewer'], 'policy': {'min_confidence': 0.5}},
                {'surface_id': 'private_working_memory', 'visibility_scope': 'private', 'policy': {'target_roles': ['builder']}},
            ],
            nodes=[
                {'id': 'n1', 'surface_id': 'shared_evidence', 'node_type': 'fact', 'content_json': {'claim': 'ok', 'confidence': 0.91}, 'provenance_json': {'source_id': 'probe_a'}},
                {'id': 'n2', 'surface_id': 'private_working_memory', 'node_type': 'note', 'content_json': {'note': 'hidden'}},
                {'id': 'n3', 'surface_id': 'shared_evidence', 'node_type': 'fact', 'status': 'quarantined', 'content_json': {'claim': 'bad', 'confidence': 0.95}},
                {'id': 'n4', 'surface_id': 'shared_evidence', 'node_type': 'fact', 'content_json': {'claim': 'weak', 'confidence': 0.12}},
                {'id': 'n5', 'surface_id': 'shared_evidence', 'node_type': 'fact', 'content_json': {'claim': 'contested', 'confidence': 0.88}},
            ],
            unresolved_conflict_node_ids=['n5'],
        )
        blocked = {row['node_id']: row['blocked_reason'] for row in projection['blocked_nodes']}
        self.assertEqual(len(projection['visible_nodes']), 1)
        self.assertEqual(blocked['n2'], 'role_not_allowed')
        self.assertEqual(blocked['n3'], 'status_quarantined')
        self.assertEqual(blocked['n4'], 'confidence_below_minimum')
        self.assertEqual(blocked['n5'], 'pending_conflict')

    def test_summarize_memory_conflicts_counts_statuses(self):
        summary = summarize_memory_conflicts([
            {'id': 'c1', 'surface_id': 'plan', 'left_node_id': 'n1', 'right_node_id': 'n2', 'status': 'pending', 'reason': 'divergent'},
            {'id': 'c2', 'surface_id': 'plan', 'left_node_id': 'n3', 'right_node_id': 'n4', 'status': 'resolved', 'reason': 'merged'},
        ])
        self.assertEqual(summary['count'], 2)
        self.assertEqual(summary['status_counts']['pending'], 1)
        self.assertEqual(summary['status_counts']['resolved'], 1)
        self.assertEqual(summary['reason_counts']['divergent'], 1)

    def test_normalize_conflict_resolution_keeps_winner_losers_and_rationale_support(self):
        resolution = normalize_conflict_resolution({
            'status': 'resolved',
            'winning_node_id': 'n2',
            'losing_node_ids': ['n1'],
            'summary': 'accept latest node',
            'rationale_codes': ['higher_confidence', 'linked_claim_support'],
            'supporting_claim_node_ids': ['claim-1'],
            'supporting_evidence_node_ids': ['ev-1'],
            'supporting_memory_node_ids': ['n2', 'n1'],
        })
        self.assertEqual(resolution['winning_node_id'], 'n2')
        self.assertEqual(resolution['losing_node_ids'], ['n1'])
        self.assertEqual(resolution['rationale_codes'], ['higher_confidence', 'linked_claim_support'])
        self.assertEqual(resolution['supporting_claim_node_ids'], ['claim-1'])
        self.assertEqual(resolution['supporting_evidence_node_ids'], ['ev-1'])
        self.assertEqual(resolution['supporting_memory_node_ids'], ['n2', 'n1'])

    def test_conflict_history_entries_are_appended_and_summarized(self):
        resolution = append_conflict_history(
            {'conflict_key': 'service_health'},
            {
                'event_type': 'conflict_detected',
                'status': 'pending',
                'summary': 'Detected conflicting writes',
                'supporting_memory_node_ids': ['n1', 'n2'],
                'source': 'memory_conflict_detector',
            },
        )
        resolution = append_conflict_history(
            resolution,
            {
                'event_type': 'conflict_resolved',
                'status': 'resolved',
                'previous_status': 'pending',
                'summary': 'Accepted n2 after review',
                'winning_node_id': 'n2',
                'losing_node_ids': ['n1'],
                'rationale_codes': ['higher_confidence'],
                'resolved_by': 'operator',
                'resolution_source': 'operator_ui',
            },
        )
        summary = summarize_memory_conflict({
            'id': 'c1',
            'surface_id': 'shared_evidence',
            'left_node_id': 'n1',
            'right_node_id': 'n2',
            'status': 'resolved',
            'reason': 'same_key_confidence_mismatch',
            'resolution_json': resolution,
        })
        self.assertEqual(summary['history_count'], 2)
        self.assertEqual(summary['merge_history_count'], 2)
        self.assertEqual(summary['latest_history_event']['event_type'], 'conflict_resolved')
        self.assertEqual(summary['latest_merge_event']['winning_node_id'], 'n2')
        self.assertEqual(summary['history'][0]['event_type'], 'conflict_detected')

    def test_normalize_conflict_history_entry_keeps_actor_source_and_merge_note(self):
        entry = normalize_conflict_history_entry({
            'event_type': 'conflict_merged',
            'status': 'merged',
            'resolved_by': 'reviewer',
            'resolution_source': 'operator_ui',
            'merge_note': 'Preserved both facts in merged summary',
        })
        self.assertEqual(entry['event_type'], 'conflict_merged')
        self.assertEqual(entry['actor'], 'reviewer')
        self.assertEqual(entry['source'], 'operator_ui')
        self.assertEqual(entry['merge_note'], 'Preserved both facts in merged summary')

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
        self.assertEqual(dataset['schema_version'], 5)
        self.assertEqual(dataset['count'], 1)
        self.assertEqual(dataset['rows'][0]['selected_topology_pattern'], 'review_loop')
        self.assertEqual(dataset['rows'][0]['selected_role_ids'], ['builder', 'reviewer'])
        self.assertEqual(dataset['archetype_counts']['implementation'], 1)
        self.assertEqual(dataset['selection_outcome_summary']['alignment_event_samples']['top_pick'][0]['run_id'], 'run-1')

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
