import os
import unittest

try:
    from fastapi.testclient import TestClient
    from sqlmodel import SQLModel, Session

    from app.db import get_session
    from app.main import app
    from app.models import ContextSet, Thread
    from app.routers import boards as boards_router
    from app.routers import improvement_jobs as improvement_jobs_router
    from tests.db_test_utils import create_test_engine, dispose_tracked_engines
except ModuleNotFoundError as exc:  # pragma: no cover
    TestClient = None
    SQLModel = None
    Session = None
    app = None
    Thread = None
    ContextSet = None
    boards_router = None
    improvement_jobs_router = None
    create_test_engine = None
    dispose_tracked_engines = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

os.environ.setdefault('GOC_ADMIN_KEY', 'dev-admin-key')
os.environ.setdefault('GOC_UI_TOKEN_SECRET', 'dev-ui-token-secret')


@unittest.skipIf(_IMPORT_ERROR is not None, f"missing dependency: {_IMPORT_ERROR}")
class ImprovementJobLogicTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_test_engine()
        SQLModel.metadata.create_all(self.engine)
        app.dependency_overrides[get_session] = lambda: Session(self.engine)
        self.original_boards_engine = boards_router.engine
        self.original_improvement_engine = improvement_jobs_router.engine
        boards_router.engine = self.engine
        improvement_jobs_router.engine = self.engine
        with Session(self.engine) as session:
            thread = Thread(title='improvement-thread')
            session.add(thread)
            session.commit()
            session.refresh(thread)
            context_set = ContextSet(thread_id=thread.id, name='default')
            session.add(context_set)
            session.commit()
            self.thread_id = thread.id
        self.client = TestClient(app)

    def tearDown(self):
        boards_router.engine = self.original_boards_engine
        improvement_jobs_router.engine = self.original_improvement_engine
        app.dependency_overrides.clear()
        try:
            self.client.close()
        except Exception:
            pass
        dispose_tracked_engines()

    def _headers(self):
        return {'X-Admin-Key': 'dev-admin-key'}

    def test_create_and_report_improvement_job_populates_board_lanes(self):
        created = self.client.post(
            f'/api/threads/{self.thread_id}/improvement_jobs',
            json={
                'title': 'Improve GoC board lane rendering',
                'target_repo': 'goc',
                'instruction': 'Inspect current board rendering and patch stale candidate pills.',
                'target_runtime': 'forge',
                'requested_by': 'telegram:100',
                'workspace_root': '/srv/goc-forge',
                'labels': ['telegram', 'self-improve'],
            },
            headers=self._headers(),
        )
        self.assertEqual(created.status_code, 200, created.text)
        job_id = created.json()['job']['payload']['job_id']

        repo_report = self.client.post(
            f'/api/threads/{self.thread_id}/improvement_jobs/{job_id}/report',
            json={
                'kind': 'repo_snapshot',
                'phase': 'history_loaded',
                'status': 'in_progress',
                'summary': 'forge workspace snapshot collected',
                'preview_text': 'branch=forge\nworkspace=/srv/goc-forge',
                'payload': {'git_available': False, 'workspace_root': '/srv/goc-forge'},
            },
            headers=self._headers(),
        )
        self.assertEqual(repo_report.status_code, 200, repo_report.text)

        code_diff = self.client.post(
            f'/api/threads/{self.thread_id}/improvement_jobs/{job_id}/report',
            json={
                'kind': 'code_diff',
                'phase': 'patch_applied',
                'status': 'applied',
                'summary': 'forge diff touched 2 files',
                'preview_text': 'src/app.js | 2 ++',
                'metrics': {'changed_file_count': 2},
            },
            headers=self._headers(),
        )
        self.assertEqual(code_diff.status_code, 200, code_diff.text)

        test_report = self.client.post(
            f'/api/threads/{self.thread_id}/improvement_jobs/{job_id}/report',
            json={
                'kind': 'test_report',
                'phase': 'tests_passed',
                'status': 'passed',
                'summary': 'backend unittest smoke passed',
                'preview_text': 'python -m unittest tests.test_board_history_logic ok',
                'metrics': {'passed': 2, 'failed': 0},
            },
            headers=self._headers(),
        )
        self.assertEqual(test_report.status_code, 200, test_report.text)

        board = self.client.get(f'/api/threads/{self.thread_id}/board', headers=self._headers())
        self.assertEqual(board.status_code, 200, board.text)
        lanes = {lane['id']: lane for lane in board.json()['lanes']}
        self.assertIn('improvement_jobs', lanes)
        self.assertIn('code_snapshots', lanes)
        self.assertIn('code_diffs', lanes)
        self.assertIn('test_reports', lanes)
        self.assertTrue(any(card.get('resource_kind') == 'improvement_job' for card in lanes['improvement_jobs']['cards']))
        self.assertTrue(any(card.get('resource_kind') == 'repo_snapshot' for card in lanes['code_snapshots']['cards']))
        self.assertTrue(any(card.get('resource_kind') == 'code_diff' for card in lanes['code_diffs']['cards']))
        self.assertTrue(any(card.get('resource_kind') == 'test_report' for card in lanes['test_reports']['cards']))

        fetched = self.client.get(
            f'/api/threads/{self.thread_id}/improvement_jobs/{job_id}',
            headers=self._headers(),
        )
        self.assertEqual(fetched.status_code, 200, fetched.text)
        payload = fetched.json()
        self.assertEqual(payload['job']['payload']['status'], 'passed')
        self.assertEqual(payload['job']['payload']['phase'], 'tests_passed')
        self.assertEqual(payload['job']['payload']['last_patch_status'], 'applied')
        self.assertEqual(payload['job']['payload']['last_test_status'], 'passed')
        self.assertEqual(payload['report_count'], 3)

    def test_canary_and_promotion_reports_update_job_status(self):
        created = self.client.post(
            f'/api/threads/{self.thread_id}/improvement_jobs',
            json={
                'target_repo': 'ddalggak',
                'instruction': 'Validate forge restart after patch',
            },
            headers=self._headers(),
        )
        self.assertEqual(created.status_code, 200, created.text)
        job_id = created.json()['job']['payload']['job_id']

        canary = self.client.post(
            f'/api/threads/{self.thread_id}/improvement_jobs/{job_id}/report',
            json={
                'kind': 'canary_result',
                'phase': 'canary_running',
                'status': 'passed',
                'summary': 'forge canary recovered after restart',
                'preview_text': 'screen session restart ok',
            },
            headers=self._headers(),
        )
        self.assertEqual(canary.status_code, 200, canary.text)

        promote = self.client.post(
            f'/api/threads/{self.thread_id}/improvement_jobs/{job_id}/report',
            json={
                'kind': 'promotion_decision',
                'phase': 'awaiting_approval',
                'status': 'ready_for_promote',
                'summary': 'safe to promote to stable after review',
                'preview_text': 'canary stable enough',
            },
            headers=self._headers(),
        )
        self.assertEqual(promote.status_code, 200, promote.text)

        fetched = self.client.get(
            f'/api/threads/{self.thread_id}/improvement_jobs/{job_id}',
            headers=self._headers(),
        )
        self.assertEqual(fetched.status_code, 200, fetched.text)
        payload = fetched.json()['job']['payload']
        self.assertEqual(payload['last_canary_status'], 'passed')
        self.assertEqual(payload['last_promotion_status'], 'ready_for_promote')
        self.assertEqual(payload['status'], 'ready_for_promote')
        self.assertEqual(payload['phase'], 'awaiting_approval')
