# Akamai Active Testing – Jenkins Integration Setup Guide

Updated Oct 6, 2026 · @Mike — revised after a live incident (see "Lessons from a real outage" at the bottom) that the original version of this guide didn't anticipate.

## Overview

A Jenkins pipeline pulls the `active-cli` scanner image from an Akamai/Noname-owned Google Artifact Registry, mints a short-lived API token from a service account, and runs an Active Testing scan against your app. Three secrets make this work, and all three live only in Jenkins Credentials, never in Git.

| Component | Value in this lab | Role |
| --- | --- | --- |
| API Security tenant | `https://michaelc-lab.nonamesec.com` | Issues service accounts and tokens; hosts Active Testing |
| Active Testing app | `ACTIVE_APP_ID` from CI/CD Parameters | The app the scans report into |
| Jenkins | `192.168.1.100` (public: `jenkins.cropseyit.com`) | Runs the pipeline; stores the three credentials |
| Git repo | Your repo's `Jenkinsfile` | Pipeline definition; non-secret values only |
| Artifact Registry | `us-central1-docker.pkg.dev/noname-artifacts/nns-docker` | Hosts the `active-cli` image. **This is Akamai/Noname's own GCP project, not the customer's** — see the callout in Step 5. |

The order of operations at runtime: log in to the registry, pull `active-cli`, exchange Client ID + Secret for an access token, run the scan.

## Prerequisites

- [ ] Admin access to the API Security tenant (to create service accounts)
- [ ] An Active Testing application and environment already created
- [ ] Jenkins admin access, with the Credentials and Pipeline plugins installed
- [ ] Docker installed on the Jenkins agent that runs the scan stage
- [ ] `curl` on that agent (for minting the token and checking versions)
- [ ] Write access to the Git repo that holds the `Jenkinsfile`

## Step 1: Create a service account

The service account's Client ID and Client Secret are what the pipeline uses to get an API token. The secret is shown only once.

1. In the API Security UI, go to **Service Accounts** and create a new one (or regenerate on an existing one).
2. The **Service Account Credentials** dialog shows the **Client ID** and **Client Secret**.
3. Copy both immediately with the copy buttons. The secret field scrolls horizontally — don't select it by hand.
4. **Regenerate ID and secret together, in the same action, and copy both in the same sitting.** A Client ID only works with the secret generated for that same account; mixing an old ID with a new secret returns `400 Bad Request` with no further detail — this cost real debugging time (see incident log below).

If the secret is lost, regenerate it on the Service Accounts page rather than trying to recover it from anywhere else.

## Step 2: Verify the credentials with curl — do this before touching Jenkins

This step is not optional. It's the fastest way to tell "bad pair" apart from "pipeline bug," and we proved that distinction matters.

```bash
curl --location 'https://michaelc-lab.nonamesec.com/auth/token' \
  --header 'Content-Type: application/json' \
  --data '{"client_id":"<CLIENT_ID>","client_secret":"<CLIENT_SECRET>"}'
```

A good pair returns:
```json
{"accessToken":"eyJhbGciOiJSUzI1NiIs..."}
```

**Gotcha:** this endpoint returns HTTP `201 Created` on success, not `200 OK`. If you write any diagnostic code that checks the status code instead of just checking for the presence of `accessToken`, check for `201`, or better, don't gate on a status code at all — judge success by whether you got a token.

A `{"statusCode":400,"message":"Bad Request"}` response means the ID and secret don't belong together, or one was copied incompletely. Regenerate both together (Step 1) and retest — don't try to fix this in Jenkins, fix it here first.

## Step 3: Collect the CI/CD Parameters

In Active Testing, open your application and click **Settings → CI/CD → CI/CD Parameters**. Copy each value with its copy button.

