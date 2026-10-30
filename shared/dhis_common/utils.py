import hashlib
import hmac
import re

from django.conf import settings
from rest_framework import serializers

NATIONAL_ID_RE = re.compile(r"^\d{16}$")
ICD10_RE = re.compile(r"^[A-TV-Z][0-9]{2}(\.[0-9A-Z]{1,4})?$")


def hash_identifier(national_id: str) -> str:
    """Salted one-way hash. Services that only need to *match* a person (the
    claim table, consent, events) store this instead of the real number."""
    return hmac.new(settings.ID_SALT.encode(), national_id.encode(), hashlib.sha256).hexdigest()


def mask_identifier(national_id: str) -> str:
    return national_id[:1] + "*" * (len(national_id) - 4) + national_id[-3:] if len(national_id) >= 8 else "***"


def validate_national_id(value: str) -> str:
    value = (value or "").strip()
    if not NATIONAL_ID_RE.match(value):
        raise serializers.ValidationError("National ID must be exactly 16 digits.")
    return value


def validate_icd10(value: str) -> str:
    value = (value or "").strip().upper()
    if value and not ICD10_RE.match(value):
        raise serializers.ValidationError("Use an ICD-10 code such as B50.9 or J18.9.")
    return value


def audit_access(request, action: str, target_ref: str, detail: dict = None):
    """Queue an audit event describing who touched what."""
    from .events import publish

    user = request.user
    publish("audit.access", {
        "actor_id": user.id, "actor_name": user.name, "role": user.role, "hospital": user.hospital,
        "action": action, "target_ref": target_ref, "detail": detail or {},
        "request_id": request.headers.get("X-Request-ID", ""),
    })
