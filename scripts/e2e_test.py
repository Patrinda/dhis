"""End-to-end test: runs the whole hospital scenario through the gateway.

Start the system first (python run_all.py), then in another terminal:

    python scripts/e2e_test.py                 normal scenario
    python scripts/e2e_test.py --with-failure  also stops and restarts the Referral service (Linux and Mac)

Prints PASS or FAIL for each check and exits with code 1 if anything failed.
"""
import argparse
import concurrent.futures
import random
import subprocess
import sys
import time
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BASE = "http://127.0.0.1:8080/api"
PASSWORD = "Dhis@Demo2025"
INTERNAL_KEY = "dev-internal-key-change-me"
tokens, results = {}, []


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("PASS  " if condition else "FAIL  ") + name + ("" if condition else f"   -> {detail}"))
    return condition


def login(username):
    r = requests.post(f"{BASE}/auth/login/", json={"username": username, "password": PASSWORD}, timeout=10)
    r.raise_for_status()
    tokens[username] = r.json()["token"]


def api(user, method, path, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = "Bearer " + tokens[user]
    return requests.request(method, f"{BASE}/{path}", headers=headers, timeout=20, **kwargs)


def new_national_id():
    return "1" + "".join(random.choice("0123456789") for _ in range(15))


def patient_body(nid, first="Test", last="Patient"):
    return {"national_id": nid, "first_name": first, "last_name": last, "sex": "F", "date_of_birth": "1990-05-14",
            "phone": "0788123456", "district": "Gasabo"}


def wait_for(fn, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        value = fn()
        if value:
            return value
        time.sleep(0.5)
    return None


def main(with_failure):
    for u in ["admin", "dpo", "reg_krh", "nurse_krh", "doctor_krh", "pharm_krh", "lab_krh", "manager_krh",
              "reg_bdh", "nurse_bdh", "doctor_bdh", "manager_bdh"]:
        login(u)
    check("login works for every role", len(tokens) == 12)
    bad = requests.post(f"{BASE}/auth/login/", json={"username": "doctor_krh", "password": "wrong"}, timeout=10)
    check("wrong password is refused (401)", bad.status_code == 401)
    check("API without token is refused (401)", requests.get(f"{BASE}/patients/", timeout=10).status_code == 401)
    check("internal routes are not reachable through the gateway",
          api("admin", "GET", "auth/internal/hospitals/").status_code == 404)
    health = requests.get(f"{BASE}/health/", timeout=10).json()
    check("all services report healthy", all(v["up"] for v in health["services"].values()), health)

    # ---- registration, duplicates and mutual exclusion
    nid = new_national_id()
    r = api("reg_krh", "POST", "patients/", json=patient_body(nid, "Alice", "Uwase"))
    check("register a patient at KRH (201)", r.status_code == 201, r.text)
    patient = r.json()
    check("duplicate at the same hospital is refused (409)",
          api("reg_krh", "POST", "patients/", json=patient_body(nid)).status_code == 409)
    r = api("reg_bdh", "POST", "patients/", json=patient_body(nid))
    check("same person at another hospital is refused (409 duplicate_elsewhere)",
          r.status_code == 409 and r.json()["error"]["code"] == "duplicate_elsewhere", r.text)
    r = api("reg_krh", "POST", "patients/", json=patient_body("123"))
    check("invalid national ID is rejected (400)", r.status_code == 400)
    check("nurse cannot register patients (403)", api("nurse_krh", "POST", "patients/", json=patient_body(new_national_id())).status_code == 403)

    race_id = new_national_id()
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        a = pool.submit(api, "reg_krh", "POST", "patients/", json=patient_body(race_id, "Race", "One"))
        b = pool.submit(api, "reg_bdh", "POST", "patients/", json=patient_body(race_id, "Race", "Two"))
        codes = sorted([a.result().status_code, b.result().status_code])
    check("two hospitals registering the same ID at the same moment: exactly one wins", codes == [201, 409], codes)

    lk = api("reg_bdh", "POST", "patients/lookup/", json={"national_id": nid}).json()
    check("federated lookup finds the patient at KRH", lk["found_at"] == ["KRH"] and not lk["partial"], lk)

    # optimistic locking on patient update
    pid = patient["id"]
    r1 = api("reg_krh", "PATCH", f"patients/{pid}/", json={"phone": "0788000111", "version": 1})
    r2 = api("reg_krh", "PATCH", f"patients/{pid}/", json={"phone": "0788000222", "version": 1})
    check("update with an old version is refused (409)", r1.status_code == 200 and r2.status_code == 409, (r1.status_code, r2.status_code))

    # ---- clinical work
    r = api("nurse_krh", "POST", "records/encounters/", json={"patient_id": pid, "encounter_type": "OUTPATIENT", "complaint": "Fever and headache",
                                                              "temperature_c": "39.1", "pulse": 104, "systolic": 118, "diastolic": 76, "spo2": 96,
                                                              "diagnosis_code": "B50.9", "plan": "should be ignored for nurses"})
    check("nurse records triage (201), diagnosis fields are ignored", r.status_code == 201 and r.json()["diagnosis_code"] == "", r.text)
    r = api("doctor_krh", "POST", "records/encounters/", json={"patient_id": pid, "encounter_type": "OUTPATIENT", "complaint": "Fever, chills",
                                                               "temperature_c": "38.6", "pulse": 98, "diagnosis_code": "B50.9",
                                                               "diagnosis_text": "Malaria, unspecified", "plan": "Artemether-lumefantrine"})
    check("doctor records diagnosis (201)", r.status_code == 201, r.text)
    enc = r.json()
    check("invalid ICD-10 code is rejected (400)", api("doctor_krh", "POST", "records/encounters/", json={"patient_id": pid, "diagnosis_code": "hello"}).status_code == 400)
    check("bad vital signs are rejected (400)", api("nurse_krh", "POST", "records/encounters/", json={"patient_id": pid, "pulse": 900}).status_code == 400)
    check("pharmacist cannot read encounters (403)", api("pharm_krh", "GET", f"records/encounters/?patient_id={pid}").status_code == 403)
    check("BDH doctor cannot read a KRH patient's encounters (empty)", api("doctor_bdh", "GET", f"records/encounters/?patient_id={pid}").json().get("count") == 0)
    api("nurse_krh", "POST", "records/allergies/", json={"patient_id": pid, "substance": "Penicillin", "severity": "SEVERE", "reaction": "Rash"})
    r = api("doctor_krh", "POST", "records/prescriptions/", json={"encounter": enc["id"], "drug_name": "Artemether-lumefantrine", "dose": "80/480 mg", "frequency": "twice daily", "duration_days": 3})
    check("doctor prescribes (201)", r.status_code == 201, r.text)
    rx = r.json()["id"]
    check("pharmacist dispenses (200)", api("pharm_krh", "POST", f"records/prescriptions/{rx}/dispense/").status_code == 200)
    check("dispensing twice is refused (409)", api("pharm_krh", "POST", f"records/prescriptions/{rx}/dispense/").status_code == 409)
    r = api("doctor_krh", "POST", "records/lab-orders/", json={"encounter": enc["id"], "test_name": "Malaria rapid test"})
    order = r.json()["id"]
    r = api("lab_krh", "POST", f"records/lab-orders/{order}/result/", json={"result_value": "Positive", "result_flag": "HIGH"})
    check("lab technician enters a result (200)", r.status_code == 200, r.text)
    check("doctor cannot enter lab results (403)", api("doctor_krh", "POST", f"records/lab-orders/{order}/result/", json={"result_value": "x", "result_flag": "HIGH"}).status_code == 403)

    # ---- consent and transfer
    body = {"national_id": nid, "to_hospital": "BDH", "priority": "URGENT", "reason": "Needs inpatient care not available here"}
    r = api("doctor_krh", "POST", "transfers/", json=body)
    check("transfer without consent is refused (400)", r.status_code == 400 and "consent" in r.text, r.text)
    check("consent recorded by registration desk", api("reg_krh", "POST", "consents/", json={"national_id": nid}).status_code in (200, 201))
    key = uuid.uuid4().hex
    r = api("doctor_krh", "POST", "transfers/", json=body, headers={"Idempotency-Key": key})
    check("transfer request created as PENDING (201)", r.status_code == 201 and r.json()["status"] == "PENDING", r.text)
    transfer = r.json()
    r2 = api("doctor_krh", "POST", "transfers/", json=body, headers={"Idempotency-Key": key})
    check("same Idempotency-Key returns the same transfer", r2.status_code == 201 and r2.json()["id"] == transfer["id"], r2.text)
    r3 = api("doctor_krh", "POST", "transfers/", json=body)
    check("second active transfer for the same patient is refused (409)", r3.status_code == 409, r3.text)
    check("BDH sees the incoming transfer", any(t["id"] == transfer["id"] for t in api("manager_bdh", "GET", "transfers/?direction=incoming").json()["results"]))
    check("KRH nurse cannot accept (403)", api("nurse_krh", "POST", f"transfers/{transfer['id']}/accept/", json={"version": 1}).status_code == 403)

    tid = transfer["id"]
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        a = pool.submit(api, "doctor_bdh", "POST", f"transfers/{tid}/accept/", json={"version": 1})
        b = pool.submit(api, "manager_bdh", "POST", f"transfers/{tid}/reject/", json={"version": 1, "reason": "No bed available"})
        codes = sorted([a.result().status_code, b.result().status_code])
    check("two simultaneous decisions: exactly one succeeds, the other gets 409", codes == [200, 409], codes)
    current = api("doctor_bdh", "GET", f"transfers/{tid}/").json()
    if current["status"] == "REJECTED":  # make the rest of the scenario deterministic
        print("      (reject won the race; creating a second transfer to continue)")
        tid = api("doctor_krh", "POST", "transfers/", json=body).json()["id"]
        current = api("doctor_bdh", "GET", f"transfers/{tid}/").json()
        api("doctor_bdh", "POST", f"transfers/{tid}/accept/", json={"version": current["version"]})
        current = api("doctor_bdh", "GET", f"transfers/{tid}/").json()
    check("transfer is ACCEPTED", current["status"] == "ACCEPTED", current["status"])
    r = api("nurse_krh", "POST", f"transfers/{tid}/in-transit/", json={"version": current["version"]})
    check("sending nurse marks IN_TRANSIT", r.status_code == 200 and r.json()["status"] == "IN_TRANSIT", r.text)
    v = r.json()["version"]
    check("sending hospital cannot complete (403)", api("nurse_krh", "POST", f"transfers/{tid}/complete/", json={"version": v}).status_code == 403)
    r = api("nurse_bdh", "POST", f"transfers/{tid}/complete/", json={"version": v})
    check("receiving nurse completes; summary is pulled", r.status_code == 200 and r.json()["status"] == "COMPLETED", r.text)
    summary = api("doctor_bdh", "GET", f"transfers/{tid}/").json()
    cs = summary["clinical_summary"] or {}
    check("clinical summary has the allergy and the malaria diagnosis",
          any(a["substance"] == "Penicillin" for a in cs.get("allergies", [])) and any(d["code"] == "B50.9" for d in cs.get("diagnoses", [])), cs)
    check("sending hospital does not see the summary", api("doctor_krh", "GET", f"transfers/{tid}/").json()["clinical_summary"] is None)
    check("history has the full trail", len(summary["history"]) >= 4, summary["history"])
    check("completed transfer cannot be cancelled (409)", api("manager_krh", "POST", f"transfers/{tid}/cancel/", json={"version": summary["version"], "reason": "too late"}).status_code == 409)

    # ---- break glass
    r = api("doctor_bdh", "POST", "records/break-glass/", json={"national_id": nid, "reason": "short"})
    check("break-glass needs a real reason (400)", r.status_code == 400)
    r = api("doctor_bdh", "POST", "records/break-glass/", json={"national_id": nid, "reason": "Unconscious patient in emergency room, no ID papers"})
    check("break-glass returns the limited summary from KRH", r.status_code == 200 and r.json()["found"] and r.json()["summaries"][0]["source_hospital"] == "KRH", r.text)

    # ---- events: dashboard and audit (eventually consistent)
    def dashboard_ready():
        s = api("manager_krh", "GET", "dashboard/summary/").json()
        return s if s.get("transfers_by_status", {}).get("COMPLETED", 0) >= 1 and s.get("patients_registered", 0) >= 1 else None
    dash = wait_for(dashboard_ready)
    check("dashboard shows registered patients and a completed transfer", bool(dash), dash)
    check("dashboard top conditions include B50 (malaria)",
          wait_for(lambda: any(c["code"] == "B50" for c in api("manager_krh", "GET", "dashboard/conditions/").json())))
    check("doctors cannot open the dashboard (403)", api("doctor_krh", "GET", "dashboard/summary/").status_code == 403)

    import requests as rq
    msg = {"message_id": str(uuid.uuid4()), "type": "encounter.created", "version": 0, "aggregate_id": "x", "source": "test",
           "occurred_at": "2025-01-15T10:00:00+02:00", "payload": {"hospital": "KRH", "diagnosis_code": "J18.9", "encounter_type": "OUTPATIENT", "patient_ref": "abc"}}
    def count_j18():
        return next((c["count"] for c in api("admin", "GET", "dashboard/conditions/").json() if c["code"] == "J18"), 0)
    before = count_j18()
    for _ in range(2):
        rq.post("http://127.0.0.1:8004/internal/events/", json=msg, headers={"X-Internal-Key": INTERNAL_KEY}, timeout=10)
    check("the same event delivered twice is counted once", count_j18() == before + 1, (before, count_j18()))
    fake = str(uuid.uuid4())
    def transfer_event(version, status):
        return {"message_id": str(uuid.uuid4()), "type": "transfer.decided", "version": version, "aggregate_id": fake, "source": "test",
                "occurred_at": "2025-01-15T10:00:00+02:00",
                "payload": {"transfer_id": fake, "from_hospital": "KRH", "to_hospital": "BDH", "priority": "ROUTINE", "status": status,
                            "requested_at": "2025-01-15T09:00:00+02:00", "decided_at": None, "completed_at": None}}
    for ev in (transfer_event(3, "ACCEPTED"), transfer_event(2, "PENDING")):  # version 3 first, then the older version 2
        rq.post("http://127.0.0.1:8004/internal/events/", json=ev, headers={"X-Internal-Key": INTERNAL_KEY}, timeout=10)
    projections = {t["transfer_id"]: t for t in api("admin", "GET", "dashboard/transfers/").json()}
    row = (projections.get(fake) or {}).get("status"), (projections.get(fake) or {}).get("version")
    check("an older event arriving late does not overwrite a newer one", row == ("ACCEPTED", 3), row)

    log = wait_for(lambda: (lambda d: d if d["count"] > 5 else None)(api("dpo", "GET", "audit/").json()))
    check("audit log is filling from events", bool(log))
    flagged = wait_for(lambda: (lambda d: d if d["count"] >= 1 else None)(api("dpo", "GET", "audit/?flagged=1").json()))
    check("break-glass use is flagged for the DPO", bool(flagged))
    if flagged:
        seq = flagged["results"][0]["seq"]
        check("DPO reviews the flagged entry", api("dpo", "POST", f"audit/{seq}/review/", json={"outcome": "JUSTIFIED", "comment": "ER emergency"}).status_code == 200)
    check("audit chain verifies as intact", api("dpo", "GET", "audit/verify/").json()["intact"])
    check("doctors cannot read the audit log (403)", api("doctor_krh", "GET", "audit/").status_code == 403)

    if with_failure:
        failure_test()

    passed = sum(results)
    print(f"\n{passed} of {len(results)} checks passed.")
    sys.exit(0 if passed == len(results) else 1)


def failure_test():
    """Stop the Referral service, create a transfer (it must be queued), restart, and watch it sync."""
    import run_all
    print("\n--- failure demonstration: Referral service goes down ---")
    nid = new_national_id()
    api("reg_krh", "POST", "patients/", json=patient_body(nid, "Queue", "Test"))
    api("reg_krh", "POST", "consents/", json={"national_id": nid})
    subprocess.run(["pkill", "-f", "runserver 127.0.0.1:8001"])
    time.sleep(1.5)
    body = {"national_id": nid, "to_hospital": "BDH", "priority": "EMERGENCY", "reason": "Road accident, needs trauma surgery"}
    r = api("doctor_krh", "POST", "transfers/", json=body)
    check("with Referral down, the request is saved as PENDING_SYNC (202)", r.status_code == 202 and r.json()["status"] == "PENDING_SYNC", r.text)
    q = api("doctor_krh", "GET", "queue/").json()
    check("the outbound queue shows one waiting request", q["pending"] >= 1, q)
    check("reading transfers while Referral is down gives a clear 503", api("doctor_krh", "GET", "transfers/").status_code == 503)
    for name, folder, port, extra in run_all.SERVICES:
        if name == "referral":
            run_all.start(name, folder, port, extra)
            run_all.wait_ready(port)
    def synced():
        api("doctor_krh", "POST", "queue/flush/")
        mine = [t for t in api("doctor_krh", "GET", "transfers/").json().get("results", []) if t["status"] == "PENDING" and t["priority"] == "EMERGENCY"]
        return mine
    found = wait_for(synced, seconds=60)
    check("after Referral returns, the queued request becomes a real PENDING transfer", bool(found))
    q = api("doctor_krh", "GET", "queue/").json()
    check("the queue is empty again and the transfer exists exactly once", q["pending"] == 0 and len(found or []) == 1, (q["pending"], len(found or [])))
    run_all.procs.get("referral")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-failure", action="store_true")
    main(parser.parse_args().with_failure)
