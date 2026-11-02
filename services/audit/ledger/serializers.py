from rest_framework import serializers

from .models import AuditEntry, Consent


class AuditEntrySerializer(serializers.ModelSerializer):
    review = serializers.SerializerMethodField()

    class Meta:
        model = AuditEntry
        fields = ["seq", "occurred_at", "event_type", "actor_name", "role", "hospital", "action", "target_ref",
                  "detail", "flagged", "hash", "review"]

    def get_review(self, obj):
        review = getattr(obj, "review", None) if obj.flagged else None
        return {"reviewed_by": review.reviewed_by, "outcome": review.outcome, "comment": review.comment,
                "reviewed_at": review.reviewed_at} if review else None


class ConsentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Consent
        fields = ["id", "hospital", "status", "recorded_by", "granted_at", "withdrawn_at"]
