from django.urls import include, path

from dhis_common import views as common

urlpatterns = [
    path("healthz", common.healthz),
    path("readyz", common.readyz),
    path("internal/events/", common.EventsWebhook.as_view()),
    path("dashboard/", include("metrics.urls")),
]
