import concurrent.futures

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
from dhis_common.permissions import IsInternal, roles, roles_for_method
from dhis_common.utils import audit_access, hash_identifier, validate_national_id
from dhis_common.pagination import StandardPagination

from .models import Allergy, Encounter, LabOrder, Prescription
from .serializers import (AllergySerializer, EncounterSerializer, LabOrderSerializer, LabResultSerializer,
                          PrescriptionSerializer)

CLINICAL = ("NURSE", "DOCTOR")
VIEWERS = ("NURSE", "DOCTOR", "PHARMACIST", "LAB_TECH")


def fetch_patient(patient_id=None, national_id=None):
    """Ask the Patient service of this node about a patient. Raises 503 if it is unreachable."""
    if patient_id:
        response = clients.call("GET", f"{settings.PATIENT_URL}/internal/by-id/{patient_id}/", timeout=2, retries=1)
    else:
        response = clients.call("POST", f"{settings.PATIENT_URL}/internal/by-national-id/", json={"national_id": national_id}, timeout=2, retries=1)
    if response.status_code == 404:
        raise NotFound("Patient not found at this hospital.")
    if response.status_code >= 300:
        raise ServiceUnavailable("Could not check the patient record.")
    data = response.json()
    if data["hospital_code"] != settings.NODE_CODE:
        raise NotFound("Patient not found at this hospital.")
    return data


def build_summary(national_id: str) -> dict:
    """The limited clinical summary that may leave this hospital: allergies,
    diagnosis codes, latest vital signs and active medicines. No free-text notes."""
    encounters = list(Encounter.objects.filter(national_id=national_id).order_by("-created_at"))
    latest_vitals = next(({"date": e.created_at.date().isoformat(), "temperature_c": float(e.temperature_c) if e.temperature_c is not None else None,
                           "pulse": e.pulse, "systolic": e.systolic, "diastolic": e.diastolic, "spo2": e.spo2}
                          for e in encounters if any([e.temperature_c, e.pulse, e.systolic, e.spo2])), None)
    return {
        "source_hospital": settings.NODE_CODE,
        "allergies": [{"substance": a.substance, "severity": a.severity} for a in Allergy.objects.filter(national_id=national_id)],
        "diagnoses": [{"code": e.diagnosis_code, "text": e.diagnosis_text, "date": e.created_at.date().isoformat()}
                      for e in encounters if e.diagnosis_code][:10],
        "active_medicines": [{"drug": p.drug_name, "dose": p.dose, "frequency": p.frequency}
                             for p in Prescription.objects.filter(national_id=national_id, status__in=["PRESCRIBED", "DISPENSED"])[:15]],
        "latest_vitals": latest_vitals,
        "generated_at": timezone.now().isoformat(),
    }


def _local_only(request, obj):
    if request.user.role != "SYSTEM_ADMIN" and obj.hospital_code != settings.NODE_CODE:
        raise NotFound("Not found.")


class EncounterList(APIView):
    permission_classes = [roles_for_method(read=VIEWERS, write=CLINICAL)]

    def get(self, request):
        patient_id = request.query_params.get("patient_id")
        if not patient_id:
            raise ValidationError({"patient_id": "patient_id is required."})
        queryset = Encounter.objects.filter(patient_id=patient_id, hospital_code=settings.NODE_CODE) \
            .prefetch_related("prescriptions", "lab_orders")
        if request.user.role in ("PHARMACIST", "LAB_TECH"):
            raise PermissionDenied("Your role cannot read encounters.")
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request)
        audit_access(request, "encounter.list", f"patient:{patient_id}")
        return paginator.get_paginated_response(EncounterSerializer(page, many=True).data)

    @idempotent
    def post(self, request):
        ser = EncounterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        patient_id = request.data.get("patient_id")
        patient = fetch_patient(patient_id=patient_id)
        data = dict(ser.validated_data)
        data.pop("patient_id", None)
        user = request.user
        if user.role == "NURSE":
            # Nurses record triage only. Diagnosis and plan belong to doctors.
            for field in ("diagnosis_code", "diagnosis_text", "plan"):
                data[field] = ""
        with transaction.atomic():
            encounter = Encounter.objects.create(patient_id=patient["id"], national_id=patient["national_id"], patient_name=patient["name"],
                                                 hospital_code=settings.NODE_CODE, author_id=user.id,
                                                 author_name=user.name, author_role=user.role, **data)
            events.publish("encounter.created", {
                "hospital": settings.NODE_CODE, "diagnosis_code": encounter.diagnosis_code,
                "encounter_type": encounter.encounter_type, "patient_ref": hash_identifier(patient["national_id"])[:16],
            }, aggregate_id=encounter.id)
            audit_access(request, "encounter.create", f"patient:{patient['id']}")
        return Response(EncounterSerializer(encounter).data, status=status.HTTP_201_CREATED)


