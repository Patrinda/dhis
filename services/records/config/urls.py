from django.urls import include, path

from clinical import urls as clinical_urls
from dhis_common import views as common

urlpatterns = [
    path("healthz", common.healthz),
    path("readyz", common.readyz),
    path("records/", include(clinical_urls)),
    path("internal/", include((clinical_urls.internal_urlpatterns, "internal"))),
]
