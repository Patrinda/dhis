"""The transfer state machine.

            +--> REJECTED
 PENDING ---+--> CANCELLED
            +--> EXPIRED        (by the expiry job)
            +--> ACCEPTED --+--> IN_TRANSIT --> COMPLETED
                            +--> CANCELLED
 (PENDING_SYNC lives in the gateway queue until the request reaches this service.)

Every change is one conditional UPDATE that also checks the version the caller
read. If two doctors act at once, one update changes a row and the other
changes none, and the second receives HTTP 409.
"""
import datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from dhis_common import clients, events
from dhis_common.exceptions import Conflict, ServiceUnavailable
from dhis_common.utils import hash_identifier

from .models import Transfer, TransferHistory

SLA = {"EMERGENCY": datetime.timedelta(hours=1), "URGENT": datetime.timedelta(hours=6), "ROUTINE": datetime.timedelta(hours=48)}

# action -> (allowed from statuses, new status, event type, side that must act, allowed roles)
ACTIONS = {
    "accept":     (["PENDING"], "ACCEPTED", "transfer.decided", "to", ("DOCTOR", "HOSPITAL_MANAGER")),
    "reject":     (["PENDING"], "REJECTED", "transfer.decided", "to", ("DOCTOR", "HOSPITAL_MANAGER")),
    "in-transit": (["ACCEPTED"], "IN_TRANSIT", "transfer.in_transit", "from", ("DOCTOR", "NURSE")),
    "complete":   (["IN_TRANSIT"], "COMPLETED", "transfer.completed", "to", ("DOCTOR", "NURSE")),
    "cancel":     (["PENDING", "ACCEPTED"], "CANCELLED", "transfer.cancelled", "either", ("DOCTOR", "HOSPITAL_MANAGER")),
}
REASON_REQUIRED = {"reject", "cancel"}
TIME_FIELD = {"ACCEPTED": "decided_at", "REJECTED": "decided_at", "IN_TRANSIT": "in_transit_at", "COMPLETED": "completed_at"}


def event_payload(transfer: Transfer) -> dict:
    return {
        "transfer_id": str(transfer.id), "from_hospital": transfer.from_hospital, "to_hospital": transfer.to_hospital,
        "priority": transfer.priority, "status": transfer.status,
        "patient_ref": hash_identifier(transfer.national_id)[:16],
        "requested_at": transfer.created_at.isoformat(),
        "decided_at": transfer.decided_at.isoformat() if transfer.decided_at else None,
        "completed_at": transfer.completed_at.isoformat() if transfer.completed_at else None,
    }


def visible_to(user):
    queryset = Transfer.objects.all()
    if user.role in ("SYSTEM_ADMIN", "DPO"):
        return queryset
    from django.db.models import Q
    return queryset.filter(Q(from_hospital=user.hospital) | Q(to_hospital=user.hospital))


def apply_action(transfer_id, action, user, sent_version, reason=""):
    if action not in ACTIONS:
        raise NotFound("Unknown action.")
    allowed_from, new_status, event_type, side, allowed_roles = ACTIONS[action]
    try:
        transfer = Transfer.objects.get(pk=transfer_id)
    except Transfer.DoesNotExist:
        raise NotFound("Transfer not found.")

    # Who may do this?
    if user.role not in allowed_roles and user.role != "SYSTEM_ADMIN":
        raise PermissionDenied("Your role cannot do this.")
    if user.role != "SYSTEM_ADMIN":
        ok = {"to": user.hospital == transfer.to_hospital, "from": user.hospital == transfer.from_hospital,
              "either": user.hospital in (transfer.from_hospital, transfer.to_hospital)}[side]
        if not ok:
            raise PermissionDenied("Your hospital cannot do this on this transfer.")
        if action == "cancel" and transfer.status == "PENDING" and user.role == "DOCTOR" and transfer.requested_by_id != user.id:
            raise PermissionDenied("Only the requesting doctor or a hospital manager can cancel a pending transfer.")
        if action == "cancel" and transfer.status == "PENDING" and user.hospital != transfer.from_hospital:
            raise PermissionDenied("Only the requesting hospital can cancel a pending transfer.")
    if action in REASON_REQUIRED and len(reason.strip()) < 5:
        raise ValidationError({"reason": "A reason of at least 5 characters is required."})
    if transfer.status not in allowed_from:
        raise Conflict(f"This transfer is {transfer.status}; it cannot be {new_status}.")

    summary = None
    if action == "complete":
        summary = pull_clinical_summary(transfer)

    now = timezone.now()
    old_status = transfer.status
    changes = {"status": new_status, "version": transfer.version + 1}
    if new_status in TIME_FIELD:
        changes[TIME_FIELD[new_status]] = now
    if action in ("accept", "reject", "cancel"):
        changes["decision_reason"] = reason.strip()
    if summary is not None:
        changes["clinical_summary"] = summary

    with transaction.atomic():
        updated = Transfer.objects.filter(pk=transfer.pk, version=sent_version, status__in=allowed_from).update(**changes)
        if not updated:
            raise Conflict()
        transfer.refresh_from_db()
        TransferHistory.objects.create(transfer=transfer, from_status=old_status,
                                       to_status=new_status, actor_name=user.name, actor_role=user.role,
                                       actor_hospital=user.hospital, note=reason.strip())
        events.publish(event_type, event_payload(transfer), aggregate_id=transfer.id, version=transfer.version)
    return transfer


def pull_clinical_summary(transfer: Transfer) -> dict:
    """On arrival the receiving hospital pulls the limited summary from the sending
    hospital's Records service. Allowed only because the transfer was accepted."""
    from dhis_common import directory
    sender = directory.by_code(transfer.from_hospital)
    if not sender or not sender.get("records_url"):
        raise ServiceUnavailable("The sending hospital's records service is not registered.")
    response = clients.call("POST", sender["records_url"] + "/internal/summary/", json={"national_id": transfer.national_id}, timeout=4, retries=1)
    if response.status_code == 404:
        return {"source_hospital": transfer.from_hospital, "allergies": [], "diagnoses": [], "active_medicines": [],
                "latest_vitals": None, "note": "The sending hospital has no clinical records for this patient yet."}
    if response.status_code >= 300:
        raise ServiceUnavailable("Could not fetch the clinical summary. The transfer stays In transit; try again.")
    return response.json()


def expire_overdue() -> int:
    """SLA job: a PENDING transfer with no decision by its deadline becomes EXPIRED."""
    now = timezone.now()
    count = 0
    for transfer in Transfer.objects.filter(status="PENDING", expires_at__lt=now)[:100]:
        with transaction.atomic():
            updated = Transfer.objects.filter(pk=transfer.pk, status="PENDING", version=transfer.version) \
                .update(status="EXPIRED", version=transfer.version + 1)
            if not updated:
                continue
            transfer.refresh_from_db()
            TransferHistory.objects.create(transfer=transfer, from_status="PENDING", to_status="EXPIRED",
                                           actor_name="SLA job", actor_role="SYSTEM", note="No decision before the deadline.")
            events.publish("transfer.expired", event_payload(transfer), aggregate_id=transfer.id, version=transfer.version)
            count += 1
    return count
