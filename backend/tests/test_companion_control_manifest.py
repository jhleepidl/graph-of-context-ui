from __future__ import annotations

import unittest

try:
    from app.routers import companion_control as companion_control_router
    from app.services.companion_control import get_companion_control_manifest
    _IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    companion_control_router = None  # type: ignore[assignment]
    get_companion_control_manifest = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc


@unittest.skipIf(_IMPORT_ERROR is not None, f"missing dependency: {_IMPORT_ERROR}")
class CompanionControlManifestTests(unittest.TestCase):
    def test_manifest_exposes_user_facing_companions_and_controls(self) -> None:
        manifest = get_companion_control_manifest()
        self.assertEqual(manifest['schema_version'], 'goc.companion_control_manifest/v1')
        self.assertEqual(manifest['product_positioning']['external_language'], 'Persistent AI Room')
        self.assertEqual(manifest['product_positioning']['principle'], 'The model can change. The Room remembers.')
        companion_ids = {item['id'] for item in manifest['companions']}
        self.assertGreaterEqual({'research', 'implementation', 'product', 'concierge'}, companion_ids)
        context_commands = {item['telegram_command'] for item in manifest['context_modes']}
        self.assertIn('/context project-only', context_commands)
        self.assertIn('/context clean-slate', context_commands)
        self.assertIn('/context exclude <source-or-assumption>', context_commands)
        flow_commands = {cmd for flow in manifest['user_flows'] for cmd in flow.get('commands', [])}
        self.assertIn('/correct materialize-preview', flow_commands)
        self.assertIn('/brief', flow_commands)
        self.assertIn('/continue', flow_commands)
        self.assertEqual(manifest['runtime_status']['goc_web_runtime'], 'manifest_and_hub_scaffold')

    def test_router_returns_same_manifest_shape_without_db(self) -> None:
        out = companion_control_router.companion_control_manifest()
        self.assertEqual(out['schema_version'], 'goc.companion_control_manifest/v1')
        self.assertTrue(out['companions'])
        self.assertTrue(out['user_flows'])


if __name__ == '__main__':
    unittest.main()
