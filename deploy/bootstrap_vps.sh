#!/usr/bin/env bash
# Dialexis VPS bootstrap — Rocky Linux 9/10 (tested target: Sakura VPS 2G, Rocky 10)
# Run as root on a fresh VPS:
#   curl -sL https://raw.githubusercontent.com/hand-shinya/dialexis/main/deploy/bootstrap_vps.sh | bash
# Idempotent: safe to re-run.
set -euo pipefail

REPO="https://github.com/hand-shinya/dialexis.git"
APP_DIR="/opt/dialexis"
CONTACT="${DIALEXIS_CONTACT:-}"   # export DIALEXIS_CONTACT=you@example.com before running (recommended)

echo "== [1/8] packages =="
dnf -y install git python3 python3-pip nginx sqlite firewalld policycoreutils-python-utils

echo "== [2/8] user + code =="
id dialexis &>/dev/null || useradd -r -m -d /var/lib/dialexis -s /sbin/nologin dialexis
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull
else
  git clone "$REPO" "$APP_DIR"
fi
chown -R dialexis:dialexis "$APP_DIR"

echo "== [3/8] venv =="
sudo -u dialexis python3 -m venv "$APP_DIR/.venv"
sudo -u dialexis "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "== [4/8] offline tests (must pass before serving) =="
sudo -u dialexis "$APP_DIR/.venv/bin/pip" install -q pytest
sudo -u dialexis bash -c "cd $APP_DIR && .venv/bin/python -m pytest tests/ -q"

echo "== [5/8] systemd =="
sed "s|__CONTACT__|$CONTACT|" "$APP_DIR/deploy/systemd/dialexis.service" > /etc/systemd/system/dialexis.service
cp "$APP_DIR/deploy/systemd/dialexis-harvester.service" /etc/systemd/system/
cp "$APP_DIR/deploy/systemd/dialexis-harvester.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now dialexis dialexis-harvester.timer

echo "== [6/8] nginx + SELinux =="
cp "$APP_DIR/deploy/nginx-dialexis.conf" /etc/nginx/conf.d/dialexis.conf
setsebool -P httpd_can_network_connect 1
nginx -t && systemctl enable --now nginx && systemctl reload nginx

echo "== [7/8] firewall =="
systemctl enable --now firewalld
firewall-cmd --permanent --add-service=http --add-service=https
firewall-cmd --reload

echo "== [8/8] daily DB backup =="
mkdir -p /var/backups/dialexis
cat > /etc/cron.d/dialexis-backup <<'EOF'
15 3 * * * root sqlite3 /opt/dialexis/data/dialexis.db ".backup /var/backups/dialexis/dialexis-$(date +\%a).db" 2>> /var/log/dialexis-backup.log
EOF

sleep 2
echo "== verify =="
curl -sf http://127.0.0.1:8000/healthz && echo && echo "OK: Dialexis is live on port 80 via nginx."
echo "NOTE (Sakura VPS): also allow TCP 80/443 in the control-panel packet filter, or disable it."
