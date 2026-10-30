"""Calling other services safely.

Every call has a time-out. Repeated failures open a circuit breaker so we stop
hammering a service that is down:
  CLOSED    normal. After N failures in a row the circuit opens.
  OPEN      calls fail at once. After a pause, one probe call is allowed.
  HALF_OPEN probe calls are allowed. After a few successes the circuit closes.
"""
import threading
import time
from urllib.parse import urlparse

import requests
from django.conf import settings

from .exceptions import ServiceUnavailable
from .middleware import current_request_id


class CircuitBreaker:
    CLOSED, OPEN, HALF_OPEN = "CLOSED", "OPEN", "HALF_OPEN"

    def __init__(self, name):
        self.name = name
        self.state = self.CLOSED
        self.failures = 0
        self.successes = 0
        self.opened_at = 0.0
        self.lock = threading.Lock()

    def allow(self) -> bool:
        with self.lock:
            if self.state == self.OPEN:
                if time.time() - self.opened_at >= settings.CIRCUIT_RESET_SECONDS:
                    self.state, self.successes = self.HALF_OPEN, 0
                    return True
                return False
            return True

    def record_success(self):
        with self.lock:
            if self.state == self.HALF_OPEN:
                self.successes += 1
                if self.successes >= settings.CIRCUIT_SUCCESSES:
                    self.state, self.failures = self.CLOSED, 0
            else:
                self.failures = 0

    def record_failure(self):
        with self.lock:
            if self.state == self.HALF_OPEN:
                self.state, self.opened_at = self.OPEN, time.time()
                return
            self.failures += 1
            if self.failures >= settings.CIRCUIT_FAILURES:
                self.state, self.opened_at = self.OPEN, time.time()


_breakers = {}
_registry_lock = threading.Lock()


def breaker_for(host: str) -> CircuitBreaker:
    with _registry_lock:
        return _breakers.setdefault(host, CircuitBreaker(host))


def reset_breakers():
    with _registry_lock:
        _breakers.clear()


def call(method, url, *, json=None, data=None, params=None, headers=None, timeout=3.0, retries=1, internal=True):
    """Send one HTTP request to another service.

    Returns the requests.Response (the caller checks the status code).
    Raises ServiceUnavailable if the service cannot be reached.
    Retries use a growing pause (0.2 s, 0.4 s, ...). Only retry calls that are
    safe to repeat: reads, or writes that carry an Idempotency-Key.
    """
    host = urlparse(url).netloc
    breaker = breaker_for(host)
    if not breaker.allow():
        raise ServiceUnavailable(f"{host} is unavailable (circuit open).")

    merged = {"X-Request-ID": current_request_id()}
    if internal:  # the gateway passes internal=False so user traffic never carries the service secret
        merged["X-Internal-Key"] = settings.INTERNAL_API_KEY
    merged.update(headers or {})

    last_error = None
    for attempt in range(retries + 1):
        try:
            response = requests.request(method, url, json=json, data=data, params=params, headers=merged, timeout=timeout)
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
            breaker.record_failure()
            if attempt < retries and breaker.allow():
                time.sleep(0.2 * (2 ** attempt))
                continue
            break
        if response.status_code in (502, 503, 504):
            breaker.record_failure()
            last_error = f"HTTP {response.status_code}"
            if attempt < retries and breaker.allow():
                time.sleep(0.2 * (2 ** attempt))
                continue
            break
        breaker.record_success()
        return response
    raise ServiceUnavailable(f"{host} did not answer ({type(last_error).__name__ if last_error else 'error'}).")
