#!/usr/bin/env bash
# Fail a pull request that adds a vulnerable dependency; report existing ones on other events.
# usage: osv-check.sh [BASE_SHA]   (no BASE: report only)
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
out="${RUNNER_TEMP:-$(mktemp -d)}"

scan() { # scan DIR OUTPUT.json
  osv-scanner scan source --recursive --format json --output-file "$2" "$1" >/dev/null 2>"$2.log"
  rc=$?
  # 0: clean, 1: vulnerabilities found, 128: no lockfile or manifest to scan. Anything else is an error.
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ] && [ "$rc" -ne 128 ]; then
    cat "$2.log" >&2
    echo "osv-scanner failed on $1 (exit $rc)" >&2
    exit "$rc"
  fi
  [ -s "$2" ] || echo '{"results":[]}' >"$2"
}

scan . "$out/osv-head.json"

base="${1:-}"
if [ -z "$base" ]; then
  exec python3 "$here/osv_diff.py" "$out/osv-head.json"
fi

wt="$out/osv-base"
git worktree add --detach --quiet "$wt" "$base" || { echo "cannot check out base $base" >&2; exit 2; }
scan "$wt" "$out/osv-base.json"
git worktree remove --force "$wt"
exec python3 "$here/osv_diff.py" "$out/osv-head.json" "$out/osv-base.json"
