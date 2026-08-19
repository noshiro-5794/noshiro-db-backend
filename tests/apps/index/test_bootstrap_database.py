from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command


def test_bootstrap_database_installs_required_extensions_idempotently() -> None:
    cursor = Mock()
    cursor_context = Mock()
    cursor_context.__enter__ = Mock(return_value=cursor)
    cursor_context.__exit__ = Mock(return_value=False)

    with (
        patch(
            "apps.index.management.commands.bootstrap_database.connection.cursor",
            return_value=cursor_context,
        ),
        patch(
            "apps.index.management.commands.bootstrap_database.transaction.atomic",
            return_value=cursor_context,
        ),
    ):
        call_command("bootstrap_database", stdout=StringIO())

    cursor.execute.assert_called_once_with('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
