# VNotes

A deliberately **vulnerable** Notes API (FastAPI + SQLite) for API security
training and tooling demos.

> ⚠️ **WARNING — intentionally insecure. For lab/training use only.**
> This app ships with a **hardcoded JWT secret**, **default credentials**, and
> a **BOLA** (Broken Object Level Authorization, API1:2023) flaw on the by-ID
> note endpoints — all on purpose. **Do not deploy on a public/production
> network, and never reuse any of its code or secrets in real software.**

## What's here

| Path | Purpose |
|------|---------|
| `app/` | FastAPI application (auth, notes CRUD, seed) |
| `static/index.html` | Web UI |
| `Dockerfile`, `docker-compose.yml` | Container build/deploy |
| `requirements.txt` | App dependencies |
| `INSTALL.md` | Full install / deploy instructions |
| `scripts/` | Baseline traffic + attack scripts (enumeration, default-creds, JWT, BOLA read/write/delete) |

## Quick start

```bash
docker compose up -d --build          # serves http://localhost:8000
curl -X POST http://localhost:8000/api/seed   # seed demo accounts + notes
```

See [`INSTALL.md`](INSTALL.md) for non-Docker options and configuration, and
[`scripts/README.md`](scripts/README.md) for the traffic/attack tooling.

## Intentional vulnerabilities

- **BOLA (API1:2023):** `GET/PUT/DELETE /api/notes/{id}` return/modify any
  note regardless of owner.
- **Weak JWT:** HS256 with a hardcoded, leaked secret in `app/auth.py`.
- **Default credentials:** seeded accounts (`alice`/`alice123`,
  `admin`/`admin123`, etc.).