| Parameter | Where it goes |
| --- | --- |
| `ACTIVE_APP_ID` | Not used by this pipeline (it uses env ID + test group ID instead). Check `active-cli --help` for your version before adding it. |
| `ACTIVE_REGISTRY_USER` | `Jenkinsfile` environment block (non-secret) — typically `_json_key_base64` |
| `ACTIVE_REGISTRY_PASSWORD` | Jenkins credential `active-registry-key` only. Never in Git. Always use the copy button — it's truncated on screen. |
| `ACTIVE_REGISTRY_URL` | `Jenkinsfile` environment block (non-secret) |
| `ACTIVE_API_TOKEN` / "Generate Token" | Skip this. It's an alternate setup path (a static long-lived token) that duplicates what Step 1+6 already do via the client-credentials exchange. Don't configure both. |

**This panel is a static display, not a live credential source.** It shows you whatever value was last configured — it does not self-update if the underlying credential is rotated or dies on the backend. Don't treat "the panel still shows the same value" as proof the credential is still valid; it only proves nobody's changed what the panel displays. The only real test is Step 2's curl call (for the client id/secret) or the registry diagnostic in Step 7 (for the registry password).

## Step 4: Scan Configuration and the generated Jenkinsfile

The Scan Configuration dialog produces a starter `Jenkinsfile` with your environment's IDs filled in. Use it as a source of IDs, not as the file you commit — it embeds secrets in plaintext and may show placeholder networking that doesn't apply outside the vendor's own infrastructure.

1. On the Active Testing integration, click the settings icon to open **Edit Scan Configuration**.
2. Under **Service Account Token**, paste the `accessToken` from Step 2.
3. Choose a **Test Profile**, adjust Scan Control / Network & Performance / Logging as needed.
4. Click **Save & View Configuration**. A **Jenkinsfile** snippet appears.
5. From the snippet, copy only the non-secret values: `ENV_ID`, `TEST_GROUP_ID`, `ACTIVE_API_URL`, `ACTIVE_BACKEND_URI`, `ACTIVE_REGISTRY_URL`, `ACTIVE_REGISTRY_USER`.

**Known issue:** the generated snippet can show `ACTIVE_API_URL`/`ACTIVE_BACKEND_URI` as something like `https://nginx:tcp://172.20.130.158:80` — an internal container-network address from inside the vendor's own infrastructure, not reachable from your Jenkins host. If you see this, use the tenant's actual public URL instead (e.g. `https://<your-tenant>.nonamesec.com/active` and `.../active/backend`) — don't paste the generated value verbatim.

## Step 5: Store the three Jenkins credentials

In Jenkins: **Manage Jenkins → Credentials → System → Global credentials → Add Credentials**. Create each as kind **Secret text**, scope **Global**.

| Credential ID | Secret value | Description |
| --- | --- | --- |
| `active-registry-key` | `ACTIVE_REGISTRY_PASSWORD` from Step 3 | Akamai Active Testing - artifact registry key (`_json_key_base64`) |
| `active-cli-client-id` | Client ID from Step 1 | Service account client id |
| `active-cli-secret` | Client Secret from Step 1 | Service account client secret |

To rotate a value later, click the pencil icon on the credential, paste the new value into **Secret**, **Save**. Keep the ID unchanged so the `Jenkinsfile` still finds it.

