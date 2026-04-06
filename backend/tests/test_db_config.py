from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app import db


class DatabaseConfigTests(unittest.TestCase):
    def test_normalize_db_url_upgrades_postgres_aliases(self) -> None:
        self.assertEqual(
            db.normalize_db_url('postgres://user:pass@localhost:5432/goc'),
            'postgresql+psycopg2://user:pass@localhost:5432/goc',
        )
        self.assertEqual(
            db.normalize_db_url('postgresql://user:pass@localhost:5432/goc'),
            'postgresql+psycopg2://user:pass@localhost:5432/goc',
        )

    def test_derive_postgres_admin_db_url_uses_explicit_override(self) -> None:
        with patch.dict(os.environ, {
            'GOC_DB_CREATE_URL': 'postgresql+psycopg2://postgres:postgres@localhost:5432/postgres',
            'GOC_DB_CREATE_DATABASE': '',
        }, clear=False):
            self.assertEqual(
                db._derive_postgres_admin_db_url('postgresql+psycopg2://postgres:postgres@localhost:5432/goc'),
                'postgresql+psycopg2://postgres:postgres@localhost:5432/postgres',
            )

    def test_derive_postgres_admin_db_url_falls_back_to_postgres_database(self) -> None:
        with patch.dict(os.environ, {
            'GOC_DB_CREATE_URL': '',
            'GOC_DB_CREATE_DATABASE': 'postgres',
        }, clear=False):
            self.assertEqual(
                db._derive_postgres_admin_db_url('postgresql+psycopg2://postgres:postgres@localhost:5432/goc'),
                'postgresql+psycopg2://postgres:postgres@localhost:5432/postgres',
            )

    def test_safe_postgres_database_name_rejects_unsafe_identifier(self) -> None:
        self.assertEqual(
            db._safe_postgres_database_name('postgresql+psycopg2://postgres:postgres@localhost:5432/goc_dev'),
            'goc_dev',
        )
        self.assertIsNone(
            db._safe_postgres_database_name('postgresql+psycopg2://postgres:postgres@localhost:5432/goc;dropdb'),
        )

    def test_ensure_database_exists_is_noop_without_auto_create(self) -> None:
        with patch.dict(os.environ, {'GOC_DB_AUTO_CREATE': 'false'}, clear=False), \
             patch('app.db.create_engine') as create_engine_mock:
            db.ensure_database_exists('postgresql+psycopg2://postgres:postgres@localhost:5432/goc')
            create_engine_mock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
