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

## Vulnerable / fixed variants

- `variants/vulnerable/` (+ `vnotes-vulnerable.tar.gz`): original intentionally vulnerable app.
- `variants/fixed/` (+ `vnotes-fixed.tar.gz`): auth-compatible fix — ownership checks on
  `/api/notes/{id}` (BOLA), random persisted JWT secret, restricted CORS, security headers, redacted public feed.
  Login/register/JWT behaviour is unchanged so Active Testing's dynamic auth still works.
- `variants/fixed-strict/`: stricter build (also random JWT secret, register password policy,
  login throttling). **Breaks Active Testing's dynamic-auth registration** (weak generated
  passwords get 422), so it is not deployed.

Seeded accounts/passwords are identical in all. Swap with `./switch-variant.sh vulnerable|fixed|fixed-strict`;
`app/` currently holds the **fixed** build.
