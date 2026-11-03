from django.test import TestCase

from .models import Allergy, Encounter, Prescription
from .serializers import EncounterSerializer
from .views import build_summary

NID = "1199880012345678"


class SerializerTests(TestCase):
    def test_vital_sign_ranges(self):
        base = {"patient_id": "11111111-1111-1111-1111-111111111111"}
        self.assertTrue(EncounterSerializer(data={**base, "pulse": 80, "systolic": 120, "diastolic": 80}).is_valid())
        self.assertFalse(EncounterSerializer(data={**base, "pulse": 900}).is_valid())
        self.assertFalse(EncounterSerializer(data={**base, "systolic": 100, "diastolic": 110}).is_valid())
        self.assertFalse(EncounterSerializer(data={**base, "diagnosis_code": "malaria"}).is_valid())


class SummaryTests(TestCase):
    def test_summary_holds_codes_but_no_free_text_notes(self):
        enc = Encounter.objects.create(patient_id="11111111-1111-1111-1111-111111111111", national_id=NID, hospital_code="KRH",
                                       complaint="PRIVATE COMPLAINT TEXT", plan="PRIVATE PLAN TEXT", diagnosis_code="B50.9",
                                       diagnosis_text="Malaria", pulse=90, author_id="u1", author_name="Dr", author_role="DOCTOR")
        Allergy.objects.create(patient_id=enc.patient_id, national_id=NID, substance="Penicillin", recorded_by="Dr")
        Prescription.objects.create(encounter=enc, patient_id=enc.patient_id, national_id=NID, drug_name="Drug", dose="1", frequency="daily",
                                    duration_days=3, prescribed_by="Dr")
        summary = build_summary(NID)
        text = str(summary)
        self.assertNotIn("PRIVATE", text)
        self.assertEqual(summary["diagnoses"][0]["code"], "B50.9")
        self.assertEqual(summary["allergies"][0]["substance"], "Penicillin")
        self.assertEqual(summary["active_medicines"][0]["drug"], "Drug")
