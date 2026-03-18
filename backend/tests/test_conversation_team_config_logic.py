import unittest

try:
    from sqlmodel import SQLModel, Session, create_engine
    from app.models import Conversation, ConversationTeamConfig, ConversationTeamConfigRevision
    from app.services import conversation_team_config
    from app.services.conversation_team_config import get_team_config_payload, save_team_config_payload
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
                'active_team': {'team_name': 'demo', 'agents': [{'agent_id': 'researcher'}]},
                'pending_team': {},
            })
            self.assertEqual(payload['status'], 'active')
            loaded = get_team_config_payload(session, thread_id='thread-1')
            self.assertEqual(loaded['active_team'].get('team_name'), 'demo')
            revisions = session.query(ConversationTeamConfigRevision).all()
            self.assertEqual(len(revisions), 1)


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
