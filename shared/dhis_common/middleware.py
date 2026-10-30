import threading
import uuid

_local = threading.local()


def current_request_id() -> str:
    return getattr(_local, "request_id", "")


class RequestIDMiddleware:
    """Gives every request a correlation id so one action can be followed
    across the gateway and all services in the logs."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        _local.request_id = rid
        response = self.get_response(request)
        response["X-Request-ID"] = rid
        return response
