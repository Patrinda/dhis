"""Turn events into dashboard numbers.

Duplicates are removed before this code runs (ProcessedEvent). Out-of-order
transfer events are handled with the version number: an event older than what
we already hold is stored but does not change the projection.
"""
from django.db.models import F
from django.utils.dateparse import parse_datetime

from .models import ConditionCount, DailyCount, EventRecord, TransferProjection


def _bump(date, hospital, measure, by=1):
    row, _ = DailyCount.objects.get_or_create(date=date, hospital=hospital, measure=measure)
    DailyCount.objects.filter(pk=row.pk).update(value=F("value") + by)


def handle(env: dict) -> None:
    occurred = parse_datetime(env["occurred_at"])
    EventRecord.objects.get_or_create(message_id=env["message_id"], defaults=dict(
        event_type=env["type"], version=env.get("version", 0), occurred_at=occurred, payload=env["payload"]))
    apply(env["type"], env.get("version", 0), occurred, env["payload"])


def apply(event_type, version, occurred, p):
    day = occurred.date()
    if event_type == "patient.registered":
        _bump(day, p["hospital"], "patients")
    elif event_type == "encounter.created":
        _bump(day, p["hospital"], "encounters")
        if p.get("diagnosis_code"):
            code = p["diagnosis_code"].split(".")[0]  # group by 3-character category, e.g. B50
            row, _ = ConditionCount.objects.get_or_create(hospital=p["hospital"], code=code)
            ConditionCount.objects.filter(pk=row.pk).update(count=F("count") + 1)
    elif event_type.startswith("transfer."):
        _transfer(event_type, version, p, day)


def _transfer(event_type, version, p, day):
    tid = p["transfer_id"]
    projection = TransferProjection.objects.filter(pk=tid).first()
    if projection and version <= projection.version:
        return  # an older or repeated version arrived late; ignore it
    fields = dict(from_hospital=p["from_hospital"], to_hospital=p["to_hospital"], priority=p["priority"], status=p["status"],
                  version=version, requested_at=parse_datetime(p["requested_at"]),
                  decided_at=parse_datetime(p["decided_at"]) if p.get("decided_at") else None,
                  completed_at=parse_datetime(p["completed_at"]) if p.get("completed_at") else None)
    TransferProjection.objects.update_or_create(transfer_id=tid, defaults=fields)
    if event_type == "transfer.requested":
        _bump(day, p["from_hospital"], "transfers_out")
        _bump(day, p["to_hospital"], "transfers_in")
