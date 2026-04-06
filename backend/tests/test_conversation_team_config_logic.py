import unittest

try:
    from sqlmodel import SQLModel, Session
    from tests.db_test_utils import create_test_engine as create_engine
    from app.models import Conversation, ConversationTeamConfig, ConversationTeamConfigRevision
    from app.services import conversation_team_config
    from app.services.conversation_team_config import get_team_config_payload, save_team_config_payload, patch_team_config_agent_context_policy
    SQLMODEL_AVAILABLE = True
except Exception:
    conversation_team_config = None
    SQLMODEL_AVAILABLE = False


@unittest.skipUnless(SQLMODEL_AVAILABLE, 'sqlmodel not available in this environment')
class ConversationTeamConfigLogicTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        SQLModel.metadata.create_all(self.engine)

    def test_save_and_load_team_config_payload(self):
        with Session(self.engine) as session:
            conv = Conversation(thread_id='thread-1', owner_user_id='user-1', service_id='default')
            session.add(conv)
            session.commit()
            payload = save_team_config_payload(session, thread_id='thread-1', payload={
                'status': 'active',
                'composition_mode': 'freeform',
                'proposal_mode': 'create',
                'active_team': {'team_name': 'demo', 'composition_mode': 'freeform', 'proposal_mode': 'create', 'agents': [{'agent_id': 'researcher'}]},
                'pending_team': {},
            })
            self.assertEqual(payload['status'], 'active')
            self.assertEqual(payload['composition_mode'], 'freeform')
            loaded = get_team_config_payload(session, thread_id='thread-1')
            self.assertEqual(loaded['active_team'].get('team_name'), 'demo')
            self.assertEqual(loaded['composition_mode'], 'freeform')
            revisions = session.query(ConversationTeamConfigRevision).all()
            self.assertEqual(len(revisions), 1)

    def test_patch_agent_context_policy_updates_grants_and_budget(self):
        with Session(self.engine) as session:
            conv = Conversation(thread_id='thread-2', owner_user_id='user-1', service_id='default')
            session.add(conv)
            session.commit()
            save_team_config_payload(session, thread_id='thread-2', payload={
                'status': 'suggested',
                'composition_mode': 'freeform',
                'proposal_mode': 'create',
                'active_team': {},
                'pending_team': {
                    'team_name': 'proposal',
                    'composition_mode': 'freeform',
                    'proposal_mode': 'create',
                    'agents': [
                        {
                            'agent_id': 'news_researcher',
                            'name': 'News Researcher',
                            'context_policy': {
                                'base_mode': 'scoped_context',
                                'reads': {'grants': ['shared_summary'], 'context_types': ['news']},
                                'writes': {'publish_targets': ['evidence_bundle']},
                            },
                        }
                    ],
                },
            })
            payload = patch_team_config_agent_context_policy(
                session,
                thread_id='thread-2',
                team_state='pending',
                agent_id='news_researcher',
                visibility_mode='shared_memory',
                grants=['shared_summary', 'upstream_summaries', 'bogus_grant'],
                context_types=['news', 'evidence'],
                publish_targets=['handoff_summary'],
                query_template='recent events and guidance',
                soft_tokens=2100,
                hard_tokens=3200,
            )
            agent = payload['pending_team']['agents'][0]
            policy = agent['context_policy']
            self.assertEqual(policy['base_mode'], 'shared_memory')
            self.assertEqual(policy['reads']['grants'], ['shared_summary', 'upstream_summaries'])
            self.assertEqual(policy['reads']['context_types'], ['news', 'evidence'])
            self.assertEqual(policy['writes']['publish_targets'], ['handoff_summary'])
            self.assertEqual(policy['reads']['query_template'], 'recent events and guidance')
            self.assertEqual(policy['default_budget']['soft_tokens'], 2100)
            self.assertEqual(policy['default_budget']['hard_tokens'], 3200)



if __name__ == '__main__':
    unittest.main()


class TeamConfigNormalizationTests(unittest.TestCase):
    def test_normalizes_status_and_clears_none_payloads(self):
        if conversation_team_config is None:
            self.skipTest('sqlmodel unavailable')
        normalize = getattr(conversation_team_config, '_normalize_team_config_payload')
        payload = normalize({'status': 'NONE', 'active_team': {'team_name': 'x'}, 'pending_team': {'team_name': 'y'}})
        self.assertEqual(payload['status'], 'none')
        self.assertEqual(payload['active_team'], {})
        self.assertEqual(payload['pending_team'], {})

    def test_normalizes_invalid_status_by_payload_shape(self):
        if conversation_team_config is None:
            self.skipTest('sqlmodel unavailable')
        normalize = getattr(conversation_team_config, '_normalize_team_config_payload')
        payload = normalize({'status': 'weird', 'active_team': {'team_name': 'x'}})
        self.assertEqual(payload['status'], 'active')
        self.assertEqual(payload['active_team']['team_name'], 'x')


class TeamConfigModeNormalizationTests(unittest.TestCase):
    def test_normalizes_modes_from_team_payload(self):
        if conversation_team_config is None:
            self.skipTest('sqlmodel unavailable')
        normalize = getattr(conversation_team_config, '_normalize_team_config_payload')
        payload = normalize({'status': 'active', 'active_team': {'composition_mode': 'freeform', 'proposal_mode': 'create'}})
        self.assertEqual(payload['composition_mode'], 'freeform')
        self.assertEqual(payload['proposal_mode'], 'create')

