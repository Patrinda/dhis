from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from dhis_common import clients, directory, events
from dhis_common.exceptions import Conflict, ServiceUnavailable
from dhis_common.idempotency import idempotent
from dhis_common.pagination import StandardPagination
from dhis_common.permissions import IsInternal, roles, roles_for_method
from dhis_common.utils import hash_identifier

from .models import ACTIVE_STATUSES, Transfer, TransferHistory
from .serializers import TransferCreateSerializer, TransferSerializer
from .services import SLA, apply_action, event_payload, expire_overdue, visible_to

READERS = ("DOCTOR", "NURSE", "HOSPITAL_MANAGER", "SYSTEM_ADMIN", "DPO", "REGISTRATION")


class TransferList(APIView):
    permission_classes = [roles_for_method(read=READERS, write=("DOCTOR",))]

    def get(self, request):
        queryset = visible_to(request.user)
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        direction = request.query_params.get("direction")
        if direction == "incoming":
            queryset = queryset.filter(to_hospital=request.user.hospital)
        elif direction == "outgoing":
            queryset = queryset.filter(from_hospital=request.user.hospital)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(TransferSerializer(page, many=True, context={"request": request}).data)

    @idempotent
    def post(self, request):
        ser = TransferCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        user = request.user

        if data["to_hospital"] == user.hospital:
            raise ValidationError({"to_hospital": "Choose a different hospital from your own."})
        if not directory.by_code(data["to_hospital"]):
            raise ValidationError({"to_hospital": "Unknown receiving hospital."})

        # 1. The patient must be registered at the sending doctor's hospital.
        sender = directory.by_code(user.hospital)
        if not sender or not sender.get("patient_url"):
            raise ServiceUnavailable("Your hospital node is not registered.")
        response = clients.call("POST", sender["patient_url"] + "/internal/by-national-id/", json={"national_id": data["national_id"]}, timeout=3, retries=1)
        if response.status_code == 404:
            raise ValidationError({"national_id": "This patient is not registered at your hospital."})
        if response.status_code >= 300:
            raise ServiceUnavailable("Could not verify the patient.")
        patient = response.json()

        # 2. Consent must be on record (Audit and Consent service).
        consent = clients.call("POST", settings.AUDIT_URL + "/internal/consents/check/",
                               json={"id_hash": hash_identifier(data["national_id"]), "hospital": user.hospital}, timeout=3, retries=1)
        if consent.status_code >= 300:
            raise ServiceUnavailable("Could not check patient consent.")
        if not consent.json().get("valid"):
            raise ValidationError({"consent": "No valid patient consent is recorded for transfers. Ask the registration desk to record it."})

        # 3. Only one active transfer per patient.
        if Transfer.objects.filter(national_id=data["national_id"], status__in=ACTIVE_STATUSES).exists():
            raise Conflict("This patient already has an active transfer.")

        now = timezone.now()
        with transaction.atomic():
            transfer = Transfer.objects.create(
                national_id=data["national_id"], patient_name=patient["name"], from_hospital=user.hospital,
                to_hospital=data["to_hospital"], priority=data["priority"], reason=data["reason"],
                requested_by=user.name, requested_by_id=user.id, expires_at=now + SLA[data["priority"]])
            TransferHistory.objects.create(transfer=transfer, from_status="", to_status="PENDING", actor_name=user.name,
                                           actor_role=user.role, actor_hospital=user.hospital, note=data["reason"][:200])
            events.publish("transfer.requested", event_payload(transfer), aggregate_id=transfer.id, version=transfer.version)
        return Response(TransferSerializer(transfer, context={"request": request}).data, status=status.HTTP_201_CREATED)


class TransferDetail(APIView):
    permission_classes = [roles(*READERS)]

    def get(self, request, pk):
        try:
            transfer = visible_to(request.user).prefetch_related("history").get(pk=pk)
        except Transfer.DoesNotExist:
            raise NotFound("Transfer not found.")
        return Response(TransferSerializer(transfer, context={"request": request}).data)


class TransferAction(APIView):
    """POST /transfers/<id>/<action>/  body: {"version": n, "reason": "..."}"""
    permission_classes = [roles("DOCTOR", "NURSE", "HOSPITAL_MANAGER", "SYSTEM_ADMIN")]

    def post(self, request, pk, action):
        version = request.data.get("version")
        if not isinstance(version, int):
            raise ValidationError({"version": "version (a whole number) is required."})
        transfer = apply_action(pk, action, request.user, version, str(request.data.get("reason", "")))
        return Response(TransferSerializer(transfer, context={"request": request}).data)


class RunExpiry(APIView):
    """Lets an administrator (or a test) run the SLA job now."""
    permission_classes = [roles("SYSTEM_ADMIN")]

    def post(self, request):
        return Response({"expired": expire_overdue()})
