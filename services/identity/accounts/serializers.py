from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Hospital, User


class HospitalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hospital
        fields = ["id", "code", "name", "district", "patient_url", "records_url", "active"]


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)
    hospital_code = serializers.CharField(source="hospital.code", read_only=True, default="")
    hospital = serializers.SlugRelatedField(slug_field="code", queryset=Hospital.objects.all(), required=False, allow_null=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "role", "hospital",
                  "hospital_code", "is_active", "password", "last_login"]
        read_only_fields = ["id", "last_login"]

    def validate(self, attrs):
        role = attrs.get("role", getattr(self.instance, "role", None))
        hospital = attrs.get("hospital", getattr(self.instance, "hospital", None))
        if role not in ("SYSTEM_ADMIN", "DPO") and not hospital:
            raise serializers.ValidationError({"hospital": "This role must belong to a hospital."})
        if not self.instance and not attrs.get("password"):
            raise serializers.ValidationError({"password": "A password is required."})
        if attrs.get("password"):
            validate_password(attrs["password"])
        return attrs

    def create(self, validated):
        password = validated.pop("password")
        user = User(**validated)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated):
        password = validated.pop("password", None)
        for key, value in validated.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)
