"""Shared Django settings builder used by every DHIS service.

Each service has a tiny config/settings.py that calls build(). This keeps the
security and database rules identical across services.
"""
import os
import sys
from pathlib import Path


def _load_env_file(root: Path) -> None:
    """Read KEY=VALUE lines from <root>/.env (no extra package needed)."""
    path = root / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _list(name: str, default: str = "") -> list:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def build(service: str, service_dir, apps: list, db_name: str = None, extra: dict = None) -> dict:
    service_dir = Path(service_dir).resolve()
    root = service_dir.parents[1]
    _load_env_file(root)
    env = os.environ.get

    testing = "test" in sys.argv[:2]
    debug = env("DJANGO_DEBUG", "1") == "1"

    cfg = {
        "BASE_DIR": service_dir,
        "PROJECT_ROOT": root,
        "SERVICE_NAME": service,
        "SECRET_KEY": env("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me"),
        "DEBUG": debug,
        "ALLOWED_HOSTS": _list("DJANGO_ALLOWED_HOSTS", "*"),
        "INSTALLED_APPS": [
            "django.contrib.contenttypes",
            "rest_framework",
            "dhis_common",
        ] + apps,
        "MIDDLEWARE": [
            "dhis_common.middleware.RequestIDMiddleware",
            "django.middleware.security.SecurityMiddleware",
            "django.middleware.common.CommonMiddleware",
        ],
        "ROOT_URLCONF": "config.urls",
        "WSGI_APPLICATION": "config.wsgi.application",
        "TEMPLATES": [],
        "LANGUAGE_CODE": "en-gb",
        "TIME_ZONE": "Africa/Kigali",
        "USE_TZ": True,
        "DEFAULT_AUTO_FIELD": "django.db.models.BigAutoField",
        "APPEND_SLASH": False,
        "REST_FRAMEWORK": {
            "DEFAULT_AUTHENTICATION_CLASSES": ["dhis_common.jwt_auth.JWTAuthentication"],
            "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
            "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
            "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
            "UNAUTHENTICATED_USER": None,
            "EXCEPTION_HANDLER": "dhis_common.exceptions.handler",
            "DEFAULT_PAGINATION_CLASS": "dhis_common.pagination.StandardPagination",
            "PAGE_SIZE": 20,
        },
        # Security and wiring shared by all services
        "INTERNAL_API_KEY": env("INTERNAL_API_KEY", "dev-internal-key-change-me"),
        "ID_SALT": env("ID_SALT", "dev-id-salt-change-me"),
        "JWT_ISSUER": "dhis-identity",
        "JWT_LIFETIME_MINUTES": int(env("JWT_LIFETIME_MINUTES", "480")),
        "JWT_PRIVATE_KEY_PATH": env("JWT_PRIVATE_KEY_PATH", str(root / "keys" / "private.pem")),
        "JWT_PUBLIC_KEY_PATH": env("JWT_PUBLIC_KEY_PATH", str(root / "keys" / "public.pem")),
        "IDENTITY_URL": env("IDENTITY_URL", "http://127.0.0.1:8003"),
        "PATIENT_URL": env("PATIENT_URL", "http://127.0.0.1:8000"),
        "RECORDS_URL": env("RECORDS_URL", "http://127.0.0.1:8002"),
        "REFERRAL_URL": env("REFERRAL_URL", "http://127.0.0.1:8001"),
        "DASHBOARD_URL": env("DASHBOARD_URL", "http://127.0.0.1:8004"),
        "AUDIT_URL": env("AUDIT_URL", "http://127.0.0.1:8005"),
        "NODE_CODE": env("NODE_CODE", "KRH"),
        "EVENT_SUBSCRIBERS": _list("EVENT_SUBSCRIBERS"),
        "RABBITMQ_URL": env("RABBITMQ_URL", ""),
        "EVENT_MAX_ATTEMPTS": 5,
        "CIRCUIT_FAILURES": int(env("CIRCUIT_FAILURES", "5")),
        "CIRCUIT_RESET_SECONDS": int(env("CIRCUIT_RESET_SECONDS", "30")),
        "CIRCUIT_SUCCESSES": int(env("CIRCUIT_SUCCESSES", "3")),
        "BACKGROUND_JOBS": env("DHIS_BACKGROUND", "0") == "1" and not testing,
    }

    name = env("DB_NAME") or db_name or service
    if env("DB_ENGINE", "sqlite") == "postgres":
        cfg["DATABASES"] = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": name,
                "USER": env("DB_USER", "dhis"),
                "PASSWORD": env("DB_PASSWORD", "dhis"),
                "HOST": env("DB_HOST", "localhost"),
                "PORT": env("DB_PORT", "5432"),
            }
        }
    else:
        data_dir = Path(env("DB_DIR", str(root / "data")))
        data_dir.mkdir(parents=True, exist_ok=True)
        cfg["DATABASES"] = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": str(data_dir / f"{name}.sqlite3"),
                "OPTIONS": {"timeout": 30},
            }
        }

    if extra:
        cfg.update(extra)
    return cfg
