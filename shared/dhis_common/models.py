import uuid

from django.db import models
from django.utils import timezone


class OutboxEvent(models.Model):
    """Transactional outbox: the event is saved in the same database
    transaction as the business change, then sent later by the dispatcher.
    This is what stops an event being lost if a service crashes after saving."""

    PENDING, SENT, DEAD = "PENDING", "SENT", "DEAD"

    message_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    event_type = models.CharField(max_length=60, db_index=True)
    aggregate_id = models.CharField(max_length=64, blank=True)
    version = models.PositiveIntegerField(default=0)
    payload = models.JSONField(default=dict)
    occurred_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=8, default=PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    last_error = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["id"]


class ProcessedEvent(models.Model):
    """Message ids a consumer has already handled. A second delivery of the
    same message is ignored, which makes at-least-once delivery safe."""

    message_id = models.UUIDField(unique=True)
    event_type = models.CharField(max_length=60)
    processed_at = models.DateTimeField(default=timezone.now)


class IdempotencyRecord(models.Model):
    """Remembers the answer to a write request so a retry returns the same
    answer instead of creating a second record."""

    key = models.CharField(max_length=80)
    scope = models.CharField(max_length=200)
    status_code = models.PositiveSmallIntegerField(default=0)  # 0 = still running
    body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["key", "scope"], name="uniq_idem_key_scope")]
