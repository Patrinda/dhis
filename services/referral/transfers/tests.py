import datetime
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from dhis_common.exceptions import Conflict
from dhis_common.jwt_auth import Principal
from dhis_common.models import OutboxEvent

from .models import Transfer
from .services import apply_action, expire_overdue


def person(role, hospital, uid="u1"):
    return Principal({"sub": uid, "username": uid, "name": uid, "role": role, "hospital": hospital})


def make_transfer(**kw):
    defaults = dict(national_id="1199880012345678", patient_name="A B", from_hospital="KRH", to_hospital="BDH", priority="URGENT",
                    reason="needs care", requested_by="Dr", requested_by_id="u1",
                    expires_at=timezone.now() + datetime.timedelta(hours=6))
    defaults.update(kw)
    return Transfer.objects.create(**defaults)


class StateMachineTests(TestCase):
    def test_happy_path_bumps_version_and_writes_history_and_events(self):
        t = make_transfer()
        t = apply_action(t.id, "accept", person("DOCTOR", "BDH"), 1)
        self.assertEqual((t.status, t.version), ("ACCEPTED", 2))
        t = apply_action(t.id, "in-transit", person("NURSE", "KRH"), 2)
        with mock.patch("transfers.services.pull_clinical_summary", return_value={"allergies": []}):
            t = apply_action(t.id, "complete", person("NURSE", "BDH"), 3)
        self.assertEqual((t.status, t.version), ("COMPLETED", 4))
        self.assertEqual([h.to_status for h in t.history.all()], ["ACCEPTED", "IN_TRANSIT", "COMPLETED"])
        self.assertEqual(OutboxEvent.objects.count(), 3)
        self.assertEqual(list(OutboxEvent.objects.values_list("version", flat=True)), [2, 3, 4])

    def test_stale_version_is_a_conflict(self):
        t = make_transfer()
        apply_action(t.id, "accept", person("DOCTOR", "BDH"), 1)
        with self.assertRaises(Conflict):
            apply_action(t.id, "reject", person("DOCTOR", "BDH"), 1, "no beds")

    def test_illegal_transition_is_refused(self):
        t = make_transfer(status="COMPLETED", version=4)
        with self.assertRaises(Conflict):
            apply_action(t.id, "accept", person("DOCTOR", "BDH"), 4)

    def test_wrong_hospital_or_role_is_refused(self):
        t = make_transfer()
        with self.assertRaises(PermissionDenied):
            apply_action(t.id, "accept", person("DOCTOR", "KRH"), 1)   # the sender cannot accept its own request
        with self.assertRaises(PermissionDenied):
            apply_action(t.id, "accept", person("NURSE", "BDH"), 1)    # nurses do not decide

    def test_reject_and_cancel_need_a_reason(self):
        t = make_transfer()
        with self.assertRaises(ValidationError):
            apply_action(t.id, "reject", person("DOCTOR", "BDH"), 1, "")

    def test_only_requester_or_manager_can_cancel_pending(self):
        t = make_transfer()
        with self.assertRaises(PermissionDenied):
            apply_action(t.id, "cancel", person("DOCTOR", "KRH", uid="other"), 1, "changed my mind")
        t = apply_action(t.id, "cancel", person("HOSPITAL_MANAGER", "KRH", uid="m1"), 1, "patient improved")
        self.assertEqual(t.status, "CANCELLED")


class ExpiryTests(TestCase):
    def test_overdue_pending_transfers_expire(self):
        late = make_transfer(expires_at=timezone.now() - datetime.timedelta(minutes=1))
        fine = make_transfer(national_id="1199880012345679")
        self.assertEqual(expire_overdue(), 1)
        late.refresh_from_db(), fine.refresh_from_db()
        self.assertEqual((late.status, late.version), ("EXPIRED", 2))
        self.assertEqual(fine.status, "PENDING")
        self.assertTrue(OutboxEvent.objects.filter(event_type="transfer.expired").exists())
