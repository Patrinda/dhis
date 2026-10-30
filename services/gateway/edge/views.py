import collections
import json
import time
import uuid

import requests
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.exceptions import AuthenticationFailed

from dhis_common import clients, directory
from dhis_common.exceptions import ServiceUnavailable
from dhis_common.jwt_auth import decode_token

from .models import QueuedRequest
from .queue import summarise, try_forward

SERVICES = {"auth": "IDENTITY_URL", "transfers": "REFERRAL_URL", "dashboard": "DASHBOARD_URL", "audit": "AUDIT_URL", "consents": "AUDIT_URL"}
NODE_SERVICES = {"patients": "patient_url", "records": "records_url"}
PUBLIC_PATHS = {"auth/login/"}
_logins = collections.defaultdict(collections.deque)


def error(status, code, message, **extra):
    return JsonResponse({"error": {"code": code, "message": message, **extra}}, status=status)


def _client_ip(request):
    return request.META.get("REMOTE_ADDR", "?")


def _rate_limited(request) -> bool:
    """At most 10 FAILED sign-ins per minute from one address."""
    window = _logins[_client_ip(request)]
    now = time.time()
    while window and now - window[0] > 60:
        window.popleft()
    return len(window) >= 10


def _record_failed_login(request) -> None:
    _logins[_client_ip(request)].append(time.time())


def _base_url(path: str, claims):
    segment = path.split("/", 1)[0]
    if segment in SERVICES:
        return getattr(settings, SERVICES[segment])
    if segment in NODE_SERVICES:
        code = (claims or {}).get("hospital") or ""
        hospitals = directory.hospitals()
        hospital = next((h for h in hospitals if h["code"] == code), None) or (hospitals[0] if hospitals else None)
        if not hospital or not hospital.get(NODE_SERVICES[segment]):
            raise ServiceUnavailable("Your hospital node is not registered.")
        return hospital[NODE_SERVICES[segment]]
    return None


@csrf_exempt
def proxy(request, path):
    path = path.lstrip("/")
    if "internal" in path.split("/"):
        return error(404, "unknown_route", "There is no such API route.")  # internal routes are never public
    claims = None
    if path not in PUBLIC_PATHS:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return error(401, "not_authenticated", "Sign in to continue.")
        try:
            claims = decode_token(header.split(" ", 1)[1])
        except AuthenticationFailed as exc:
            return error(401, str(exc.detail.code), str(exc.detail))
    elif _rate_limited(request):
        return error(429, "too_many_attempts", "Too many sign-in attempts. Wait a minute and try again.")

    try:
        base = _base_url(path, claims)
    except ServiceUnavailable as exc:
        return error(503, "service_unavailable", str(exc.detail))
    if base is None:
        return error(404, "unknown_route", "There is no such API route.")

    method = request.method
    body = request.body if method in ("POST", "PUT", "PATCH", "DELETE") else None
    headers = {"Content-Type": request.headers.get("Content-Type", "application/json"),
               "X-Request-ID": request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]}
    if request.headers.get("Authorization"):
        headers["Authorization"] = request.headers["Authorization"]
    key = request.headers.get("Idempotency-Key", "")
    is_transfer_create = method == "POST" and path.rstrip("/") == "transfers"
    if is_transfer_create and not key:
        key = uuid.uuid4().hex  # the gateway guarantees every transfer request is safe to retry
    if key:
        headers["Idempotency-Key"] = key

    safe_to_retry = method in ("GET", "HEAD") or bool(key)
    url = base.rstrip("/") + "/" + path
    if request.META.get("QUERY_STRING"):
        url += "?" + request.META["QUERY_STRING"]
    try:
        upstream = clients.call(method, url, data=body, headers=headers, timeout=8, retries=1 if safe_to_retry else 0, internal=False)
    except ServiceUnavailable as exc:
        if is_transfer_create and claims:
            return _queue_transfer(request, claims, path, key)
        return error(503, "service_unavailable", str(exc.detail))

    if path in PUBLIC_PATHS and upstream.status_code == 401:
        _record_failed_login(request)
    response = HttpResponse(upstream.content, status=upstream.status_code, content_type=upstream.headers.get("Content-Type", "application/json"))
    for name in ("X-Request-ID", "Idempotent-Replay"):
        if name in upstream.headers:
            response[name] = upstream.headers[name]
    return response


def _queue_transfer(request, claims, path, key):
    """The Referral service is unreachable: keep the request and answer 202 PENDING_SYNC."""
    token = request.headers["Authorization"].split(" ", 1)[1]
    item, created = QueuedRequest.objects.get_or_create(
        idempotency_key=key,
        defaults=dict(hospital=claims.get("hospital", ""), user_name=claims.get("name", ""), path=path,
                      body=request.body.decode(), token=token, summary=summarise(request.body.decode())))
    return JsonResponse({"status": "PENDING_SYNC", "queue_id": str(item.id), "idempotency_key": key,
                         "message": "The transfer service is not reachable. Your request is saved and will be sent automatically."}, status=202)


def queue_list(request):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return error(401, "not_authenticated", "Sign in to continue.")
    try:
        claims = decode_token(header.split(" ", 1)[1])
    except AuthenticationFailed as exc:
        return error(401, str(exc.detail.code), str(exc.detail))
    items = QueuedRequest.objects.all() if claims["role"] == "SYSTEM_ADMIN" else QueuedRequest.objects.filter(hospital=claims.get("hospital", ""))
    rows = [{"id": str(i.id), "status": i.status, "summary": i.summary, "attempts": i.attempts, "last_error": i.last_error,
             "created_at": i.created_at.isoformat(), "transfer_id": (i.result_body or {}).get("id") if i.status == "DONE" and isinstance(i.result_body, dict) else None}
            for i in items.order_by("-created_at")[:30]]
    return JsonResponse({"results": rows, "pending": sum(r["status"] == "PENDING_SYNC" for r in rows)})


@csrf_exempt
def queue_flush(request):
    """Try the waiting requests now instead of waiting for the next automatic retry."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return error(401, "not_authenticated", "Sign in to continue.")
    try:
        decode_token(header.split(" ", 1)[1])
    except AuthenticationFailed as exc:
        return error(401, str(exc.detail.code), str(exc.detail))
    from .queue import flush_queue
    return JsonResponse({"completed": flush_queue()})


def health(request):
    """Status of every service, for the admin page and for checks."""
    checks = [("identity", settings.IDENTITY_URL), ("referral", settings.REFERRAL_URL),
              ("dashboard", settings.DASHBOARD_URL), ("audit", settings.AUDIT_URL)]
    try:
        for hospital in directory.hospitals():
            if hospital.get("patient_url"):
                checks.append((f"patient-{hospital['code']}", hospital["patient_url"]))
            if hospital.get("records_url"):
                checks.append((f"records-{hospital['code']}", hospital["records_url"]))
    except ServiceUnavailable:
        pass
    out = {}
    for name, url in checks:
        started = time.time()
        try:
            r = requests.get(url + "/readyz", timeout=1.5)
            out[name] = {"up": r.status_code == 200, "ms": round((time.time() - started) * 1000)}
        except requests.RequestException:
            out[name] = {"up": False, "ms": None}
    breakers = {k: v.state for k, v in clients._breakers.items()}
    return JsonResponse({"gateway": "ok", "services": out, "circuits": breakers})
