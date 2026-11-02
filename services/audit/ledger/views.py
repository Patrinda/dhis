from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from dhis_common.pagination import StandardPagination
from dhis_common.permissions import IsInternal, roles
from dhis_common.utils import hash_identifier, validate_national_id

from .models import AuditEntry, BreakGlassReview, Consent
from .serializers import AuditEntrySerializer, ConsentSerializer

AUDITORS = ("DPO", "SYSTEM_ADMIN")


class AuditList(APIView):
    permission_classes = [roles(*AUDITORS)]

    def get(self, request):
        queryset = AuditEntry.objects.select_related("review").order_by("-seq")
        q = request.query_params
        for field in ("hospital", "role", "action", "event_type"):
            if q.get(field):
                queryset = queryset.filter(**{field: q[field]})
        if q.get("flagged") == "1":
            queryset = queryset.filter(flagged=True)
        if q.get("actor"):
            queryset = queryset.filter(actor_name__icontains=q["actor"])
        paginator = StandardPagination()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response(AuditEntrySerializer(page, many=True).data)


class AuditVerify(APIView):
    """Walk the chain from the first line and report the first line that does not match."""
    permission_classes = [roles(*AUDITORS)]

    def get(self, request):
        previous, count = "0" * 64, 0
        for entry in AuditEntry.objects.order_by("seq").iterator(chunk_size=500):
            if entry.prev_hash != previous or entry.compute_hash() != entry.hash:
                return Response({"intact": False, "checked": count, "first_bad_seq": entry.seq})
            previous, count = entry.hash, count + 1
        return Response({"intact": True, "checked": count, "first_bad_seq": None})


class BreakGlassReviewView(APIView):
    permission_classes = [roles("DPO")]

    def post(self, request, seq):
        try:
            entry = AuditEntry.objects.get(pk=seq, flagged=True)
        except AuditEntry.DoesNotExist:
            raise NotFound("No flagged entry with that number.")
        outcome = request.data.get("outcome")
        if outcome not in ("JUSTIFIED", "QUERY"):
            raise ValidationError({"outcome": "Choose JUSTIFIED or QUERY."})
        review, _ = BreakGlassReview.objects.update_or_create(
            entry=entry, defaults=dict(reviewed_by=request.user.name, outcome=outcome, comment=str(request.data.get("comment", ""))[:1000],
                                       reviewed_at=timezone.now()))
        return Response({"seq": entry.seq, "outcome": review.outcome, "reviewed_by": review.reviewed_by})


class ConsentList(APIView):
    """Registration desk and doctors record consent. The DPO can see the register."""
    permission_classes = [roles("REGISTRATION", "DOCTOR", "DPO", "SYSTEM_ADMIN")]

    def get(self, request):
        queryset = Consent.objects.all()
        if request.user.role in ("REGISTRATION", "DOCTOR"):
            queryset = queryset.filter(hospital=request.user.hospital)
        return Response(ConsentSerializer(queryset[:200], many=True).data)

    def post(self, request):
        if request.user.role not in ("REGISTRATION", "DOCTOR"):
            raise ValidationError({"role": "Only registration staff or doctors record consent."})
        try:
            national_id = validate_national_id(request.data.get("national_id", ""))
        except Exception:
            raise ValidationError({"national_id": "National ID must be exactly 16 digits."})
        id_hash = hash_identifier(national_id)
        consent, created = Consent.objects.get_or_create(id_hash=id_hash, hospital=request.user.hospital, status="GRANTED",
                                                         defaults={"recorded_by": request.user.name})
        return Response(ConsentSerializer(consent).data, status=201 if created else 200)


class ConsentWithdraw(APIView):
    permission_classes = [roles("REGISTRATION", "DOCTOR")]

    def post(self, request):
        try:
            national_id = validate_national_id(request.data.get("national_id", ""))
        except Exception:
            raise ValidationError({"national_id": "National ID must be exactly 16 digits."})
        n = Consent.objects.filter(id_hash=hash_identifier(national_id), hospital=request.user.hospital, status="GRANTED") \
            .update(status="WITHDRAWN", withdrawn_at=timezone.now())
        return Response({"withdrawn": n})


class ConsentCheck(APIView):
    authentication_classes = []
    permission_classes = [IsInternal]

    def post(self, request):
        valid = Consent.objects.filter(id_hash=request.data.get("id_hash", ""), hospital=request.data.get("hospital", ""), status="GRANTED").exists()
        return Response({"valid": valid})


class ConsentStatus(APIView):
    """Does this patient have consent on record at the caller's hospital?"""
    permission_classes = [roles("REGISTRATION", "DOCTOR", "NURSE")]

    def post(self, request):
        try:
            national_id = validate_national_id(request.data.get("national_id", ""))
        except Exception:
            raise ValidationError({"national_id": "National ID must be exactly 16 digits."})
        granted = Consent.objects.filter(id_hash=hash_identifier(national_id), hospital=request.user.hospital, status="GRANTED").exists()
        return Response({"granted": granted})
