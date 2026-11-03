from rest_framework import serializers

from dhis_common.utils import validate_national_id

from .models import Transfer, TransferHistory


class HistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TransferHistory
        fields = ["from_status", "to_status", "actor_name", "actor_role", "actor_hospital", "note", "at"]


class TransferSerializer(serializers.ModelSerializer):
    history = HistorySerializer(many=True, read_only=True)

    class Meta:
        model = Transfer
        fields = ["id", "patient_name", "from_hospital", "to_hospital", "priority", "reason", "status", "version",
                  "requested_by", "decision_reason", "clinical_summary", "created_at", "expires_at",
                  "decided_at", "in_transit_at", "completed_at", "history", "national_id"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        user = self.context["request"].user
        # The clinical summary is for the receiving hospital only, once the patient is on the way.
        if not (user.hospital == instance.to_hospital or user.role == "SYSTEM_ADMIN") or instance.status not in ("IN_TRANSIT", "COMPLETED"):
            data["clinical_summary"] = None
        # Managers and the DPO do not need the full national ID.
        if user.role in ("HOSPITAL_MANAGER", "DPO", "SYSTEM_ADMIN"):
            nid = data["national_id"]
            data["national_id"] = nid[:1] + "*" * 12 + nid[-3:]
        return data


class TransferCreateSerializer(serializers.Serializer):
    national_id = serializers.CharField()
    to_hospital = serializers.CharField(max_length=10)
    priority = serializers.ChoiceField(choices=["EMERGENCY", "URGENT", "ROUTINE"])
    reason = serializers.CharField(min_length=10, max_length=2000)

    def validate_national_id(self, value):
        return validate_national_id(value)
