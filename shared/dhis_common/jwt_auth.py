"""RS256 token handling.

Only the Identity service holds the private key and signs tokens. Every other
service holds the public key and can verify a token without calling Identity.
"""
import datetime
import uuid
from functools import lru_cache

import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

ROLES = [
    "SYSTEM_ADMIN", "REGISTRATION", "NURSE", "DOCTOR",
    "PHARMACIST", "LAB_TECH", "HOSPITAL_MANAGER", "DPO",
]


class Principal:
    """The signed-in person, rebuilt from the token (no database lookup)."""

    is_authenticated = True
    is_anonymous = False

    def __init__(self, claims: dict):
        self.id = str(claims["sub"])
        self.username = claims.get("username", "")
        self.name = claims.get("name", "")
        self.role = claims.get("role", "")
        self.hospital = claims.get("hospital", "")
        self.claims = claims

    def __str__(self):
        return f"{self.username} ({self.role}@{self.hospital or 'national'})"


@lru_cache(maxsize=1)
def _public_key() -> bytes:
    with open(settings.JWT_PUBLIC_KEY_PATH, "rb") as handle:
        return handle.read()


@lru_cache(maxsize=1)
def _private_key() -> bytes:
    with open(settings.JWT_PRIVATE_KEY_PATH, "rb") as handle:
        return handle.read()


def issue_token(*, user_id, username, name, role, hospital) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    claims = {
        "iss": settings.JWT_ISSUER,
        "sub": str(user_id),
        "username": username,
        "name": name,
        "role": role,
        "hospital": hospital or "",
        "iat": now,
        "exp": now + datetime.timedelta(minutes=settings.JWT_LIFETIME_MINUTES),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, _private_key(), algorithm="RS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token, _public_key(), algorithms=["RS256"],
            issuer=settings.JWT_ISSUER, options={"require": ["exp", "sub", "iss"]},
        )
    except jwt.ExpiredSignatureError:
        raise AuthenticationFailed("Your session has expired. Please sign in again.", code="token_expired")
    except jwt.PyJWTError:
        raise AuthenticationFailed("The sign-in token is not valid.", code="token_invalid")
    except FileNotFoundError:
        raise AuthenticationFailed("Server is missing the public key. Run scripts/setup_dev.py.", code="no_key")


class JWTAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            raise AuthenticationFailed("Authorization header must be: Bearer <token>.")
        return Principal(decode_token(parts[1])), parts[1]

    def authenticate_header(self, request):
        return self.keyword
