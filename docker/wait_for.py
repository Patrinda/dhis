"""Wait until the database accepts connections (used by the container entrypoint)."""
import os
import socket
import sys
import time

host, port = os.environ.get("DB_HOST", "postgres"), int(os.environ.get("DB_PORT", "5432"))
for _ in range(60):
    try:
        socket.create_connection((host, port), timeout=2).close()
        sys.exit(0)
    except OSError:
        time.sleep(1)
print(f"Database {host}:{port} did not become ready", file=sys.stderr)
sys.exit(1)
