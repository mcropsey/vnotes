#!/usr/bin/env bash
# Refresh the per-user Bearer tokens stored on an Akamai Active Testing environment.
#
# VNotes JWTs expire after 24h, so static tokens saved in the AT environment go
# stale. Before each scan, log in as every test user and overwrite the matching
# AT authentication (matched by name) with a fresh "Authorization: Bearer <jwt>".
#
# Required env:
#   AT_TOKEN      platform bearer token (service-account token from /auth/token)
#   AT_BASE       e.g. https://mikec-lab.nonamesec.com
#   APP_ID        Active Testing application id
#   ENV_ID        Active Testing environment id
#   TARGET_URL    app base URL, e.g. https://notes.cropseyit.com
#   AT_USERS      space-separated user:password pairs, e.g. "alice:alice123 bob:bob12345"
#
# Uses only bash/curl/sed/grep (the Jenkins controller has no python or jq).
# Tokens are never echoed.
set -euo pipefail

: "${AT_TOKEN:?}" "${AT_BASE:?}" "${APP_ID:?}" "${ENV_ID:?}" "${TARGET_URL:?}" "${AT_USERS:?}"

AUTHS_URL="$AT_BASE/api/active/v2/applications/$APP_ID/environments/$ENV_ID/authentications"

# id/name/role triples of the auths currently on the environment
AUTH_LIST="$(curl -fsS --max-time 30 -H "Authorization: Bearer $AT_TOKEN" "$AUTHS_URL" \
  | grep -o '"id":"[^"]*","authenticationName":"[^"]*","role":"[^"]*"' || true)"

if [ -z "$AUTH_LIST" ]; then
  echo "No authentications found on env $ENV_ID" >&2
  exit 1
fi

updated=0
for pair in $AT_USERS; do
  user="${pair%%:*}"
  pass="${pair#*:}"

  line="$(echo "$AUTH_LIST" | grep "\"authenticationName\":\"$user\"" || true)"
  if [ -z "$line" ]; then
    echo "WARN: no AT authentication named '$user' on env $ENV_ID; skipping" >&2
    continue
  fi
  auth_id="$(echo "$line" | sed -E 's/.*"id":"([^"]*)".*/\1/')"
  role="$(echo "$line" | sed -E 's/.*"role":"([^"]*)".*/\1/')"

  # VNotes login is OAuth2 password-form style (application/x-www-form-urlencoded)
  jwt="$(curl -fsS --max-time 30 -X POST "$TARGET_URL/api/auth/login" \
           --data-urlencode "username=$user" --data-urlencode "password=$pass" \
         | sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  if [ -z "$jwt" ]; then
    echo "ERROR: login failed for '$user'" >&2
    exit 1
  fi

  code="$(printf '{"authenticationName":"%s","role":"%s","mappings":[{"type":"header","key":"Authorization","value":"Bearer %s"}]}' \
            "$user" "$role" "$jwt" \
          | curl -sS --max-time 30 -o /dev/null -w '%{http_code}' -X PUT \
              -H "Authorization: Bearer $AT_TOKEN" -H 'Content-Type: application/json' \
              --data-binary @- "$AUTHS_URL/$auth_id")"
  if [ "$code" != "200" ]; then
    echo "ERROR: updating AT auth '$user' ($auth_id) returned HTTP $code" >&2
    exit 1
  fi
  echo "Refreshed AT auth: $user (role=$role)"
  updated=$((updated + 1))
done

echo "Refreshed $updated authentication(s) on env $ENV_ID"
