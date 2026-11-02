from django.urls import include, path

from dhis_common import views as common
from patients import urls as patient_urls

urlpatterns = [
    path("healthz", common.healthz),
    path("readyz", common.readyz),
    path("patients/", include(patient_urls)),
    path("internal/", include((patient_urls.internal_urlpatterns, "internal"))),
]
