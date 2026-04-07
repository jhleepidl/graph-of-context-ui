import unittest

try:
    from fastapi import HTTPException
    from sqlmodel import SQLModel, Session, select

    from app.auth import Principal, reset_current_principal, set_current_principal
    from app.models import MemoryConflict, MemoryNode, MemoryProjection, MemorySurface, Thread
    from app.routers import memory_graphs as memory_graphs_router
    from app.schemas import MemoryConflictResolveRequest, MemoryNodeCreateRequest, MemoryProjectionRequest, MemorySurfaceCreateRequest
    from tests.db_test_utils import create_test_engine, dispose_tracked_engines
except ModuleNotFoundError as exc:  # pragma: no cover
    HTTPException = None
    SQLModel = None
    Session = None
    select = None
    Principal = None
    reset_current_principal = None
    set_current_principal = None
    MemoryConflict = None
    MemoryNode = None
    MemoryProjection = None
    MemorySurface = None
    Thread = None
    memory_graphs_router = None
    MemoryConflictResolveRequest = None
    MemoryNodeCreateRequest = None
    MemoryProjectionRequest = None
    MemorySurfaceCreateRequest = None
    create_test_engine = None
    dispose_tracked_engines = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


@unittest.skipIf(_IMPORT_ERROR is not None, f"missing dependency: {_IMPORT_ERROR}")
class MemoryGraphRuntimeGuardTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self.original_engine = memory_graphs_router.engine
        memory_graphs_router.engine = self.engine
        with Session(self.engine) as session:
            thread = Thread(service_id='default', title='Memory Thread')
            session.add(thread)
            session.commit()
            session.refresh(thread)
            self.thread_id = thread.id
        self.principal_token = set_current_principal(Principal(role='admin', user_id='admin'))

    def tearDown(self):
        memory_graphs_router.engine = self.original_engine
        try:
            reset_current_principal(self.principal_token)
        except Exception:
            pass
        dispose_tracked_engines()

    def test_create_memory_node_requires_existing_surface(self):
        with self.assertRaises(HTTPException) as ctx:
            memory_graphs_router.create_memory_node(
                self.thread_id,
                MemoryNodeCreateRequest(surface_id='missing_surface', node_type='note', content={'text': 'orphan'}),
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('surface', str(ctx.exception.detail))

    def test_conflict_projection_blocks_nodes_and_resolve_validates_pair(self):
        memory_graphs_router.create_memory_surface(
            self.thread_id,
            MemorySurfaceCreateRequest(surface_id='shared_evidence', title='Shared Evidence'),
        )
        first = memory_graphs_router.create_memory_node(
            self.thread_id,
            MemoryNodeCreateRequest(
                surface_id='shared_evidence',
                node_type='fact',
                trust_tier='verified',
                content={'claim': 'service is degraded', 'conflict_key': 'service_health', 'confidence': 0.91},
                provenance={'source_id': 'probe_a', 'entity': 'service_health'},
            ),
        )
        second = memory_graphs_router.create_memory_node(
            self.thread_id,
            MemoryNodeCreateRequest(
                surface_id='shared_evidence',
                node_type='fact',
                trust_tier='derived',
                content={'claim': 'service is healthy', 'conflict_key': 'service_health', 'confidence': 0.32},
                provenance={'source_id': 'probe_b', 'entity': 'service_health'},
            ),
        )
        self.assertEqual(len(second['conflicts']), 1)
        conflict_id = second['conflicts'][0]['id']
        first_node_id = first['node']['id']
        second_node_id = second['node']['id']

        with Session(self.engine) as session:
            nodes = session.exec(select(MemoryNode).where(MemoryNode.thread_id == self.thread_id)).all()
            statuses = {node.id: node.status for node in nodes}
            self.assertEqual(statuses[first_node_id], 'conflicted')
            self.assertEqual(statuses[second_node_id], 'conflicted')

        projection = memory_graphs_router.project_memory(
            self.thread_id,
            MemoryProjectionRequest(role_id='reviewer', run_id='run-1'),
        )
        blocked_reasons = {row['node_id']: row['blocked_reason'] for row in projection['projection']['blocked_nodes']}
        self.assertEqual(projection['projection']['visible_node_ids'], [])
        self.assertEqual(blocked_reasons[first_node_id], 'pending_conflict')
        self.assertEqual(blocked_reasons[second_node_id], 'pending_conflict')

        memory_graphs_router.create_memory_surface(
            self.thread_id,
            MemorySurfaceCreateRequest(surface_id='foreign_surface', title='Foreign Surface'),
        )
        foreign = memory_graphs_router.create_memory_node(
            self.thread_id,
            MemoryNodeCreateRequest(surface_id='foreign_surface', node_type='note', content={'note': 'unrelated'}),
        )
        with self.assertRaises(HTTPException) as ctx:
            memory_graphs_router.resolve_memory_conflict(
                conflict_id,
                MemoryConflictResolveRequest(status='resolved', winning_node_id=first_node_id, losing_node_ids=[foreign['node']['id']]),
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('outside the conflict pair', str(ctx.exception.detail))

        resolved = memory_graphs_router.resolve_memory_conflict(
            conflict_id,
            MemoryConflictResolveRequest(status='resolved', winning_node_id=first_node_id),
        )
        self.assertEqual(resolved['conflict']['status'], 'resolved')

        with Session(self.engine) as session:
            node_a = session.get(MemoryNode, first_node_id)
            node_b = session.get(MemoryNode, second_node_id)
            self.assertEqual(node_a.status, 'published')
            self.assertEqual(node_b.status, 'superseded')
            self.assertEqual(session.exec(select(MemoryProjection)).all(), [])

    def test_create_memory_surface_upserts_by_thread_and_surface_id(self):
        created = memory_graphs_router.create_memory_surface(
            self.thread_id,
            MemorySurfaceCreateRequest(surface_id='plan', title='Plan', visibility_scope='shared'),
        )
        updated = memory_graphs_router.create_memory_surface(
            self.thread_id,
            MemorySurfaceCreateRequest(surface_id='plan', title='Updated Plan', visibility_scope='private', policy={'target_roles': ['builder']}),
        )
        self.assertEqual(created['surface']['surface_id'], updated['surface']['surface_id'])
        with Session(self.engine) as session:
            rows = session.exec(select(MemorySurface).where(MemorySurface.thread_id == self.thread_id, MemorySurface.surface_id == 'plan')).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].title, 'Updated Plan')
            self.assertEqual(rows[0].visibility_scope, 'private')


if __name__ == '__main__':
    unittest.main()
