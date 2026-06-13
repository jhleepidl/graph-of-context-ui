import importlib.util
import unittest

HAS_SQLMODEL = importlib.util.find_spec('sqlmodel') is not None


@unittest.skipUnless(HAS_SQLMODEL, 'sqlmodel not installed')
class TeamPackagesLogicTest(unittest.TestCase):
    def test_sanitize_team_package_forces_safe_clone_policy(self):
        from app.services.team_packages import sanitize_team_package

        pkg = sanitize_team_package({
            'package_id': 'demo',
            'title': 'Demo Team',
            'visibility': 'public',
            'clone_policy': {'private_memory': 'copy', 'credential_binding': 'copy'},
            'memory_contract': {
                'copies_private_memory': True,
                'required_surfaces': [{'surface_id': 'drafts', 'content_policy': 'schema_only'}],
                'private_exclusions': [{'surface_id': 'user_notes', 'label': 'User Notes'}],
            },
            'team_seed': {
                'team_name': 'Demo Team',
                'credentials': {'API_KEY': 'secret'},
                'provider_state': {'session': 'private'},
                'agents': [{'agent_id': 'writer', 'role': 'synthesizer'}],
            },
        })
        self.assertEqual(pkg['kind'], 'shared_team_package_v1')
        self.assertFalse(pkg['memory_contract']['copies_private_memory'])
        self.assertEqual(pkg['clone_policy']['private_memory'], 'fresh_on_clone')
        self.assertEqual(pkg['clone_policy']['credential_binding'], 'never_copy')
        self.assertNotIn('credentials', pkg['team_seed'])
        self.assertNotIn('provider_state', pkg['team_seed'])


if __name__ == '__main__':
    unittest.main()
