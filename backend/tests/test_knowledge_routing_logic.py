import unittest

from app.services.knowledge_routing import summarize_knowledge_route_event, summarize_knowledge_route_events


class KnowledgeRoutingLogicTests(unittest.TestCase):
    def test_summarize_route_event_marks_artifact_attention(self) -> None:
        row = summarize_knowledge_route_event({
            'route': 'standard_workbench',
            'signals': ['artifact_reference_intent'],
            'knowledge_surfaces': ['artifact_memory', 'room_memory'],
            'model_policy': {'provider': 'antigravity'},
            'executor': 'direct_ask_fast_path',
            'outcome': 'answered_direct_fast_path',
            'query_excerpt': '전에 올린 메뉴 이미지 기준으로 추천해줘',
        })
        self.assertEqual(row['knowledge_surfaces'], ['artifact_memory', 'room_memory'])
        self.assertTrue(row['needs_attention'])
        self.assertEqual(row['provider'], 'antigravity')
        self.assertEqual(row['executor'], 'direct_ask_fast_path')
        self.assertEqual(row['outcome'], 'answered_direct_fast_path')

    def test_summarize_route_events_counts_surfaces(self) -> None:
        summary = summarize_knowledge_route_events([
            {'route': 'concierge_direct_answer', 'knowledge_surfaces': ['model_prior']},
            {'route': 'standard_workbench', 'knowledge_surfaces': ['artifact_memory', 'room_memory']},
        ])
        self.assertEqual(summary['event_count'], 2)
        self.assertEqual(summary['by_surface']['model_prior'], 1)
        self.assertEqual(summary['by_surface']['artifact_memory'], 1)
        self.assertEqual(summary['by_outcome']['unknown'], 2)


if __name__ == '__main__':
    unittest.main()
