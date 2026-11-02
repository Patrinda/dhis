import datetime
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from dhis_common.jwt_auth import Principal

from .models import Patient
from .serializers import PatientSerializer
from .views import age_band


def user(role="REGISTRATION"):
    return Principal({"sub": "u1", "username": "u1", "name": "U One", "role": role, "hospital": "KRH"})


def good(**kw):
    data = {"national_id": "1199880012345678", "first_name": "A", "last_name": "B", "sex": "F", "date_of_birth": "1990-01-01"}
    data.update(kw)
    return data


class ValidationTests(TestCase):
    def test_rules(self):
        self.assertTrue(PatientSerializer(data=good()).is_valid())
        for bad in ({"national_id": "123"}, {"national_id": "11998800123456ab"}, {"date_of_birth": "2999-01-01"},
                    {"phone": "abc"}, {"date_of_birth": "1800-01-01"}):
            self.assertFalse(PatientSerializer(data=good(**bad)).is_valid(), bad)

    def test_age_band(self):
        today = datetime.date.today()
        self.assertEqual(age_band(today.replace(year=today.year - 2)), "0-4")
        self.assertEqual(age_band(today.replace(year=today.year - 30)), "18-49")


class RegistrationFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user())

    def test_claim_conflict_blocks_registration(self):
        fake_claim = mock.Mock(status_code=409)
        with mock.patch("patients.views.federated_lookup", return_value={"found_at": [], "unreachable": [], "partial": False}), \
             mock.patch("patients.views.clients.call", return_value=fake_claim):
            response = self.client.post("/patients/", good(), format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "claimed_elsewhere")
        self.assertEqual(Patient.objects.count(), 0)

    def test_known_elsewhere_blocks_registration(self):
        with mock.patch("patients.views.federated_lookup", return_value={"found_at": ["BDH"], "unreachable": [], "partial": False}):
            response = self.client.post("/patients/", good(), format="json")
        self.assertEqual(response.json()["error"]["code"], "duplicate_elsewhere")

    def test_identity_down_fails_closed(self):
        from dhis_common.exceptions import ServiceUnavailable
        with mock.patch("patients.views.federated_lookup", return_value={"found_at": [], "unreachable": [], "partial": False}), \
             mock.patch("patients.views.clients.call", side_effect=ServiceUnavailable()):
            response = self.client.post("/patients/", good(), format="json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(Patient.objects.count(), 0)

    def test_update_needs_current_version(self):
        patient = Patient.objects.create(**{**good(date_of_birth=datetime.date(1990, 1, 1)), "hospital_code": "KRH", "created_by": "u1"})
        ok = self.client.patch(f"/patients/{patient.id}/", {"phone": "0788111222", "version": 1}, format="json")
        stale = self.client.patch(f"/patients/{patient.id}/", {"phone": "0788333444", "version": 1}, format="json")
        self.assertEqual((ok.status_code, stale.status_code), (200, 409))

    def test_non_registration_roles_see_masked_id(self):
        Patient.objects.create(**{**good(date_of_birth=datetime.date(1990, 1, 1)), "hospital_code": "KRH", "created_by": "u1"})
        nurse = APIClient()
        nurse.force_authenticate(user("NURSE"))
        row = nurse.get("/patients/").json()["results"][0]
        self.assertIn("*", row["national_id"])
