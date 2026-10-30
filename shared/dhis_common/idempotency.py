import json
from functools import wraps

from django.db import IntegrityError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from .models import IdempotencyRecord


def idempotent(view_method):
    """Decorator for POST handlers. If the same Idempotency-Key is sent twice
    by the same user to the same address, the second call returns the first
    answer and does nothing new."""

    @wraps(view_method)
    def wrapper(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key", "").strip()
        if not key:
            return view_method(self, request, *args, **kwargs)
        scope = f"{request.user.id}:{request.method}:{request.path}"[:200]
        try:
            record = IdempotencyRecord.objects.create(key=key[:80], scope=scope)
        except IntegrityError:
            record = IdempotencyRecord.objects.get(key=key[:80], scope=scope)
            if record.status_code == 0:
                return Response({"error": {"code": "in_progress", "message": "The same request is still being processed."}}, status=409)
            replay = Response(record.body, status=record.status_code)
            replay["Idempotent-Replay"] = "true"
            return replay
        try:
            response = view_method(self, request, *args, **kwargs)
        except Exception:
            record.delete()
            raise
        if 200 <= response.status_code < 300:
            record.status_code = response.status_code
            record.body = json.loads(JSONRenderer().render(response.data))
            record.save(update_fields=["status_code", "body"])
        else:
            record.delete()  # failures can be retried with the same key
        return response

    return wrapper
