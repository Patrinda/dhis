import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission


def has_internal_key(request) -> bool:
    supplied = request.headers.get("X-Internal-Key", "")
    return bool(supplied) and hmac.compare_digest(supplied, settings.INTERNAL_API_KEY)


class IsInternal(BasePermission):
    """Service-to-service calls carry a shared secret instead of a user token."""

    def has_permission(self, request, view):
        return has_internal_key(request)


def roles(*allowed):
    """Build a permission class that admits only the listed roles.
    Use as: permission_classes = [roles('DOCTOR', 'NURSE')]"""

    class _RolePermission(BasePermission):
        message = "Your role is not allowed to do this."

        def has_permission(self, request, view):
            user = request.user
            return bool(user and getattr(user, "role", None) in allowed)

    _RolePermission.__name__ = "Roles_" + "_".join(allowed)
    return _RolePermission


def roles_for_method(read=(), write=()):
    """Different roles for safe (GET) and unsafe (POST/PUT/PATCH/DELETE) methods."""

    class _MethodRolePermission(BasePermission):
        message = "Your role is not allowed to do this."

        def has_permission(self, request, view):
            user = request.user
            role = getattr(user, "role", None) if user else None
            if request.method in ("GET", "HEAD", "OPTIONS"):
                return role in read or role in write
            return role in write

    return _MethodRolePermission
