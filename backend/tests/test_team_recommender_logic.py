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
        self.assertEqual(dataset['schema_version'], 5)
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


if __name__ == '__main__':
    unittest.main()
