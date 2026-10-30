import uuid

from django.db import models
from django.utils import timezone


class QueuedRequest(models.Model):
    """Outbound queue (the PENDING_SYNC state).

    When a doctor creates a transfer request while the Referral service cannot be
    reached, the gateway keeps the request here and keeps retrying it with the same
    Idempotency-Key, so the transfer is created exactly once when the service returns.
    """

    PENDING_SYNC, DONE, FAILED = "PENDING_SYNC", "DONE", "FAILED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(max_length=80, unique=True)
    hospital = models.CharField(max_length=10, db_index=True)
    user_name = models.CharField(max_length=120)
    path = models.CharField(max_length=200)
    body = models.TextField()
    token = models.TextField()
    status = models.CharField(max_length=12, default=PENDING_SYNC, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=250, blank=True)
    result_status = models.PositiveSmallIntegerField(null=True, blank=True)
    result_body = models.JSONField(null=True, blank=True)
    summary = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