> **⚠️ If you are a customer, not Akamai/Noname staff: you almost certainly cannot self-service rotate `active-registry-key`.**
> `us-central1-docker.pkg.dev/noname-artifacts/nns-docker` is Akamai/Noname's own GCP project, used to distribute the `active-cli` image to every customer. You will not have IAM/console access to it. **Do not go looking for a GCP console for this** — that's a dead end we burned real time on. If this credential dies (see Step 7), it needs to be reissued by whoever internally administers that project, not by the customer.
>
> **If you *are* internal Akamai/Noname staff with access to that project:** the credential is a base64-encoded GCP service-account JSON key (`ACTIVE_REGISTRY_USER=_json_key_base64` is Google's own documented convention for this). To check whether a specific key is dead: decode the current `ACTIVE_REGISTRY_PASSWORD` (`base64 -d | jq -r '.client_email, .private_key_id'`) and check, in GCP Console → IAM & Admin → Service Accounts → that account → **Keys** tab, whether a key with that `private_key_id` is still listed as active. If it's gone, the key was deleted — generate a new one, base64-encode it, and update `active-registry-key`.

You do not need a Jenkins user API token (Account → Security → API Token) for the pipeline itself. That's only for calling the Jenkins API remotely (e.g. for automated build-triggering/log-reading); delete it when nothing needs it, since it's set to never expire by default.

## Step 6: Commit a sanitized Jenkinsfile

The committed file holds IDs and URLs only; every secret is bound at runtime with `withCredentials`.

```groovy
pipeline {
    agent any

    environment {
        // Non-secret identifiers
        ACTIVE_REGISTRY_URL  = 'us-central1-docker.pkg.dev/noname-artifacts/nns-docker'
        ACTIVE_REGISTRY_USER = '_json_key_base64'
        ACTIVE_API_URL       = 'https://<your-tenant>.nonamesec.com/active'
        ACTIVE_BACKEND_URI   = 'https://<your-tenant>.nonamesec.com/active/backend'
        ACTIVE_TOKEN_URL     = 'https://<your-tenant>.nonamesec.com/auth/token'
        ENV_ID               = '<ENV_ID from Step 4>'
        TEST_GROUP_ID         = '<TEST_GROUP_ID from Step 4>'

        // Last active-cli tag known to exist in the registry. The backend's
        // reported /version can briefly (or permanently, if the registry
        // credential dies) outpace what's actually pullable -- fall back to
        // this rather than hard-failing the whole pipeline.
        FALLBACK_CLI_VERSION = '3.71.0'

        APP_VERSION = "${(env.BRANCH_NAME ?: env.GIT_BRANCH ?: 'main').replaceAll('^origin/', '')}"
    }

    stages {
        stage('Active Scan') {
            steps {
                withCredentials([
                    string(credentialsId: 'active-registry-key',  variable: 'ACTIVE_REGISTRY_PASSWORD'),
                    string(credentialsId: 'active-cli-client-id', variable: 'SA_CLIENT_ID'),
                    string(credentialsId: 'active-cli-secret',    variable: 'SA_CLIENT_SECRET'),
                ]) {
                    // Leading shebang stops Jenkins injecting `-x`, so the minted
                    // bearer token is never echoed to the console log.
                    //
                    // GOTCHA: this is a Groovy TRIPLE-SINGLE-QUOTED string. Groovy still
                    // applies its own backslash-escape processing to it, not just the
                    // shell's -- an unrecognized escape like `\(` fails PIPELINE
                    // COMPILATION outright ("unexpected char: '\'"), before the shell
                    // ever runs. Any sed/grep pattern with backslashes in here needs
                    // them doubled (`\\(`, `\\)`, `\\1`), not single.
                    sh '''#!/bin/bash
                        set -euo pipefail

                        CLI_VERSION="$(curl -fsS --max-time 30 "$ACTIVE_BACKEND_URI/version" | tr -d '[:space:]')"
                        case "$CLI_VERSION" in
                            ''|*[!0-9.]*) echo "Unexpected /version response: '$CLI_VERSION'"; exit 1 ;;
                        esac
                        echo "Using active-cli:$CLI_VERSION"

                        # Exchange client id/secret for a short-lived API token.
                        # No -f on this curl: on failure we want the auth server's error
                        # body (never contains our secrets, only its own error text)
                        # printed to the log instead of curl silently swallowing it.
                        TOKEN_RESPONSE="$(
                            printf '{"grant_type":"client_credentials","client_id":"%s","client_secret":"%s"}' \
                                "$SA_CLIENT_ID" "$SA_CLIENT_SECRET" \
                            | curl -sS --max-time 30 -w '\n%{http_code}' -X POST "$ACTIVE_TOKEN_URL" \
                                -H 'Content-Type: application/json' --data-binary @-
                        )"
                        TOKEN_HTTP_CODE="$(echo "$TOKEN_RESPONSE" | tail -n1)"
                        TOKEN_BODY="$(echo "$TOKEN_RESPONSE" | sed '$d')"
                        # Judge success by "did we get an accessToken", NOT a specific
                        # status code -- this endpoint returns 201 on success, not 200.
                        ACTIVE_API_TOKEN="$(echo "$TOKEN_BODY" | sed -n 's/.*"accessToken"[[:space:]]*:[[:space:]]*"\\([^"]*\\)".*/\\1/p')"
                        if [ -z "$ACTIVE_API_TOKEN" ]; then
                            echo "Could not obtain an accessToken from $ACTIVE_TOKEN_URL (HTTP $TOKEN_HTTP_CODE): $TOKEN_BODY" >&2
                            exit 1
                        fi
                        export ACTIVE_API_TOKEN
                        echo "Obtained Active Testing API token."

                        mkdir -p "$WORKSPACE/akamai"

                        # Resilience: if we already have a known-good tag cached locally
                        # (e.g. from before a registry credential died), use it directly
                        # and skip the registry entirely. `docker run` only hits the
                        # network when the image isn't already present. See "Lessons
                        # from a real outage" below for why this exists.
                        FALLBACK_IMAGE="$ACTIVE_REGISTRY_URL/active-cli:$FALLBACK_CLI_VERSION"
                        if docker image inspect "$FALLBACK_IMAGE" >/dev/null 2>&1; then
                            echo "Using locally cached $FALLBACK_IMAGE"
                            ACTIVE_CLI_IMAGE="$FALLBACK_IMAGE"
                        else
                            # docker login wants the registry HOST only, not the repo path.
                            # (We tested host-only vs. full-path login head to head during
                            # a real incident -- it made no difference to a dead-credential
                            # failure either way, but host-only matches Google's own
                            # documented GAR convention, so keep it.)
                            ACTIVE_REGISTRY_HOST="${ACTIVE_REGISTRY_URL%%/*}"
                            echo "$ACTIVE_REGISTRY_PASSWORD" \
                              | docker login "https://$ACTIVE_REGISTRY_HOST" -u "$ACTIVE_REGISTRY_USER" --password-stdin

                            ACTIVE_CLI_IMAGE="$ACTIVE_REGISTRY_URL/active-cli:$CLI_VERSION"
                            if ! docker pull "$ACTIVE_CLI_IMAGE"; then
                                echo "WARNING: $ACTIVE_CLI_IMAGE not available; falling back to $FALLBACK_CLI_VERSION" >&2
                                ACTIVE_CLI_IMAGE="$FALLBACK_IMAGE"
                                docker pull "$ACTIVE_CLI_IMAGE"
                            fi
                        fi

                        docker run --rm \
                          -e ACTIVE_BACKEND_URI \
                          -e ACTIVE_API_TOKEN \
                          -v "$WORKSPACE/akamai:/akamai" \
                          "$ACTIVE_CLI_IMAGE" \
                          scan \
                            --api-url="$ACTIVE_API_URL" \
                            --env-id="$ENV_ID" \
                            --test-group-id="$TEST_GROUP_ID" \
                            --app-version="$APP_VERSION" \
                            --verbose
                    '''
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'akamai/**', allowEmptyArchive: true
            sh 'docker logout "$ACTIVE_REGISTRY_URL" || true'
        }
    }
}
```

Commit and push; Jenkins reads the `Jenkinsfile` from Git on the next build.

## Step 7: Diagnose a registry failure fast

If you see `unauthorized: authentication required` or `name unknown: authentication failed` from `docker login`/`docker pull`, don't assume it's the credential until you've ruled out the cheap explanations first, in this order:

1. **Re-copy the credential.** Use the copy button in CI/CD Parameters, not manual selection of the (truncated) on-screen text.
2. **Verify it isn't a stale/mixed pair** — this error message is generic enough to also show up for client id/secret problems in some pipeline designs; don't assume it's specifically the registry password just because that's what's in the error text.
3. **Check if it's actually dead at the source**, not a pipeline bug:
   - For Akamai/Noname staff: decode the key and check its `private_key_id` against the GCP service account's Keys tab (see the callout in Step 5).
   - For everyone else: there's no self-service way to check this directly — if steps 1-2 don't fix it, it needs internal escalation, not more Jenkinsfile changes.
4. **If the credential is confirmed dead and reissuing it isn't immediately possible**, use the local-image-cache fallback in Step 6's Jenkinsfile — it keeps the pipeline running on whatever tag was last successfully pulled, until the credential is actually fixed. This is a stopgap, not a fix: it stops working the moment the cache is gone (new agent, pruned images, etc.), and it can't pick up a newer `active-cli` version until the registry works again.

## Step 8: Run and verify

A healthy build (with a working registry credential) shows, in order:
1. `Obtained Active Testing API token.`
2. Either `Using locally cached ...` or a clean `docker login`/`docker pull`.
3. The `active-cli` container starts without `unauthorized`/`name unknown` errors.
4. `Scan completed successfully!` and a new scan appears under the application in Active Testing.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `/auth/token` returns `400 Bad Request` | Client ID and Secret are from different generations, or one was copied incompletely | Regenerate both together (Step 1), verify with curl (Step 2) *before* touching Jenkins |
| Token request "fails" but the body actually contains a valid `accessToken` | Your own diagnostic code is checking for HTTP `200` — this endpoint returns `201` on success | Judge success by the presence of `accessToken`, not a specific status code |
| Jenkins pipeline fails to even start, `unexpected char: '\'` at some line | A `sh '''...'''` block got a single backslash where Groovy needed a doubled one | Double every backslash in sed/regex patterns inside triple-single-quoted `sh` blocks |
| `docker login` → `unauthorized`/`name unknown: authentication failed`, identically, across multiple rebuilds/re-copies | The underlying key was deleted/revoked at the source, not a formatting issue | Confirm per Step 7; this needs the credential reissued, not more pipeline tweaking |
| Registry login works with one login-target style but you're not sure if host-only vs. full-path matters | It doesn't, for this failure mode — tested both head to head during a live incident, identical result either way | Don't spend time on this; look at the credential itself instead |
| Pull → `name unknown` specifically, but login succeeded | The requested `active-cli` tag was never published (backend version ahead of the registry) | Pin/fall back to a tag that's confirmed to exist (`FALLBACK_CLI_VERSION`) |
| Token works in curl but the scan container rejects it | Token pasted with its JSON wrapper, or a shell `%` appended | Use only the `eyJ…` string |

## Security notes

- Secrets live only in Jenkins Credentials. The `Jenkinsfile`, Git history, screenshots, and chat logs should contain IDs and URLs only — never the registry password, client secret, or a minted access token.
- If a credential was ever pasted in plaintext anywhere outside Jenkins' own Credentials UI during setup or debugging, treat it as burned: regenerate it and update the Jenkins credential, rather than trying to "clean up" the place it was pasted.
- Access tokens from `/auth/token` are long-lived (the one minted in this lab was valid 180 days). Minting a fresh one per build (as in Step 6) avoids storing a long-lived token anywhere at all.
- Delete unused Jenkins user API tokens set to never expire.

---

## Lessons from a real outage (keep for next time)

This section exists because the first version of this guide didn't anticipate any of this, and figuring it out live cost real time. Keeping it so the next incident goes faster.

- **A credential that "looks the same" in the UI isn't proof it's still valid.** The CI/CD Parameters panel is a static display; it showed the identical registry password across three separate failed builds because nothing about the panel changes when the underlying key dies.
- **Don't assume you have infrastructure access just because a value looks like it should be yours.** `us-central1-docker.pkg.dev/noname-artifacts/nns-docker` looks like a normal GAR path, but `noname-artifacts` is the vendor's project, not the customer's. Chasing a "GCP console" that doesn't exist for a given account wasted real time — check who actually owns the project before assuming self-service is possible.
- **Isolate failures with the minimum number of moving parts.** Testing the client id/secret exchange with a bare `curl`, independent of Jenkins entirely, is what proved a mismatched pair in minutes instead of guessing from pipeline logs.
- **A "helpful" diagnostic change can introduce its own bug.** Adding an HTTP-status check to catch real errors backfired when the assumed success code (200) didn't match the API's actual one (201) — it silently converted a real success into a false failure. When in doubt, check for the thing you actually want (a token), not a proxy for it (a status code).
- **When the real fix is blocked, look for a legitimate local workaround before giving up.** The Jenkins agent still had the last-known-good `active-cli` image cached from before the registry broke. Skipping the registry entirely when that cache exists kept the pipeline *actually working* while the real credential issue remains open — not a substitute for fixing it, but a real stopgap.
