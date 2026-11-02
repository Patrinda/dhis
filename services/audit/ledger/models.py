import hashlib
import json
import uuid

from django.db import models
from django.utils import timezone


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("The audit log is append-only.")

    def delete(self):
        raise PermissionError("The audit log is append-only.")


class AuditEntry(models.Model):
    """One line of the audit log. Each line stores a hash of its own content plus
    the hash of the line before it, so any later change breaks the chain and is
    found by /audit/verify/. Lines can be added but never edited or deleted."""

    seq = models.BigAutoField(primary_key=True)
    message_id = models.UUIDField(unique=True, null=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    event_type = models.CharField(max_length=60, db_index=True)
    actor_id = models.CharField(max_length=40, blank=True)
    actor_name = models.CharField(max_length=120, blank=True)
    role = models.CharField(max_length=20, blank=True)
    hospital = models.CharField(max_length=10, blank=True, db_index=True)
    action = models.CharField(max_length=60, db_index=True)
    target_ref = models.CharField(max_length=80, blank=True)
    detail = models.JSONField(default=dict)
    flagged = models.BooleanField(default=False, db_index=True)  # break-glass
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["seq"]

    def compute_hash(self) -> str:
        body = json.dumps([str(self.message_id), self.occurred_at.isoformat(), self.event_type, self.actor_id, self.actor_name,
                           self.role, self.hospital, self.action, self.target_ref, self.detail, self.flagged, self.prev_hash],
                          sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(body.encode()).hexdigest()

    def save(self, *args, **kwargs):
        if self.pk is not None and AuditEntry.objects.filter(pk=self.pk).exists():
            raise PermissionError("The audit log is append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("The audit log is append-only.")


class BreakGlassReview(models.Model):
    """The DPO's review of a flagged entry. Kept apart so the log itself never changes."""

    entry = models.OneToOneField(AuditEntry, on_delete=models.PROTECT, related_name="review")
    reviewed_by = models.CharField(max_length=120)
    outcome = models.CharField(max_length=12, choices=[("JUSTIFIED", "Justified"), ("QUERY", "Query raised")])
    comment = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(default=timezone.now)


class Consent(models.Model):
    """Patient consent to share a limited summary for transfers. Keyed by the hashed ID."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_hash = models.CharField(max_length=64, db_index=True)
    hospital = models.CharField(max_length=10, db_index=True)
    status = models.CharField(max_length=10, default="GRANTED", choices=[("GRANTED", "Granted"), ("WITHDRAWN", "Withdrawn")])
    recorded_by = models.CharField(max_length=120)
    granted_at = models.DateTimeField(default=timezone.now)
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-granted_at"]
