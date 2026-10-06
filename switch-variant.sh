#!/bin/bash
# Usage: ./switch-variant.sh vulnerable|fixed   — swaps app/ and static/ to the chosen build.
# Then redeploy:  docker compose up -d --build   (or commit+push to run the Jenkins pipeline)
set -euo pipefail
cd "$(dirname "$0")"
v="${1:-}"
[ -d "variants/$v" ] || { echo "usage: $0 vulnerable|fixed"; exit 1; }
rm -rf app static
cp -a "variants/$v/app" "variants/$v/static" .
echo "Switched to '$v' variant. Rebuild: docker compose up -d --build"
