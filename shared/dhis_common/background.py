"""Small background loops (outbox sender, expiry job, queue flusher).

They start only when DHIS_BACKGROUND=1 and the process is a real server
(runserver --noreload or gunicorn), never during migrate, tests or shell.
In production you could run the same functions as separate worker processes.
"""
import logging
import os
import sys
import threading
import time

from django.conf import settings
from django.db import close_old_connections

log = logging.getLogger("dhis.background")
_started = set()


def _is_server_process() -> bool:
    argv = sys.argv
    if "gunicorn" in os.path.basename(argv[0]):
        return True
    if "runserver" in argv:
        return "--noreload" in argv or os.environ.get("RUN_MAIN") == "true"
    return False


def start_job(name: str, func, interval: float) -> None:
    if not settings.BACKGROUND_JOBS or not _is_server_process() or name in _started:
        return
    _started.add(name)

    def loop():
        time.sleep(1.0)
        while True:
            try:
                func()
            except Exception:  # noqa: BLE001 - a job must never kill the loop
                log.exception("background job %s failed", name)
            finally:
                close_old_connections()
            time.sleep(interval)

    threading.Thread(target=loop, name=f"dhis-{name}", daemon=True).start()


def start_outbox_dispatcher() -> None:
    from .events import dispatch_once
    start_job("outbox", dispatch_once, 1.0)
