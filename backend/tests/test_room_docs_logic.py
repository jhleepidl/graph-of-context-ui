import json
import unittest
from datetime import datetime, timezone

try:
    from sqlmodel import SQLModel, Session
except ModuleNotFoundError:  # pragma: no cover - optional local test dependency
    SQLModel = None
    Session = None

if SQLModel is not None:
    from app.models import RoomUsageEventRecord, Thread
    from app.services.room_docs import build_room_docs_browser
    from tests.db_test_utils import create_test_engine


@unittest.skipIf(SQLModel is None, 'sqlmodel is not installed in this environment')
class RoomDocsLogicTest(unittest.TestCase):
    def test_room_docs_browser_builds_moc_docs_and_actions_without_raw_transcript(self):
        engine = create_test_engine()
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            thread = Thread(title='논문 작성')
            session.add(thread)
            session.commit()
            session.refresh(thread)
            row = RoomUsageEventRecord(
                thread_id=thread.id,
                event_type='work_depth_used',
                command='/loop',
                domain_label='research_paper_factory',
                payload_json=json.dumps({'goal': '논문 실험 코드를 구현하고 검증'}, ensure_ascii=False),
                created_at=datetime(2026, 7, 5, 1, 0, tzinfo=timezone.utc),
            )
            session.add(row)
            session.commit()
            browser = build_room_docs_browser(session, thread, limit=10)
        self.assertEqual(browser['schema_version'], 'goc.room_docs_browser/v1')
        paths = {item['path'] for item in browser['files']}
        self.assertIn('AGENTS.md', paths)
        self.assertIn('moc-by-date.md', paths)
        self.assertTrue(any(path.startswith('action/') for path in paths))
        action = next(item for item in browser['files'] if item['path'].startswith('action/'))
        self.assertIn('raw transcript copied: false', action['content'])
        self.assertGreaterEqual(browser['summary']['action_count'], 1)


if __name__ == '__main__':
    unittest.main()
