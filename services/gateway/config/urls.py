from django.urls import path, re_path
from django.views.static import serve

from django.conf import settings

from dhis_common import views as common
from edge import views

FRONTEND = settings.PROJECT_ROOT / "frontend"

urlpatterns = [
    path("healthz", common.healthz),
    path("readyz", common.readyz),
    path("api/health/", views.health),
    path("api/queue/", views.queue_list),
    path("api/queue/flush/", views.queue_flush),
    re_path(r"^api/(?P<path>.+)$", views.proxy),
    path("", serve, {"path": "index.html", "document_root": FRONTEND}),
    re_path(r"^(?P<path>.+)$", serve, {"document_root": FRONTEND}),
]
