"""Hospital directory: which hospital runs which node (service addresses).

The Identity service owns the Hospital table. Other services read it through
this helper and keep a short cache. If Identity is briefly down, the last
known list is used, so the rest of the system keeps working.
"""
import time

from django.conf import settings

from . import clients
from .exceptions import ServiceUnavailable

_cache = {"at": 0.0, "data": []}
TTL_SECONDS = 30


def hospitals(force: bool = False) -> list:
    fresh = time.time() - _cache["at"] < TTL_SECONDS
    if _cache["data"] and fresh and not force:
        return _cache["data"]
    try:
        response = clients.call("GET", settings.IDENTITY_URL + "/auth/internal/hospitals/", timeout=2, retries=1)
        if response.status_code == 200:
            _cache["data"], _cache["at"] = response.json(), time.time()
            return _cache["data"]
    except ServiceUnavailable:
        pass
    if _cache["data"]:
        return _cache["data"]  # stale but usable
    raise ServiceUnavailable("The hospital directory is not available.")


def by_code(code: str):
    for hospital in hospitals():
        if hospital["code"] == code:
            return hospital
    return None


def clear_cache():
    _cache["at"], _cache["data"] = 0.0, []
