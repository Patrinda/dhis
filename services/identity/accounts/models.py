from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from dhis_common.jwt_auth import ROLES


class Hospital(models.Model):
    """A hospital node. patient_url and records_url say where its services run;
    the gateway reads these to route each user to the right node."""

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120)
    district = models.CharField(max_length=60)
    patient_url = models.URLField(blank=True)
    records_url = models.URLField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class User(AbstractUser):
    ROLE_CHOICES = [(r, r.replace("_", " ").title()) for r in ROLES]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    hospital = models.ForeignKey(Hospital, null=True, blank=True, on_delete=models.PROTECT, related_name="users")
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())


class IdentifierClaim(models.Model):
    """Mutual exclusion for national IDs.

    Before a hospital registers a new patient it must claim the ID here. Only
    one hospital can hold a claim, so two hospitals cannot both register the
    same person at the same moment. A claim is a lease: if the hospital never
    confirms it (for example it crashed), it expires after two minutes.
    The ID is stored as a salted hash, never in clear.
    """

    CLAIMED, CONFIRMED = "CLAIMED", "CONFIRMED"

    id_hash = models.CharField(max_length=64, unique=True)
    hospital_code = models.CharField(max_length=10)
    status = models.CharField(max_length=10, default=CLAIMED)
    lease_expires_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)
