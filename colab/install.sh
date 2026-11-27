#!/usr/bin/env bash
# Installs the Colab check runner on the CI host. Run as root from this folder:
#   sudo ./install.sh
# It creates the `colabci` user (owner of the Colab login), the `colab-ci-users` group (every
# runner user, allowed to start colab-ci-run as colabci and nothing else), the pinned Colab CLI in
# /opt/colab-ci/venv, the broker and VM script, and the reaper timer. Idempotent.
# After the first install, log in once as colabci (README "Checks on Colab").
set -euo pipefail
cd "$(dirname "$0")"
CLI_VERSION=0.8.0
KEYRINGS_ALT_VERSION=5.0.2

id colabci >/dev/null 2>&1 || useradd --system --home-dir /var/lib/colab-ci --create-home \
  --shell /usr/sbin/nologin colabci
chmod 700 /var/lib/colab-ci
getent group colab-ci-users >/dev/null || groupadd --system colab-ci-users
for user in $(getent passwd | cut -d: -f1 | grep '^gha-'); do
  usermod -aG colab-ci-users "$user"
done

UV=$(command -v uv || echo /root/.local/bin/uv)
[ -x /opt/colab-ci/venv/bin/python ] || "$UV" venv --quiet --python 3.12 /opt/colab-ci/venv
VIRTUAL_ENV=/opt/colab-ci/venv "$UV" pip install --quiet \
  "google-colab-cli==$CLI_VERSION" "keyrings.alt==$KEYRINGS_ALT_VERSION"

install -D -o root -g root -m 755 colab-ci-run /usr/local/bin/colab-ci-run
install -D -o root -g root -m 644 vm-job.sh /usr/local/lib/colab-ci/vm-job.sh
install -D -o root -g root -m 644 colab_vm.py /usr/local/lib/colab-ci/colab_vm.py

sudoers=$(mktemp)
cat > "$sudoers" <<'EOF'
# Runner users may start the Colab check broker as colabci, with no arguments (job on stdin).
%colab-ci-users ALL=(colabci) NOPASSWD: /usr/local/bin/colab-ci-run ""
EOF
visudo -cqf "$sudoers"
install -o root -g root -m 440 "$sudoers" /etc/sudoers.d/colab-ci
rm -f "$sudoers"

cat > /etc/systemd/system/colab-ci-reaper.service <<'EOF'
[Unit]
Description=Stop Colab check VMs whose deadline passed

[Service]
Type=oneshot
User=colabci
ExecStart=/usr/local/bin/colab-ci-run --reap
EOF
cat > /etc/systemd/system/colab-ci-reaper.timer <<'EOF'
[Unit]
Description=Stop Colab check VMs whose deadline passed, every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now colab-ci-reaper.timer >/dev/null
echo "Installed. Logged in: $(sudo -u colabci env HOME=/var/lib/colab-ci \
  PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring OAUTHLIB_RELAX_TOKEN_SCOPE=1 \
  /opt/colab-ci/venv/bin/colab usage 2>/dev/null | head -1 || echo no)"
