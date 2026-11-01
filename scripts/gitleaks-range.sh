#!/usr/bin/env bash
# Scan the commits a push or pull request adds for leaked secrets.
# usage: gitleaks-range.sh BASE_SHA HEAD_SHA   (BASE may be empty or all zeros for a new branch)
set -euo pipefail

base="${1:-}"
head="${2:?head sha required}"

if [ -n "$base" ] && [ "$base" != 0000000000000000000000000000000000000000 ] \
  && git cat-file -e "${base}^{commit}" 2>/dev/null; then
  range="${base}..${head}"
elif git cat-file -e "${head}~1^{commit}" 2>/dev/null; then
  range="${head}~1..${head}" # new branch or unknown base: the latest commit only
else
  range="$head" # the repository's first commit
fi

echo "gitleaks: scanning ${range} ($(git rev-list --count "$range") commits)"
# A repository can silence a false positive with .gitleaksignore or tune rules with .gitleaks.toml.
gitleaks git --log-opts="$range" --redact --no-banner --verbose .
