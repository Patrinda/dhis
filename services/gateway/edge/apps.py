from django.apps import AppConfig


class EdgeConfig(AppConfig):
    name = "edge"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from dhis_common.background import start_job
        from .queue import flush_queue
        start_job("queue-flush", flush_queue, 5)
