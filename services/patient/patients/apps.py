from django.apps import AppConfig


class PatientsConfig(AppConfig):
    name = "patients"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from dhis_common.background import start_outbox_dispatcher
        start_outbox_dispatcher()
