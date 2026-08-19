from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection, transaction


class Command(BaseCommand):
    help = "Install PostgreSQL extensions required before the first Django migration."

    REQUIRED_EXTENSIONS = ("pg_trgm",)

    def handle(self, *args: Any, **options: Any) -> None:
        quoted_extensions = [
            connection.ops.quote_name(extension)
            for extension in self.REQUIRED_EXTENSIONS
        ]
        with transaction.atomic(), connection.cursor() as cursor:
            for extension in quoted_extensions:
                cursor.execute(f"CREATE EXTENSION IF NOT EXISTS {extension}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Database extensions ready: {', '.join(self.REQUIRED_EXTENSIONS)}"
            )
        )
