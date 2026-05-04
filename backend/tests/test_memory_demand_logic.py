from __future__ import annotations

import unittest

from sqlmodel import SQLModel, Session
from tests.db_test_utils import create_test_engine

from app.models import Thread
from app.services.memory_demand import (
    build_run_studio_memory_demand,
    normalize_memory_demand_event,
    record_memory_demand_events,
)


class MemoryDemandLogicTests(unittest.TestCase):
    def test_normalize_runtime_memory_demand_event(self) -> None:
        event = normalize_memory_demand_event({
            'query': '아까 올렸던 파일 기준으로 이어서 패치해줘',
            'demand_reasons': ['continuity_reference', 'artifact_reference'],
            'sources': ['local_memory/turns.jsonl', 'artifact_observations.jsonl'],
            'item_count': 3,
            'agent_id': 'builder-1',
            'role_id': 'builder',
            'matching': {'strategy': 'intent_plus_token_scoring'},
        }, run_id='run-1')
        self.assertEqual(event['run_id'], 'run-1')
        self.assertIn('continuity_reference', event['demand_reasons'])
        self.assertIn('artifact_observations.jsonl', event['sources'])
        self.assertEqual(event['item_count'], 3)
        self.assertEqual(event['matching']['strategy'], 'intent_plus_token_scoring')


    def test_router_memory_classifier_fields_are_preserved(self) -> None:
        event = normalize_memory_demand_event({
            'query': '그 설계대로 이어서 구현해줘',
            'router_memory_plan': {
                'mode': 'query',
                'query': 'adaptive memory topology design',
                'source_types': ['turns', 'shared_work', 'decisions'],
                'surface_ids': ['shared_core', 'decisions'],
                'classifier': 'supervisor_router_llm',
                'confidence': 0.82,
            },
            'demand_reasons': ['router_memory_classifier'],
            'sources': ['local_memory/turns.jsonl'],
            'item_count': 1,
        }, run_id='run-router')
        self.assertEqual(event['classifier'], 'supervisor_router_llm')
        self.assertAlmostEqual(event['confidence'], 0.82)
        self.assertIn('shared_work', event['source_types'])
        self.assertIn('decisions', event['source_types'])
        self.assertIn('shared_core', event['surface_ids'])
        self.assertEqual(event['matching']['classifier'], 'supervisor_router_llm')

    def test_run_studio_memory_demand_summary(self) -> None:
        engine = create_test_engine()
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            thread = Thread(title='memory demand')
            session.add(thread)
            session.commit()
            session.refresh(thread)
            rows = record_memory_demand_events(
                session,
                thread=thread,
                run_id='run-1',
                source='ddalggak-test',
                events=[{
                    'query': '전에 말한 메모리 구조 그대로 이어서 구현해줘',
                    'demand_reasons': ['continuity_reference', 'task_state_reference'],
                    'sources': ['local_memory/summary.md', 'shared/progress.md'],
                    'item_count': 2,
                    'role_id': 'planner',
                    'retrieval_mode': 'router_llm_preflight',
                    'classifier': 'supervisor_router_llm',
                    'confidence': 0.74,
                    'source_types': ['turns', 'shared_work'],
                    'surface_ids': ['shared_core'],
                }],
            )
            self.assertEqual(len(rows), 1)
            session.commit()
            summary = build_run_studio_memory_demand(session, thread=thread, run_id='run-1')
            self.assertEqual(summary['event_count'], 1)
            self.assertEqual(summary['events'][0]['source'], 'ddalggak-test')
            self.assertIn('continuity_reference', summary['reason_counts'])
            self.assertIn('local_memorysummary.md', summary['source_counts'])
            self.assertEqual(summary['retrieval_mode_counts']['router_llm_preflight'], 1)
            self.assertEqual(summary['classifier_counts']['supervisor_router_llm'], 1)
            self.assertEqual(summary['source_type_counts']['shared_work'], 1)
            self.assertEqual(summary['surface_counts']['shared_core'], 1)
            self.assertEqual(summary['events'][0]['classifier'], 'supervisor_router_llm')
            self.assertFalse(summary['empty'])


if __name__ == '__main__':
    unittest.main()
