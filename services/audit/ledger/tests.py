import uuid

from django.db import connection
from django.test import TestCase
from django.utils import timezone

from .handlers import append, handle
from .models import AuditEntry


def make(n):
    for i in range(n):
        append(message_id=uuid.uuid4(), occurred_at=timezone.now(), event_type="audit.access", actor_name=f"user{i}",
               role="DOCTOR", hospital="KRH", action="patient.view", target_ref=f"patient:{i}")


class ChainTests(TestCase):
    def test_chain_links_each_line_to_the_previous(self):
        make(3)
        rows = list(AuditEntry.objects.order_by("seq"))
        self.assertEqual(rows[0].prev_hash, "0" * 64)
        self.assertEqual(rows[1].prev_hash, rows[0].hash)
        self.assertEqual(rows[2].prev_hash, rows[1].hash)

    def test_log_cannot_be_edited_or_deleted(self):
        make(1)
        entry = AuditEntry.objects.first()
        entry.action = "changed"
        with self.assertRaises(PermissionError):
            entry.save()
        with self.assertRaises(PermissionError):
            entry.delete()
        with self.assertRaises(PermissionError):
            AuditEntry.objects.all().update(action="x")
        with self.assertRaises(PermissionError):
            AuditEntry.objects.all().delete()

    def test_tampering_with_the_database_is_detected(self):
        make(4)
        with connection.cursor() as cursor:  # someone edits the table directly, bypassing Django
            cursor.execute("UPDATE ledger_auditentry SET actor_name = 'someone else' WHERE seq = 2")
        previous, first_bad = "0" * 64, None
        for entry in AuditEntry.objects.order_by("seq"):
            if entry.prev_hash != previous or entry.compute_hash() != entry.hash:
                first_bad = entry.seq
                break
            previous = entry.hash
        self.assertEqual(first_bad, 2)


class HandlerTests(TestCase):
    def test_break_glass_events_are_flagged(self):
        handle({"message_id": str(uuid.uuid4()), "type": "audit.break_glass", "occurred_at": timezone.now().isoformat(),
                "payload": {"actor_name": "Dr X", "role": "DOCTOR", "hospital": "BDH", "action": "break_glass.view",
                            "target_ref": "patient_ref:abc", "detail": {"reason": "emergency"}}})
        self.assertTrue(AuditEntry.objects.get().flagged)

    def test_transfer_events_are_logged_without_patient_details(self):
        handle({"message_id": str(uuid.uuid4()), "type": "transfer.requested", "occurred_at": timezone.now().isoformat(),
                "payload": {"transfer_id": "t1", "from_hospital": "KRH", "to_hospital": "BDH", "status": "PENDING", "priority": "URGENT",
                            "patient_ref": "abc"}})
        entry = AuditEntry.objects.get()
        self.assertEqual(entry.action, "transfer.requested")
        self.assertNotIn("national", str(entry.detail).lower())
