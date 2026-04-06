import unittest

try:
    from sqlmodel import SQLModel, Session
    from tests.db_test_utils import create_test_engine as create_engine
    from app.models import Conversation, Thread
    from app.services.team_manifest import (
        export_thread_team_manifest,
        install_thread_team_manifest,
        validate_team_manifest_payload,
        diff_team_manifest_payload,
    )
    from app.services.conversation_team_config import get_team_config_payload, save_team_config_payload
    SQLMODEL_AVAILABLE = True
except Exception:
    SQLMODEL_AVAILABLE = False


@unittest.skipUnless(SQLMODEL_AVAILABLE, 'sqlmodel not available in this environment')
class TeamManifestLogicTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        SQLModel.metadata.create_all(self.engine)

    def test_export_manifest_preserves_team_shape(self):
        with Session(self.engine) as session:
            thread = Thread(id='thread-manifest-1', service_id='svc-1', title='Demo')
            session.add(thread)
            session.add(Conversation(thread_id=thread.id, owner_user_id='user-1', service_id='svc-1'))
            session.commit()

            save_team_config_payload(session, thread_id=thread.id, payload={
                'status': 'active',
                'composition_mode': 'freeform',
                'proposal_mode': 'create',
                'active_team': {
                    'team_name': 'Research Squad',
                    'composition_mode': 'freeform',
                    'proposal_mode': 'create',
                    'agents': [
                        {'agent_id': 'researcher', 'name': 'Researcher'},
                        {'agent_id': 'synthesizer', 'name': 'Synthesizer'},
                    ],
                    'capability_gaps': [
                        {'kind': 'missing_tool', 'agent_name': 'Researcher', 'tool_id': 'web_search', 'detail': 'web_search missing'},
                    ],
                },
                'pending_team': {},
            })

            manifest = export_thread_team_manifest(session, thread)
            self.assertEqual(manifest['kind'], 'ddalggak_team_blueprint')
            self.assertEqual(manifest['thread_id'], thread.id)
            self.assertEqual(manifest['service_id'], thread.service_id)
            self.assertEqual(manifest['team']['agents'][0]['agent_id'], 'researcher')
            self.assertTrue(manifest['compatibility']['ddalggak'])
            self.assertEqual(manifest['requirements']['tools'][0]['tool_id'], 'web_search')
            self.assertTrue(isinstance(manifest['requirements'].get('install_hints'), list))
            self.assertEqual(manifest['structure_v2']['topology']['pattern'], 'single')
            self.assertEqual(manifest.get('install_proposal_state'), None)
            self.assertIsInstance(manifest['install_proposal'].get('actions'), dict)

    def test_validate_and_install_supports_team_only_manifest_shape(self):
        with Session(self.engine) as session:
            thread = Thread(id='thread-manifest-2', service_id='svc-2', title='Demo 2')
            session.add(thread)
            session.add(Conversation(thread_id=thread.id, owner_user_id='user-1', service_id='svc-2'))
            session.commit()

            team_only_manifest = {
                'composition_mode': 'freeform',
                'proposal_mode': 'refine',
                'team': {
                    'team_name': 'Notebook Team',
                    'agents': [
                        {'agent_id': 'builder', 'name': 'Notebook Builder'},
                    ],
                },
            }
            validation = validate_team_manifest_payload(team_only_manifest, apply_state='pending')
            self.assertTrue(validation['ok'])
            self.assertEqual(validation['manifest']['team']['agents'][0]['agent_id'], 'builder')

            installed = install_thread_team_manifest(session, thread, team_only_manifest, apply_state='pending')
            self.assertEqual(installed['team']['agents'][0]['agent_id'], 'builder')
            payload = get_team_config_payload(session, thread_id=thread.id)
            self.assertEqual(payload['status'], 'suggested')
            self.assertEqual(payload['pending_team']['agents'][0]['agent_id'], 'builder')
            self.assertIsInstance(payload['pending_team'].get('requirements'), dict)

    def test_diff_manifest_reports_agent_and_requirement_changes(self):
        with Session(self.engine) as session:
            thread = Thread(id='thread-manifest-3', service_id='svc-3', title='Demo 3')
            session.add(thread)
            session.add(Conversation(thread_id=thread.id, owner_user_id='user-1', service_id='svc-3'))
            session.commit()

            save_team_config_payload(session, thread_id=thread.id, payload={
                'status': 'active',
                'composition_mode': 'freeform',
                'proposal_mode': 'create',
                'active_team': {
                    'team_name': 'Current Team',
                    'agents': [
                        {'agent_id': 'researcher', 'name': 'Researcher'},
                    ],
                    'requirements': {
                        'tools': [{'tool_id': 'web_search', 'required_by': 'Researcher'}],
                    },
                },
                'pending_team': {},
            })

            current_manifest = export_thread_team_manifest(session, thread)
            candidate = {
                'team': {
                    'team_name': 'Candidate Team',
                    'agents': [
                        {'agent_id': 'researcher', 'name': 'Researcher', 'purpose': 'Updated'},
                        {'agent_id': 'builder', 'name': 'Builder'},
                    ],
                },
                'requirements': {
                    'tools': [{'tool_id': 'workspace_fs', 'required_by': 'Builder'}],
                    'credentials': [{'credential_key': 'OPENAI_API_KEY', 'required_by': 'Builder'}],
                },
                'install_proposal': {
                    'kind': 'capability_install_proposal',
                    'gap_count': 2,
                    'blocking': True,
                    'requirements': {
                        'tools': [{'tool_id': 'workspace_fs', 'required_by': 'Builder'}],
                    },
                    'actions': {
                        'tool_install_proposals': [{'tool_id': 'workspace_fs', 'required_by': 'Builder', 'strategy': 'enable_workspace_fs'}],
                        'credential_requests': [{'credential_key': 'OPENAI_API_KEY', 'required_by': 'Builder'}],
                    },
                },
                'install_proposal_state': {
                    'proposal': {
                        'kind': 'capability_install_proposal',
                        'gap_count': 2,
                        'blocking': True,
                    },
                    'status': 'awaiting_install_approval',
                },
            }
            diff = diff_team_manifest_payload(current_manifest, candidate, apply_state='active')
            self.assertTrue(diff['ok'])
            self.assertIn('builder', diff['diff']['agents']['added'])
            self.assertIn('researcher', diff['diff']['agents']['changed'])
            self.assertIn('workspace_fs', diff['diff']['requirements']['tools_added'])
            self.assertIn('web_search', diff['diff']['requirements']['tools_removed'])
            self.assertIn('openai_api_key', diff['diff']['requirements']['credentials_added'])
            self.assertEqual(diff['diff']['install_proposal']['candidate_gap_count'], 2)
            self.assertEqual(diff['diff']['install_proposal']['candidate_state'], 'awaiting_install_approval')
            self.assertEqual(diff['diff']['install_proposal']['candidate_actions']['summary']['tool_install_count'], 1)
            self.assertEqual(diff['diff']['summary']['credential_request_delta'], 1)
            self.assertTrue(diff['diff']['summary']['participant_delta'] >= 1)
            self.assertEqual(diff['diff']['structure_v2']['candidate_pattern'], 'sequential')
            self.assertIn('openai_api_key', diff['diff']['credential_binding']['bound_added'])



    def test_manifest_runtime_execution_roundtrip(self):
        with Session(self.engine) as session:
            thread = Thread(id='thread-manifest-runtime', service_id='svc-runtime', title='Runtime Policy Demo')
            session.add(thread)
            session.add(Conversation(thread_id=thread.id, owner_user_id='user-1', service_id='svc-runtime'))
            session.commit()

            manifest = {
                'team': {
                    'team_name': 'Runtime Policy Team',
                    'agents': [
                        {'agent_id': 'builder', 'name': 'Builder'},
                    ],
                    'runtime_execution': {
                        'checkpointing': {'write_on_turn_end': True, 'write_on_resume': False},
                        'continuous_improvement': {'enabled': True, 'max_turns': 9, 'max_total_actions': 33, 'stop_signals': ['ready_for_user']},
                        'approval_matrix': {'shell_exec': 'ask', 'network': 'deny'},
                        'providers': {
                            'codex': {'sandbox_mode': 'danger-full-access', 'approval_policy': 'on-request', 'mcp_servers': {'repo_docs': {'command': 'npx'}}},
                            'gemini': {'approval_mode': 'default', 'mcp_servers': {'workspace_docs': {'command': 'node'}}},
                        },
                    },
                },
            }

            validation = validate_team_manifest_payload(manifest, apply_state='active')
            self.assertTrue(validation['ok'])
            runtime_execution = validation['manifest']['structure_v2']['control_policy']['runtime_execution']
            self.assertTrue(runtime_execution['checkpointing']['write_on_turn_end'])
            self.assertTrue(runtime_execution['continuous_improvement']['enabled'])
            self.assertEqual(runtime_execution['providers']['codex']['sandbox_mode'], 'danger-full-access')
            self.assertIn('repo_docs', runtime_execution['providers']['codex']['mcp_servers'])

            installed = install_thread_team_manifest(session, thread, manifest, apply_state='active')
            self.assertEqual(installed['team']['runtime_execution']['providers']['codex']['sandbox_mode'], 'danger-full-access')
            payload = get_team_config_payload(session, thread_id=thread.id)
            self.assertEqual(payload['active_team']['runtime_execution']['providers']['codex']['sandbox_mode'], 'danger-full-access')
            self.assertEqual(payload['active_team']['runtime_execution']['continuous_improvement']['max_turns'], 9)

            exported = export_thread_team_manifest(session, thread)
            exported_runtime = exported['structure_v2']['control_policy']['runtime_execution']
            self.assertEqual(exported_runtime['providers']['codex']['approval_policy'], 'on-request')
            self.assertEqual(exported_runtime['providers']['gemini']['approval_mode'], 'default')
            self.assertTrue(exported['summary']['continuous_improvement_enabled'])
            self.assertEqual(exported['summary']['codex_sandbox_mode'], 'danger-full-access')
            self.assertEqual(exported['summary']['codex_mcp_count'], 1)
            self.assertEqual(exported['summary']['gemini_mcp_count'], 1)

    def test_diff_manifest_reports_runtime_execution_changes(self):
        with Session(self.engine) as session:
            thread = Thread(id='thread-manifest-runtime-diff', service_id='svc-runtime-diff', title='Runtime Policy Diff')
            session.add(thread)
            session.add(Conversation(thread_id=thread.id, owner_user_id='user-1', service_id='svc-runtime-diff'))
            session.commit()

            save_team_config_payload(session, thread_id=thread.id, payload={
                'status': 'active',
                'composition_mode': 'freeform',
                'proposal_mode': 'create',
                'active_team': {
                    'team_name': 'Current Team',
                    'agents': [{'agent_id': 'builder', 'name': 'Builder'}],
                    'runtime_execution': {
                        'continuous_improvement': {'enabled': False},
                        'providers': {'codex': {'sandbox_mode': 'workspace-write', 'approval_policy': 'never'}},
                    },
                },
                'pending_team': {},
            })

            current_manifest = export_thread_team_manifest(session, thread)
            candidate = {
                'team': {
                    'team_name': 'Current Team',
                    'agents': [{'agent_id': 'builder', 'name': 'Builder'}],
                    'runtime_execution': {
                        'continuous_improvement': {'enabled': True, 'max_turns': 7},
                        'providers': {
                            'codex': {'sandbox_mode': 'danger-full-access', 'approval_policy': 'on-request', 'mcp_servers': {'repo_docs': {'command': 'npx'}}},
                            'gemini': {'approval_mode': 'auto', 'mcp_servers': {'workspace_docs': {'command': 'node'}}},
                        },
                    },
                },
            }
            diff = diff_team_manifest_payload(current_manifest, candidate, apply_state='active')
            self.assertTrue(diff['ok'])
            self.assertTrue(diff['diff']['runtime_execution']['continuous_improvement_changed'])
            self.assertTrue(diff['diff']['runtime_execution']['codex_changed'])
            self.assertTrue(diff['diff']['runtime_execution']['gemini_changed'])
            self.assertTrue(diff['diff']['summary']['runtime_execution_changed'])
            self.assertEqual(diff['diff']['summary']['runtime_execution_mcp_delta'], 2)
            preview = '\n'.join(diff['diff']['preview_lines'])
            self.assertIn('runtime_execution.codex: sandbox=danger-full-access', preview)
            self.assertIn('runtime_execution.gemini: approval_mode=auto', preview)

    def test_structure_v2_only_manifest_is_accepted(self):
        with Session(self.engine) as session:
            thread = Thread(id='thread-manifest-5', service_id='svc-5', title='Demo 5')
            session.add(thread)
            session.add(Conversation(thread_id=thread.id, owner_user_id='user-1', service_id='svc-5'))
            session.commit()

            manifest = {
                'structure_v2': {
                    'metadata': {'team_name': 'Structured Team', 'composition_mode': 'freeform', 'proposal_mode': 'refine'},
                    'intent': {'task_brief': 'structured topology'},
                    'participants': [
                        {'participant_id': 'researcher', 'kind': 'agent', 'name': 'Researcher', 'role': 'researcher'},
                        {'participant_id': 'judge', 'kind': 'agent', 'name': 'Judge', 'role': 'synthesizer'}
                    ],
                    'topology': {
                        'pattern': 'sequential',
                        'execution_pattern': 'sequential_pipeline',
                        'edges': [{'from': 'researcher', 'to': 'judge', 'payload': 'summary_only'}],
                        'final_participant_id': 'judge'
                    }
                }
            }
            validation = validate_team_manifest_payload(manifest, apply_state='active')
            self.assertTrue(validation['ok'])
            self.assertEqual(validation['manifest']['team']['agents'][0]['agent_id'], 'researcher')
            installed = install_thread_team_manifest(session, thread, manifest, apply_state='active')
            self.assertEqual(installed['structure_v2']['topology']['pattern'], 'sequential')
            self.assertEqual(installed['team']['structure_v2']['topology']['pattern'], 'sequential')

    def test_manifest_preserves_pattern_runtime_state(self):
        with Session(self.engine) as session:
            thread = Thread(id='thread-manifest-6', service_id='svc-6', title='Demo 6')
            session.add(thread)
            session.add(Conversation(thread_id=thread.id, owner_user_id='user-1', service_id='svc-6'))
            session.commit()

            manifest = {
                'team': {
                    'team_name': 'Pattern Team',
                    'agents': [
                        {'agent_id': 'builder', 'name': 'Builder'},
                    ],
                },
                'pattern_conflict': {
                    'classification': 'structure_override_required',
                    'current_pattern': 'debate',
                    'requested_pattern': 'single',
                    'reason': 'user asked for direct answer only',
                },
                'temporary_execution_override': {
                    'mode': 'single_turn_override',
                    'original_pattern': 'debate',
                    'effective_pattern': 'single',
                },
                'pattern_recovery': {
                    'original_pattern': 'debate',
                    'recovery_mode': 'restore_after_turn',
                },
            }
            installed = install_thread_team_manifest(session, thread, manifest, apply_state='pending')
            self.assertEqual(installed['pattern_conflict']['classification'], 'structure_override_required')
            self.assertEqual(installed['temporary_execution_override']['effective_pattern'], 'single')
            self.assertEqual(installed['pattern_recovery']['recovery_mode'], 'restore_after_turn')
            payload = get_team_config_payload(session, thread_id=thread.id)
            self.assertEqual(payload['pattern_conflict']['classification'], 'structure_override_required')
            self.assertEqual(payload['temporary_execution_override']['effective_pattern'], 'single')
            self.assertEqual(payload['pattern_recovery']['recovery_mode'], 'restore_after_turn')


    def test_manifest_roundtrips_knowledge_surface_and_memory_policy(self):
        with Session(self.engine) as session:
            thread = Thread(id='thread-manifest-7', service_id='svc-7', title='Demo 7')
            session.add(thread)
            session.add(Conversation(thread_id=thread.id, owner_user_id='user-1', service_id='svc-7'))
            session.commit()

            manifest = {
                'structure_v2': {
                    'metadata': {'team_name': 'KB Team', 'composition_mode': 'freeform', 'proposal_mode': 'refine'},
                    'intent': {'task_brief': 'implement with dynamic kb'},
                    'participants': [
                        {'participant_id': 'builder', 'kind': 'agent', 'name': 'Builder', 'role': 'builder'},
                        {'participant_id': 'reviewer', 'kind': 'agent', 'name': 'Reviewer', 'role': 'reviewer'},
                    ],
                    'topology': {
                        'pattern': 'sequential',
                        'execution_pattern': 'sequential_pipeline',
                        'edges': [{'from': 'builder', 'to': 'reviewer', 'payload': 'summary_only'}],
                        'final_participant_id': 'reviewer',
                    },
                    'knowledge_surface': {
                        'profile_id': 'impl_review_kb',
                        'display_name': 'Implementation Review KB',
                        'docs': [
                            {'doc_id': 'plan', 'file_name': 'implementation_blueprint.md', 'semantic_slot': 'plan', 'write_policy': 'mutable'},
                            {'doc_id': 'decisions', 'file_name': 'review_rulings.md', 'semantic_slot': 'decisions', 'write_policy': 'append_only'},
                        ],
                        'stable_memory_files': ['knowledge_base_contract.md'],
                    },
                    'memory_policy': {
                        'stable_semantic_slots': ['decisions', 'artifacts'],
                        'mutable_semantic_slots': ['plan', 'research', 'progress'],
                        'migration_strategy': 'semantic_slot_preserving',
                    },
                }
            }
            validation = validate_team_manifest_payload(manifest, apply_state='active')
            self.assertTrue(validation['ok'])
            self.assertEqual(validation['manifest']['structure_v2']['knowledge_surface']['profile_id'], 'impl_review_kb')
            self.assertEqual(validation['manifest']['structure_v2']['memory_policy']['stable_semantic_slots'], ['decisions', 'artifacts'])

            installed = install_thread_team_manifest(session, thread, manifest, apply_state='active')
            self.assertEqual(installed['summary']['knowledge_doc_count'], 2)
            self.assertEqual(installed['structure_v2']['knowledge_surface']['docs'][0]['file_name'], 'implementation_blueprint.md')
            self.assertEqual(installed['team']['knowledge_base_profile']['profile_id'], 'impl_review_kb')
            self.assertIn('decisions', installed['team']['memory_policy']['stable_semantic_slots'])

            exported = export_thread_team_manifest(session, thread)
            self.assertEqual(exported['structure_v2']['knowledge_surface']['profile_id'], 'impl_review_kb')
            self.assertEqual(exported['summary']['stable_memory_slot_count'], 2)

    def test_validate_rejects_empty_team(self):
        validation = validate_team_manifest_payload({'team': {'agents': []}}, apply_state='active')
        self.assertFalse(validation['ok'])
        self.assertTrue(any('at least one agent' in err for err in validation['errors']))

    def test_install_preserves_install_proposal_state(self):
        with Session(self.engine) as session:
            thread = Thread(id='thread-manifest-4', service_id='svc-4', title='Demo 4')
            session.add(thread)
            session.add(Conversation(thread_id=thread.id, owner_user_id='user-1', service_id='svc-4'))
            session.commit()

            manifest = {
                'team': {
                    'team_name': 'Proposal Team',
                    'agents': [
                        {'agent_id': 'builder', 'name': 'Builder'},
                    ],
                },
                'install_proposal': {
                    'kind': 'capability_install_proposal',
                    'gap_count': 1,
                    'blocking': True,
                    'requirements': {
                        'tools': [{'tool_id': 'workspace_fs', 'required_by': 'Builder'}],
                    },
                },
                'install_proposal_state': {
                    'proposal': {
                        'kind': 'capability_install_proposal',
                        'gap_count': 1,
                        'blocking': True,
                    },
                    'status': 'installed_pending',
                },
            }
            installed = install_thread_team_manifest(session, thread, manifest, apply_state='pending')
            self.assertEqual(installed['install_proposal_state']['status'], 'installed_pending')
            payload = get_team_config_payload(session, thread_id=thread.id)
            self.assertEqual(payload['install_proposal_state']['status'], 'installed_pending')
            self.assertEqual(payload['credential_binding_state']['summary']['bound_count'], 1)

    def test_manifest_roundtrip_preserves_required_and_optional_tools(self):
        with Session(self.engine) as session:
            thread = Thread(id='thread-manifest-tools', service_id='svc-tools', title='Tools')
            session.add(thread)
            session.add(Conversation(thread_id=thread.id, owner_user_id='user-1', service_id='svc-tools'))
            session.commit()

            manifest = {
                'team': {
                    'team_name': 'Implementation Team',
                    'agents': [
                        {
                            'agent_id': 'builder',
                            'name': 'Builder',
                            'role': 'builder',
                            'required_tool_ids': ['workspace_fs'],
                            'optional_tool_ids': ['shell'],
                        },
                    ],
                },
            }

            installed = install_thread_team_manifest(session, thread, manifest, apply_state='active')
            self.assertEqual(installed['team']['agents'][0]['required_tool_ids'], ['workspace_fs'])
            self.assertEqual(installed['team']['agents'][0]['optional_tool_ids'], ['shell'])

            exported = export_thread_team_manifest(session, thread)
            self.assertEqual(exported['team']['agents'][0]['required_tool_ids'], ['workspace_fs'])
            self.assertEqual(exported['team']['agents'][0]['optional_tool_ids'], ['shell'])

    def test_manifest_roundtrip_preserves_provider_and_context_policy(self):
        with Session(self.engine) as session:
            thread = Thread(id='thread-manifest-provider', service_id='svc-provider', title='Provider')
            session.add(thread)
            session.add(Conversation(thread_id=thread.id, owner_user_id='user-1', service_id='svc-provider'))
            session.commit()

            manifest = {
                'structure_v2': {
                    'metadata': {'team_name': 'Provider Team', 'composition_mode': 'structured', 'proposal_mode': 'refine'},
                    'intent': {'task_brief': 'preserve provider + context policy'},
                    'participants': [
                        {
                            'participant_id': 'builder',
                            'kind': 'agent',
                            'name': 'Builder',
                            'role': 'builder',
                            'provider': 'codex',
                            'model': 'gpt-5-codex',
                            'required_tool_ids': ['workspace_fs'],
                            'optional_tool_ids': ['shell'],
                            'context_policy': {
                                'reads': {'grants': ['upstream_results']},
                                'writes': {'publish_targets': ['artifact_index']},
                            },
                        },
                    ],
                    'topology': {'pattern': 'single', 'execution_pattern': 'single_specialist'},
                },
            }

            installed = install_thread_team_manifest(session, thread, manifest, apply_state='active')
            participant = installed['structure_v2']['participants'][0]
            self.assertEqual(participant['provider'], 'codex')
            self.assertEqual(participant['required_tool_ids'], ['workspace_fs'])
            self.assertEqual(participant['optional_tool_ids'], ['shell'])
            self.assertEqual(participant['context_policy']['writes']['publish_targets'], ['artifact_index'])

            exported = export_thread_team_manifest(session, thread)
            agent = exported['team']['agents'][0]
            self.assertEqual(agent['provider'], 'codex')
            self.assertEqual(agent['required_tool_ids'], ['workspace_fs'])
            self.assertEqual(agent['optional_tool_ids'], ['shell'])
            self.assertEqual(agent['context_policy']['writes']['publish_targets'], ['artifact_index'])

    def test_diff_manifest_guardrails_warn_on_destructive_changes(self):
        with Session(self.engine) as session:
            thread = Thread(id='thread-manifest-guardrails', service_id='svc-guardrails', title='Guardrails')
            session.add(thread)
            session.add(Conversation(thread_id=thread.id, owner_user_id='user-1', service_id='svc-guardrails'))
            session.commit()

            current_manifest = {
                'structure_v2': {
                    'metadata': {'team_name': 'Current Team', 'composition_mode': 'structured', 'proposal_mode': 'apply'},
                    'participants': [
                        {'participant_id': 'repo_scout', 'kind': 'agent', 'name': 'Repo Scout', 'role': 'researcher', 'provider': 'openai', 'model': 'gpt-5.4', 'required_tool_ids': ['web']},
                        {'participant_id': 'client_companion_builder', 'kind': 'agent', 'name': 'Client Companion Builder', 'role': 'builder', 'required_tool_ids': ['workspace_fs'], 'optional_tool_ids': ['shell']},
                        {'participant_id': 'delivery_synthesizer', 'kind': 'agent', 'name': 'Delivery Synthesizer', 'role': 'synthesizer'},
                    ],
                    'topology': {'pattern': 'workflow', 'execution_pattern': 'builder_reviewer_loop', 'final_participant_id': 'delivery_synthesizer'},
                    'control_policy': {'final_answer_owner_participant_id': 'delivery_synthesizer'},
                    'memory_plan': {
                        'surfaces': [
                            {'surface_id': 'implementation_notes', 'semantic_slots': ['implementation'], 'target_roles': ['builder'], 'write_policy': 'shared'},
                            {'surface_id': 'final_answer', 'semantic_slots': ['final_answer'], 'target_roles': ['synthesizer'], 'write_policy': 'final'},
                        ],
                        'default_load_surface_ids': ['implementation_notes'],
                        'writable_surface_ids': ['implementation_notes', 'final_answer'],
                    },
                },
            }
            candidate_manifest = {
                'structure_v2': {
                    'metadata': {'team_name': 'Candidate Team', 'composition_mode': 'structured', 'proposal_mode': 'refine'},
                    'participants': [
                        {'participant_id': 'client_companion_builder', 'kind': 'agent', 'name': 'Client Companion Builder', 'role': 'researcher'},
                        {'participant_id': 'delivery_synthesizer', 'kind': 'agent', 'name': 'Delivery Synthesizer', 'role': 'researcher'},
                    ],
                    'topology': {'pattern': 'sequential', 'execution_pattern': 'sequential_pipeline', 'final_participant_id': 'client_companion_builder'},
                    'control_policy': {'final_answer_owner_participant_id': 'client_companion_builder'},
                    'memory_plan': {
                        'surfaces': [
                            {'surface_id': 'final_answer', 'semantic_slots': ['final_answer'], 'target_roles': ['researcher'], 'write_policy': 'final'},
                        ],
                        'default_load_surface_ids': [],
                        'writable_surface_ids': ['final_answer'],
                    },
                },
            }
            diff = diff_team_manifest_payload(current_manifest, candidate_manifest, apply_state='active')
            self.assertTrue(diff['ok'])
            guardrails = diff['diff']['guardrails']
            self.assertEqual(guardrails['risk_level'], 'high')
            self.assertTrue(guardrails['destructive_changes_present'])
            self.assertIn('repo_scout', guardrails['issues']['removed_participants'])
            self.assertIn('builder', guardrails['issues']['lost_role_coverage'])
            self.assertTrue(any('Removing participants' in warning for warning in guardrails['warnings']))
            self.assertTrue(any('Removing memory surfaces' in warning for warning in guardrails['warnings']))

    def test_install_manifest_returns_guardrails(self):
        with Session(self.engine) as session:
            thread = Thread(id='thread-manifest-install-guardrails', service_id='svc-install-guardrails', title='Install Guardrails')
            session.add(thread)
            session.add(Conversation(thread_id=thread.id, owner_user_id='user-1', service_id='svc-install-guardrails'))
            session.commit()

            save_team_config_payload(session, thread_id=thread.id, payload={
                'status': 'active',
                'composition_mode': 'structured',
                'proposal_mode': 'apply',
                'active_team': {
                    'team_name': 'Current Team',
                    'agents': [
                        {'agent_id': 'builder', 'name': 'Builder', 'role': 'builder', 'required_tool_ids': ['workspace_fs']},
                        {'agent_id': 'synth', 'name': 'Synth', 'role': 'synthesizer'},
                    ],
                    'memory_plan': {
                        'surfaces': [
                            {'surface_id': 'implementation_notes', 'semantic_slots': ['implementation'], 'target_roles': ['builder'], 'write_policy': 'shared'},
                        ],
                        'writable_surface_ids': ['implementation_notes'],
                    },
                },
                'pending_team': {},
            })

            manifest = {
                'team': {
                    'team_name': 'Candidate Team',
                    'agents': [
                        {'agent_id': 'builder', 'name': 'Builder', 'role': 'researcher'},
                    ],
                    'memory_plan': {
                        'surfaces': [
                            {'surface_id': 'final_answer', 'semantic_slots': ['final_answer'], 'target_roles': ['researcher'], 'write_policy': 'final'},
                        ],
                        'writable_surface_ids': ['final_answer'],
                    },
                },
            }

            installed = install_thread_team_manifest(session, thread, manifest, apply_state='active')
            self.assertIn('install_guardrails', installed)
            self.assertTrue(installed['install_guardrails']['warning_count'] >= 1)
            self.assertTrue(installed['install_guardrails']['destructive_changes_present'])

    def test_guardrails_flag_publish_contract_mismatch(self):
        current_manifest = {
            'structure_v2': {
                'participants': [
                    {'participant_id': 'builder', 'kind': 'agent', 'name': 'Builder', 'role': 'builder'},
                    {'participant_id': 'synth', 'kind': 'agent', 'name': 'Synth', 'role': 'synthesizer'},
                ],
                'topology': {'pattern': 'sequential', 'execution_pattern': 'sequential_pipeline', 'final_participant_id': 'synth'},
                'control_policy': {'final_answer_owner_participant_id': 'synth'},
                'memory_plan': {
                    'surfaces': [
                        {'surface_id': 'final_answer', 'semantic_slots': ['final_answer'], 'target_roles': ['synthesizer'], 'write_policy': 'final'},
                        {'surface_id': 'artifact_index', 'semantic_slots': ['artifact_index'], 'target_roles': ['synthesizer'], 'write_policy': 'index'},
                    ],
                    'default_load_surface_ids': ['final_answer'],
                    'writable_surface_ids': ['final_answer', 'artifact_index'],
                },
            },
        }
        candidate_manifest = {
            'structure_v2': {
                'participants': [
                    {'participant_id': 'builder', 'kind': 'agent', 'name': 'Builder', 'role': 'builder'},
                    {'participant_id': 'synth', 'kind': 'agent', 'name': 'Synth', 'role': 'researcher'},
                ],
                'topology': {'pattern': 'sequential', 'execution_pattern': 'sequential_pipeline', 'final_participant_id': 'synth'},
                'control_policy': {'final_answer_owner_participant_id': 'synth'},
                'memory_plan': {
                    'surfaces': [
                        {'surface_id': 'final_answer', 'semantic_slots': ['final_answer'], 'target_roles': ['synthesizer'], 'write_policy': 'final'},
                    ],
                    'default_load_surface_ids': ['final_answer'],
                    'writable_surface_ids': ['final_answer'],
                },
            },
        }
        diff = diff_team_manifest_payload(current_manifest, candidate_manifest, apply_state='active')
        self.assertTrue(diff['ok'])
        guardrails = diff['diff']['guardrails']
        self.assertEqual(guardrails['recommended_action'], 'fix_publish_contract')
        self.assertTrue(guardrails['issues']['final_owner_publish_blocked'])
        self.assertTrue(guardrails['issues']['artifact_publish_missing'])
        self.assertTrue(any('Final answer owner cannot publish final_answer' in warning for warning in guardrails['warnings']))


    def test_guardrails_flag_missing_final_owner_as_publish_contract_issue(self):
        candidate_manifest = {
            'structure_v2': {
                'participants': [
                    {'participant_id': 'builder', 'kind': 'agent', 'name': 'Builder', 'role': 'builder'},
                    {'participant_id': 'synth', 'kind': 'agent', 'name': 'Synth', 'role': 'synthesizer'},
                ],
                'topology': {'pattern': 'sequential', 'execution_pattern': 'sequential_pipeline'},
                'control_policy': {},
                'memory_plan': {
                    'surfaces': [
                        {'surface_id': 'final_answer', 'semantic_slots': ['final_answer'], 'target_roles': ['synthesizer'], 'write_policy': 'final'},
                        {'surface_id': 'artifact_index', 'semantic_slots': ['artifact_index'], 'target_roles': ['builder'], 'write_policy': 'index'},
                    ],
                    'default_load_surface_ids': ['final_answer'],
                    'writable_surface_ids': ['final_answer', 'artifact_index'],
                },
            },
        }
        diff = diff_team_manifest_payload({'structure_v2': {}}, candidate_manifest, apply_state='active')
        self.assertTrue(diff['ok'])
        guardrails = diff['diff']['guardrails']
        self.assertEqual(guardrails['recommended_action'], 'fix_publish_contract')
        self.assertTrue(guardrails['issues']['final_owner_missing'])
        self.assertTrue(any('Final answer owner is not declared' in warning for warning in guardrails['warnings']))


if __name__ == '__main__':
    unittest.main()
