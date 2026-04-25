import os
import unittest

try:
    from fastapi.testclient import TestClient
    from sqlmodel import SQLModel, Session

    from app.db import get_session
    from app.main import app
    from app.routers import threads as threads_router
    from tests.db_test_utils import create_test_engine, dispose_tracked_engines
except ModuleNotFoundError as exc:  # pragma: no cover
    TestClient = None
    SQLModel = None
    Session = None
    app = None
    threads_router = None
    create_test_engine = None
    dispose_tracked_engines = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

os.environ.setdefault("GOC_ADMIN_KEY", "dev-admin-key")
os.environ.setdefault("GOC_UI_TOKEN_SECRET", "dev-ui-token-secret")


@unittest.skipIf(_IMPORT_ERROR is not None, f"missing dependency: {_IMPORT_ERROR}")
class ThreadRouteCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_test_engine()
        SQLModel.metadata.create_all(self.engine)
        app.dependency_overrides[get_session] = lambda: Session(self.engine)
        self.original_threads_engine = threads_router.engine
        threads_router.engine = self.engine
        self.client = TestClient(app)

    def tearDown(self):
        threads_router.engine = self.original_threads_engine
        app.dependency_overrides.clear()
        try:
            self.client.close()
        except Exception:
            pass
        dispose_tracked_engines()

    def _headers(self):
        return {"X-Admin-Key": "dev-admin-key"}

    def test_legacy_singular_thread_create_and_ensure_routes_work(self):
        created = self.client.post(
            "/api/thread",
            headers=self._headers(),
            json={"title": "compat-thread", "external_ref": "compat:thread:1"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        created_payload = created.json()
        self.assertTrue(created_payload.get("id"))
        self.assertEqual(created_payload.get("title"), "compat-thread")

        ensured = self.client.post(
            "/api/thread/ensure",
            headers=self._headers(),
            json={"title": "compat-thread-updated", "external_ref": "compat:thread:1"},
        )
        self.assertEqual(ensured.status_code, 200, ensured.text)
        ensured_payload = ensured.json()
        self.assertEqual(ensured_payload.get("id"), created_payload.get("id"))
        self.assertEqual(ensured_payload.get("title"), "compat-thread-updated")


if __name__ == "__main__":
    unittest.main()
