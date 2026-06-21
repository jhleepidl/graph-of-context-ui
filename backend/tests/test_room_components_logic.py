import importlib.util
import unittest

from app.services.room_components import (
    augment_room_package_with_components,
    build_room_components,
    create_borrowed_agent_invocation,
    recommend_borrowed_agents,
)

HAS_SQLMODEL = importlib.util.find_spec('sqlmodel') is not None


class RoomComponentsPureLogicTest(unittest.TestCase):
    def test_borrow_invocation_is_projection_only(self):
        pkg = augment_room_package_with_components({
            'package_id': 'creative_room',
            'title': 'Creative Room',
            'domain_label': 'creative_writing',
            'agents': ['draft_writer', 'canon_reviewer'],
            'memory_schema': {'object_types': ['characters', 'canon_facts']},
            'private_memory_content': {'secret': 'do not copy'},
        })
        invocation = create_borrowed_agent_invocation(
            source_room_package=pkg,
            agent_id='canon_reviewer',
            target_room_id='target_room',
        )
        self.assertEqual(invocation['kind'], 'borrowed_agent_invocation_v1')
        self.assertFalse(invocation['memory_access']['read_source_private_memory'])
        self.assertFalse(invocation['memory_access']['write_memory'])
        self.assertTrue(invocation['memory_access']['allow_propose_update'])
        self.assertFalse(invocation['lineage']['copied_private_memory'])
        self.assertNotIn('do not copy', str(invocation))

    def test_recommend_borrowed_agents_from_component_library(self):
        pkg = augment_room_package_with_components({
            'package_id': 'creative_room',
            'title': 'Creative Room',
            'domain_label': 'creative_writing',
            'agents': ['draft_writer', 'canon_reviewer', 'continuity_checker'],
        })
        result = recommend_borrowed_agents(
            task_text='이 팬픽 줄거리에서 캐릭터 말투와 설정 모순을 찾아줘',
            package_items=[{'package': pkg}],
            target_room_id='target_room',
        )
        self.assertTrue(result['ok'])
        self.assertTrue(any(item['invocation']['agent_id'] in {'canon_reviewer', 'continuity_checker'} for item in result['items']))

    def test_build_room_components_contains_policy_cards(self):
        library = build_room_components({
            'package_id': 'paper_room',
            'domain_label': 'research_paper',
            'agents': ['related_work_scout', 'novelty_critic'],
            'memory_schema': {'object_types': ['claims', 'related_work']},
        })
        types = {item['component_type'] for item in library['components']}
        self.assertIn('agent_card', types)
        self.assertIn('memory_schema_card', types)
        self.assertIn('context_policy_card', types)
        self.assertFalse(library['summary']['private_memory_copied'])


@unittest.skipUnless(HAS_SQLMODEL, 'sqlmodel not installed')
class RoomComponentsWithPackageSanitizerTest(unittest.TestCase):
    def test_room_package_sanitize_adds_composable_components(self):
        from app.services.room_packages import sanitize_room_package

        pkg = sanitize_room_package({
            'package_id': 'creative_room',
            'title': 'Creative Room',
            'domain_label': 'creative_writing',
            'agents': ['draft_writer', 'canon_reviewer'],
            'memory_schema': {'object_types': ['characters', 'canon_facts']},
            'private_memory_content': {'secret': 'do not copy'},
        })
        self.assertEqual(pkg['component_model'], 'composable_room_components_v1')
        self.assertEqual(pkg['components']['kind'], 'room_component_library_v1')
        self.assertTrue(any(agent['local_id'] == 'canon_reviewer' for agent in pkg['components']['agents']))
        self.assertFalse(pkg['composition_policy']['private_memory_copied'])
        self.assertNotIn('do not copy', str(pkg))


if __name__ == '__main__':
    unittest.main()
