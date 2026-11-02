from django.urls import include, path

from dhis_common import views as common
from ledger import urls as ledger_urls

urlpatterns = [
    path("healthz", common.healthz),
    path("readyz", common.readyz),
    path("internal/events/", common.EventsWebhook.as_view()),
    path("internal/", include((ledger_urls.internal_urlpatterns, "internal"))),
    path("audit/", include(ledger_urls)),
    path("consents/", include((ledger_urls.consent_urlpatterns, "consents"))),
]
