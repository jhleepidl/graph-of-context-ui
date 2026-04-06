from __future__ import annotations

import unittest

from app.services.team_recommender import recommend_team_blueprints
try:
    from app.services.team_blueprint import _manifest_to_blueprint_doc
    from app.services.team_blueprint_templates import list_team_blueprint_templates
    _TEAM_BLUEPRINT_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    _TEAM_BLUEPRINT_IMPORT_ERROR = exc


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
