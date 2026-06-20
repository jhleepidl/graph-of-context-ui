import importlib.util
import unittest

HAS_SQLMODEL = importlib.util.find_spec('sqlmodel') is not None


@unittest.skipUnless(HAS_SQLMODEL, 'sqlmodel not installed')
class RoomPackagesLogicTest(unittest.TestCase):
    def test_sanitize_room_package_forces_share_safe_boundary(self):
        from app.services.room_packages import sanitize_room_package

        pkg = sanitize_room_package({
            'package_id': 'research-room',
            'title': 'Research Room',
            'visibility': 'public',
            'domain_label': 'research_paper',
            'agents': ['idea_expander', 'novelty_critic'],
            'memory_schema': {
                'object_types': ['claims', 'related_work'],
                'copies_private_memory': True,
            },
            'context_policy': {
                'private_memory': 'copy_all',
            },
            'private_memory_content': 'do not copy',
            'credentials': {'API_KEY': 'secret'},
            'examples': [{'user': 'make this idea stronger', 'room': 'compare framings'}],
        })
        self.assertEqual(pkg['kind'], 'shared_room_package_v1')
        self.assertFalse(pkg['memory_schema']['copies_private_memory'])
        self.assertFalse(pkg['context_policy']['shared_package_copies_private_memory'])
        self.assertFalse(pkg['safety_report']['copies_private_memory'])
        self.assertEqual(pkg['install_policy']['private_memory'], 'fresh_on_install')
        self.assertNotIn('private_memory_content', pkg)
        self.assertNotIn('credentials', pkg)
        self.assertEqual(pkg['domain_label'], 'research_paper')
        self.assertEqual(pkg['examples'][0]['user'], 'make this idea stronger')


if __name__ == '__main__':
    unittest.main()
