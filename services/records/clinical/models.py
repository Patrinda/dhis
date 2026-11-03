import uuid

from django.db import models
from django.utils import timezone


class Encounter(models.Model):
    """One visit: triage by a nurse, diagnosis and plan by a doctor."""

    TYPES = [("OUTPATIENT", "Outpatient"), ("EMERGENCY", "Emergency"), ("INPATIENT", "Inpatient")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient_id = models.UUIDField(db_index=True)
    national_id = models.CharField(max_length=16, db_index=True)
    patient_name = models.CharField(max_length=130, blank=True)
    hospital_code = models.CharField(max_length=10)
    encounter_type = models.CharField(max_length=12, choices=TYPES, default="OUTPATIENT")
    complaint = models.TextField(blank=True)
    temperature_c = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    pulse = models.PositiveSmallIntegerField(null=True, blank=True)
    systolic = models.PositiveSmallIntegerField(null=True, blank=True)
    diastolic = models.PositiveSmallIntegerField(null=True, blank=True)
    spo2 = models.PositiveSmallIntegerField(null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    diagnosis_code = models.CharField(max_length=10, blank=True)
    diagnosis_text = models.CharField(max_length=200, blank=True)
    plan = models.TextField(blank=True)
    author_id = models.CharField(max_length=40)
    author_name = models.CharField(max_length=120)
    author_role = models.CharField(max_length=20)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]


class Allergy(models.Model):
    patient_id = models.UUIDField(db_index=True)
    national_id = models.CharField(max_length=16, db_index=True)
    substance = models.CharField(max_length=80)
    reaction = models.CharField(max_length=120, blank=True)
    severity = models.CharField(max_length=10, choices=[("MILD", "Mild"), ("MODERATE", "Moderate"), ("SEVERE", "Severe")], default="MODERATE")
    recorded_by = models.CharField(max_length=120)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]


class Prescription(models.Model):
    PRESCRIBED, DISPENSED, CANCELLED = "PRESCRIBED", "DISPENSED", "CANCELLED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="prescriptions")
    patient_id = models.UUIDField(db_index=True)
    national_id = models.CharField(max_length=16, db_index=True)
    drug_name = models.CharField(max_length=100)
    dose = models.CharField(max_length=60)
    frequency = models.CharField(max_length=60)
    duration_days = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, default=PRESCRIBED, db_index=True)
    prescribed_by = models.CharField(max_length=120)
    dispensed_by = models.CharField(max_length=120, blank=True)
    dispensed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]


class LabOrder(models.Model):
    ORDERED, COMPLETED = "ORDERED", "COMPLETED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="lab_orders")
    patient_id = models.UUIDField(db_index=True)
    national_id = models.CharField(max_length=16, db_index=True)
    test_name = models.CharField(max_length=100)
    status = models.CharField(max_length=10, default=ORDERED, db_index=True)
    ordered_by = models.CharField(max_length=120)
    result_value = models.CharField(max_length=60, blank=True)
    result_unit = models.CharField(max_length=20, blank=True)
    result_flag = models.CharField(max_length=10, blank=True, choices=[("NORMAL", "Normal"), ("HIGH", "High"), ("LOW", "Low"), ("CRITICAL", "Critical")])
    entered_by = models.CharField(max_length=120, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
