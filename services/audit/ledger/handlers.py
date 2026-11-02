from django.db import connection
from django.utils.dateparse import parse_datetime

from .models import AuditEntry

ADVISORY_LOCK_KEY = 7283910


def append(*, message_id, occurred_at, event_type, actor_id="", actor_name="", role="", hospital="",
           action="", target_ref="", detail=None, flagged=False) -> AuditEntry:
    if connection.vendor == "postgresql":
        # One writer at a time across ALL processes, until this transaction commits.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [ADVISORY_LOCK_KEY])
    last = AuditEntry.objects.order_by("-seq").first()
    entry = AuditEntry(message_id=message_id, occurred_at=occurred_at, event_type=event_type, actor_id=str(actor_id),
                       actor_name=actor_name, role=role, hospital=hospital, action=action, target_ref=target_ref,
                       detail=detail or {}, flagged=flagged, prev_hash=last.hash if last else "0" * 64)
    entry.hash = entry.compute_hash()
    entry.save()
    return entry


def handle(env: dict) -> None:
    """Every event in the system becomes an audit line."""
    p, etype = env["payload"], env["type"]
    common = dict(message_id=env["message_id"], occurred_at=parse_datetime(env["occurred_at"]), event_type=etype)
    if etype in ("audit.access", "audit.break_glass"):
        append(**common, actor_id=p.get("actor_id", ""), actor_name=p.get("actor_name", ""), role=p.get("role", ""),
               hospital=p.get("hospital", ""), action=p.get("action", etype), target_ref=p.get("target_ref", ""),
               detail=p.get("detail", {}), flagged=etype == "audit.break_glass")
    elif etype.startswith("auth."):
        append(**common, actor_id=p.get("actor_id", ""), actor_name=p.get("actor_name", p.get("username", "")), role=p.get("role", ""),
               hospital=p.get("hospital", ""), action=etype.split(".", 1)[1])
    else:
        append(**common, hospital=p.get("hospital", p.get("from_hospital", "")), action=etype,
               target_ref=p.get("transfer_id", p.get("patient_ref", "")), detail={k: v for k, v in p.items() if k in ("status", "priority", "from_hospital", "to_hospital")})


handle.serialize = True  # see dhis_common.events.process_once
