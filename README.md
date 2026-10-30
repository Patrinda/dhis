# DHIS: Distributed Hospital Information System

DHIS lets hospitals keep their own patient records while safely **transferring patients between hospitals**.
A patient is registered once in the whole country, a doctor requests a transfer, the receiving hospital accepts or
rejects it, and a short clinical summary is shared only after acceptance and with the patient's consent.

It is the practical project for the Distributed Systems module. Every distributed-systems idea from the module
that applies to the project is built in and tested, and the Learning Guide explains each one in plain words.

## What the system does

| Area | What users can do |
| --- | --- |
| Registration | Register a patient. The system checks every hospital first and blocks duplicates, even when two hospitals try at the same moment. |
| Clinical work | Nurses record triage and vital signs. Doctors record diagnoses (ICD-10 codes), allergies, prescriptions and lab orders. Pharmacists dispense. Lab technicians enter results. |
| Transfers | Eight-state workflow: waiting for decision, accepted, rejected, cancelled, expired, in transit, completed, and not yet sent (saved while the transfer service is down). |
| Consent | Registration staff record the patient's consent before a transfer can be requested. |
| Emergency access | A doctor can open a short summary of a patient from another hospital by writing a reason. Every use is flagged and reviewed by the data protection officer. |
| Overview | Managers see live figures for their hospital. Administrators see all hospitals. |
| Audit | A tamper-evident log of who did what. It can be checked for changes with one click. |

## How it is built

Seven small Django services, each with its own database, behind one gateway.

| Service | Port | Folder | Owns |
| --- | --- | --- | --- |
| Gateway and web pages | 8080 | `services/gateway` | Checks tokens, routes requests, saves transfer requests when the transfer service is down, serves the web pages |
| Identity | 8003 | `services/identity` | Users, roles, hospitals, signing of login tokens, national ID claims |
| Patient (one per hospital) | 8000 and 9000 | `services/patient` | Patient registration, federated lookup |
| Records (one per hospital) | 8002 and 9002 | `services/records` | Visits, allergies, prescriptions, lab orders, emergency access |
| Referral | 8001 | `services/referral` | Transfers, the state machine, history, expiry job |
| Dashboard | 8004 | `services/dashboard` | Figures built from events |
| Audit and consent | 8005 | `services/audit` | Audit log with hash chain, consent register |

Shared code used by all services is in `shared/dhis_common`. The web pages are in `frontend`.
Services talk in two ways: direct calls with time-outs and a circuit breaker, and events (RabbitMQ, or plain HTTP when running locally).

## Requirements

- Python 3.12 or newer (tested with 3.13)
- Git
- Packages in `requirements.txt`: Django, Django REST framework, PyJWT, cryptography, requests, pika, gunicorn, psycopg2-binary
- Optional: Docker Desktop, to run PostgreSQL and RabbitMQ the way a real deployment would

Node.js is **not** needed. The front end has no build step.

## Run it on your computer

```
python -m venv venv
venv\Scripts\activate          (Windows)   |   source venv/bin/activate   (Mac and Linux)
pip install -r requirements.txt
python run_all.py
```

The first run creates the signing keys, the databases and the demo users. When the banner says the system is
ready, open <http://127.0.0.1:8080>. Use `python run_all.py --reset` to start again from empty databases.
Then fill it with demonstration data in a second terminal:

```
python scripts/seed_demo.py
```

### Demo accounts

All demo accounts use the password `Dhis@Demo2025`. These are for training only. Delete them before any real use.

| Username | Role | Hospital |
| --- | --- | --- |
| `doctor_krh`, `nurse_krh`, `reg_krh`, `pharm_krh`, `lab_krh`, `manager_krh` | Doctor, nurse, registration, pharmacist, lab technician, manager | Kigali (KRH) |
| `doctor_bdh`, `nurse_bdh`, `reg_bdh`, `pharm_bdh`, `lab_bdh`, `manager_bdh` | The same roles | Butare (BDH) |
| `dpo` | Data protection officer | National |
| `admin` | System administrator | National |

## Run it with Docker (PostgreSQL and RabbitMQ)

