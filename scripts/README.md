# VNotes Lab Scripts

Scripts for the deliberately vulnerable **VNotes API** (FastAPI + SQLite,
BOLA on by-ID note endpoints + weak hardcoded JWT secret). Security training
lab only — point at your own lab instance.

Default target: `http://192.168.1.98:8000` (container `vnotes`)

## Seeded accounts (from `POST /api/seed`)

| user    | password | role  |
|---------|----------|-------|
| alice   | alice123 | user  |
| bob     | bob12345 | user  |
| charlie | charlie1 | user  |
| admin   | admin123 | admin |

JWT secret (leaked in `app/auth.py`): `vnotes-weak-secret-for-lab-only-do-not-use-in-prod` (HS256)

## Scripts

| Script | Purpose |
|--------|---------|
| `normal_traffic.py` | **Baseline** — concurrent legitimate user journeys so the sensor learns normal behaviour |
| `enumerate_api.py` | **Enumeration** — works out every endpoint: unauth probes, then per-account authed probes |
| `exploit_default_creds.py` | **Attack** — verify which seeded default credentials are live + admin impact |
| `exploit_jwt.py` | **Attack** — decode tokens, alg=none, HS256 forgery with leaked secret, 10-yr tokens, admin takeover |
| `exploit_bola.py` | **Attack** — BOLA read + write (Bob reads/overwrites Alice's note), `--aggressive` ID enumeration |
| `exploit_bola_delete.py` | **Attack** — BOLA delete; `--aggressive --yes` wipes a victim's notes (destructive) |
| `run_all.sh` | **Runner** — baseline → enumeration → attacks, logs to `/var/log/notes-scripts.log` |

## Usage

```bash
pip install -r requirements.txt

# 1. baseline traffic (learning period)
python3 normal_traffic.py --base-url http://192.168.1.98:8000 --duration 120

# 2. enumerate the full API surface
python3 enumerate_api.py --base-url http://192.168.1.98:8000

# 3. attacks
python3 exploit_default_creds.py --base-url http://192.168.1.98:8000
python3 exploit_jwt.py           --base-url http://192.168.1.98:8000
python3 exploit_bola.py          --base-url http://192.168.1.98:8000 --aggressive
python3 exploit_bola_delete.py   --base-url http://192.168.1.98:8000

# or everything in one shot
./run_all.sh http://192.168.1.98:8000
```

## API reference (12 endpoints)

| method | path | auth | note |
|--------|------|------|------|
| GET    | /health | – | |
| GET    | /api/stats | – | open |
| GET    | /api/notes/public/recent | – | open |
| POST   | /api/auth/register | – | open |
| POST   | /api/auth/login | – | form-encoded → `access_token` |
| GET    | /api/users/me | Bearer | |
| GET    | /api/notes | Bearer | own notes only |
| POST   | /api/notes | Bearer | |
| GET    | /api/notes/{id} | Bearer | **BOLA** — any note |
| PUT    | /api/notes/{id} | Bearer | **BOLA** — any note |
| DELETE | /api/notes/{id} | Bearer | **BOLA** — any note |
| POST   | /api/seed | – | re-seed demo data |
