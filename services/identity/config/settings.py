from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parents[1] / "shared"))

from dhis_common.settings_base import build  # noqa: E402

globals().update(build(
    service="identity",
    service_dir=HERE,
    apps=["django.contrib.auth", "accounts"],
    db_name="db_auth",
    extra={
        "AUTH_USER_MODEL": "accounts.User",
        "AUTH_PASSWORD_VALIDATORS": [
            {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
            {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
        ],
        "PASSWORD_HASHERS": ["django.contrib.auth.hashers.PBKDF2PasswordHasher"],
    },
))
