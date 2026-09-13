#!/usr/bin/env python3
"""
enumerate_api.py — Full API surface enumeration for VulnNotes
Works out every endpoint: unauthenticated first, then authenticated as each
seeded account. Reports status codes, what requires auth, and what data each
endpoint exposes.

Usage:
  python enumerate_api.py --base-url http://192.168.1.98:8000
"""

import argparse
import json
import sys
import time
from typing import Optional

try:
    import httpx
except ImportError:
    print("[ERROR] httpx not installed. Run:  pip install httpx")
    sys.exit(1)

# ── ANSI colours ──────────────────────────────────────────────────────────────
RED    = "\033[91m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
PURPLE = "\033[95m"
DIM    = "\033[2m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

ACCOUNTS = [
    {"username": "alice",   "password": "alice123"},
    {"username": "bob",     "password": "bob12345"},
    {"username": "charlie", "password": "charlie1"},
    {"username": "admin",   "password": "admin123"},
]

# Endpoint inventory (from app source / openapi.json)
# (method, path, auth_expected, destructive)
ENDPOINTS = [
    ("GET",    "/health",                          False, False),
    ("GET",    "/api/stats",                       False, False),
    ("GET",    "/api/notes/public/recent",         False, False),
    ("POST",   "/api/auth/login",                  False, False),
    ("GET",    "/api/users/me",                    True,  False),
    ("GET",    "/api/notes",                       True,  False),
    ("GET",    "/api/notes/1",                     True,  False),
    ("POST",   "/api/notes",                       True,  False),
    ("PUT",    "/api/notes/1",                     True,  True),
    ("DELETE", "/api/notes/1",                     True,  True),
    ("POST",   "/api/auth/register",               False, True),
    ("POST",   "/api/seed",                        False, True),
]

META_ENDPOINTS = [
    ("GET", "/"),
    ("GET", "/docs"),
    ("GET", "/redoc"),
    ("GET", "/openapi.json"),
]


def ok(msg):   print(f"  {GREEN}[✓]{RESET} {msg}")
def fail(msg): print(f"  {RED}[✗]{RESET} {msg}")
def info(msg): print(f"  {CYAN}[i]{RESET} {msg}")
def warn(msg): print(f"  {YELLOW}[!]{RESET} {msg}")
def step(msg): print(f"\n{BOLD}{PURPLE}── {msg}{RESET}")


def login(client: httpx.Client, username: str, password: str) -> Optional[str]:
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    if r.status_code == 200:
        return r.json()["access_token"]
    return None


