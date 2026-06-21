import unittest

from app.services.room_learning import build_room_learning_snapshot


class RoomUsageLearningLogicTest(unittest.TestCase):
    def test_repeated_ask_same_domain_recommends_team_upgrade_without_private_memory_copy(self):
        items = [
            {'event_type': 'work_depth_used', 'command': '/ask', 'domain_label': 'creative_writing', 'payload': {'extra': {'depth': 'ask'}}},
            {'event_type': 'work_depth_used', 'command': '/ask', 'domain_label': 'creative_writing', 'payload': {'extra': {'depth': 'ask'}}},
            {'event_type': 'work_depth_used', 'command': '/ask', 'domain_label': 'creative_writing', 'payload': {'extra': {'depth': 'ask'}}},
        ]
        snapshot = build_room_learning_snapshot(items)
        self.assertEqual(snapshot['top_domain'], 'creative_writing')
        self.assertEqual(snapshot['recommended_depth'], 'team_task')
        self.assertTrue(any(row['action'] == 'offer_team_task_upgrade' for row in snapshot['suggested_actions']))
        self.assertFalse(snapshot['component_reuse_policy']['copy_private_memory'])

    def test_loop_usage_recommends_team_loop_task(self):
        snapshot = build_room_learning_snapshot([
            {'event_type': 'work_depth_used', 'command': '/loop', 'domain_label': 'research_paper', 'payload': {'extra': {'depth': 'loop'}}},
        ])
        self.assertEqual(snapshot['recommended_depth'], 'team_loop_task')
        self.assertIn('loop_usage_observed', snapshot['reason_codes'])


if __name__ == '__main__':
    unittest.main()
