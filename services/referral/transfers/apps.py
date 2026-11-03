from django.apps import AppConfig


class TransfersConfig(AppConfig):
    name = "transfers"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from dhis_common.background import start_job, start_outbox_dispatcher
        start_outbox_dispatcher()
        from .services import expire_overdue
        start_job("expiry", expire_overdue, 30)
