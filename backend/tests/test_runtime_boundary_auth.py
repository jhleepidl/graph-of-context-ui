from __future__ import annotations

import unittest

try:
    from fastapi import HTTPException

    from app.auth import Principal, reset_current_principal, set_current_principal
    from app.routers.runtime_commands import RuntimeCommandCreateRequest, create_command, list_pending_commands
    from app.routers.runtime_events import RuntimeEventIngestRequest, ingest_events, read_events
    _IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # pragma: no cover
    Principal = None  # type: ignore[assignment]
    reset_current_principal = set_current_principal = None  # type: ignore[assignment]
    RuntimeCommandCreateRequest = RuntimeEventIngestRequest = None  # type: ignore[assignment]
    create_command = list_pending_commands = ingest_events = read_events = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]
    _IMPORT_ERROR = exc


@unittest.skipIf(_IMPORT_ERROR is not None, f'missing dependency: {_IMPORT_ERROR}')
class RuntimeBoundaryAuthTests(unittest.TestCase):
    def test_runtime_reads_and_command_creation_require_principal(self) -> None:
        with self.assertRaises(HTTPException) as read_error:
            read_events()
        self.assertEqual(read_error.exception.status_code, 401)

        with self.assertRaises(HTTPException) as create_error:
            create_command(RuntimeCommandCreateRequest(command_type='runtime_ping'))
        self.assertEqual(create_error.exception.status_code, 401)

    def test_ingest_and_worker_queue_require_service_principal(self) -> None:
        token = set_current_principal(Principal(role='ui', service_id='svc-1', user_id='user-1'))
        try:
            with self.assertRaises(HTTPException) as ingest_error:
                ingest_events(RuntimeEventIngestRequest(events=[{'event_id': 'evt-1', 'event_type': 'run.start'}]))
            self.assertEqual(ingest_error.exception.status_code, 403)

            with self.assertRaises(HTTPException) as queue_error:
                list_pending_commands()
            self.assertEqual(queue_error.exception.status_code, 403)
        finally:
            reset_current_principal(token)


if __name__ == '__main__':
    unittest.main()
