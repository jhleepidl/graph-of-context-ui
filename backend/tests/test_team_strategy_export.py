from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, SQLModel, create_engine

from app.models import Conversation, Thread
from app.services.conversation_team_config import save_team_config_payload
from app.services.team_strategy_export import build_team_strategy_dataset, serialize_team_strategy_dataset_jsonl


class TestTeamStrategyExport:
    def test_build_team_strategy_dataset_summarizes_recommendations(self) -> None:
        engine = create_engine('sqlite://')
        SQLModel.metadata.create_all(engine)
        base = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)

        with Session(engine) as session:
            thread = Thread(title='Strategy Export', owner_user_id='u1', service_id='svc')
            conversation = Conversation(thread_id=thread.id, title='Strategy Export Conversation')
            session.add(thread)
            session.add(conversation)
            session.commit()
            session.refresh(thread)

            save_team_config_payload(session, thread_id=thread.id, payload={
                'status': 'active',
                'active_team': {
                    'team_name': 'starter_single',
                    'planner_metadata': {
                        'adaptive_expansion': {
                            'recommendation': 'augment_context',
                            'augmentation': {'score': 2.2, 'reasons': ['missing_memory']},
                            'role_separation': {'score': 0.5, 'reasons': ['weak_split_signal']},
                            'quality': {'quality_gap': 1, 'contradiction_pressure': 0, 'followup_burden': 1},
                            'capability_gap_summary': 'missing_skill:repo.context',
                            'rationale': ['missing_memory'],
                            'source': 'runtime',
                            'ts': base.isoformat(),
                        },
                    },
                },
            })
            save_team_config_payload(session, thread_id=thread.id, payload={
                'status': 'suggested',
                'active_team': {
                    'team_name': 'starter_single',
                    'planner_metadata': {
                        'adaptive_expansion': {
                            'recommendation': 'augment_context',
                            'augmentation': {'score': 2.0, 'reasons': ['memory_refresh']},
                            'role_separation': {'score': 0.7, 'reasons': ['split_not_needed']},
                            'quality': {'quality_gap': 1, 'contradiction_pressure': 0, 'followup_burden': 1},
                            'capability_gap_summary': 'missing_skill:repo.context',
                            'rationale': ['memory_refresh'],
                            'source': 'runtime',
                            'ts': (base.replace(minute=5)).isoformat(),
                        },
                    },
                },
                'pending_team': {
                    'team_name': 'starter_plus_reviewer',
                    'planner_metadata': {
                        'adaptive_expansion': {
                            'recommendation': 'expand_team',
                            'augmentation': {'score': 1.1, 'reasons': ['already_augmented']},
                            'role_separation': {'score': 3.5, 'reasons': ['independent_review_needed'], 'independent_review_needed': True, 'persistent_split_needed': True},
                            'quality': {'quality_gap': 2, 'contradiction_pressure': 1, 'followup_burden': 1},
                            'capability_gap_summary': 'missing_capability:review.code',
                            'rationale': ['independent_review_needed'],
                            'auto_prepared_draft': True,
                            'source': 'pending_team_draft',
                            'ts': (base.replace(minute=10)).isoformat(),
                        },
                    },
                },
            })

            dataset = build_team_strategy_dataset(session, thread=thread, limit=20)

        assert dataset['count'] == 2
        assert dataset['recommendation_counts']['augment_context'] == 1
        assert dataset['recommendation_counts']['expand_team'] == 1
        assert dataset['summary']['augment_only_count'] == 1
        assert dataset['summary']['expand_team_count'] == 1
        assert dataset['summary']['auto_prepared_draft_count'] == 1
        assert dataset['summary']['independent_review_count'] == 1
        assert dataset['summary']['persistent_split_count'] == 1
        assert dataset['summary']['latest_recommendation'] == 'expand_team'
        assert dataset['rows'][0]['recommendation'] == 'expand_team'
        assert dataset['rows'][0]['team_state'] == 'pending'

    def test_serialize_team_strategy_dataset_jsonl_outputs_rows(self) -> None:
        payload = {
            'rows': [
                {'revision_id': 'rev_1', 'recommendation': 'augment_context'},
                {'revision_id': 'rev_2', 'recommendation': 'expand_team'},
            ]
        }
        text = serialize_team_strategy_dataset_jsonl(payload)
        lines = [line for line in text.splitlines() if line.strip()]
        assert len(lines) == 2
        assert 'augment_context' in lines[0]
        assert 'expand_team' in lines[1]
