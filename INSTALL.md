# VulnNotes — Install / Deploy

Deliberately vulnerable Notes API (FastAPI + SQLite) for API security training.
**Lab use only — never expose to the public internet.** Contains intentional
BOLA (API1:2023) on the by-ID note endpoints and a weak/leaked HS256 JWT secret.

## Contents

```
Dockerfile             reconstructed from the running image (python:3.12.14 base)
docker-compose.yml     one-command deploy, named volume for the SQLite DB
requirements.txt       pinned Python deps
app/                   FastAPI application (main, auth, models, schemas, database)
static/index.html      web UI
```

## Option A — Docker Compose (recommended)

```bash
cd vulnnotes-src
docker compose up -d --build
```

App is served on `http://<host>:8000`. Health check: `GET /health`.

## Option B — Plain Docker

```bash
cd vulnnotes-src
docker build -t vulnnotes:latest .
docker run -d --name vulnnotes \
  -p 8000:8000 \
  -v vulnnotes-data:/app/data \
  --restart unless-stopped \
  vulnnotes:latest
```

## Option C — Run locally without Docker

```bash
cd vulnnotes-src
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# DB defaults to /app/data/vulnnotes.db; override for a local run:
export DB_PATH=./vulnnotes.db
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## First-run data

The SQLite DB is created automatically at `DB_PATH` (default
`/app/data/vulnnotes.db`, persisted in the `vulnnotes-data` volume under Docker).
Seed the demo accounts and notes:

```bash
curl -X POST http://<host>:8000/api/seed
```

Seeded accounts (see `scripts/README.md` for the full table):

| user  | password | role  |
|-------|----------|-------|
| alice | alice123 | user  |
| bob   | bob12345 | user  |
| admin | admin123 | admin |

## Config

- `DB_PATH` — SQLite file path (default `/app/data/vulnnotes.db`).
- JWT secret is **hardcoded** in `app/auth.py` (intentional vuln); HS256.

## Notes

- No Dockerfile existed on disk on the original host (`hv-rocky-linux-1` /
  192.168.1.98); this source tree was extracted from the running
  `vulnnotes:latest` image and the Dockerfile reconstructed from its build
  history, so it reproduces the same image.
- The companion attack/traffic scripts live in the `scripts/` subdirectory
  (point them at the new host with `--base-url`).
