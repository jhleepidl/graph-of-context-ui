from __future__ import annotations

import unittest

try:
    from sqlmodel import SQLModel, Session

    from app.auth import Principal, reset_current_principal, set_current_principal
    from app.models import ContextSet, Thread
    from app.routers import memory_graphs as memory_graphs_router
    from app.routers import messages as messages_router
    from app.routers import threads as threads_router
    from app.schemas import EdgeCreate, MessageCreate, NodeCreate
    from tests.db_test_utils import create_test_engine, dispose_tracked_engines
    _IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    SQLModel = Session = None  # type: ignore[assignment]
    Principal = reset_current_principal = set_current_principal = None  # type: ignore[assignment]
    ContextSet = Thread = None  # type: ignore[assignment]
    memory_graphs_router = messages_router = threads_router = None  # type: ignore[assignment]
    EdgeCreate = MessageCreate = NodeCreate = None  # type: ignore[assignment]
    create_test_engine = dispose_tracked_engines = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc


@unittest.skipIf(_IMPORT_ERROR is not None, f"missing dependency: {_IMPORT_ERROR}")
class RuntimeCompatibilityRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self._old_threads_engine = threads_router.engine
        self._old_messages_engine = messages_router.engine
        self._old_memory_graphs_engine = memory_graphs_router.engine
        threads_router.engine = self.engine
        messages_router.engine = self.engine
        memory_graphs_router.engine = self.engine
        self._principal_token = set_current_principal(Principal(role='admin'))
        with Session(self.engine) as session:
            self.thread = Thread(title='runtime compat')
            session.add(self.thread)
            session.flush()
            self.context_set = ContextSet(thread_id=self.thread.id, name='default')
            session.add(self.context_set)
            session.commit()
            session.refresh(self.thread)
            session.refresh(self.context_set)
            self.thread_id = self.thread.id
            self.context_set_id = self.context_set.id

    def tearDown(self) -> None:
        threads_router.engine = self._old_threads_engine
        messages_router.engine = self._old_messages_engine
        memory_graphs_router.engine = self._old_memory_graphs_engine
        reset_current_principal(self._principal_token)
        dispose_tracked_engines()

    def test_thread_scoped_nodes_and_edges_are_listable(self) -> None:
        run = threads_router.create_node(self.thread_id, NodeCreate(type='Run', text='run'))
        step = threads_router.create_node(self.thread_id, NodeCreate(type='Step', text='step'))
        threads_router.create_edge(self.thread_id, EdgeCreate(from_id=run['id'], to_id=step['id'], type='IN_RUN'))

        nodes = threads_router.list_thread_nodes(self.thread_id)
        self.assertEqual(nodes['count'], 2)
        self.assertEqual({item['type'] for item in nodes['items']}, {'Run', 'Step'})

        steps = threads_router.list_thread_nodes(self.thread_id, node_type='Step')
        self.assertEqual(steps['count'], 1)
        self.assertEqual(steps['items'][0]['id'], step['id'])

        edges = threads_router.list_thread_edges(self.thread_id, type='IN_RUN')
        self.assertEqual(edges['count'], 1)
        self.assertEqual(edges['items'][0]['from_id'], run['id'])
        self.assertEqual(edges['items'][0]['to_id'], step['id'])

    def test_thread_scoped_messages_are_listable(self) -> None:
        first = messages_router.add_message(self.thread_id, MessageCreate(role='user', text='hello'))
        second = messages_router.add_message(self.thread_id, MessageCreate(role='assistant', text='hi'))

        messages = messages_router.list_messages(self.thread_id)
        self.assertEqual(messages['count'], 2)
        self.assertEqual([item['id'] for item in messages['items']], [first['id'], second['id']])
        self.assertEqual([item['text'] for item in messages['items']], ['hello', 'hi'])

    def test_memory_endpoints_accept_camel_case_runtime_payloads(self) -> None:
        surface = memory_graphs_router.create_memory_surface(self.thread_id, {
            'surfaceId': 'shared_core',
            'name': 'Shared Core',
            'semanticKind': 'summary',
            'visibilityScope': 'shared',
            'writeMode': 'shared_append',
            'policyJson': {'owner': 'runtime'},
        })
        self.assertEqual(surface['surface']['surface_id'], 'shared_core')

        node = memory_graphs_router.create_memory_node(self.thread_id, {
            'surfaceId': 'shared_core',
            'nodeType': 'decision',
            'ownerAgentId': 'builder-1',
            'contentJson': {'text': 'keep canonical paths'},
            'provenanceJson': {'source': 'test'},
            'trustTier': 'observed',
            'status': 'active',
            'runId': 'run-1',
        })
        self.assertEqual(node['node']['surface_id'], 'shared_core')
        self.assertEqual(node['node']['node_type'], 'decision')
        self.assertEqual(node['node']['created_run_id'], 'run-1')

        topology = memory_graphs_router.record_memory_topology(self.thread_id, {
            'runId': 'run-1',
            'source': 'ddalggak-test',
            'memoryTopology': {'mode': 'compact_single', 'surfaces': [{'id': 'shared_core'}]},
            'items': [{'kind': 'memory_topology_event', 'next_mode': 'compact_single'}],
        })
        self.assertEqual(topology['topology']['run_id'], 'run-1')
        self.assertEqual(topology['topology']['source'], 'ddalggak-test')

        demand = memory_graphs_router.record_memory_demand(self.thread_id, {
            'runId': 'run-1',
            'source': 'ddalggak-test',
            'items': [{
                'query': 'continue implementation',
                'demandReasons': ['work_state_reference'],
                'sourceTypes': ['shared_work'],
                'surfaceIds': ['shared_core'],
                'retrievalMode': 'preflight',
            }],
        })
        self.assertEqual(demand['run_id'], 'run-1')
        self.assertEqual(demand['count'], 1)


if __name__ == '__main__':
    unittest.main()
