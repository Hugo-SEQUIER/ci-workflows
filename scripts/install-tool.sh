#!/usr/bin/env bash
# Install a pinned, checksum-verified scanner into the runner's tool cache, once per version.
# usage: install-tool.sh gitleaks|osv-scanner   (prints nothing on success; adds the tool to PATH)
set -euo pipefail

GITLEAKS_VERSION=8.30.1
GITLEAKS_SHA256=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb
OSV_VERSION=2.7.0
OSV_SHA256=160c6253e2922e9e0a6a9771c5c4c40a4b3c6090b34a3cdd5e80c96cc2e4218b

cache="${RUNNER_TOOL_CACHE:-$HOME/.cache/ci-tools}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

case "${1:-}" in
  gitleaks)
    dir="$cache/gitleaks/$GITLEAKS_VERSION"
    if [ ! -x "$dir/gitleaks" ]; then
      curl -fsSL -o "$tmp/gitleaks.tgz" \
        "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
      echo "$GITLEAKS_SHA256  $tmp/gitleaks.tgz" | sha256sum -c --quiet -
      mkdir -p "$dir"
      tar -xzf "$tmp/gitleaks.tgz" -C "$dir" gitleaks
    fi
    ;;
  osv-scanner)
    dir="$cache/osv-scanner/$OSV_VERSION"
    if [ ! -x "$dir/osv-scanner" ]; then
      curl -fsSL -o "$tmp/osv-scanner" \
        "https://github.com/google/osv-scanner/releases/download/v${OSV_VERSION}/osv-scanner_linux_amd64"
      echo "$OSV_SHA256  $tmp/osv-scanner" | sha256sum -c --quiet -
      mkdir -p "$dir"
      install -m 755 "$tmp/osv-scanner" "$dir/osv-scanner"
    fi
    ;;
  *)
    echo "usage: install-tool.sh gitleaks|osv-scanner" >&2
    exit 2
    ;;
esac

if [ -n "${GITHUB_PATH:-}" ]; then echo "$dir" >>"$GITHUB_PATH"; fi
