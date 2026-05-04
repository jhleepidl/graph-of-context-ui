from __future__ import annotations

import unittest

from sqlmodel import SQLModel, Session
from tests.db_test_utils import create_test_engine

from app.models import MemoryProjection, MemorySurface, Thread
from app.services.memory_topology import build_run_studio_memory_topology, normalize_memory_topology_payload, record_memory_topology_snapshot


class MemoryTopologyLogicTests(unittest.TestCase):
    def test_normalize_runtime_memory_topology_payload(self) -> None:
        topology = normalize_memory_topology_payload({
            'mode': 'team_scoped',
            'stress': {'score': 4.7, 'reasons': ['multi_agent_team']},
            'surfaces': [
                {'id': 'shared_core', 'kind': 'summary', 'readers': ['*'], 'writers': ['runtime']},
                {'id': 'implementation', 'kind': 'team_surface', 'readers': ['builder', 'reviewer'], 'writers': ['builder']},
            ],
            'agent_grants': {'builder': {'role': 'builder', 'read': ['shared_core', 'implementation'], 'write': ['implementation']}},
            'maintenance': {'actions': [{'action': 'build_cross_surface_digest'}]},
        })
        self.assertEqual(topology['mode'], 'team_scoped')
        self.assertEqual(len(topology['surfaces']), 2)
        self.assertIn('builder', topology['agent_grants'])
        self.assertEqual(topology['maintenance']['actions'][0]['action'], 'build_cross_surface_digest')

    def test_run_studio_topology_prefers_runtime_snapshot(self) -> None:
        engine = create_test_engine()
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            thread = Thread(title='topology')
            session.add(thread)
            session.commit()
            session.refresh(thread)
            record_memory_topology_snapshot(
                session,
                thread=thread,
                run_id='run-1',
                source='ddalggak-test',
                topology={
                    'mode': 'compact_single',
                    'stress': {'score': 1.2, 'reasons': ['single_agent_low_pressure']},
                    'surfaces': [{'id': 'core', 'kind': 'compact_summary', 'readers': ['*'], 'writers': ['runtime']}],
                    'agent_grants': {'agent': {'read': ['core'], 'write': ['core']}},
                    'maintenance': {'idle_safe': True, 'actions': [{'action': 'refresh_core_summary'}]},
                },
                events=[{'kind': 'memory_topology_event', 'next_mode': 'compact_single', 'stress_score': 1.2}],
            )
            session.commit()
            summary = build_run_studio_memory_topology(session, thread=thread, run_id='run-1')
            self.assertEqual(summary['source'], 'ddalggak-test')
            self.assertEqual(summary['mode'], 'compact_single')
            self.assertEqual(summary['surface_count'], 1)
            self.assertEqual(summary['event_count'], 1)
            self.assertFalse(summary['fallback'])

    def test_run_studio_topology_falls_back_to_memory_graph(self) -> None:
        engine = create_test_engine()
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            thread = Thread(title='fallback')
            session.add(thread)
            session.commit()
            session.refresh(thread)
            session.add(MemorySurface(thread_id=thread.id, surface_id='shared', title='Shared', semantic_kind='summary', visibility_scope='shared', write_mode='shared'))
            session.add(MemorySurface(thread_id=thread.id, surface_id='review', title='Review', semantic_kind='team_surface', visibility_scope='shared', write_mode='contracted_append'))
            session.add(MemoryProjection(thread_id=thread.id, run_id='run-2', agent_id='reviewer-1', role_id='reviewer', visible_node_ids_json='[]', blocked_node_ids_json='[]', summary_json='{"visible_surface_ids":["shared","review"]}'))
            session.commit()
            summary = build_run_studio_memory_topology(session, thread=thread, run_id='run-2')
            self.assertTrue(summary['fallback'])
            self.assertGreaterEqual(summary['surface_count'], 2)
            self.assertIn(summary['mode'], {'compact_single', 'structured_single', 'team_scoped', 'graph_snapshot'})
            self.assertIn('reviewer-1', summary['agent_grants'])


if __name__ == '__main__':
    unittest.main()
