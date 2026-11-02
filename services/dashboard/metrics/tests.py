import uuid

from django.core.management import call_command
from django.test import TestCase
from django.db.models import Sum

from dhis_common.events import process_once

from .handlers import handle
from .models import ConditionCount, DailyCount, TransferProjection


def event(etype, payload, version=0, when="2025-03-10T09:00:00+02:00", mid=None):
    return {"message_id": mid or str(uuid.uuid4()), "type": etype, "version": version, "occurred_at": when, "payload": payload}


def transfer_payload(status, tid="11111111-1111-1111-1111-111111111111"):
    return {"transfer_id": tid, "from_hospital": "KRH", "to_hospital": "BDH", "priority": "URGENT", "status": status,
            "requested_at": "2025-03-10T08:00:00+02:00", "decided_at": None, "completed_at": None}


class ProjectionTests(TestCase):
    def test_duplicate_delivery_counts_once(self):
        ev = event("patient.registered", {"hospital": "KRH"})
        self.assertTrue(process_once(ev, handle))
        self.assertFalse(process_once(ev, handle))
        self.assertEqual(DailyCount.objects.get(hospital="KRH", measure="patients").value, 1)

    def test_older_version_arriving_late_is_ignored(self):
        process_once(event("transfer.decided", transfer_payload("ACCEPTED"), version=3), handle)
        process_once(event("transfer.requested", transfer_payload("PENDING"), version=1), handle)
        self.assertEqual(TransferProjection.objects.get().status, "ACCEPTED")

    def test_conditions_group_by_category(self):
        for code in ("B50.9", "B50.0", "J18.9"):
            process_once(event("encounter.created", {"hospital": "KRH", "diagnosis_code": code}), handle)
        self.assertEqual(ConditionCount.objects.get(code="B50").count, 2)

    def test_rebuild_gives_the_same_numbers(self):
        process_once(event("patient.registered", {"hospital": "KRH"}), handle)
        process_once(event("encounter.created", {"hospital": "KRH", "diagnosis_code": "B50.9"}), handle)
        process_once(event("transfer.requested", transfer_payload("PENDING"), version=1), handle)
        before = (DailyCount.objects.aggregate(s=Sum("value"))["s"], ConditionCount.objects.count(), TransferProjection.objects.count())
        call_command("rebuild", verbosity=0)
        after = (DailyCount.objects.aggregate(s=Sum("value"))["s"], ConditionCount.objects.count(), TransferProjection.objects.count())
        self.assertEqual(before, after)