```
copy .env.example .env         (Mac and Linux: cp .env.example .env)
docker compose up --build
```

Open <http://localhost:8080>. Edit `.env` first and change every secret.

## Tests

```
python scripts/setup_dev.py                       one time: keys and databases
python services/identity/manage.py test dhis_common accounts
python services/patient/manage.py test patients
python services/records/manage.py test clinical
python services/referral/manage.py test transfers
python services/dashboard/manage.py test metrics
python services/audit/manage.py test ledger
python scripts/e2e_test.py                        needs python run_all.py running; 52 checks through the gateway
python scripts/e2e_test.py --with-failure         57 checks: also stops and restarts the transfer service (Mac and Linux)
```

## Team roles and folders

Each person owns separate folders, so pull requests never conflict.

| Member | Role in the team | Owns |
| --- | --- | --- |
| Ndacyayisenga Patrick | Team lead and repository owner | `shared/`, `services/gateway/`, `frontend/` core and styles, `scripts/`, `docker/`, root files |
| Uwikuzo Theopiste | Identity and access | `services/identity/`, `frontend/js/pages/login.js`, `frontend/js/pages/admin.js` |
| Mukeshimana Justine | Patients | `services/patient/`, `frontend/js/pages/patients.js` |
| Masengesho Donatien | Clinical records | `services/records/`, `frontend/js/pages/records.js` |
| Mudahogora Justine | Transfers | `services/referral/`, `frontend/js/pages/transfers.js` |
| John Seemore | Dashboard and audit | `services/dashboard/`, `services/audit/`, `frontend/js/pages/dashboard.js`, `frontend/js/pages/audit.js` |

### Working agreement

- Never commit to `main` directly. Work on your own branch, push it, and open a pull request.
- Pull before you start each work session: `git pull`.
- Touch only your own folders. If you need a change elsewhere, ask the owner of that folder.
- Never commit `.env`, `keys/`, `data/` or database files. The `.gitignore` already blocks them.
- Commit messages say what changed, for example `patients: add federated lookup`.

## Security design in short

- Login tokens are signed with RS256. Only the Identity service holds the private key. Every other service verifies tokens with the public key.
- Eight roles control every endpoint. Nurses cannot diagnose, pharmacists cannot read visits, and so on.
- Five wrong passwords lock an account for 15 minutes. The gateway also limits failed sign-ins per address.
- National IDs are hashed with a secret salt in the claim table, the consent register and events. Events never carry names.
- Internal service routes need a shared secret and are blocked at the gateway.
- The audit log is append-only and every line carries the fingerprint of the one before.
- Production still needs HTTPS in front of the gateway, a secrets manager, and removal of the demo accounts.

## What is and is not built

Built and tested: everything in the tables above, plus idempotent writes, the transactional outbox, duplicate and
out-of-order event handling, optimistic locking, the circuit breaker, the saved-request queue, and a dashboard that can be
rebuilt from events.

Explained in the Learning Guide but not coded (they belong to a production deployment, not to a student prototype):
database replicas with automatic fail-over, Raft or Paxos based consensus (RabbitMQ quorum queues and Patroni are the real-world tools),
HTTPS termination, appointments, bed management, e-mail and SMS notifications, password reset and two-factor sign-in.

RabbitMQ and Docker are included and configured, but they were **not run** while this project was built, because the
build environment has neither. Everything else, including PostgreSQL, was run: the full 57-check scenario passes on both SQLite and PostgreSQL.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `python` is not recognised | On Mac and Linux use `python3`. On Windows reinstall Python and tick Add to PATH. |
| Port already in use | Another copy is running. Stop it with Ctrl+C, or close the terminal. |
| A service did not start | Open `data/<service>.log`. The last lines say why. |
| Sign-in says wrong password for a demo user | Run `python run_all.py --reset` to rebuild the demo users. |
| `Missing the public key` | Run `python scripts/setup_dev.py`. |

## Credits

Chart.js (MIT), Bootstrap Icons (MIT), Raleway and Source Sans 3 (SIL Open Font License). Licence files are in `frontend/vendor`.
