from rest_framework import serializers

from dhis_common.utils import validate_icd10

from .models import Allergy, Encounter, LabOrder, Prescription


class PrescriptionSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="encounter.patient_name", read_only=True)

    class Meta:
        model = Prescription
        fields = ["id", "encounter", "patient_id", "patient_name", "drug_name", "dose", "frequency", "duration_days", "status",
                  "prescribed_by", "dispensed_by", "dispensed_at", "created_at"]
        read_only_fields = ["id", "patient_id", "status", "prescribed_by", "dispensed_by", "dispensed_at", "created_at"]

    def validate_duration_days(self, value):
        if not 1 <= value <= 365:
            raise serializers.ValidationError("Duration must be between 1 and 365 days.")
        return value


class LabOrderSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source="encounter.patient_name", read_only=True)

    class Meta:
        model = LabOrder
        fields = ["id", "encounter", "patient_id", "patient_name", "test_name", "status", "ordered_by", "result_value",
                  "result_unit", "result_flag", "entered_by", "completed_at", "created_at"]
        read_only_fields = ["id", "patient_id", "status", "ordered_by", "result_value", "result_unit",
                            "result_flag", "entered_by", "completed_at", "created_at"]


class LabResultSerializer(serializers.Serializer):
    result_value = serializers.CharField(max_length=60)
    result_unit = serializers.CharField(max_length=20, allow_blank=True, required=False, default="")
    result_flag = serializers.ChoiceField(choices=["NORMAL", "HIGH", "LOW", "CRITICAL"])


class AllergySerializer(serializers.ModelSerializer):
    class Meta:
        model = Allergy
        fields = ["id", "patient_id", "substance", "reaction", "severity", "recorded_by", "created_at"]
        read_only_fields = ["id", "recorded_by", "created_at"]


class EncounterSerializer(serializers.ModelSerializer):
    prescriptions = PrescriptionSerializer(many=True, read_only=True)
    lab_orders = LabOrderSerializer(many=True, read_only=True)

    class Meta:
        model = Encounter
        fields = ["id", "patient_id", "hospital_code", "encounter_type", "complaint", "temperature_c", "pulse",
                  "systolic", "diastolic", "spo2", "weight_kg", "diagnosis_code", "diagnosis_text", "plan",
                  "author_name", "author_role", "version", "created_at", "prescriptions", "lab_orders"]
        read_only_fields = ["id", "hospital_code", "author_name", "author_role", "version", "created_at"]

    def validate_diagnosis_code(self, value):
        return validate_icd10(value)

    def validate(self, attrs):
        ranges = {"temperature_c": (30, 45), "pulse": (20, 250), "systolic": (50, 280), "diastolic": (30, 180),
                  "spo2": (50, 100), "weight_kg": (0.3, 400)}
        errors = {}
        for field, (low, high) in ranges.items():
            value = attrs.get(field)
            if value is not None and not (low <= float(value) <= high):
                errors[field] = f"Must be between {low} and {high}."
        if attrs.get("systolic") and attrs.get("diastolic") and attrs["diastolic"] >= attrs["systolic"]:
            errors["diastolic"] = "Diastolic pressure must be lower than systolic."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
