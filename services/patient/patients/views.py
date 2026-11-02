import concurrent.futures

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from dhis_common import clients, directory, events
from dhis_common.exceptions import Conflict, ServiceUnavailable
from dhis_common.idempotency import idempotent
from dhis_common.permissions import IsInternal, roles, roles_for_method
from dhis_common.utils import audit_access, hash_identifier, validate_national_id

from .models import Patient
from .serializers import PatientSerializer

READ_ROLES = ("REGISTRATION", "NURSE", "DOCTOR", "PHARMACIST", "LAB_TECH", "SYSTEM_ADMIN")
LOOKUP_TIMEOUT = 2.0


def age_band(dob):
    import datetime
    today = datetime.date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return "0-4" if age < 5 else "5-17" if age < 18 else "18-49" if age < 50 else "50+"


def federated_lookup(national_id: str) -> dict:
    """Ask every other hospital node whether it knows this national ID.

    Scatter: send the question to all peers at the same time.
    Gather: collect the answers within 2 seconds. A peer that does not answer
    is reported as unreachable and the result is marked partial. Each peer
    answers only yes or no, never any patient data.
    """
    found, unreachable = [], []
    peers = [h for h in directory.hospitals() if h["code"] != settings.NODE_CODE and h.get("patient_url")]

    def ask(hospital):
        response = clients.call("POST", hospital["patient_url"] + "/internal/exists/", json={"national_id": national_id},
                                timeout=LOOKUP_TIMEOUT, retries=0)
        return hospital["code"], response.status_code == 200 and response.json().get("exists", False)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(peers))) as pool:
        futures = {pool.submit(ask, h): h["code"] for h in peers}
        for future, code in futures.items():
            try:
                peer_code, exists = future.result(timeout=LOOKUP_TIMEOUT + 1)
                if exists:
                    found.append(peer_code)
            except Exception:  # noqa: BLE001 - any failure means "could not check this node"
                unreachable.append(code)
    return {"found_at": found, "unreachable": sorted(unreachable), "partial": bool(unreachable)}


class PatientList(APIView):
    permission_classes = [roles_for_method(read=READ_ROLES, write=("REGISTRATION",))]

    def get(self, request):
        queryset = Patient.objects.all()
        if request.user.role != "SYSTEM_ADMIN":
            queryset = queryset.filter(hospital_code=settings.NODE_CODE)
        q = request.query_params.get("q", "").strip()
        if q:
            queryset = queryset.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(national_id__startswith=q))
        from rest_framework.pagination import PageNumberPagination
        from dhis_common.pagination import StandardPagination
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(PatientSerializer(page, many=True, context={"request": request}).data)

    @idempotent
    def post(self, request):
        ser = PatientSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        national_id = ser.validated_data["national_id"]

        if Patient.objects.filter(national_id=national_id).exists():
            return Response({"error": {"code": "duplicate", "message": "This person is already registered at this hospital."}}, status=409)

        # 1. Federated lookup: is the person already known at another hospital?
        lookup = federated_lookup(national_id)
        if lookup["found_at"]:
            return Response({"error": {"code": "duplicate_elsewhere", "message":
                             f"This person is already registered at {', '.join(lookup['found_at'])}. Request a transfer instead.",
                             "details": lookup}}, status=409)

        # 2. Claim the ID at Identity (mutual exclusion). Fails closed if Identity is down.
        id_hash = hash_identifier(national_id)
        claim = clients.call("POST", settings.IDENTITY_URL + "/auth/internal/claims/",
                             json={"id_hash": id_hash, "hospital": settings.NODE_CODE}, timeout=3, retries=1)
        if claim.status_code == 409:
            return Response({"error": {"code": "claimed_elsewhere", "message":
                             "Another hospital is registering or has registered this person. Request a transfer instead."}}, status=409)
        if claim.status_code >= 300:
            raise ServiceUnavailable("Could not confirm the national ID is unique. Try again shortly.")

        # 3. Save the patient and queue the event in one transaction.
        try:
            with transaction.atomic():
                patient = ser.save(hospital_code=settings.NODE_CODE, created_by=request.user.id)
                events.publish("patient.registered", {
                    "patient_ref": id_hash[:16], "hospital": settings.NODE_CODE, "district": patient.district,
                    "sex": patient.sex, "age_band": age_band(patient.date_of_birth),
                }, aggregate_id=patient.id)
                audit_access(request, "patient.register", f"patient:{patient.id}")
        except Exception:
            clients.call("POST", settings.IDENTITY_URL + "/auth/internal/claims/release/",
                         json={"id_hash": id_hash, "hospital": settings.NODE_CODE}, timeout=2, retries=0)
            raise
        try:
            clients.call("POST", settings.IDENTITY_URL + "/auth/internal/claims/confirm/",
                         json={"id_hash": id_hash, "hospital": settings.NODE_CODE}, timeout=2, retries=1)
        except ServiceUnavailable:
            pass  # the lease simply stays CLAIMED; the patient row is the source of truth

        data = PatientSerializer(patient, context={"request": request}).data
        data["lookup_partial"] = lookup["partial"]
        return Response(data, status=status.HTTP_201_CREATED)


