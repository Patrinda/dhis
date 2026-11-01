import datetime

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from dhis_common import events
from dhis_common.jwt_auth import issue_token
from dhis_common.permissions import IsInternal, roles
from dhis_common.utils import audit_access

from .models import Hospital, IdentifierClaim, User
from .serializers import HospitalSerializer, LoginSerializer, UserSerializer

MAX_FAILED = 5
LOCK_MINUTES = 15
LEASE_MINUTES = 2


def _claims_of(user):
    return dict(user_id=user.id, username=user.username, name=user.display_name,
                role=user.role, hospital=user.hospital.code if user.hospital else "")


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        username, password = ser.validated_data["username"], ser.validated_data["password"]
        target = User.objects.filter(username=username).select_related("hospital").first()

        if target and target.is_locked():
            return Response({"error": {"code": "locked", "message": "Account locked after too many failed attempts. Try again later."}}, status=423)

        user = authenticate(username=username, password=password)
        if not user or not user.is_active:
            if target:
                target.failed_attempts += 1
                if target.failed_attempts >= MAX_FAILED:
                    target.locked_until = timezone.now() + datetime.timedelta(minutes=LOCK_MINUTES)
                    target.failed_attempts = 0
                target.save(update_fields=["failed_attempts", "locked_until"])
            events.publish("auth.login_failed", {"username": username[:60]})
            return Response({"error": {"code": "invalid_credentials", "message": "Wrong username or password."}}, status=401)

        user = User.objects.select_related("hospital").get(pk=user.pk)
        user.failed_attempts, user.locked_until, user.last_login = 0, None, timezone.now()
        user.save(update_fields=["failed_attempts", "locked_until", "last_login"])
        events.publish("auth.login", {"actor_id": str(user.id), "actor_name": user.display_name, "role": user.role,
                                      "hospital": user.hospital.code if user.hospital else ""})
        token = issue_token(**_claims_of(user))
        return Response({"token": token, "user": UserSerializer(user).data})


class MeView(APIView):
    def get(self, request):
        user = User.objects.select_related("hospital").get(pk=request.user.id)
        return Response(UserSerializer(user).data)


class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [roles("SYSTEM_ADMIN")]
    serializer_class = UserSerializer
    queryset = User.objects.select_related("hospital").order_by("username")

    def perform_create(self, serializer):
        user = serializer.save()
        audit_access(self.request, "user.create", f"user:{user.id}", {"role": user.role})

    def perform_update(self, serializer):
        user = serializer.save()
        audit_access(self.request, "user.update", f"user:{user.id}", {"role": user.role, "active": user.is_active})

    def perform_destroy(self, instance):
        # Users are deactivated, never deleted, so the audit trail stays meaningful.
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        audit_access(self.request, "user.deactivate", f"user:{instance.id}")


class HospitalViewSet(viewsets.ModelViewSet):
    serializer_class = HospitalSerializer
    queryset = Hospital.objects.all()
    pagination_class = None

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return super().get_permissions()
        return [roles("SYSTEM_ADMIN")()]


class InternalHospitals(APIView):
    """Hospital directory for the gateway and other services."""
    authentication_classes = []
    permission_classes = [IsInternal]

    def get(self, request):
        return Response(HospitalSerializer(Hospital.objects.filter(active=True), many=True).data)


class PublicKeyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        with open(settings.JWT_PUBLIC_KEY_PATH, "rb") as handle:
            return HttpResponse(handle.read(), content_type="application/x-pem-file")


# ------------------------------------------------------------ ID claims
class ClaimView(APIView):
    """POST /auth/internal/claims/ {id_hash, hospital}  -> 201 granted, 409 held elsewhere."""
    authentication_classes = []
    permission_classes = [IsInternal]

    def post(self, request):
        id_hash, hospital = request.data.get("id_hash", ""), request.data.get("hospital", "")
        if len(id_hash) != 64 or not hospital:
            return Response({"error": {"code": "bad_request", "message": "id_hash and hospital are required."}}, status=400)
        now = timezone.now()
        lease = now + datetime.timedelta(minutes=LEASE_MINUTES)
        with transaction.atomic():
            try:
                with transaction.atomic():
                    IdentifierClaim.objects.create(id_hash=id_hash, hospital_code=hospital, lease_expires_at=lease)
                return Response({"granted": True}, status=status.HTTP_201_CREATED)
            except IntegrityError:
                pass
            # Someone already has a row. Decide whether it still counts.
            claim = IdentifierClaim.objects.get(id_hash=id_hash)
            if claim.hospital_code == hospital:
                return Response({"granted": True, "already_yours": True})
            if claim.status == IdentifierClaim.CLAIMED and claim.lease_expires_at < now:
                updated = IdentifierClaim.objects.filter(pk=claim.pk, status=IdentifierClaim.CLAIMED, lease_expires_at__lt=now) \
                    .update(hospital_code=hospital, lease_expires_at=lease)
                if updated:
                    return Response({"granted": True, "took_over_expired_lease": True}, status=status.HTTP_201_CREATED)
            return Response({"granted": False, "home_hospital": claim.hospital_code}, status=status.HTTP_409_CONFLICT)


class ClaimConfirmView(APIView):
    authentication_classes = []
    permission_classes = [IsInternal]

    def post(self, request):
        updated = IdentifierClaim.objects.filter(id_hash=request.data.get("id_hash"), hospital_code=request.data.get("hospital")) \
            .update(status=IdentifierClaim.CONFIRMED)
        return Response({"confirmed": bool(updated)})


class ClaimReleaseView(APIView):
    """Give a claim back when registration failed after the claim was granted."""
    authentication_classes = []
    permission_classes = [IsInternal]

    def post(self, request):
        deleted, _ = IdentifierClaim.objects.filter(id_hash=request.data.get("id_hash"), hospital_code=request.data.get("hospital"),
                                                    status=IdentifierClaim.CLAIMED).delete()
        return Response({"released": bool(deleted)})
