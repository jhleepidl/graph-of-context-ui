import os
import unittest

try:
    from fastapi.testclient import TestClient
    from sqlmodel import SQLModel, Session, select

    from app.db import get_session
    from app.main import app
    from app.models import ContextSet, Node, Thread
    from app.routers import boards as boards_router
    from app.routers import skills as skills_router
    from tests.db_test_utils import create_test_engine, dispose_tracked_engines
except ModuleNotFoundError as exc:  # pragma: no cover
    TestClient = None
    SQLModel = None
    Session = None
    app = None
    Thread = None
    ContextSet = None
    Node = None
    boards_router = None
    skills_router = None
    create_test_engine = None
    dispose_tracked_engines = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

os.environ.setdefault('GOC_ADMIN_KEY', 'dev-admin-key')
os.environ.setdefault('GOC_UI_TOKEN_SECRET', 'dev-ui-token-secret')


@unittest.skipIf(_IMPORT_ERROR is not None, f"missing dependency: {_IMPORT_ERROR}")
class BoardHistoryLogicTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_test_engine()
        SQLModel.metadata.create_all(self.engine)
        app.dependency_overrides[get_session] = lambda: Session(self.engine)
        self.original_boards_engine = boards_router.engine
        self.original_skills_engine = skills_router.engine
        boards_router.engine = self.engine
        skills_router.engine = self.engine
        with Session(self.engine) as session:
            thread = Thread(title='board-thread')
            session.add(thread)
            session.commit()
            session.refresh(thread)
            context_set = ContextSet(thread_id=thread.id, name='default')
            session.add(context_set)
            session.commit()
            session.refresh(context_set)
            self.thread_id = thread.id
            self.context_set_id = context_set.id
        self.client = TestClient(app)

    def tearDown(self):
        boards_router.engine = self.original_boards_engine
        skills_router.engine = self.original_skills_engine
        app.dependency_overrides.clear()
        try:
            self.client.close()
        except Exception:
            pass
        dispose_tracked_engines()

    def _headers(self):
        return {'X-Admin-Key': 'dev-admin-key'}

    def test_raw_history_is_board_visible_but_excluded_from_learning(self):
        upsert = self.client.post(
            f'/api/threads/{self.thread_id}/raw_history',
            json={
                'title': 'Episode 1',
                'summary': 'chat state=running',
                'raw_text': 'secret_like_text should stay only in history lane',
                'chat_id': 'chat-1',
                'stream_key': 'chat:chat-1',
                'provenance': {
                    'runtime': {'thread_id': self.thread_id},
                    'skill_package': {
                        'id': 'skill.should_not_learn.v1',
                        'name': 'Should Not Learn',
                    },
                },
            },
            headers=self._headers(),
        )
        self.assertEqual(upsert.status_code, 200, upsert.text)
        payload = upsert.json()
        self.assertFalse(payload['updated'])

        board = self.client.get(f'/api/threads/{self.thread_id}/board', headers=self._headers())
        self.assertEqual(board.status_code, 200, board.text)
        board_payload = board.json()
        self.assertTrue(board_payload['policy']['raw_history_learning_excluded'])
        raw_lane = next((lane for lane in board_payload['lanes'] if lane['id'] == 'raw_history'), None)
        self.assertIsNotNone(raw_lane)
        self.assertEqual(raw_lane['cards'][0]['learning_excluded'], True)
        self.assertEqual(raw_lane['cards'][0]['privacy_class'], 'raw_history')

        listed = self.client.get(f'/api/skills?thread_id={self.thread_id}&include_defaults=false', headers=self._headers())
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()['count'], 0)

        candidate_lane = next((lane for lane in board_payload['lanes'] if lane['id'] == 'promotion_candidates'), None)
        self.assertIsNotNone(candidate_lane)
        candidate_kinds = {card['resource_kind'] for card in candidate_lane['cards']}
        self.assertIn('team_candidate', candidate_kinds)
        self.assertTrue(any(card['candidate_kind'] == 'team_blueprint' for card in candidate_lane['cards']))
        self.assertTrue(any(card['learning_excluded'] is True for card in candidate_lane['cards']))




    def test_approve_team_candidate_promotes_team_blueprint_in_thread(self):
        upsert = self.client.post(
            f'/api/threads/{self.thread_id}/raw_history',
            json={
                'title': 'Episode approve-team',
                'raw_text': 'team candidate snapshot',
                'chat_id': 'chat-team',
                'stream_key': 'chat:chat-team',
                'provenance': {
                    'active_team': {
                        'team_name': 'Patch Crew',
                        'agent_count': 2,
                        'roles': ['analyst', 'critic'],
                        'attached_skill_ids': ['skill.claim_evidence_audit.v1'],
                    },
                },
            },
            headers=self._headers(),
        )
        self.assertEqual(upsert.status_code, 200, upsert.text)
        board = self.client.get(f'/api/threads/{self.thread_id}/board', headers=self._headers())
        self.assertEqual(board.status_code, 200, board.text)
        lane = next((lane for lane in board.json()['lanes'] if lane['id'] == 'promotion_candidates'), None)
        self.assertIsNotNone(lane)
        team_card = next((card for card in lane['cards'] if card.get('candidate_kind') == 'team_blueprint'), None)
        self.assertIsNotNone(team_card)

        approved = self.client.post(
            f"/api/threads/{self.thread_id}/board/candidates/{team_card['id']}/approve",
            json={'publish_to_library': False},
            headers=self._headers(),
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()['promoted_resource_kind'], 'team_blueprint')

        board_after = self.client.get(f'/api/threads/{self.thread_id}/board', headers=self._headers())
        self.assertEqual(board_after.status_code, 200, board_after.text)
        board_payload = board_after.json()
        candidate_lane = next((lane for lane in board_payload['lanes'] if lane['id'] == 'promotion_candidates'), None)
        self.assertIsNotNone(candidate_lane)
        approved_card = next((card for card in candidate_lane['cards'] if card['id'] == team_card['id']), None)
        self.assertIsNotNone(approved_card)
        self.assertEqual(approved_card['review_status'], 'approved')
        self.assertEqual(approved_card['promotion_status'], 'promoted')
        asset_lane = next((lane for lane in board_payload['lanes'] if lane['id'] == 'team_assets'), None)
        self.assertIsNotNone(asset_lane)
        self.assertTrue(any(card.get('resource_kind') == 'team_blueprint' for card in asset_lane['cards']))

    def test_approve_skill_candidate_can_publish_to_public_library(self):
        upsert = self.client.post(
            f'/api/threads/{self.thread_id}/raw_history',
            json={
                'title': 'Episode approve-skill',
                'raw_text': 'skill candidate snapshot',
                'chat_id': 'chat-skill',
                'stream_key': 'chat:chat-skill',
                'extracted_artifacts': [
                    {
                        'kind': 'skill_package_reference',
                        'skill_id': 'skill.kskill_korean_stock_search.v1',
                        'source_phase': 'runtime',
                        'reason': 'observed in runtime',
                    },
                ],
            },
            headers=self._headers(),
        )
        self.assertEqual(upsert.status_code, 200, upsert.text)
        board = self.client.get(f'/api/threads/{self.thread_id}/board', headers=self._headers())
        self.assertEqual(board.status_code, 200, board.text)
        lane = next((lane for lane in board.json()['lanes'] if lane['id'] == 'promotion_candidates'), None)
        self.assertIsNotNone(lane)
        skill_card = next((card for card in lane['cards'] if card.get('candidate_kind') == 'skill_package'), None)
        self.assertIsNotNone(skill_card)

        approved = self.client.post(
            f"/api/threads/{self.thread_id}/board/candidates/{skill_card['id']}/approve",
            json={'publish_to_library': True},
            headers=self._headers(),
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()['published_to_library'], True)
        self.assertEqual(approved.json()['promoted_resource_kind'], 'skill_package')

        with Session(self.engine) as session:
            library_thread = session.exec(select(Thread).where(Thread.title == 'skills:library')).first()
            self.assertIsNotNone(library_thread)
            skill_nodes = session.exec(select(Node).where(Node.thread_id == library_thread.id, Node.type == 'Resource')).all()
            self.assertTrue(any('skill_package' in (row.payload_json or '') for row in skill_nodes))

        listed = self.client.get(f"/api/skills?thread_id={library_thread.id}&include_defaults=false", headers=self._headers())
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertGreaterEqual(listed.json()['count'], 1)

    def test_candidate_nodes_become_stale_when_structured_signals_disappear(self):
        first = self.client.post(
            f'/api/threads/{self.thread_id}/raw_history',
            json={
                'title': 'Episode 3',
                'raw_text': 'first snapshot with team candidate',
                'chat_id': 'chat-3',
                'stream_key': 'chat:chat-3',
                'provenance': {
                    'active_team': {
                        'team_name': 'Reviewers',
                        'agent_count': 2,
                        'roles': ['reviewer', 'critic'],
                        'attached_skill_ids': ['skill.review.v1'],
                    },
                },
            },
            headers=self._headers(),
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertGreaterEqual(first.json()['derived_candidates']['count'], 2)

        second = self.client.post(
            f'/api/threads/{self.thread_id}/raw_history',
            json={
                'title': 'Episode 3',
                'raw_text': 'second snapshot without extracted signals',
                'chat_id': 'chat-3',
                'stream_key': 'chat:chat-3',
                'provenance': {},
                'extracted_artifacts': [],
            },
            headers=self._headers(),
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertTrue(second.json()['updated'])

        board = self.client.get(f'/api/threads/{self.thread_id}/board', headers=self._headers())
        self.assertEqual(board.status_code, 200, board.text)
        lane = next((lane for lane in board.json()['lanes'] if lane['id'] == 'promotion_candidates'), None)
        self.assertIsNotNone(lane)
        self.assertTrue(any(card.get('stale') is True for card in lane['cards']))

    def test_upsert_updates_existing_stream_without_activating_context(self):
        first = self.client.post(
            f'/api/threads/{self.thread_id}/raw_history',
            json={
                'title': 'Episode 1',
                'raw_text': 'first snapshot',
                'chat_id': 'chat-2',
                'stream_key': 'chat:chat-2',
            },
            headers=self._headers(),
        )
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.post(
            f'/api/threads/{self.thread_id}/raw_history',
            json={
                'title': 'Episode 1',
                'raw_text': 'second snapshot',
                'chat_id': 'chat-2',
                'stream_key': 'chat:chat-2',
            },
            headers=self._headers(),
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertTrue(second.json()['updated'])

        with Session(self.engine) as session:
            rows = session.exec(select(Node).where(Node.thread_id == self.thread_id, Node.type == 'Resource')).all()
            self.assertGreaterEqual(len(rows), 1)
            import json
            raw_rows = []
            for row in rows:
                try:
                    payload = json.loads(row.payload_json or '{}')
                except Exception:
                    payload = {}
                if payload.get('resource_kind') == 'raw_history':
                    raw_rows.append(row)
            self.assertEqual(len(raw_rows), 1)
            self.assertIn('second snapshot', raw_rows[0].text)
            context_set = session.get(ContextSet, self.context_set_id)
            self.assertEqual(context_set.active_node_ids_json or '[]', '[]')


if __name__ == '__main__':
    unittest.main()