class PatientDetail(APIView):
    permission_classes = [roles_for_method(read=READ_ROLES, write=("REGISTRATION",))]

    def _get(self, request, pk):
        try:
            patient = Patient.objects.get(pk=pk)
        except (Patient.DoesNotExist, ValueError):
            raise NotFound("Patient not found.")
        if request.user.role != "SYSTEM_ADMIN" and patient.hospital_code != settings.NODE_CODE:
            raise NotFound("Patient not found.")
        return patient

    def get(self, request, pk):
        patient = self._get(request, pk)
        audit_access(request, "patient.view", f"patient:{patient.id}")
        return Response(PatientSerializer(patient, context={"request": request}).data)

    def patch(self, request, pk):
        patient = self._get(request, pk)
        sent_version = request.data.get("version")
        if sent_version is None:
            return Response({"error": {"code": "validation_error", "message": "version is required."}}, status=400)
        ser = PatientSerializer(patient, data=request.data, partial=True, context={"request": request})
        ser.is_valid(raise_exception=True)
        data = {k: v for k, v in ser.validated_data.items() if k != "national_id"}  # the ID never changes
        # Optimistic locking: the update only succeeds if nobody changed the row since it was read.
        with transaction.atomic():
            updated = Patient.objects.filter(pk=patient.pk, version=sent_version).update(version=patient.version + 1, **data)
            if not updated:
                raise Conflict()
            audit_access(request, "patient.update", f"patient:{patient.id}", {"fields": sorted(data)})
        patient.refresh_from_db()
        return Response(PatientSerializer(patient, context={"request": request}).data)


class LookupView(APIView):
    """POST /patients/lookup/ {national_id}: is this person known anywhere?"""
    permission_classes = [roles("REGISTRATION", "DOCTOR", "NURSE")]

    def post(self, request):
        try:
            national_id = validate_national_id(request.data.get("national_id", ""))
        except Exception:
            return Response({"error": {"code": "validation_error", "message": "National ID must be exactly 16 digits."}}, status=400)
        local = Patient.objects.filter(national_id=national_id).first()
        result = federated_lookup(national_id)
        result["local"] = bool(local)
        result["patient_id"] = str(local.id) if local else None
        return Response(result)


# --------------------------------------------------------------- internal
class InternalExists(APIView):
    """Used by other nodes. Answers yes or no and nothing else."""
    authentication_classes = []
    permission_classes = [IsInternal]

    def post(self, request):
        return Response({"exists": Patient.objects.filter(national_id=str(request.data.get("national_id", ""))).exists()})


class InternalByNationalId(APIView):
    """Used by the Referral and Records services to validate a patient."""
    authentication_classes = []
    permission_classes = [IsInternal]

    def post(self, request):
        patient = Patient.objects.filter(national_id=str(request.data.get("national_id", ""))).first()
        if not patient:
            return Response({"found": False}, status=404)
        return Response({"found": True, "id": str(patient.id), "national_id": patient.national_id,
                         "name": patient.full_name, "hospital_code": patient.hospital_code,
                         "sex": patient.sex, "date_of_birth": patient.date_of_birth.isoformat()})


class InternalById(APIView):
    authentication_classes = []
    permission_classes = [IsInternal]

    def get(self, request, pk):
        patient = Patient.objects.filter(pk=pk).first()
        if not patient:
            return Response({"found": False}, status=404)
        return Response({"found": True, "id": str(patient.id), "national_id": patient.national_id,
                         "name": patient.full_name, "hospital_code": patient.hospital_code})
