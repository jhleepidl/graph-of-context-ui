import unittest

from app.services.memory_graph import build_memory_projection, normalize_memory_surfaces, summarize_memory_projection
try:
    from app.services.team_recommender import recommend_team_blueprints
except Exception:
    recommend_team_blueprints = None


class MemoryGraphLogicTests(unittest.TestCase):
    def test_memory_projection_filters_by_role(self):
        surfaces = normalize_memory_surfaces([
            {'surface_id': 'plan', 'target_roles': ['builder', 'reviewer']},
            {'surface_id': 'review_notes', 'target_roles': ['reviewer']},
            {'surface_id': 'private_working_memory', 'target_roles': ['builder']},
        ])
        projection = build_memory_projection(
            role_id='builder',
            agent_id='builder_1',
            surfaces=surfaces,
            nodes=[
                {'id': 'n1', 'surface_id': 'plan'},
                {'id': 'n2', 'surface_id': 'review_notes'},
                {'id': 'n3', 'surface_id': 'private_working_memory'},
            ],
        )
        summary = summarize_memory_projection(projection)
        self.assertIn('plan', projection['visible_surface_ids'])
        self.assertIn('private_working_memory', projection['visible_surface_ids'])
        self.assertIn('review_notes', projection['blocked_surface_ids'])
        self.assertEqual(summary['visible_node_count'], 2)
        self.assertEqual(summary['blocked_node_count'], 1)

    def test_team_recommender_returns_executable_candidates(self):
        if recommend_team_blueprints is None:
            self.skipTest('team_recommender dependencies unavailable in this environment')
        try:
            result = recommend_team_blueprints('implement a repository patch and review it', limit=2)
        except ModuleNotFoundError:
            self.skipTest('team_recommender template dependencies unavailable in this environment')
        self.assertEqual(result['kind'], 'team_composer_recommendation_v1')
        self.assertGreaterEqual(result['candidate_count'], 1)
        first = result['candidates'][0]
        self.assertIn('memory_fit', first)
        self.assertIn('topology', first)


if __name__ == '__main__':
    unittest.main()
