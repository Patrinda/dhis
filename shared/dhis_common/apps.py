from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _sqlite_wal(sender, connection, **kwargs):
    """Let several local services share SQLite files without 'database is locked'."""
    if connection.vendor == "sqlite":
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")


class DhisCommonConfig(AppConfig):
    name = "dhis_common"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        connection_created.connect(_sqlite_wal)
