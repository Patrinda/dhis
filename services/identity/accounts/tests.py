import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from dhis_common.utils import hash_identifier

from .models import Hospital, IdentifierClaim, User

KEY = {"HTTP_X_INTERNAL_KEY": "dev-internal-key-change-me"}


class ClaimTests(TestCase):
    """Mutual exclusion: only one hospital can hold a claim on a national ID."""

    def setUp(self):
        self.client = APIClient()
        self.h = hash_identifier("1199880012345678")

    def claim(self, hospital):
        return self.client.post("/auth/internal/claims/", {"id_hash": self.h, "hospital": hospital}, format="json", **KEY)

    def test_second_hospital_is_refused(self):
        self.assertEqual(self.claim("KRH").status_code, 201)
        second = self.claim("BDH")
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["home_hospital"], "KRH")

    def test_same_hospital_can_repeat(self):
        self.claim("KRH")
        self.assertEqual(self.claim("KRH").status_code, 200)

    def test_expired_lease_can_be_taken_over(self):
        self.claim("KRH")
        IdentifierClaim.objects.update(lease_expires_at=timezone.now() - datetime.timedelta(minutes=1))
        self.assertEqual(self.claim("BDH").status_code, 201)

    def test_confirmed_claim_never_expires(self):
        self.claim("KRH")
        self.client.post("/auth/internal/claims/confirm/", {"id_hash": self.h, "hospital": "KRH"}, format="json", **KEY)
        IdentifierClaim.objects.update(lease_expires_at=timezone.now() - datetime.timedelta(days=5))
        self.assertEqual(self.claim("BDH").status_code, 409)

    def test_internal_routes_need_the_key(self):
        self.assertEqual(self.client.post("/auth/internal/claims/", {"id_hash": self.h, "hospital": "KRH"}, format="json").status_code, 403)


class LoginTests(TestCase):
    def setUp(self):
        hospital = Hospital.objects.create(code="KRH", name="Test", district="Gasabo")
        self.user = User.objects.create_user("nurse1", password="CorrectHorse!42", role="NURSE", hospital=hospital)

    def test_account_locks_after_five_failures(self):
        client = APIClient()
        for _ in range(5):
            self.assertEqual(client.post("/auth/login/", {"username": "nurse1", "password": "bad"}, format="json").status_code, 401)
        locked = client.post("/auth/login/", {"username": "nurse1", "password": "CorrectHorse!42"}, format="json")
        self.assertEqual(locked.status_code, 423)

    def test_good_login_returns_a_token(self):
        response = APIClient().post("/auth/login/", {"username": "nurse1", "password": "CorrectHorse!42"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())


class UserRuleTests(TestCase):
    def test_clinical_roles_need_a_hospital(self):
        from .serializers import UserSerializer
        ser = UserSerializer(data={"username": "x1", "role": "DOCTOR", "password": "CorrectHorse!42"})
        self.assertFalse(ser.is_valid())
        self.assertIn("hospital", ser.errors)
