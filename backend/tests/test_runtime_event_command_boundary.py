from __future__ import annotations

import unittest

try:
    from fastapi import HTTPException
    from sqlmodel import SQLModel, Session, select

    from app.models import RuntimeRunProjection
    from app.services.runtime_commands import (
        acknowledge_runtime_command,
        create_runtime_command,
        serialize_runtime_command,
    )
    from app.services.runtime_events import ingest_runtime_events
    from tests.db_test_utils import create_test_engine, dispose_tracked_engines
    _IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # pragma: no cover
    SQLModel = Session = select = None  # type: ignore[assignment]
    RuntimeRunProjection = None  # type: ignore[assignment]
    acknowledge_runtime_command = create_runtime_command = serialize_runtime_command = None  # type: ignore[assignment]
    ingest_runtime_events = None  # type: ignore[assignment]
    create_test_engine = dispose_tracked_engines = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]
    _IMPORT_ERROR = exc


@unittest.skipIf(_IMPORT_ERROR is not None, f'missing dependency: {_IMPORT_ERROR}')
class RuntimeEventCommandBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_test_engine()
        SQLModel.metadata.create_all(self.engine)

    def tearDown(self) -> None:
        dispose_tracked_engines()

    def test_event_ingest_is_idempotent_and_projection_uses_sequence(self) -> None:
        events = [
            {
                'schema_version': 'openharness.run_trace/v1',
                'sync_schema_version': 'openharness.run_sync/v1',
                'event_id': 'evt-2',
                'event_sequence': 2,
                'run_id': 'run-1',
                'job_id': 'job-1',
                'event_type': 'run.agent_finish',
                'payload': {'agent_id': 'builder', 'provider': 'codex'},
            },
            {
                'schema_version': 'openharness.run_trace/v1',
                'sync_schema_version': 'openharness.run_sync/v1',
                'event_id': 'evt-1',
                'event_sequence': 1,
                'run_id': 'run-1',
                'job_id': 'job-1',
                'event_type': 'run.start',
                'payload': {'status': 'running'},
            },
            {
                'schema_version': 'openharness.run_trace/v1',
                'sync_schema_version': 'openharness.run_sync/v1',
                'event_id': 'evt-3',
                'event_sequence': 3,
                'run_id': 'run-1',
                'job_id': 'job-1',
                'event_type': 'run.finish',
                'payload': {'status': 'done'},
            },
        ]
        with Session(self.engine) as session:
            result = ingest_runtime_events(session, events)
            session.commit()
            self.assertEqual(result['accepted'], 3)
            self.assertEqual(result['duplicates'], 0)
            projection = session.exec(select(RuntimeRunProjection).where(RuntimeRunProjection.run_id == 'run-1')).one()
            self.assertEqual(projection.status, 'completed')
            self.assertEqual(projection.last_sequence, 3)
            self.assertEqual(projection.event_count, 3)
            self.assertEqual(projection.agent_event_count, 1)

            duplicate = ingest_runtime_events(session, [events[0]])
            session.commit()
            self.assertEqual(duplicate['accepted'], 0)
            self.assertEqual(duplicate['duplicates'], 1)
            projection = session.exec(select(RuntimeRunProjection).where(RuntimeRunProjection.run_id == 'run-1')).one()
            self.assertEqual(projection.event_count, 3)

    def test_command_creation_is_idempotent_and_acknowledged(self) -> None:
        body = {
            'command_id': 'cmd-1',
            'command_type': 'apply_context_policy',
            'aggregate_type': 'room',
            'aggregate_id': 'room-1',
            'expected_revision': 4,
            'actor': {'type': 'user', 'id': 'user-1'},
            'payload': {'policy': 'strict'},
        }
        with Session(self.engine) as session:
            row, created = create_runtime_command(session, body)
            self.assertTrue(created)
            same, created_again = create_runtime_command(session, body)
            self.assertFalse(created_again)
            self.assertEqual(row.command_id, same.command_id)

            accepted = acknowledge_runtime_command(session, row, {'status': 'accepted', 'worker_id': 'worker-1'})
            self.assertEqual(accepted.status, 'accepted')
            with self.assertRaises(HTTPException):
                acknowledge_runtime_command(session, row, {'status': 'accepted', 'worker_id': 'worker-2'})
            applied = acknowledge_runtime_command(session, row, {'status': 'applied', 'worker_id': 'worker-1', 'result': {'revision': 5}})
            session.commit()
            payload = serialize_runtime_command(applied)
            self.assertEqual(payload['status'], 'applied')
            self.assertEqual(payload['result']['revision'], 5)

            with self.assertRaises(HTTPException):
                acknowledge_runtime_command(session, row, {'status': 'rejected', 'worker_id': 'worker-2'})


if __name__ == '__main__':
    unittest.main()
