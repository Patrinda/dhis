"""Start the whole system on your computer with one command.

    python run_all.py            start everything (stop with Ctrl+C)
    python run_all.py --reset    delete local databases first, then start

Needs no Docker and no RabbitMQ: events travel over HTTP between services.
Open http://127.0.0.1:8080 when the banner says the system is ready.
"""
import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable

AUDIT, DASH = "http://127.0.0.1:8005", "http://127.0.0.1:8004"
URLS = {
    "IDENTITY_URL": "http://127.0.0.1:8003", "REFERRAL_URL": "http://127.0.0.1:8001",
    "DASHBOARD_URL": DASH, "AUDIT_URL": AUDIT,
}
SUBSCRIBERS = f"{AUDIT},{DASH}"

# name, service folder, port, extra environment
SERVICES = [
    ("identity", "identity", 8003, {"EVENT_SUBSCRIBERS": AUDIT}),
    ("audit", "audit", 8005, {}),
    ("dashboard", "dashboard", 8004, {}),
    ("patient-KRH", "patient", 8000, {"NODE_CODE": "KRH", "DB_NAME": "db_pat_a", "EVENT_SUBSCRIBERS": SUBSCRIBERS, "PATIENT_URL": "http://127.0.0.1:8000"}),
    ("patient-BDH", "patient", 9000, {"NODE_CODE": "BDH", "DB_NAME": "db_pat_b", "EVENT_SUBSCRIBERS": SUBSCRIBERS, "PATIENT_URL": "http://127.0.0.1:9000"}),
    ("records-KRH", "records", 8002, {"NODE_CODE": "KRH", "DB_NAME": "db_rec_a", "EVENT_SUBSCRIBERS": SUBSCRIBERS, "PATIENT_URL": "http://127.0.0.1:8000"}),
    ("records-BDH", "records", 9002, {"NODE_CODE": "BDH", "DB_NAME": "db_rec_b", "EVENT_SUBSCRIBERS": SUBSCRIBERS, "PATIENT_URL": "http://127.0.0.1:9000"}),
    ("referral", "referral", 8001, {"EVENT_SUBSCRIBERS": SUBSCRIBERS}),
    ("gateway", "gateway", 8080, {}),
]

procs = {}


def start(name, folder, port, extra):
    env = dict(os.environ, DHIS_BACKGROUND="1", **URLS, **extra)
    log = open(ROOT / "data" / f"{name}.log", "w")
    procs[name] = subprocess.Popen(
        [PY, str(ROOT / "services" / folder / "manage.py"), "runserver", f"127.0.0.1:{port}", "--noreload"],
        env=env, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT / "services" / folder)
    return port


def wait_ready(port, timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1)
            return True
        except Exception:
            time.sleep(0.4)
    return False


def stop_all(*_):
    for proc in procs.values():
        if proc.poll() is None:
            proc.terminate()
    for proc in procs.values():
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    print("\nAll services stopped.")
    sys.exit(0)


def has_users():
    """True when the local identity database already contains at least one user."""
    import sqlite3
    path = ROOT / "data" / "db_auth.sqlite3"
    if not path.exists():
        return False
    try:
        with sqlite3.connect(path) as db:
            return db.execute("SELECT COUNT(*) FROM accounts_user").fetchone()[0] > 0
    except sqlite3.Error:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="delete local databases and rebuild them with demo users")
    parser.add_argument("--skip", default="", help="comma list of services NOT to start, for example referral")
    parser.add_argument("--only", default="", help="comma list: start only these services (for failure demonstrations)")
    args = parser.parse_args()
    skip = {x.strip() for x in args.skip.split(",") if x.strip()}
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    selected = [item for item in SERVICES if item[0] not in skip and (not only or item[0] in only)]
    missing = sorted({item[1] for item in selected if not (ROOT / "services" / item[1] / "manage.py").exists()})
    if missing:
        print("Not started because the folder is not in the project yet:", ", ".join(missing))
        selected = [item for item in selected if item[1] not in missing]
    (ROOT / "data").mkdir(exist_ok=True)
    if args.reset:
        for item in (ROOT / "data").glob("*"):
            item.unlink()
    if not (ROOT / "keys" / "private.pem").exists() or args.reset or not list((ROOT / "data").glob("*.sqlite3")):
        subprocess.run([PY, str(ROOT / "scripts" / "setup_dev.py")], check=True)
    if (ROOT / "services" / "identity" / "manage.py").exists() and not has_users():
        # also covers the case where setup_dev.py was run on its own and created empty databases
        subprocess.run([PY, str(ROOT / "services" / "identity" / "manage.py"), "seed_demo"], check=True)

    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)
    for name, folder, port, extra in selected:
        start(name, folder, port, extra)
    failed = [name for name, _, port, _ in selected if not wait_ready(port)]
    if failed:
        print("These services did not start:", ", ".join(failed), "\nSee the files in the data/ folder (name.log).")
        stop_all()
    print("\n" + "=" * 60)
    print(" DHIS is ready.  Open  http://127.0.0.1:8080")
    print(" Sign in with a demo user, for example doctor_krh")
    print(" Demo password: Dhis@Demo2025")
    print(" Stop with Ctrl+C. Service logs are in the data/ folder.")
    print("=" * 60)
    warned = set()
    while True:
        time.sleep(1)
        for name, proc in procs.items():
            if proc.poll() is not None and name not in warned:
                warned.add(name)  # keep the others running: a stopped service is a useful failure demo
                print(f"WARNING: {name} stopped. See data/{name}.log")


if __name__ == "__main__":
    main()