def main():
    parser = argparse.ArgumentParser(description="VulnNotes full API enumeration")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--include-destructive", action="store_true",
                        help="also probe mutating endpoints with a live account (creates/deletes a throwaway note)")
    args = parser.parse_args()

    print(f"""
{CYAN}{BOLD}╔═══════════════════════════════════════════════════╗
║   VulnNotes — API Surface Enumeration             ║
║   FOR SECURITY TRAINING AND LAB USE ONLY          ║
╚═══════════════════════════════════════════════════╝{RESET}
{DIM}Target: {args.base_url}{RESET}
""")

    with httpx.Client(base_url=args.base_url, timeout=10, follow_redirects=True) as client:
        # ── Phase 0: metadata ─────────────────────────────────────────────────
        step("Phase 0 — Metadata / discovery endpoints")
        for method, path in META_ENDPOINTS:
            try:
                r = client.request(method, path)
                body = r.text if "html" in r.headers.get("content-type", "") else None
                extra = ""
                if path == "/openapi.json":
                    spec = r.json()
                    n_paths = len(spec.get("paths", {}))
                    extra = f" — {spec['info'].get('title')} v{spec['info'].get('version')} — {n_paths} paths"
                status = f"{GREEN}{r.status_code}{RESET}" if r.status_code < 400 else f"{YELLOW}{r.status_code}{RESET}"
                print(f"  {method:<4} {path:<28} {status} {DIM}{extra}{RESET}")
            except Exception as e:
                print(f"  {method:<4} {path:<28} {RED}ERR{RESET} {e}")

        # ── Phase 1: unauthenticated probes ───────────────────────────────────
        step("Phase 1 — Unauthenticated probes (auth required or not?)")
        print(f"  {'METHOD':<7} {'PATH':<28} {'STATUS':<8} {'VERDICT'}")
        print(f"  {'─'*7} {'─'*28} {'─'*8} {'─'*15}")
        open_endpoints = 0
        for method, path, needs_auth, _destructive in ENDPOINTS:
            if method == "POST" and path == "/api/auth/login":
                r = client.post(path, data={"username": "probe_user", "password": "wrong"})
                code = r.status_code
            elif method == "POST" and path == "/api/notes":
                r = client.post(path, json={"title": "x", "content": "x"})
                code = r.status_code
            elif method == "POST" and path == "/api/auth/register":
                # use an EXISTING username → 400 without creating anything
                r = client.post(path, json={"username": "alice", "password": "x", "email": "a@x.test"})
                code = r.status_code
            elif method in ("PUT", "DELETE") or (method == "POST" and path == "/api/seed"):
                continue  # skip destructive probes unauthenticated
            else:
                r = client.request(method, path)
                code = r.status_code
            if code in (401, 403):
                verdict = f"{YELLOW}auth required{RESET}"
            elif code < 400:
                verdict = f"{RED}{BOLD}OPEN — no auth{RESET}"
                open_endpoints += 1
            elif code == 404:
                verdict = f"{DIM}not found{RESET}"
            else:
                verdict = f"{YELLOW}{code}{RESET}"
            print(f"  {method:<7} {path:<28} {code:<8} {verdict}")
            time.sleep(0.05)
        if open_endpoints:
            warn(f"{open_endpoints} endpoint(s) respond without authentication")
        else:
            ok("All probed endpoints enforce some auth (401/403)")

        # ── Phase 2: authenticated probes per account ─────────────────────────
        step("Phase 2 — Authenticated probes (per seeded account)")
        for acct in ACCOUNTS:
            u = acct["username"]
            token = login(client, u, acct["password"])
            if not token:
                print(f"  {u}: {RED}login failed{RESET}")
                continue
            r = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
            me = r.json() if r.status_code == 200 else {}
            info(f"{u} (id={me.get('id')} admin={me.get('is_admin')}) — probing authenticated endpoints")

            results = []
            for method, path, _a, _d in ENDPOINTS:
                if path in ("/api/auth/login", "/api/auth/register", "/api/seed"):
                    continue
                if method == "GET" and path == "/api/notes/1":
                    r = client.get(path, headers={"Authorization": f"Bearer {token}"})
                    code = r.status_code
                    owner = r.json().get("owner_id") if code == 200 else None
                    cross = f"{RED}owner={owner} ≠ {me.get('id')} (BOLA){RESET}" if owner and owner != me.get("id") else f"owner={owner}"
                    results.append((method, path, code, cross))
                elif method == "POST" and path == "/api/notes":
                    r = client.post(path, headers={"Authorization": f"Bearer {token}"},
                                    json={"title": f"probe-{u}", "content": "enumeration probe"})
                    results.append((method, path, r.status_code, ""))
                    if r.status_code == 201 and args.include_destructive:
                        nid = r.json()["id"]
                        rd = client.delete(f"/api/notes/{nid}", headers={"Authorization": f"Bearer {token}"})
                        results.append(("DELETE", f"/api/notes/{nid} (cleanup)", rd.status_code, ""))
                elif method in ("PUT", "DELETE"):
                    continue  # destructive — left to exploit scripts
                else:
                    r = client.request(method, path, headers={"Authorization": f"Bearer {token}"})
                    results.append((method, path, r.status_code, ""))
                time.sleep(0.05)

            for method, path, code, extra in results:
                mark = f"{GREEN}{code}{RESET}" if code < 400 else f"{YELLOW}{code}{RESET}"
                print(f"    {method:<7} {path:<30} {mark}  {extra}")

    step("Enumeration complete")
    warn("Open endpoints + BOLA cross-user reads are the detection targets for Active Testing.")


if __name__ == "__main__":
    main()
