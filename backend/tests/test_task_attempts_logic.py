from __future__ import annotations

import unittest

try:
    from sqlmodel import SQLModel, Session

    from app.auth import Principal, reset_current_principal, set_current_principal
    from app.models import Thread
    from app.routers import task_attempts as task_attempts_router
    from app.schemas import (
        TaskAttemptArchiveRequest,
        TaskAttemptCreateRequest,
        TaskAttemptLaunchRequest,
        TaskAttemptMemoryPackageRequest,
        TaskAttemptPromoteRequest,
    )
    from tests.db_test_utils import create_test_engine, dispose_tracked_engines
    _IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    SQLModel = Session = None  # type: ignore[assignment]
    Principal = reset_current_principal = set_current_principal = None  # type: ignore[assignment]
    Thread = None  # type: ignore[assignment]
    task_attempts_router = None  # type: ignore[assignment]
    TaskAttemptArchiveRequest = TaskAttemptCreateRequest = TaskAttemptLaunchRequest = TaskAttemptMemoryPackageRequest = TaskAttemptPromoteRequest = None  # type: ignore[assignment]
    create_test_engine = dispose_tracked_engines = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc


@unittest.skipIf(_IMPORT_ERROR is not None, f"missing dependency: {_IMPORT_ERROR}")
class TaskAttemptRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_test_engine()
        SQLModel.metadata.create_all(self.engine)
        self._old_engine = task_attempts_router.engine
        task_attempts_router.engine = self.engine
        self._principal_token = set_current_principal(Principal(role='admin'))
        with Session(self.engine) as session:
            self.thread = Thread(title='attempt control')
            session.add(self.thread)
            session.commit()
            session.refresh(self.thread)
            self.thread_id = self.thread.id

    def tearDown(self) -> None:
        task_attempts_router.engine = self._old_engine
        reset_current_principal(self._principal_token)
        dispose_tracked_engines()

    def test_create_branch_attempt_defaults_to_isolated_previous_result(self) -> None:
        result = task_attempts_router.create_attempt(TaskAttemptCreateRequest(
            thread_id=self.thread_id,
            task_id='task-demo',
            run_mode='branch',
            target_team='paper',
            task_text='rewrite as paper',
            work_mode={'work_mode': 'research_campaign', 'review_policy': 'stage_gate'},
        ))
        attempt = result['attempt']
        self.assertTrue(result['ok'])
        self.assertEqual(attempt['task_id'], 'task-demo')
        self.assertEqual(attempt['run_mode'], 'branch')
        self.assertEqual(attempt['target_team'], 'paper')
        self.assertEqual(attempt['previous_result_policy'], 'exclude')
        self.assertFalse(attempt['context_policy']['include_previous_result'])
        self.assertEqual(attempt['work_mode'], 'research_campaign')
        self.assertEqual(attempt['review_policy'], 'stage_gate')
        self.assertEqual(attempt['events'][0]['event_type'], 'created')

    def test_memory_attach_launch_promote_and_archive_flow(self) -> None:
        created = task_attempts_router.create_attempt(TaskAttemptCreateRequest(
            thread_id=self.thread_id,
            task_id='task-flow',
            run_mode='retry',
            target_team='coding',
            task_text='fix the code',
        ))
        attempt_id = created['attempt']['attempt_id']

        attached = task_attempts_router.attach_attempt_memory_package(attempt_id, TaskAttemptMemoryPackageRequest(
            memory_package_id='mem_pkg_1',
            projection_profile='coding',
            package={'topic': 'goc write actions'},
        ))
        self.assertEqual(attached['attempt']['memory_package_id'], 'mem_pkg_1')
        self.assertEqual(attached['attempt']['memory_projection_profile'], 'coding')
        self.assertTrue(attached['attempt']['context_policy']['include_memory_package'])

        launched = task_attempts_router.launch_attempt(attempt_id, TaskAttemptLaunchRequest())
        self.assertEqual(launched['attempt']['status'], 'launch_requested')
        self.assertEqual(launched['launch_packet']['kind'], 'task_attempt_launch_request_v1')
        self.assertFalse(launched['launch_packet']['runtime_bridge']['execute'])

        promoted = task_attempts_router.promote_attempt(attempt_id, TaskAttemptPromoteRequest(summary='good result'))
        self.assertEqual(promoted['attempt']['status'], 'promoted')
        self.assertEqual(promoted['compare']['promoted_attempt_id'], attempt_id)

        archived = task_attempts_router.archive_attempt(attempt_id, TaskAttemptArchiveRequest(reason='cleanup'))
        self.assertEqual(archived['attempt']['status'], 'archived')

    def test_promote_can_supersede_siblings(self) -> None:
        first = task_attempts_router.create_attempt(TaskAttemptCreateRequest(
            thread_id=self.thread_id,
            task_id='task-siblings',
            attempt_id='attempt-a',
            run_mode='branch',
        ))
        second = task_attempts_router.create_attempt(TaskAttemptCreateRequest(
            thread_id=self.thread_id,
            task_id='task-siblings',
            attempt_id='attempt-b',
            run_mode='branch',
        ))
        self.assertEqual(first['attempt']['attempt_id'], 'attempt-a')
        self.assertEqual(second['attempt']['attempt_id'], 'attempt-b')

        promoted = task_attempts_router.promote_attempt('attempt-b', TaskAttemptPromoteRequest(supersede_siblings=True))
        self.assertEqual(promoted['attempt']['status'], 'promoted')
        comparison = task_attempts_router.compare_attempts(self.thread_id, task_id='task-siblings')
        self.assertEqual(comparison['status_counts']['promoted'], 1)
        self.assertEqual(comparison['status_counts']['superseded'], 1)


if __name__ == '__main__':
    unittest.main()
