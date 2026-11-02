import datetime

from rest_framework import serializers

from dhis_common.utils import mask_identifier, validate_national_id

from .models import Patient


class PatientSerializer(serializers.ModelSerializer):
    national_id_masked = serializers.SerializerMethodField()
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Patient
        fields = ["id", "national_id", "national_id_masked", "first_name", "last_name", "full_name", "sex",
                  "date_of_birth", "phone", "district", "next_of_kin_name", "next_of_kin_phone",
                  "hospital_code", "version", "created_at", "updated_at"]
        read_only_fields = ["id", "hospital_code", "version", "created_at", "updated_at"]
        extra_kwargs = {"national_id": {"validators": []}}  # uniqueness is handled with the claim

    def get_national_id_masked(self, obj):
        return mask_identifier(obj.national_id)

    def validate_national_id(self, value):
        return validate_national_id(value)

    def validate_date_of_birth(self, value):
        if value > datetime.date.today():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        if value.year < 1900:
            raise serializers.ValidationError("Date of birth is not realistic.")
        return value

    def validate_phone(self, value):
        value = value.strip()
        if value and not (value.lstrip("+").isdigit() and 9 <= len(value.lstrip("+")) <= 15):
            raise serializers.ValidationError("Phone number must have 9 to 15 digits.")
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        # Only the registration desk needs to see the full ID. Everyone else sees it masked.
        if request is not None and getattr(request.user, "role", "") not in ("REGISTRATION", "DOCTOR"):
            data["national_id"] = data["national_id_masked"]
        return data
