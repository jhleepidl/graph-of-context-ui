from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase

from app.services.scope_materializer import materialize_scope_from_graph


class DummyNode(SimpleNamespace):
    def __init__(self, node_id: str, node_type: str, text: str, payload: dict | None = None):
        super().__init__(
            id=node_id,
            thread_id='thread_1',
            type=node_type,
            text=text,
            payload_json=json.dumps(payload or {}),
            created_at=datetime.now(timezone.utc),
        )


class ScopeMaterializerLogicTests(TestCase):
    def test_materialize_scope_from_graph_prefers_matching_context_and_expands_closure(self) -> None:
        now = datetime.now(timezone.utc)
        nodes = [
            SimpleNamespace(
                id='node_filing',
                thread_id='thread_1',
                type='Resource',
                text='Samsung Electronics filing debt operating margin',
                payload_json='{"resource_kind":"filings","title":"Q4 filing"}',
                created_at=now,
            ),
            SimpleNamespace(
                id='node_table',
                thread_id='thread_1',
                type='Artifact',
                text='Operating margin table',
                payload_json='{"kind":"financial_tables"}',
                created_at=now,
            ),
            SimpleNamespace(
                id='node_chat',
                thread_id='thread_1',
                type='Message',
                text='random chat',
                payload_json='{"role":"assistant"}',
                created_at=now,
            ),
        ]
        edges = [
            SimpleNamespace(
                thread_id='thread_1',
                from_id='node_filing',
                to_id='node_table',
                type='TABLE_OF',
            )
        ]
        scope_spec = {
            'scope_id': 'scope_filings',
            'context_types': ['filings', 'financial_tables'],
            'node_selection': {
                'strategy': 'query_plus_closure',
                'query': 'Samsung filing operating margin',
                'closure_edge_types': ['TABLE_OF'],
                'max_nodes': 8,
            },
            'memory_grants': {
                'conversation_tail': False,
                'explicit_uploaded_files': True,
            },
            'budget': {'soft_tokens': 1200},
        }

        materialized = materialize_scope_from_graph(
            scope_spec,
            nodes=nodes,
            edges=edges,
            thread_id='thread_1',
            session=None,
        )

        self.assertEqual(materialized['scope_id'], 'scope_filings')
        self.assertIn('node_filing', materialized['active_node_ids'])
        self.assertIn('node_table', materialized['active_node_ids'])
        self.assertNotEqual(materialized['compiled_text'], '')
        self.assertEqual(materialized['lineage']['compiler'], 'goc_scope_materializer')

    def test_materialize_scope_from_graph_fails_closed_when_no_nodes_match_scoped_query(self) -> None:
        now = datetime.now(timezone.utc)
        nodes = [
            SimpleNamespace(
                id='node_unrelated',
                thread_id='thread_1',
                type='Resource',
                text='totally unrelated note',
                payload_json='{"resource_kind":"notes","title":"misc"}',
                created_at=now,
            )
        ]
        scope_spec = {
            'scope_id': 'scope_strict',
            'visibility_mode': 'scoped',
            'context_types': ['filings'],
            'node_selection': {'query': 'Samsung debt filing', 'max_nodes': 8},
        }

        materialized = materialize_scope_from_graph(scope_spec, nodes=nodes, edges=[], thread_id='thread_1', session=None)

        self.assertEqual(materialized['active_node_ids'], [])
        self.assertEqual(materialized['compiled_text'], '')
        self.assertTrue(materialized['lineage']['empty_scope'])
        self.assertEqual(materialized['lineage']['selection_confidence'], 'none')

    def test_materialize_scope_from_graph_clips_compiled_text_to_hard_budget(self) -> None:
        now = datetime.now(timezone.utc)
        long_text = 'evidence ' * 2000
        nodes = [
            SimpleNamespace(
                id='node_long',
                thread_id='thread_1',
                type='Resource',
                text=long_text,
                payload_json='{"resource_kind":"evidence","title":"long evidence"}',
                created_at=now,
            )
        ]
        scope_spec = {
            'scope_id': 'scope_budget',
            'visibility_mode': 'scoped',
            'context_types': ['evidence'],
            'node_selection': {'query': 'evidence', 'max_nodes': 4},
            'budget': {'soft_tokens': 200, 'hard_tokens': 220},
        }

        materialized = materialize_scope_from_graph(scope_spec, nodes=nodes, edges=[], thread_id='thread_1', session=None)

        self.assertTrue(materialized['lineage']['truncated'])
        self.assertLessEqual(materialized['token_estimate'], 220)

    def test_scope_materializer_emits_selection_diagnostics(self) -> None:
        scope_spec = {
            'scope_id': 'scope_news',
            'role_id': 'researcher',
            'visibility_mode': 'scoped',
            'context_types': ['news'],
            'node_selection': {'strategy': 'query_plus_closure', 'query': 'market headline'},
            'budget': {'soft_tokens': 200, 'hard_tokens': 400},
        }
        nodes = [
            DummyNode('n1', 'Message', 'market headline and earnings', {'title': 'market headline'}),
            DummyNode('n2', 'Artifact', 'summary artifact', {'kind': 'artifact'}),
        ]
        materialized = materialize_scope_from_graph(scope_spec, nodes=nodes, edges=[], thread_id='thread_1', session=None)
        lineage = materialized.get('lineage') or {}
        self.assertEqual(lineage.get('compiler'), 'goc_scope_materializer')
        self.assertIn('market', list(lineage.get('matched_query_terms') or []))
        self.assertEqual(lineage.get('selection_strategy'), 'query_plus_closure')
        self.assertIsInstance(lineage.get('seed_node_ids'), list)
        self.assertEqual(lineage.get('selection_confidence'), 'high')

    def test_scope_materializer_upstream_results_strategy_penalizes_raw_resources(self) -> None:
        scope_spec = {
            'scope_id': 'scope_synth',
            'role_id': 'synthesizer',
            'visibility_mode': 'scoped',
            'memory_grants': {'upstream_results': True},
            'node_selection': {'strategy': 'upstream_results_only'},
            'budget': {'soft_tokens': 200, 'hard_tokens': 400},
        }
        nodes = [
            DummyNode('artifact_1', 'Artifact', 'upstream result summary', {'kind': 'artifact'}),
            DummyNode('resource_1', 'Resource', 'raw repository file', {'resource_kind': 'code_file'}),
        ]
        materialized = materialize_scope_from_graph(scope_spec, nodes=nodes, edges=[], thread_id='thread_1', session=None)
        self.assertEqual(materialized['active_node_ids'][0], 'artifact_1')

    def test_scope_materializer_records_rejected_broad_candidates(self) -> None:
        scope_spec = {
            'scope_id': 'scope_workspace',
            'role_id': 'builder',
            'visibility_mode': 'scoped',
            'context_types': ['code'],
            'node_selection': {'strategy': 'workspace_plus_closure', 'query': 'apply repo patch'},
            'budget': {'soft_tokens': 200, 'hard_tokens': 400},
        }
        nodes = [
            DummyNode('repo_file', 'Resource', 'repository patch file', {'resource_kind': 'code_file'}),
            DummyNode('chat_1', 'Message', 'assistant small talk', {'role': 'assistant'}),
            DummyNode('note_1', 'Resource', 'misc note unrelated', {'resource_kind': 'notes'}),
        ]
        materialized = materialize_scope_from_graph(scope_spec, nodes=nodes, edges=[], thread_id='thread_1', session=None)
        lineage = materialized.get('lineage') or {}
        self.assertIn('repo_file', materialized['active_node_ids'])
        self.assertIsInstance(lineage.get('rejected_positive_node_ids'), list)
        self.assertGreaterEqual(lineage.get('candidate_node_count') or 0, 3)
