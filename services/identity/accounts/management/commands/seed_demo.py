"""Create demo hospitals and one user for every role. Demo data only."""
import os

from django.core.management.base import BaseCommand

from accounts.models import Hospital, User

HOSPITALS = [  # service addresses can be overridden with environment variables (Docker does this)
    ("KRH", "Kigali Referral Hospital", "Gasabo", os.environ.get("KRH_PATIENT_URL", "http://127.0.0.1:8000"), os.environ.get("KRH_RECORDS_URL", "http://127.0.0.1:8002")),
    ("BDH", "Butare District Hospital", "Huye", os.environ.get("BDH_PATIENT_URL", "http://127.0.0.1:9000"), os.environ.get("BDH_RECORDS_URL", "http://127.0.0.1:9002")),
]

# username, first, last, role, hospital code ('' = national)
USERS = [
    ("admin", "System", "Administrator", "SYSTEM_ADMIN", ""),
    ("dpo", "Diane", "Uwase", "DPO", ""),
    ("reg_krh", "Aline", "Mukamana", "REGISTRATION", "KRH"),
    ("nurse_krh", "Eric", "Habimana", "NURSE", "KRH"),
    ("doctor_krh", "Claire", "Ingabire", "DOCTOR", "KRH"),
    ("pharm_krh", "Jean", "Niyonzima", "PHARMACIST", "KRH"),
    ("lab_krh", "Grace", "Uwera", "LAB_TECH", "KRH"),
    ("manager_krh", "Patrick", "Mugisha", "HOSPITAL_MANAGER", "KRH"),
    ("reg_bdh", "Solange", "Uwimana", "REGISTRATION", "BDH"),
    ("nurse_bdh", "David", "Nsengiyumva", "NURSE", "BDH"),
    ("doctor_bdh", "Olivier", "Habineza", "DOCTOR", "BDH"),
    ("pharm_bdh", "Marie", "Mukeshimana", "PHARMACIST", "BDH"),
    ("lab_bdh", "Emmanuel", "Ndayisaba", "LAB_TECH", "BDH"),
    ("manager_bdh", "Jeanne", "Uwamahoro", "HOSPITAL_MANAGER", "BDH"),
]


class Command(BaseCommand):
    help = "Create demo hospitals and users (safe to run again)."

    def handle(self, *args, **options):
        password = os.environ.get("DEMO_PASSWORD", "Dhis@Demo2025")
        hospitals = {}
        for code, name, district, patient_url, records_url in HOSPITALS:
            hospitals[code], _ = Hospital.objects.update_or_create(
                code=code, defaults=dict(name=name, district=district, patient_url=patient_url, records_url=records_url))
        created = 0
        for username, first, last, role, code in USERS:
            user, new = User.objects.get_or_create(username=username, defaults=dict(
                first_name=first, last_name=last, role=role, hospital=hospitals.get(code), email=f"{username}@demo.dhis.local"))
            if new:
                user.set_password(password)
                user.save()
                created += 1
        self.stdout.write(self.style.SUCCESS(f"{len(hospitals)} hospitals, {created} new users. Demo password: {password}"))
