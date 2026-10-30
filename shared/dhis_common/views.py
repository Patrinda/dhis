from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils.module_loading import import_string
from rest_framework.response import Response
from rest_framework.views import APIView

from .events import process_once
from .permissions import IsInternal


def healthz(request):
    """Liveness: the process is running."""
    return JsonResponse({"status": "ok", "service": settings.SERVICE_NAME, "node": settings.NODE_CODE})


def readyz(request):
    """Readiness: the process can reach its database."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ready", "service": settings.SERVICE_NAME})
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"status": "not ready", "error": type(exc).__name__}, status=503)


class EventsWebhook(APIView):
    """POST /internal/events/ : the HTTP transport entry point for consumers.
    settings.EVENT_HANDLER names the function that handles one event."""

    authentication_classes = []
    permission_classes = [IsInternal]

    def post(self, request):
        handler = import_string(settings.EVENT_HANDLER)
        env = request.data
        if not isinstance(env, dict) or "message_id" not in env or "type" not in env:
            return Response({"error": {"code": "bad_event", "message": "Not a valid event."}}, status=400)
        processed = process_once(env, handler)
        return Response({"processed": processed, "duplicate": not processed})
