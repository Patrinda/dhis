from django.db import models
from django.utils import timezone


class EventRecord(models.Model):
    """Every event received is kept, so all numbers can be rebuilt from scratch."""

    message_id = models.UUIDField(unique=True)
    event_type = models.CharField(max_length=60, db_index=True)
    version = models.PositiveIntegerField(default=0)
    occurred_at = models.DateTimeField()
    payload = models.JSONField()


class TransferProjection(models.Model):
    transfer_id = models.UUIDField(primary_key=True)
    from_hospital = models.CharField(max_length=10, db_index=True)
    to_hospital = models.CharField(max_length=10, db_index=True)
    priority = models.CharField(max_length=10)
    status = models.CharField(max_length=14, db_index=True)
    version = models.PositiveIntegerField()
    requested_at = models.DateTimeField()
    decided_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class DailyCount(models.Model):
    """One row per day, hospital and measure, for example (2025-06-01, KRH, patients, 12)."""

    date = models.DateField()
    hospital = models.CharField(max_length=10)
    measure = models.CharField(max_length=30)
    value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["date", "hospital", "measure"], name="uniq_daily")]


class ConditionCount(models.Model):
    hospital = models.CharField(max_length=10)
    code = models.CharField(max_length=10)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["hospital", "code"], name="uniq_condition")]
