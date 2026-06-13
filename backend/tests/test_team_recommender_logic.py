from __future__ import annotations

import unittest

from app.services.team_recommender import build_team_selection_dataset, serialize_team_selection_dataset_jsonl
try:
    from app.services.team_recommender import recommend_team_blueprints
    from app.services.team_blueprint import _manifest_to_blueprint_doc
    from app.services.team_blueprint_templates import list_team_blueprint_templates
    _TEAM_BLUEPRINT_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    recommend_team_blueprints = None
    _manifest_to_blueprint_doc = None
    list_team_blueprint_templates = None
    _TEAM_BLUEPRINT_IMPORT_ERROR = exc


class TeamSelectionDatasetLogicTest(unittest.TestCase):
    def test_build_team_selection_dataset_marks_missing_selected_candidate_as_excluded(self) -> None:
        dataset = build_team_selection_dataset([
            {
                'id': 'evt-1',
                'task_text': 'Implement a code patch in the repo and verify it',
                'selected_blueprint_id': 'impl_team',
                'recommendation': {
                    'candidates': [
                        {'template_id': 'research_team', 'task_archetype': 'research'},
                    ],
                },
            }
        ])
        self.assertEqual(dataset['schema_version'], 7)
        self.assertEqual(dataset['eligible_count'], 0)
        self.assertEqual(dataset['excluded_count'], 1)
        self.assertEqual(dataset['exclusion_reason_counts']['selected_candidate_not_in_recommendation'], 1)
        row = dataset['rows'][0]
        self.assertFalse(row['training_eligible'])
        self.assertFalse(row['selected_candidate_found'])
        self.assertIsNone(row['selected_features'])


    def test_dataset_includes_ui_comparison_fields(self) -> None:
        dataset = build_team_selection_dataset([
            {
                'id': 'evt-1',
                'task_text': 'Implement a code patch in the repo and verify it',
                'selected_blueprint_id': 'review_team',
                'recommendation': {
                    'candidates': [
                        {
                            'template_id': 'impl_team',
                            'title': 'Implementation Team',
                            'task_archetype': 'implementation',
                            'score': 12,
                            'feature_score_breakdown': {'implementation_boost': 4},
                            'rationale': ['archetype=implementation'],
                        },
                        {
                            'template_id': 'review_team',
                            'title': 'Review Team',
                            'task_archetype': 'review_repair',
                            'score': 9,
                            'feature_score_breakdown': {'review_boost': 4},
                            'rationale': ['archetype=review_repair'],
                        },
                    ],
                },
                'outcome': {'success': True},
            }
        ])
        row = dataset['rows'][0]
        self.assertEqual(row['recommendation_alignment'], 'in_candidates')
        self.assertEqual(row['selected_candidate_rank'], 2)
        self.assertEqual(row['top_recommended_candidate']['template_id'], 'impl_team')
        self.assertEqual(row['recommended_candidates'][1]['template_id'], 'review_team')
        self.assertIn('feature_score_breakdown', row['recommended_candidates'][0])
        summary = dataset['selection_outcome_summary']
        self.assertEqual(summary['alignment_counts']['in_candidates'], 1)
        self.assertAlmostEqual(summary['success_rate_by_alignment']['in_candidates'], 1.0)
        self.assertEqual(summary['alignment_event_samples']['in_candidates'][0]['event_id'], 'evt-1')

    def test_serialize_team_selection_dataset_jsonl_omits_excluded_rows(self) -> None:
        text = serialize_team_selection_dataset_jsonl([
            {
                'id': 'evt-1',
                'selected_blueprint_id': 'impl_team',
                'recommendation': {'candidates': [{'template_id': 'impl_team', 'task_archetype': 'implementation'}]},
            },
            {
                'id': 'evt-2',
                'selected_blueprint_id': 'missing_team',
                'recommendation': {'candidates': [{'template_id': 'impl_team', 'task_archetype': 'implementation'}]},
            },
        ])
        lines = [line for line in text.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        self.assertIn('impl_team', lines[0])



    def test_dataset_preserves_user_orchestration_intent_features_without_optional_blueprints(self) -> None:
        dataset = build_team_selection_dataset([
            {
                'id': 'evt-user-intent-core',
                'task_text': 'Simple edit, but do it as a writer reviewer team',
                'selected_blueprint_id': 'review_team',
                'recommendation': {
                    'candidates': [
                        {
                            'template_id': 'review_team',
                            'title': 'Review Team',
                            'task_archetype': 'writing',
                            'score': 9,
                            'user_orchestration_intent': {
                                'team_intent': 'explicit',
                                'team_style': 'review',
                                'required_roles': ['reviewer'],
                                'min_team_size': 2,
                                'debt_policy': 'user_requested_overhead',
                            },
                            'skeleton_advisory': {
                                'status': 'ok',
                                'labels': {'Y_UTIL': 'good', 'Y_DEBT': 'med'},
                            },
                        },
                    ],
                },
            }
        ])
        feature = dataset['rows'][0]['selected_features']
        self.assertEqual(feature['user_orchestration_intent']['team_intent'], 'explicit')
        self.assertEqual(feature['user_orchestration_intent']['team_style'], 'review')
        self.assertEqual(feature['user_orchestration_intent']['required_roles'], ['reviewer'])


@unittest.skipIf(_TEAM_BLUEPRINT_IMPORT_ERROR is not None, f"optional dependency missing: {_TEAM_BLUEPRINT_IMPORT_ERROR}")
class TeamRecommenderLogicTest(unittest.TestCase):
    def test_recommendation_prefers_implementation_for_code_task(self) -> None:
        payload = recommend_team_blueprints('Implement a code patch in the repo and verify it', limit=2)
        self.assertEqual(payload['kind'], 'team_composer_recommendation_v1')
        self.assertGreaterEqual(payload['candidate_count'], 1)
        first = payload['candidates'][0]
        self.assertEqual(first['task_archetype'], 'implementation')
        self.assertIn('manifest', first)
        self.assertIn('executable_definition', first)
        self.assertIn('feature_score_breakdown', first)
        self.assertGreaterEqual(first['feature_score_breakdown']['implementation_boost'], 0)

    def test_blueprint_doc_includes_executable_definition(self) -> None:
        template = list_team_blueprint_templates()[0]
        doc = _manifest_to_blueprint_doc(template)
        summary = doc.get('summary') or {}
        blueprint = doc.get('blueprint') or {}
        self.assertIn('memory_governance_policy', summary)
        self.assertIn('executable_team_definition', summary)
        self.assertIn('memory_governance_policy', blueprint)
        self.assertIn('interaction_topology_contract', blueprint)

    def test_dataset_preserves_skeleton_advisory_features(self) -> None:
        dataset = build_team_selection_dataset([
            {
                'id': 'evt-advisory',
                'task_text': 'Patch the repo and verify the artifact',
                'selected_blueprint_id': 'review_team',
                'recommendation': {
                    'candidates': [
                        {
                            'template_id': 'review_team',
                            'title': 'Review Team',
                            'task_archetype': 'implementation',
                            'score': 9,
                            'skeleton_advisory': {
                                'status': 'ok',
                                'source': 'mock',
                                'labels': {
                                    'Y_UTIL': 'good',
                                    'Y_DEBT': 'med',
                                    'Y_FRONTIER_NEEDED': 'no',
                                },
                                'capacity_gaps': ['reviewer'],
                                'warnings': ['predicted_team_debt_high'],
                            },
                        },
                    ],
                },
                'outcome': {'success': True},
            }
        ])
        feature = dataset['rows'][0]['selected_features']
        self.assertEqual(feature['skeleton_advisory']['utility_label'], 'good')
        self.assertEqual(feature['skeleton_advisory']['debt_label'], 'med')
        self.assertEqual(feature['skeleton_advisory']['capacity_gaps'], ['reviewer'])
        summary = dataset['selection_outcome_summary']
        self.assertEqual(summary['advisory_status_counts']['ok'], 1)
        self.assertEqual(summary['advisory_debt_counts']['med'], 1)
        self.assertEqual(summary['advisory_capacity_gap_counts']['reviewer'], 1)

    def test_dataset_preserves_user_orchestration_intent_features(self) -> None:
        dataset = build_team_selection_dataset([
            {
                'id': 'evt-user-intent',
                'task_text': 'Simple edit, but do it as a writer reviewer team',
                'selected_blueprint_id': 'review_team',
                'recommendation': {
                    'candidates': [
                        {
                            'template_id': 'review_team',
                            'title': 'Review Team',
                            'task_archetype': 'writing',
                            'score': 9,
                            'user_orchestration_intent': {
                                'team_intent': 'explicit',
                                'team_style': 'review',
                                'required_roles': ['reviewer'],
                                'min_team_size': 2,
                                'debt_policy': 'user_requested_overhead',
                            },
                            'score_detail': {},
                            'score': 9,
                            'skeleton_advisory': {
                                'status': 'ok',
                                'labels': {'Y_UTIL': 'good', 'Y_DEBT': 'med'},
                            },
                            'score': 9,
                            'score_payload': {},
                        },
                    ],
                },
                'outcome': {'success': True},
            }
        ])
        feature = dataset['rows'][0]['selected_features']
        self.assertEqual(feature['user_orchestration_intent']['team_intent'], 'explicit')
        self.assertEqual(feature['user_orchestration_intent']['team_style'], 'review')
        self.assertEqual(feature['user_orchestration_intent']['required_roles'], ['reviewer'])



if __name__ == '__main__':
    unittest.main()

class TeamAttemptMemoryImportLogicTest(unittest.TestCase):
    def test_dataset_preserves_task_attempt_and_memory_import_features(self) -> None:
        dataset = build_team_selection_dataset([
            {
                'id': 'evt-branch-memory',
                'task_text': 'Retry same topic with paper team and exclude the previous result',
                'selected_blueprint_id': 'paper_team',
                'task_attempt_plan': {
                    'task_id': 'task-1',
                    'attempt_id': 'attempt-2',
                    'parent_attempt_id': 'attempt-1',
                    'run_mode': 'branch',
                    'retry_reason': 'user_dissatisfied',
                    'target_team': 'paper',
                    'previous_result_policy': 'exclude',
                    'context_policy': {
                        'include_original_user_request': True,
                        'include_previous_result': False,
                        'include_memory_package': True,
                    },
                    'memory_import': {
                        'import_intent': 'explicit',
                        'topic': 'current_topic',
                        'target_team': 'paper',
                        'projection_profile': 'paper',
                        'mode': 'snapshot',
                        'scope': 'current_topic',
                        'previous_result_policy': 'exclude',
                    },
                },
                'recommendation': {
                    'candidates': [
                        {
                            'template_id': 'paper_team',
                            'title': 'Paper Team',
                            'task_archetype': 'writing',
                            'score': 11,
                            'task_attempt_plan': {
                                'run_mode': 'branch',
                                'target_team': 'paper',
                                'previous_result_policy': 'exclude',
                            },
                            'memory_import_intent': {
                                'import_intent': 'explicit',
                                'projection_profile': 'paper',
                                'mode': 'snapshot',
                            },
                            'target_team': 'paper',
                        },
                    ],
                },
                'outcome': {'success': True},
            }
        ])
        row = dataset['rows'][0]
        self.assertEqual(row['task_attempt_plan']['run_mode'], 'branch')
        self.assertEqual(row['task_attempt_plan']['target_team'], 'paper')
        self.assertEqual(row['memory_import_intent']['projection_profile'], 'paper')
        self.assertEqual(row['selected_features']['target_team'], 'paper')
        self.assertEqual(row['selected_features']['memory_import_intent']['import_intent'], 'explicit')
        summary = dataset['selection_outcome_summary']
        self.assertEqual(summary['attempt_run_mode_counts']['branch'], 1)
        self.assertEqual(summary['memory_import_profile_counts']['paper'], 1)

    def test_dataset_preserves_work_mode_features(self) -> None:
        dataset = build_team_selection_dataset([
            {
                'id': 'evt-work-mode',
                'task_text': 'Run this as a Research Campaign with staged checkpoints',
                'selected_blueprint_id': 'research_campaign_team',
                'work_mode': {
                    'work_mode': 'research_campaign',
                    'label': 'Research Campaign',
                    'context_depth': 'structured',
                    'loop_budget': 'staged',
                    'stop_condition': 'user_checkpoint',
                    'review_policy': 'stage_gate',
                    'memory_mode': 'structured',
                    'goc_mode': 'required',
                    'reason_codes': ['explicit_work_mode_text'],
                },
                'task_attempt_plan': {
                    'run_mode': 'new',
                    'work_mode': {
                        'work_mode': 'research_campaign',
                        'loop_budget': 'staged',
                        'review_policy': 'stage_gate',
                        'memory_mode': 'structured',
                        'goc_mode': 'required',
                    },
                    'cycle_policy': {'cycle_shape': 'staged_checkpoints'},
                },
                'recommendation': {
                    'candidates': [
                        {
                            'template_id': 'research_campaign_team',
                            'title': 'Research Campaign Team',
                            'task_archetype': 'research',
                            'score': 12,
                            'work_mode': {
                                'work_mode': 'research_campaign',
                                'loop_budget': 'staged',
                                'review_policy': 'stage_gate',
                                'memory_mode': 'structured',
                                'goc_mode': 'required',
                            },
                            'work_mode_satisfaction': {'satisfied': True, 'reason': 'research_campaign_staged_team'},
                        },
                    ],
                },
                'outcome': {'success': True},
            }
        ])
        row = dataset['rows'][0]
        self.assertEqual(row['work_mode']['work_mode'], 'research_campaign')
        self.assertEqual(row['work_mode']['loop_budget'], 'staged')
        self.assertEqual(row['task_attempt_plan']['work_mode']['goc_mode'], 'required')
        self.assertEqual(row['selected_features']['work_mode']['review_policy'], 'stage_gate')
        self.assertEqual(row['selected_features']['work_mode_satisfaction']['satisfied'], True)
        summary = dataset['selection_outcome_summary']
        self.assertEqual(summary['work_mode_counts']['research_campaign'], 1)
        self.assertEqual(summary['work_mode_review_policy_counts']['stage_gate'], 1)

