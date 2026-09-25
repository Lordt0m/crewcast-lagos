from django.apps import AppConfig
from django.db.backends.signals import connection_created

def configure_sqlite(sender, connection, **kwargs):
    """Configures SQLite for WAL mode and busy timeout for local test concurrency."""
    if connection.vendor == 'sqlite':
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA busy_timeout = 10000;")

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'CrewCast Core'

    def ready(self):
        connection_created.connect(configure_sqlite)
