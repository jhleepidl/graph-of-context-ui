from __future__ import annotations

import unittest
from sqlalchemy import inspect, text

from tests.db_test_utils import create_test_engine
from app import db as app_db


class DbLightMigrationTests(unittest.TestCase):
    def test_conversation_team_config_state_json_added_to_existing_table(self) -> None:
        engine = create_test_engine("sqlite://")
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE conversation_team_configs (
                        id VARCHAR PRIMARY KEY,
                        conversation_id VARCHAR,
                        thread_id VARCHAR,
                        status VARCHAR,
                        active_team_json TEXT,
                        pending_team_json TEXT,
                        updated_at DATETIME
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO conversation_team_configs
                    (id, conversation_id, thread_id, status, active_team_json, pending_team_json, updated_at)
                    VALUES ('cfg-1', 'conv-1', 'thread-1', 'active', '{}', '{}', CURRENT_TIMESTAMP)
                    """
                )
            )

        previous_engine = app_db.engine
        app_db.engine = engine
        try:
            app_db._ensure_conversation_team_config_columns()
            with engine.connect() as conn:
                cols = {c["name"] for c in inspect(conn).get_columns("conversation_team_configs")}
                self.assertIn("state_json", cols)
                value = conn.execute(text("SELECT state_json FROM conversation_team_configs WHERE id='cfg-1'")).scalar()
                self.assertEqual(value, "{}")
        finally:
            app_db.engine = previous_engine


if __name__ == "__main__":
    unittest.main()
