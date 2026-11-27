#!/usr/bin/env bash
# Runs on the Colab VM, started by colab-ci-run. Clones the commit, installs the toolchains the
# caller asked for (the same ones check.yml installs on a runner) and runs the check command.
# Writes the command's exit code to /content/ci/status, or 75 when setup failed.
set -uo pipefail
cd /content/ci
# shellcheck disable=SC1091
source ./job.env

fail_setup() {
  echo "colab-ci: setup failed: $1"
  echo 75 > /content/ci/status
  exit 75
}
step() { echo "colab-ci: $1 ($SECONDS s)"; }

mkdir -p repo && cd repo || fail_setup "workspace"
git init -q . || fail_setup "git init"
auth=$(printf 'x-access-token:%s' "$(cat /content/ci/token)" | base64 -w0)
rm -f /content/ci/token
git -c http.extraHeader="Authorization: basic $auth" fetch -q --depth 1 \
  "https://github.com/$REPOSITORY" "$SHA" || fail_setup "clone $REPOSITORY@$SHA"
unset auth
git checkout -q FETCH_HEAD || fail_setup "checkout"
step "cloned $REPOSITORY@${SHA:0:7}"

if [ -n "$UV_VERSION" ]; then
  curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" \
    | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh >/dev/null 2>&1 \
    || fail_setup "uv $UV_VERSION"
  step "uv $(uv --version | cut -d' ' -f2)"
fi
if [ -n "$NODE_VERSION" ]; then
  # Like actions/setup-node: "24" means the newest 24.x, "24.1.0" that exact version.
  if [[ "$NODE_VERSION" == *.*.* ]]; then base="https://nodejs.org/dist/v$NODE_VERSION"
  else base="https://nodejs.org/dist/latest-v${NODE_VERSION%%.*}.x"; fi
  sums=$(curl -fsSL "$base/SHASUMS256.txt") || fail_setup "node $NODE_VERSION list"
  file=$(grep -oE 'node-v[0-9.]+-linux-x64\.tar\.xz$' <<< "$sums" | head -1)
  [ -n "$file" ] || fail_setup "node $NODE_VERSION file"
  curl -fsSL -o "/tmp/$file" "$base/$file" || fail_setup "node download"
  (cd /tmp && grep " $file\$" <<< "$sums" | sha256sum -c --quiet) || fail_setup "node checksum"
  rm -rf /opt/node && mkdir -p /opt/node && tar -xJf "/tmp/$file" -C /opt/node --strip-components 1
  export PATH="/opt/node/bin:$PATH"
  step "node $(node --version)"
fi
if [ -n "$BUN_VERSION" ]; then
  curl -fsSL https://bun.sh/install | bash -s "bun-v$BUN_VERSION" >/dev/null 2>&1 \
    || fail_setup "bun $BUN_VERSION"
  export PATH="$HOME/.bun/bin:$PATH"
  step "bun $(bun --version)"
fi

cd "$WORKING_DIRECTORY" || fail_setup "working directory $WORKING_DIRECTORY"
step "running the check command"
bash -euo pipefail -c "$(cat /content/ci/command)"
code=$?
step "check command exited $code"
echo "$code" > /content/ci/status
