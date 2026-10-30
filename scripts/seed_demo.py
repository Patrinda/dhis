"""Fill a running system with realistic demonstration data through the gateway.

    python scripts/seed_demo.py

Safe to run once on a fresh system (python run_all.py --reset). Running it twice
will skip people who are already registered. All names and numbers are invented.
"""
import sys
import time

import requests

BASE = "http://127.0.0.1:8080/api"
PASSWORD = "Dhis@Demo2025"
tokens = {}


def login(user):
    r = requests.post(f"{BASE}/auth/login/", json={"username": user, "password": PASSWORD}, timeout=10)
    r.raise_for_status()
    tokens[user] = r.json()["token"]


def api(user, method, path, **kw):
    return requests.request(method, f"{BASE}/{path}", headers={"Authorization": "Bearer " + tokens[user]}, timeout=20, **kw)


# national id, first, last, sex, dob, phone, district, hospital user
PEOPLE = [
    ("1199880012345601", "Alice", "Uwase", "F", "1988-03-12", "0788111201", "Gasabo", "reg_krh"),
    ("1199270034567802", "Jean Paul", "Habimana", "M", "1992-07-21", "0788111202", "Kicukiro", "reg_krh"),
    ("1200150056789003", "Aline", "Mukamana", "F", "2015-11-02", "0788111203", "Nyarugenge", "reg_krh"),
    ("1196560078901204", "Emmanuel", "Nsengimana", "M", "1965-01-30", "0788111204", "Gasabo", "reg_krh"),
    ("1199990090123405", "Grace", "Ingabire", "F", "1999-09-09", "0788111205", "Kicukiro", "reg_krh"),
    ("1198580011223306", "Claude", "Niyonsenga", "M", "1985-05-17", "0788111206", "Gasabo", "reg_krh"),
    ("1199470022334407", "Diane", "Uwimana", "F", "1994-12-25", "0788111207", "Huye", "reg_bdh"),
    ("1198080033445508", "Patrick", "Mugabo", "M", "1980-08-08", "0788111208", "Nyanza", "reg_bdh"),
    ("1200320044556609", "Solange", "Mutesi", "F", "2003-04-04", "0788111209", "Huye", "reg_bdh"),
    ("1197190055667710", "Olivier", "Habineza", "M", "1971-10-19", "0788111210", "Gisagara", "reg_bdh"),
]
VISITS = [  # index into PEOPLE, doctor, complaint, vitals, code, text, plan, drug
    (0, "doctor_krh", "Fever and chills for 3 days", dict(temperature_c="38.9", pulse=102, systolic=112, diastolic=70, spo2=97), "B50.9", "Malaria, unspecified", "Artemether-lumefantrine for 3 days", ("Artemether-lumefantrine", "80/480 mg", "twice daily", 3)),
    (1, "doctor_krh", "Cough and chest pain", dict(temperature_c="38.2", pulse=96, systolic=120, diastolic=78, spo2=93), "J18.9", "Pneumonia, unspecified", "Amoxicillin and review in 48 hours", ("Amoxicillin", "500 mg", "three times daily", 7)),
    (2, "doctor_krh", "Watery diarrhoea since yesterday", dict(temperature_c="37.8", pulse=118, weight_kg="19.5"), "A09", "Gastroenteritis", "Oral rehydration, zinc", ("Zinc sulphate", "20 mg", "once daily", 10)),
    (3, "doctor_krh", "Headache, high blood pressure", dict(pulse=88, systolic=168, diastolic=102), "I10", "Essential hypertension", "Start amlodipine, review in 2 weeks", ("Amlodipine", "5 mg", "once daily", 30)),
    (4, "doctor_krh", "Fever, headache", dict(temperature_c="39.4", pulse=110, systolic=108, diastolic=66), "B50.9", "Malaria, unspecified", "Artemether-lumefantrine for 3 days", ("Artemether-lumefantrine", "80/480 mg", "twice daily", 3)),
    (6, "doctor_bdh", "Fever and vomiting", dict(temperature_c="39.0", pulse=108, systolic=110, diastolic=70), "B50.9", "Malaria, unspecified", "Treat and observe", ("Artemether-lumefantrine", "80/480 mg", "twice daily", 3)),
    (7, "doctor_bdh", "Chest tightness on walking", dict(pulse=92, systolic=150, diastolic=96, spo2=96), "I10", "Essential hypertension", "Start treatment", ("Amlodipine", "5 mg", "once daily", 30)),
    (9, "doctor_bdh", "Persistent cough", dict(temperature_c="37.9", pulse=90, spo2=94), "J18.9", "Pneumonia, unspecified", "Antibiotics and chest X-ray", ("Amoxicillin", "500 mg", "three times daily", 7)),
]


