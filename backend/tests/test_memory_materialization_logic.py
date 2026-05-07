from __future__ import annotations

import importlib.util
import unittest

HAS_SQLMODEL = importlib.util.find_spec('sqlmodel') is not None


@unittest.skipUnless(HAS_SQLMODEL, 'sqlmodel not installed')
class MemoryMaterializationLogicTest(unittest.TestCase):
    def setUp(self):
        from sqlmodel import SQLModel, create_engine
        self.engine = create_engine('sqlite:///:memory:')
        SQLModel.metadata.create_all(self.engine)

    def test_time_series_materialization_preview(self):
        from sqlmodel import Session
        from app.models import MemoryDemandEvent, Node, Thread
        from app.services.memory_materialization import build_memory_materialization_preview
        with Session(self.engine) as session:
            thread = Thread(title='meal thread')
            session.add(thread)
            session.commit()
            session.refresh(thread)
            for text in [
                '아침은 삶은 계란 2개랑 바나나 먹었어.',
                '점심은 김치찌개랑 밥 먹었어.',
                '저녁은 닭가슴살 샐러드 먹었어.',
                '이번 주 아침 거른 날이 며칠인지 알고 싶어.',
            ]:
                session.add(Node(thread_id=thread.id, type='Message', text=text))
            session.add(MemoryDemandEvent(thread_id=thread.id, query='최근 식사 단백질 섭취 추세 알려줘', sources_json='["nodes"]', item_count=3))
            session.commit()
            preview = build_memory_materialization_preview(session, thread)
            self.assertEqual(preview['kind'], 'goc_memory_materialization_preview')
            series = next((row for row in preview['candidates'] if row.get('shape_id') == 'time_series'), None)
            self.assertIsNotNone(series)
            self.assertEqual(series['proposed_schema']['table'], 'time_series_entries')
            self.assertFalse(series['safety']['generated_code_execution'])

    def test_shadow_module_persists_rows_without_enabling_writes(self):
        from sqlmodel import Session
        from app.models import MemoryDemandEvent, MemoryModule, MemoryModuleRow, Node, Thread
        from app.services.memory_materialization import build_memory_materialization_preview, create_shadow_memory_module
        with Session(self.engine) as session:
            thread = Thread(title='meal module thread')
            session.add(thread)
            session.commit()
            session.refresh(thread)
            for text in [
                '아침은 삶은 계란 2개랑 바나나 먹었어.',
                '점심은 김치찌개랑 밥 먹었어.',
                '저녁은 닭가슴살 샐러드 먹었어.',
                '오늘 아침은 오트밀 먹었어.',
            ]:
                session.add(Node(thread_id=thread.id, type='Message', text=text))
            session.add(MemoryDemandEvent(thread_id=thread.id, query='이번 주 식사 요약해줘', sources_json='["nodes"]', item_count=4))
            session.commit()
            preview = build_memory_materialization_preview(session, thread, min_score=.1)
            series = next(row for row in preview['candidates'] if row.get('shape_id') == 'time_series')
            module = create_shadow_memory_module(session, thread, {'candidate': series})
            self.assertEqual(module['domain'], 'time_series')
            self.assertEqual(module['status'], 'shadow')
            self.assertFalse(module['manifest']['canonical_memory_switch'])
            self.assertGreaterEqual(module['row_count'], 3)
            stored_module = session.query(MemoryModule).filter(MemoryModule.thread_id == thread.id).one()
            self.assertEqual(stored_module.status, 'shadow')
            rows = session.query(MemoryModuleRow).filter(MemoryModuleRow.thread_id == thread.id).all()
            self.assertGreaterEqual(len(rows), 3)


if __name__ == '__main__':
    unittest.main()
