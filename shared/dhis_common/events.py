"""Events: publish with an outbox, deliver at least once, consume idempotently.

Two transports carry the same message:
  * RabbitMQ topic exchange 'dhis.events' when RABBITMQ_URL is set.
  * HTTP webhook (POST <subscriber>/internal/events/) otherwise. This is the
    default for local development so no broker has to be installed.
"""
import json
import threading
from datetime import timedelta

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import OutboxEvent, ProcessedEvent

EXCHANGE = "dhis.events"


def publish(event_type: str, payload: dict, *, aggregate_id: str = "", version: int = 0) -> OutboxEvent:
    """Save an event. Call inside the same transaction.atomic() block as the
    business change so both are saved together or not at all."""
    return OutboxEvent.objects.create(
        event_type=event_type, payload=payload, aggregate_id=str(aggregate_id), version=version,
    )


def envelope(event: OutboxEvent) -> dict:
    return {
        "message_id": str(event.message_id),
        "type": event.event_type,
        "version": event.version,
        "aggregate_id": event.aggregate_id,
        "occurred_at": event.occurred_at.isoformat(),
        "source": settings.SERVICE_NAME,
        "payload": event.payload,
    }


# ---------------------------------------------------------------- sending
def _send_rabbit(env: dict) -> None:
    import pika

    connection = pika.BlockingConnection(pika.URLParameters(settings.RABBITMQ_URL))
    try:
        channel = connection.channel()
        channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
        channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=env["type"],
            body=json.dumps(env).encode(),
            properties=pika.BasicProperties(
                delivery_mode=2, content_type="application/json", message_id=env["message_id"],
            ),
        )
    finally:
        connection.close()


def _send_http(env: dict) -> None:
    errors = []
    for base in settings.EVENT_SUBSCRIBERS:
        try:
            response = requests.post(
                base.rstrip("/") + "/internal/events/", json=env, timeout=3,
                headers={"X-Internal-Key": settings.INTERNAL_API_KEY},
            )
            if response.status_code >= 300:
                errors.append(f"{base}: HTTP {response.status_code}")
        except requests.RequestException as exc:
            errors.append(f"{base}: {type(exc).__name__}")
    if errors:
        raise RuntimeError("; ".join(errors))


def _send(env: dict) -> None:
    if settings.RABBITMQ_URL:
        _send_rabbit(env)
    else:
        _send_http(env)


def dispatch_once(limit: int = 50) -> int:
    """Send due events. Failed events wait longer each time (2, 4, 8, 16 s).
    After EVENT_MAX_ATTEMPTS failures an event is marked DEAD for a person to inspect."""
    now = timezone.now()
    due = list(OutboxEvent.objects.filter(status=OutboxEvent.PENDING, next_attempt_at__lte=now).order_by("id")[:limit])
    sent = 0
    for event in due:
        try:
            _send(envelope(event))
        except Exception as exc:  # noqa: BLE001 - any transport error means "retry later"
            event.attempts += 1
            event.last_error = str(exc)[:250]
            if event.attempts >= settings.EVENT_MAX_ATTEMPTS:
                event.status = OutboxEvent.DEAD
            else:
                event.next_attempt_at = now + timedelta(seconds=min(300, 2 ** event.attempts))
            event.save(update_fields=["attempts", "last_error", "status", "next_attempt_at"])
        else:
            event.status = OutboxEvent.SENT
            event.save(update_fields=["status"])
            sent += 1
    return sent


# -------------------------------------------------------------- receiving
_serial_lock = threading.Lock()


def process_once(env: dict, handler) -> bool:
    """Run handler(env) unless this message id was already handled.
    Returns True if processed, False if it was a duplicate.

    A handler marked `handler.serialize = True` (the audit log, which builds a hash
    chain) is run one at a time. The lock is held until the transaction commits;
    otherwise a second thread could read the chain before the first line is saved."""
    guard = _serial_lock if getattr(handler, "serialize", False) else None
    if guard:
        guard.acquire()
    try:
        for _ in range(2):
            try:
                with transaction.atomic():
                    _, created = ProcessedEvent.objects.get_or_create(
                        message_id=env["message_id"], defaults={"event_type": env["type"]},
                    )
                    if not created:
                        return False
                    handler(env)
                    return True
            except IntegrityError:
                continue  # two copies arrived at the same moment; the retry sees the winner
        return False
    finally:
        if guard:
            guard.release()
