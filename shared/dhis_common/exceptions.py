from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_handler


class ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "A required service is not reachable right now."
    default_code = "service_unavailable"


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The record was changed by someone else. Reload and try again."
    default_code = "conflict"


def handler(exc, context):
    """One error shape for the whole system: {"error": {"code", "message", "details"}}"""
    response = drf_handler(exc, context)
    if response is None:
        return None
    data = response.data
    if isinstance(data, dict) and set(data.keys()) == {"detail"}:
        message, details = str(data["detail"]), None
        code = getattr(data["detail"], "code", None) or getattr(exc, "default_code", "error")
    else:
        message, details = "Some fields are not valid.", data
        code = "validation_error" if response.status_code == 400 else getattr(exc, "default_code", "error")
    response.data = {"error": {"code": str(code), "message": message}}
    if details is not None:
        response.data["error"]["details"] = details
    return response
