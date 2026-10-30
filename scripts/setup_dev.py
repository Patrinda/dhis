"""One-time local setup: signing keys, data folder, database tables.

Run from the project root:   python scripts/setup_dev.py
Safe to run again: existing keys are kept.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "shared"))

# (service folder, database name or None for default, extra environment)
DATABASES = [
    ("identity", None, {}),
    ("patient", "db_pat_a", {"NODE_CODE": "KRH"}),
    ("patient", "db_pat_b", {"NODE_CODE": "BDH"}),
    ("records", "db_rec_a", {"NODE_CODE": "KRH"}),
    ("records", "db_rec_b", {"NODE_CODE": "BDH"}),
    ("referral", None, {}),
    ("dashboard", None, {}),
    ("audit", None, {}),
    ("gateway", None, {}),
]


def make_keys():
    keys = ROOT / "keys"
    keys.mkdir(exist_ok=True)
    private, public = keys / "private.pem", keys / "public.pem"
    if private.exists() and public.exists():
        print("keys: already exist, kept")
        return
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    public.write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    private.chmod(0o600)
    print("keys: created keys/private.pem and keys/public.pem")


def migrate_all():
    import os

    for service, db_name, extra in DATABASES:
        env = dict(os.environ, **extra)
        if db_name:
            env["DB_NAME"] = db_name
        manage = ROOT / "services" / service / "manage.py"
        label = db_name or service
        if not manage.exists():
            print(f"migrate {label}: skipped (the {service} folder has not been added yet)")
            continue
        result = subprocess.run([sys.executable, str(manage), "migrate", "--noinput", "-v", "0"],
                                env=env, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"migrate {label}: FAILED\n{result.stderr}")
            sys.exit(1)
        print(f"migrate {label}: ok")


if __name__ == "__main__":
    if "--keys-only" in sys.argv:  # used by the Docker "keys" container
        make_keys()
        sys.exit(0)
    (ROOT / "data").mkdir(exist_ok=True)
    make_keys()
    migrate_all()
    print("\nSetup finished. Next: python services/identity/manage.py seed_demo")
