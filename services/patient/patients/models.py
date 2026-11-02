import uuid

from django.db import models
from django.utils import timezone


class Patient(models.Model):
    """One person registered at this hospital node. Each hospital owns the
    patients it registered (partitioning by hospital)."""

    SEX_CHOICES = [("F", "Female"), ("M", "Male")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    national_id = models.CharField(max_length=16, unique=True)
    first_name = models.CharField(max_length=60)
    last_name = models.CharField(max_length=60)
    sex = models.CharField(max_length=1, choices=SEX_CHOICES)
    date_of_birth = models.DateField()
    phone = models.CharField(max_length=20, blank=True)
    district = models.CharField(max_length=60, blank=True)
    next_of_kin_name = models.CharField(max_length=120, blank=True)
    next_of_kin_phone = models.CharField(max_length=20, blank=True)
    hospital_code = models.CharField(max_length=10)
    version = models.PositiveIntegerField(default=1)  # optimistic locking
    created_by = models.CharField(max_length=40)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["last_name", "first_name"])]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