class EncounterDetail(APIView):
    permission_classes = [roles_for_method(read=CLINICAL, write=CLINICAL)]

    def _get(self, request, pk):
        try:
            encounter = Encounter.objects.prefetch_related("prescriptions", "lab_orders").get(pk=pk)
        except Encounter.DoesNotExist:
            raise NotFound("Encounter not found.")
        _local_only(request, encounter)
        return encounter

    def get(self, request, pk):
        encounter = self._get(request, pk)
        audit_access(request, "encounter.view", f"patient:{encounter.patient_id}")
        return Response(EncounterSerializer(encounter).data)

    def patch(self, request, pk):
        encounter = self._get(request, pk)
        if request.user.role == "NURSE":
            raise PermissionDenied("Only a doctor can change a diagnosis or plan.")
        version = request.data.get("version")
        if version is None:
            raise ValidationError({"version": "version is required."})
        ser = EncounterSerializer(encounter, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            updated = Encounter.objects.filter(pk=encounter.pk, version=version).update(version=encounter.version + 1, **ser.validated_data)
            if not updated:
                raise Conflict()
            audit_access(request, "encounter.update", f"patient:{encounter.patient_id}")
        encounter.refresh_from_db()
        return Response(EncounterSerializer(encounter).data)


class AllergyList(APIView):
    permission_classes = [roles_for_method(read=VIEWERS, write=("NURSE", "DOCTOR", "PHARMACIST"))]

    def get(self, request):
        patient_id = request.query_params.get("patient_id")
        if not patient_id:
            raise ValidationError({"patient_id": "patient_id is required."})
        return Response(AllergySerializer(Allergy.objects.filter(patient_id=patient_id), many=True).data)

    @idempotent
    def post(self, request):
        ser = AllergySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        patient = fetch_patient(patient_id=request.data.get("patient_id"))
        allergy = Allergy.objects.create(patient_id=patient["id"], national_id=patient["national_id"],
                                         recorded_by=request.user.name, **{k: v for k, v in ser.validated_data.items() if k != "patient_id"})
        audit_access(request, "allergy.create", f"patient:{patient['id']}")
        return Response(AllergySerializer(allergy).data, status=status.HTTP_201_CREATED)


class PrescriptionList(APIView):
    permission_classes = [roles_for_method(read=("DOCTOR", "PHARMACIST", "NURSE"), write=("DOCTOR",))]

    def get(self, request):
        queryset = Prescription.objects.filter(encounter__hospital_code=settings.NODE_CODE)
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        if request.query_params.get("patient_id"):
            queryset = queryset.filter(patient_id=request.query_params["patient_id"])
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(PrescriptionSerializer(page, many=True).data)

    @idempotent
    def post(self, request):
        ser = PrescriptionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        encounter = ser.validated_data["encounter"]
        _local_only(request, encounter)
        prescription = Prescription.objects.create(patient_id=encounter.patient_id, national_id=encounter.national_id,
                                                   prescribed_by=request.user.name,
                                                   **{k: v for k, v in ser.validated_data.items()})
        audit_access(request, "prescription.create", f"patient:{encounter.patient_id}")
        return Response(PrescriptionSerializer(prescription).data, status=status.HTTP_201_CREATED)


class PrescriptionDispense(APIView):
    permission_classes = [roles("PHARMACIST")]

    def post(self, request, pk):
        now = timezone.now()
        # One conditional update: only a still-PRESCRIBED item can be dispensed, so two
        # pharmacists cannot dispense the same prescription twice.
        updated = Prescription.objects.filter(pk=pk, status=Prescription.PRESCRIBED, encounter__hospital_code=settings.NODE_CODE) \
            .update(status=Prescription.DISPENSED, dispensed_by=request.user.name, dispensed_at=now)
        if not updated:
            raise Conflict("This prescription is not waiting to be dispensed (already dispensed, cancelled or not found).")
        prescription = Prescription.objects.get(pk=pk)
        audit_access(request, "prescription.dispense", f"patient:{prescription.patient_id}")
        return Response(PrescriptionSerializer(prescription).data)


class LabOrderList(APIView):
    permission_classes = [roles_for_method(read=("DOCTOR", "NURSE", "LAB_TECH"), write=("DOCTOR",))]

    def get(self, request):
        queryset = LabOrder.objects.filter(encounter__hospital_code=settings.NODE_CODE)
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        if request.query_params.get("patient_id"):
            queryset = queryset.filter(patient_id=request.query_params["patient_id"])
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(LabOrderSerializer(page, many=True).data)

    @idempotent
    def post(self, request):
        ser = LabOrderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        encounter = ser.validated_data["encounter"]
        _local_only(request, encounter)
        order = LabOrder.objects.create(patient_id=encounter.patient_id, national_id=encounter.national_id,
                                        ordered_by=request.user.name, **ser.validated_data)
        audit_access(request, "laborder.create", f"patient:{encounter.patient_id}")
        return Response(LabOrderSerializer(order).data, status=status.HTTP_201_CREATED)


class LabOrderResult(APIView):
    permission_classes = [roles("LAB_TECH")]

    def post(self, request, pk):
        ser = LabResultSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        updated = LabOrder.objects.filter(pk=pk, status=LabOrder.ORDERED, encounter__hospital_code=settings.NODE_CODE).update(
            status=LabOrder.COMPLETED, entered_by=request.user.name, completed_at=timezone.now(), **ser.validated_data)
        if not updated:
            raise Conflict("This order already has a result or does not exist.")
        order = LabOrder.objects.get(pk=pk)
        audit_access(request, "laborder.result", f"patient:{order.patient_id}", {"flag": order.result_flag})
        return Response(LabOrderSerializer(order).data)


class BreakGlass(APIView):
    """Emergency access: a doctor reads the limited summary of a patient held by
    ANOTHER hospital, with a written reason. Every use is flagged for the DPO."""
    permission_classes = [roles("DOCTOR")]

    def post(self, request):
        try:
            national_id = validate_national_id(request.data.get("national_id", ""))
        except Exception:
            raise ValidationError({"national_id": "National ID must be exactly 16 digits."})
        reason = (request.data.get("reason") or "").strip()
        if len(reason) < 15:
            raise ValidationError({"reason": "Write at least 15 characters explaining the emergency."})

        peers = [h for h in directory.hospitals() if h["code"] != settings.NODE_CODE and h.get("records_url")]
        summaries, unreachable = [], []

        def ask(hospital):
            r = clients.call("POST", hospital["records_url"] + "/internal/summary/", json={"national_id": national_id}, timeout=3, retries=0)
            return hospital["code"], (r.json() if r.status_code == 200 else None)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(peers))) as pool:
            futures = {pool.submit(ask, h): h["code"] for h in peers}
            for future, code in futures.items():
                try:
                    _, data = future.result(timeout=4)
                    if data:
                        summaries.append(data)
                except Exception:  # noqa: BLE001
                    unreachable.append(code)

        ref = hash_identifier(national_id)[:16]
        events.publish("audit.break_glass", {
            "actor_id": request.user.id, "actor_name": request.user.name, "role": request.user.role,
            "hospital": request.user.hospital, "action": "break_glass.view", "target_ref": f"patient_ref:{ref}",
            "detail": {"reason": reason, "found": bool(summaries), "unreachable": unreachable},
        })
        if not summaries:
            return Response({"found": False, "unreachable": unreachable,
                             "message": "No summary found at the hospitals that answered."}, status=200)
        return Response({"found": True, "summaries": summaries, "unreachable": unreachable})


class InternalSummary(APIView):
    authentication_classes = []
    permission_classes = [IsInternal]

    def post(self, request):
        national_id = str(request.data.get("national_id", ""))
        if not Encounter.objects.filter(national_id=national_id).exists() and not Allergy.objects.filter(national_id=national_id).exists():
            return Response({"found": False}, status=404)
        return Response(build_summary(national_id))
