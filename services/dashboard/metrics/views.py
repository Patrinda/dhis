from django.db.models import Avg, Count, F, Q, Sum
from rest_framework.response import Response
from rest_framework.views import APIView

from dhis_common.permissions import roles

from .models import ConditionCount, DailyCount, TransferProjection

ALLOWED = ("HOSPITAL_MANAGER", "SYSTEM_ADMIN", "DPO")
STATUSES = ["PENDING", "ACCEPTED", "REJECTED", "CANCELLED", "EXPIRED", "IN_TRANSIT", "COMPLETED"]


def scope(request):
    """Managers see their own hospital. Administrators and the DPO see everything."""
    if request.user.role == "HOSPITAL_MANAGER":
        return request.user.hospital
    return request.query_params.get("hospital") or None


class Summary(APIView):
    permission_classes = [roles(*ALLOWED)]

    def get(self, request):
        hospital = scope(request)
        transfers = TransferProjection.objects.all()
        daily = DailyCount.objects.all()
        if hospital:
            transfers = transfers.filter(Q(from_hospital=hospital) | Q(to_hospital=hospital))
            daily = daily.filter(hospital=hospital)
        by_status = {row["status"]: row["n"] for row in transfers.values("status").annotate(n=Count("pk"))}
        decided = transfers.filter(decided_at__isnull=False).annotate(wait=F("decided_at") - F("requested_at")).aggregate(avg=Avg("wait"))
        totals = {row["measure"]: row["total"] for row in daily.values("measure").annotate(total=Sum("value"))}
        return Response({
            "scope": hospital or "ALL",
            "patients_registered": totals.get("patients", 0),
            "encounters": totals.get("encounters", 0),
            "transfers_total": sum(by_status.values()),
            "transfers_by_status": {s: by_status.get(s, 0) for s in STATUSES},
            "transfers_by_priority": {row["priority"]: row["n"] for row in transfers.values("priority").annotate(n=Count("pk"))},
            "avg_decision_minutes": round(decided["avg"].total_seconds() / 60, 1) if decided["avg"] else None,
        })


class Timeseries(APIView):
    permission_classes = [roles(*ALLOWED)]

    def get(self, request):
        hospital = scope(request)
        daily = DailyCount.objects.all()
        if hospital:
            daily = daily.filter(hospital=hospital)
        series = {}
        for row in daily.values("date", "measure").annotate(total=Sum("value")).order_by("date"):
            series.setdefault(row["measure"], []).append({"date": row["date"].isoformat(), "value": row["total"]})
        return Response(series)


class Conditions(APIView):
    permission_classes = [roles(*ALLOWED)]

    def get(self, request):
        hospital = scope(request)
        rows = ConditionCount.objects.all()
        if hospital:
            rows = rows.filter(hospital=hospital)
        top = rows.values("code").annotate(total=Sum("count")).order_by("-total")[:10]
        return Response([{"code": r["code"], "count": r["total"]} for r in top])


class Hospitals(APIView):
    """Side-by-side figures for each hospital (administrators and the DPO only)."""
    permission_classes = [roles("SYSTEM_ADMIN", "DPO")]

    def get(self, request):
        out = {}
        for row in DailyCount.objects.values("hospital", "measure").annotate(total=Sum("value")):
            out.setdefault(row["hospital"], {})[row["measure"]] = row["total"]
        return Response(out)


class RecentTransfers(APIView):
    """Latest transfers as the dashboard sees them (built from events, so possibly a few seconds behind)."""
    permission_classes = [roles(*ALLOWED)]

    def get(self, request):
        hospital = scope(request)
        rows = TransferProjection.objects.all()
        if hospital:
            rows = rows.filter(Q(from_hospital=hospital) | Q(to_hospital=hospital))
        data = [{"transfer_id": str(r.transfer_id), "from_hospital": r.from_hospital, "to_hospital": r.to_hospital,
                 "priority": r.priority, "status": r.status, "version": r.version, "requested_at": r.requested_at}
                for r in rows.order_by("-requested_at")[:50]]
        return Response(data)
