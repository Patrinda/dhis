import uuid

from django.db import models
from django.utils import timezone

ACTIVE_STATUSES = ["PENDING", "ACCEPTED", "IN_TRANSIT"]


class Transfer(models.Model):
    """One patient transfer between two hospitals. This service is the only
    writer of transfer status, so there is one source of truth."""

    STATUS_CHOICES = [(s, s) for s in ("PENDING_SYNC", "PENDING", "ACCEPTED", "REJECTED", "CANCELLED",
                                       "EXPIRED", "IN_TRANSIT", "COMPLETED")]
    PRIORITY_CHOICES = [("EMERGENCY", "Emergency"), ("URGENT", "Urgent"), ("ROUTINE", "Routine")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    national_id = models.CharField(max_length=16, db_index=True)
    patient_name = models.CharField(max_length=130)
    from_hospital = models.CharField(max_length=10, db_index=True)
    to_hospital = models.CharField(max_length=10, db_index=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="ROUTINE")
    reason = models.TextField()
    status = models.CharField(max_length=14, choices=STATUS_CHOICES, default="PENDING", db_index=True)
    version = models.PositiveIntegerField(default=1)  # logical clock: rises with every status change
    requested_by = models.CharField(max_length=120)
    requested_by_id = models.CharField(max_length=40)
    decision_reason = models.TextField(blank=True)
    clinical_summary = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    decided_at = models.DateTimeField(null=True, blank=True)
    in_transit_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["national_id", "status"])]


class TransferHistory(models.Model):
    transfer = models.ForeignKey(Transfer, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(max_length=14, blank=True)
    to_status = models.CharField(max_length=14)
    actor_name = models.CharField(max_length=120)
    actor_role = models.CharField(max_length=20)
    actor_hospital = models.CharField(max_length=10, blank=True)
    note = models.TextField(blank=True)
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["id"]
