import unittest

try:
    from fastapi.testclient import TestClient
    from sqlmodel import SQLModel, Session

    from app.db import get_session
    from app.main import app
    from app.models import Agent, User
    from app.routers import agents as agents_router
    from tests.db_test_utils import create_test_engine, dispose_tracked_engines
except ModuleNotFoundError as exc:  # pragma: no cover - dependency may be absent in sandbox
    TestClient = None
    SQLModel = None
    Session = None
    app = None
    Agent = None
    User = None
    agents_router = None
    create_test_engine = None
    dispose_tracked_engines = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


@unittest.skipIf(_IMPORT_ERROR is not None, f"missing dependency: {_IMPORT_ERROR}")
class AgentForkLineageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_test_engine()
        SQLModel.metadata.create_all(self.engine)
        app.dependency_overrides[get_session] = lambda: Session(self.engine)
        self.original_engine = agents_router.engine
        agents_router.engine = self.engine
        with Session(self.engine) as session:
            user = User(telegram_user_id='tg1', username='tester')
            session.add(user)
            session.flush()
            agent = Agent(owner_user_id=user.id, service_id='default', name='Builder', description='src', system_prompt='sp', instruction='inst', tools_json='["bash"]', model='gpt', visibility='private')
            session.add(agent)
            session.commit()
            self.user_id = user.id
            self.agent_id = agent.id
        self.client = TestClient(app)

    def tearDown(self):
        agents_router.engine = self.original_engine
        app.dependency_overrides.clear()
        try:
            self.client.close()
        except Exception:
            pass
        dispose_tracked_engines()

    def _headers(self):
        return {'X-Admin-Key': 'dev-admin-key'}

    def test_fork_and_rejoin_record_lineage(self):
        fork = self.client.post(f'/api/agents/{self.agent_id}/fork', json={
            'visibility': 'private',
            'reason': 'isolate risky patch',
            'purpose': 'patch db migration',
            'scope': {'mode': 'unfold_query', 'query': 'migration'},
            'scope_node_ids': ['n1', 'n2'],
            'source_surface_ids': ['plan'],
            'publish_surface_ids': ['artifact_index'],
            'rejoin_strategy': 'manual',
        }, headers=self._headers())
        self.assertEqual(fork.status_code, 200, fork.text)
        payload = fork.json()
        forked_id = payload['agent']['id']
        self.assertEqual(payload['fork']['source_agent_id'], self.agent_id)
        self.assertEqual(payload['fork']['forked_agent_id'], forked_id)
        self.assertEqual(payload['fork']['scope_mode'], 'unfold_query')

        rejoin = self.client.post(f'/api/agents/{forked_id}/rejoin', json={
            'summary': 'validated and merged',
            'publish_surface_ids': ['final_answer'],
            'artifact_ids': ['artifact-1'],
        }, headers=self._headers())
        self.assertEqual(rejoin.status_code, 200, rejoin.text)
        rejoin_payload = rejoin.json()
        self.assertEqual(rejoin_payload['fork']['rejoin_status'], 'rejoined')
        self.assertEqual(rejoin_payload['fork']['rejoin_summary'], 'validated and merged')

        lineage = self.client.get(f'/api/agents/{forked_id}/fork-lineage', headers=self._headers())
        self.assertEqual(lineage.status_code, 200, lineage.text)
        lineage_payload = lineage.json()
        self.assertEqual(lineage_payload['fork']['forked_agent_id'], forked_id)
        self.assertEqual(lineage_payload['forked_agent']['id'], forked_id)
        self.assertEqual(lineage_payload['source_agent']['id'], self.agent_id)


if __name__ == '__main__':
    unittest.main()