def main():
    for u in ["admin", "dpo", "reg_krh", "reg_bdh", "doctor_krh", "doctor_bdh", "nurse_krh", "nurse_bdh", "pharm_krh", "lab_krh", "manager_krh", "manager_bdh"]:
        login(u)
    ids = {}
    for nid, first, last, sex, dob, phone, district, reg in PEOPLE:
        r = api(reg, "POST", "patients/", json=dict(national_id=nid, first_name=first, last_name=last, sex=sex, date_of_birth=dob, phone=phone, district=district))
        if r.status_code == 201:
            ids[nid] = r.json()["id"]
        elif r.status_code == 409:
            print("skip (already registered):", first, last)
        else:
            sys.exit(f"registration failed: {r.status_code} {r.text}")
    if not ids:
        print("Nothing new to add."); return
    api("nurse_krh", "POST", "records/allergies/", json=dict(patient_id=ids[PEOPLE[0][0]], substance="Penicillin", reaction="Skin rash", severity="SEVERE"))
    api("nurse_krh", "POST", "records/allergies/", json=dict(patient_id=ids[PEOPLE[3][0]], substance="Aspirin", reaction="Wheezing", severity="MODERATE"))
    for idx, doc, complaint, vitals, code, text, plan, drug in VISITS:
        nid = PEOPLE[idx][0]
        nurse = "nurse_krh" if doc.endswith("krh") else "nurse_bdh"
        api(nurse, "POST", "records/encounters/", json=dict(patient_id=ids[nid], encounter_type="OUTPATIENT", complaint=complaint, **vitals))
        r = api(doc, "POST", "records/encounters/", json=dict(patient_id=ids[nid], encounter_type="OUTPATIENT", complaint=complaint, diagnosis_code=code, diagnosis_text=text, plan=plan))
        enc = r.json()["id"]
        api(doc, "POST", "records/prescriptions/", json=dict(encounter=enc, drug_name=drug[0], dose=drug[1], frequency=drug[2], duration_days=drug[3]))
        if code == "B50.9":
            api(doc, "POST", "records/lab-orders/", json=dict(encounter=enc, test_name="Malaria rapid test"))
    # a few already dispensed and resulted
    pend = api("pharm_krh", "GET", "records/prescriptions/?status=PRESCRIBED").json()["results"]
    for p in pend[:2]:
        api("pharm_krh", "POST", f"records/prescriptions/{p['id']}/dispense/")
    labs = api("lab_krh", "GET", "records/lab-orders/?status=ORDERED").json()["results"]
    for o in labs[:1]:
        api("lab_krh", "POST", f"records/lab-orders/{o['id']}/result/", json=dict(result_value="Positive", result_unit="", result_flag="HIGH"))

    # transfers in different states
    for nid in (PEOPLE[1][0], PEOPLE[3][0], PEOPLE[4][0], PEOPLE[5][0]):
        api("reg_krh", "POST", "consents/", json=dict(national_id=nid))
    def request(nid, priority, reason):
        r = api("doctor_krh", "POST", "transfers/", json=dict(national_id=nid, to_hospital="BDH", priority=priority, reason=reason))
        return r.json()
    t1 = request(PEOPLE[1][0], "URGENT", "Pneumonia with low oxygen saturation, needs oxygen and inpatient care")
    t2 = request(PEOPLE[3][0], "ROUTINE", "Resistant hypertension, needs cardiology review")
    t3 = request(PEOPLE[4][0], "EMERGENCY", "Severe malaria with confusion, needs intensive care")
    for t, who, action, body in ((t1, "doctor_bdh", "accept", {}), (t3, "doctor_bdh", "accept", {})):
        cur = api(who, "GET", f"transfers/{t['id']}/").json()
        api(who, "POST", f"transfers/{t['id']}/{action}/", json=dict(version=cur["version"], **body))
    cur = api("doctor_bdh", "GET", f"transfers/{t3['id']}/").json()
    api("nurse_krh", "POST", f"transfers/{t3['id']}/in-transit/", json=dict(version=cur["version"]))
    cur = api("doctor_bdh", "GET", f"transfers/{t3['id']}/").json()
    api("nurse_bdh", "POST", f"transfers/{t3['id']}/complete/", json=dict(version=cur["version"]))
    print("Demo data created: patients, visits, medicines, lab tests and transfers in several states.")


if __name__ == "__main__":
    main()
