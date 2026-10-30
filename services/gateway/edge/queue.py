import datetime
import json

import jwt
from django.conf import settings
from django.utils import timezone

from dhis_common import clients
from dhis_common.exceptions import ServiceUnavailable

from .models import QueuedRequest

MAX_AGE = datetime.timedelta(hours=24)


def try_forward(item: QueuedRequest) -> None:
    """One attempt to send a queued request. Updates the row."""
    now = timezone.now()
    if now - item.created_at > MAX_AGE:
        item.status, item.last_error, item.completed_at = QueuedRequest.FAILED, "Waited more than 24 hours.", now
        item.save()
        return
    try:
        response = clients.call("POST", settings.REFERRAL_URL + "/" + item.path, data=item.body.encode(), timeout=4, retries=0, internal=False,
                                headers={"Authorization": "Bearer " + item.token, "Content-Type": "application/json",
                                         "Idempotency-Key": item.idempotency_key})
    except ServiceUnavailable as exc:
        item.attempts += 1
        item.last_error = str(exc)[:250]
        item.save(update_fields=["attempts", "last_error"])
        return
    item.attempts += 1
    item.result_status = response.status_code
    try:
        item.result_body = response.json()
    except ValueError:
        item.result_body = None
    if response.status_code < 300:
        item.status, item.completed_at, item.last_error = QueuedRequest.DONE, now, ""
    else:
        message = (item.result_body or {}).get("error", {}).get("message", f"HTTP {response.status_code}") if isinstance(item.result_body, dict) else f"HTTP {response.status_code}"
        item.status, item.completed_at, item.last_error = QueuedRequest.FAILED, now, str(message)[:250]
    item.save()


def flush_queue() -> int:
    done = 0
    for item in QueuedRequest.objects.filter(status=QueuedRequest.PENDING_SYNC).order_by("created_at")[:20]:
        try_forward(item)
        done += item.status == QueuedRequest.DONE
    return done


def summarise(body: str) -> str:
    try:
        data = json.loads(body)
        return f"{data.get('priority', '')} transfer to {data.get('to_hospital', '')}"[:200]
    except ValueError:
        return "Transfer request"
