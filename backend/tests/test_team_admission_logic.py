import unittest

from app.services.team_admission import (
    build_memory_acl_summary,
    build_team_capability_contract,
    compile_team_admission_decision,
)
from app.services.runtime_snapshot import normalize_blueprint_summary


class TeamAdmissionLogicTests(unittest.TestCase):
    def test_team_admission_helpers_expose_admission_and_memory_acl(self):
        team = {
            'agents': [
                {
                    'agent_id': 'builder',
                    'name': 'Builder',
                    'role': 'builder',
                    'purpose': 'Implement python file patch',
                    'runtime_capabilities_required': ['filesystem_write'],
                },
                {
                    'agent_id': 'synth',
                    'name': 'Synth',
                    'role': 'synthesizer',
                },
            ],
            'requirements': {
                'required_tools': ['filesystem_write'],
                'optional_tools': ['web_search'],
            },
        }
        contract = build_team_capability_contract(team)
        decision = compile_team_admission_decision(contract)
        acl = build_memory_acl_summary(
            {
                'surfaces': [
                    {'surface_id': 'plan', 'load_policy': 'required'},
                    {'surface_id': 'change_log', 'write_policy': 'append'},
                    {'surface_id': 'final_answer'},
                    {'surface_id': 'artifact_index'},
                ]
            },
            team['agents'],
            [],
        )
        self.assertEqual(decision['status'], 'unbound')
        self.assertEqual(decision['decision'], 'defer')
        self.assertFalse(decision['runtime_bound'])
        self.assertIn('missing_required_tools', decision['blocking_reason_codes'])
        self.assertTrue(any(item.get('role_id') == 'builder' for item in acl))

    def test_runtime_snapshot_normalizes_false_runtime_bound(self):
        summary = normalize_blueprint_summary({
            'title': 'Test Team',
            'runtime_bound': False,
            'admission_status': 'unbound',
            'admission_decision': 'defer',
            'memory_acl_summary': [
                {
                    'role_id': 'builder',
                    'read_surface_ids': ['plan'],
                    'write_surface_ids': ['change_log'],
                    'publish_surface_ids': ['artifact_index'],
                    'can_publish_final_answer': False,
                    'can_publish_artifact_index': True,
                }
            ],
        })
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertIn('runtime_bound', summary)
        self.assertFalse(summary['runtime_bound'])
        self.assertEqual(summary['admission_status'], 'unbound')
        self.assertEqual(summary['memory_acl_summary'][0]['role_id'], 'builder')
        self.assertFalse(summary['memory_acl_summary'][0]['can_publish_final_answer'])


if __name__ == '__main__':
    unittest.main()
