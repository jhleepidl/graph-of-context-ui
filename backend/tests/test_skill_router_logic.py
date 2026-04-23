import os
import unittest

try:
    from fastapi.testclient import TestClient
    from sqlmodel import SQLModel, Session

    from app.db import get_session
    from app.main import app
    from app.models import ContextSet, Node, Thread
    from app.routers import skills as skills_router
    from app.services.run_studio import build_run_studio_audit_timeline
    from tests.db_test_utils import create_test_engine, dispose_tracked_engines
except ModuleNotFoundError as exc:  # pragma: no cover
    TestClient = None
    SQLModel = None
    Session = None
    app = None
    Thread = None
    ContextSet = None
    Node = None
    skills_router = None
    build_run_studio_audit_timeline = None
    create_test_engine = None
    dispose_tracked_engines = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

os.environ.setdefault('GOC_ADMIN_KEY', 'dev-admin-key')
os.environ.setdefault('GOC_UI_TOKEN_SECRET', 'dev-ui-token-secret')


@unittest.skipIf(_IMPORT_ERROR is not None, f"missing dependency: {_IMPORT_ERROR}")
class SkillRouterLogicTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_test_engine()
        SQLModel.metadata.create_all(self.engine)
        app.dependency_overrides[get_session] = lambda: Session(self.engine)
        self.original_engine = skills_router.engine
        skills_router.engine = self.engine
        with Session(self.engine) as session:
            source_thread = Thread(title='source-thread')
            target_thread = Thread(title='skills:catalog')
            session.add(source_thread)
            session.add(target_thread)
            session.commit()
            session.refresh(source_thread)
            session.refresh(target_thread)
            session.add(ContextSet(thread_id=source_thread.id, name='default'))
            session.add(ContextSet(thread_id=target_thread.id, name='default'))
            session.add(Node(
                thread_id=source_thread.id,
                type='Resource',
                text='{"id":"skill.test_shared.v1","name":"Test Shared Skill"}',
                payload_json='{"resource_kind":"skill_package","skill_package":{"id":"skill.test_shared.v1","name":"Test Shared Skill","version":"v1","description":"Shared through GoC","category":"testing","capability_tags":["share"],"compatible_roles":["analyst"],"execution_adapter":{"kind":"http_proxy","endpoint_env":"KSKILL_PROXY_BASE_URL"},"credential_requirements":[{"key":"KSKILL_PROXY_BASE_URL","required":false}],"trust_level":"reviewed","side_effect_level":"read_only","visibility":"public","status":"active"}}',
            ))
            session.commit()
            self.source_thread_id = source_thread.id
            self.target_thread_id = target_thread.id
        self.client = TestClient(app)

    def tearDown(self):
        skills_router.engine = self.original_engine
        app.dependency_overrides.clear()
        try:
            self.client.close()
        except Exception:
            pass
        dispose_tracked_engines()

    def _headers(self):
        return {'X-Admin-Key': 'dev-admin-key'}

    def test_skill_export_publish_and_install_roundtrip(self):
        listed = self.client.get(f'/api/skills?thread_id={self.source_thread_id}&include_defaults=false', headers=self._headers())
        self.assertEqual(listed.status_code, 200, listed.text)
        listed_payload = listed.json()
        self.assertEqual(listed_payload['count'], 1)
        self.assertEqual(listed_payload['items'][0]['id'], 'skill.test_shared.v1')

        exported = self.client.get(f'/api/skills/skill.test_shared.v1/export?thread_id={self.source_thread_id}', headers=self._headers())
        self.assertEqual(exported.status_code, 200, exported.text)
        exported_payload = exported.json()
        self.assertEqual(exported_payload['package']['id'], 'skill.test_shared.v1')
        self.assertEqual(exported_payload['package']['execution_adapter']['kind'], 'http_proxy')

        published = self.client.post('/api/skills/publish', json={
            'skill_id': 'skill.test_shared.v1',
            'thread_id': self.source_thread_id,
        }, headers=self._headers())
        self.assertEqual(published.status_code, 200, published.text)
        published_payload = published.json()
        self.assertEqual(published_payload['library_title'], 'skills:library')

        installed = self.client.post('/api/skills/install', json={
            'thread_id': self.target_thread_id,
            'skill_id': 'skill.test_shared.v1',
            'source_thread_id': self.source_thread_id,
        }, headers=self._headers())
        self.assertEqual(installed.status_code, 200, installed.text)
        installed_payload = installed.json()
        self.assertEqual(installed_payload['package']['id'], 'skill.test_shared.v1')

        with Session(self.engine) as session:
            from sqlmodel import select
            rows = session.exec(select(Node).where(Node.thread_id == self.target_thread_id, Node.type == 'Resource')).all()
            self.assertEqual(len(rows), 1)
            self.assertIn('skill_package', rows[0].payload_json)

    def test_run_studio_audit_timeline_regression_created_sort_key(self):
        with Session(self.engine) as session:
            thread = Thread(title='timeline-thread')
            session.add(thread)
            session.commit()
            session.refresh(thread)
            session.add(Node(thread_id=thread.id, type='Step', text='participant step', payload_json='{"role":"assistant"}'))
            session.commit()
            payload = build_run_studio_audit_timeline(session, thread=thread)
            self.assertTrue(isinstance(payload, dict))
            self.assertIn('items', payload)


if __name__ == '__main__':
    unittest.main()
