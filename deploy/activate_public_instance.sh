#!/usr/bin/env bash
# One-time privileged activation for an already bootstrapped Dialexis VPS.
#
# Run on the VPS from the ubuntu account:
#   sudo /opt/dialexis/deploy/activate_public_instance.sh
#
# This is intentionally separate from vps_update.sh.  It installs the
# public-instance environment and systemd definition once; later updates can
# use the narrow NOPASSWD commands in dialexis-deploy.sudoers.
set -euo pipefail

APP_DIR="${DIALEXIS_APP_DIR:-/opt/dialexis}"
APP_USER="${DIALEXIS_APP_USER:-dialexis}"
APP_GROUP="${DIALEXIS_APP_GROUP:-dialexis}"
ENV_DIR="/etc/dialexis"
ENV_FILE="$ENV_DIR/dialexis.env"
UNIT_DIR="/etc/systemd/system"
UNIT_FILE="$UNIT_DIR/dialexis.service"
HARVESTER_SERVICE="$UNIT_DIR/dialexis-harvester.service"
HARVESTER_TIMER="$UNIT_DIR/dialexis-harvester.timer"
SUDOERS_FILE="/etc/sudoers.d/dialexis-deploy"

if [[ "${EUID}" -ne 0 ]]; then
  echo "public activation: root権限が必要です。sudoで再実行してください。" >&2
  exit 2
fi

for command_name in cmp curl install mktemp openssl sed systemctl visudo; do
  command -v "$command_name" >/dev/null || {
    echo "public activation: 必須コマンドがありません: $command_name" >&2
    exit 3
  }
done

[[ -d "$APP_DIR" ]] || { echo "public activation: APP_DIRがありません: $APP_DIR" >&2; exit 3; }
[[ -r "$APP_DIR/deploy/systemd/dialexis.service" ]] || { echo "public activation: service定義がありません" >&2; exit 3; }
[[ -r "$APP_DIR/deploy/systemd/dialexis-harvester.service" ]] || { echo "public activation: harvester定義がありません" >&2; exit 3; }
[[ -r "$APP_DIR/deploy/systemd/dialexis-harvester.timer" ]] || { echo "public activation: timer定義がありません" >&2; exit 3; }
[[ -r "$APP_DIR/deploy/dialexis-deploy.sudoers" ]] || { echo "public activation: sudoers定義がありません" >&2; exit 3; }
getent passwd "$APP_USER" >/dev/null || { echo "public activation: app userがありません: $APP_USER" >&2; exit 3; }
getent group "$APP_GROUP" >/dev/null || { echo "public activation: app groupがありません: $APP_GROUP" >&2; exit 3; }

TMP_DIR="$(mktemp -d /tmp/dialexis-public-activation.XXXXXX)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

backup_if_changed() {
  local candidate="$1"
  local target="$2"
  if [[ -e "$target" ]] && ! cmp -s "$candidate" "$target"; then
    cp -a "$target" "$target.pre-public.$(date +%Y%m%d%H%M%S)"
  fi
}

install -d -m 0750 -o root -g "$APP_GROUP" "$ENV_DIR"
if [[ ! -e "$ENV_FILE" ]]; then
  umask 077
  printf 'DIALEXIS_SESSION_SECRET=%s\n' "$(openssl rand -hex 32)" > "$TMP_DIR/dialexis.env"
  install -o root -g "$APP_GROUP" -m 0640 "$TMP_DIR/dialexis.env" "$ENV_FILE"
else
  [[ -s "$ENV_FILE" ]] || { echo "public activation: 既存のenvが空です。削除せず内容を確認してください。" >&2; exit 4; }
  existing_secret="$(sed -n 's/^DIALEXIS_SESSION_SECRET=//p' "$ENV_FILE" | head -n 1)"
  [[ "${#existing_secret}" -ge 32 ]] || { echo "public activation: 既存secretが短すぎます。上書きせず停止しました。" >&2; exit 4; }
  chown root:"$APP_GROUP" "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
fi

CONTACT="${DIALEXIS_CONTACT:-}"
if [[ -z "$CONTACT" && -r "$UNIT_FILE" ]]; then
  CONTACT="$(sed -n 's/^Environment=DIALEXIS_CONTACT=//p' "$UNIT_FILE" | head -n 1)"
fi
CONTACT="${CONTACT:-dialexis@localhost}"
CONTACT_ESCAPED="${CONTACT//\\/\\\\}"
CONTACT_ESCAPED="${CONTACT_ESCAPED//&/\\&}"
CONTACT_ESCAPED="${CONTACT_ESCAPED//|/\\|}"
sed "s|__CONTACT__|$CONTACT_ESCAPED|g" "$APP_DIR/deploy/systemd/dialexis.service" > "$TMP_DIR/dialexis.service"

backup_if_changed "$TMP_DIR/dialexis.service" "$UNIT_FILE"
install -o root -g root -m 0644 "$TMP_DIR/dialexis.service" "$UNIT_FILE"
backup_if_changed "$APP_DIR/deploy/systemd/dialexis-harvester.service" "$HARVESTER_SERVICE"
backup_if_changed "$APP_DIR/deploy/systemd/dialexis-harvester.timer" "$HARVESTER_TIMER"
install -o root -g root -m 0644 "$APP_DIR/deploy/systemd/dialexis-harvester.service" "$HARVESTER_SERVICE"
install -o root -g root -m 0644 "$APP_DIR/deploy/systemd/dialexis-harvester.timer" "$HARVESTER_TIMER"

visudo -cf "$APP_DIR/deploy/dialexis-deploy.sudoers" >/dev/null
install -o root -g root -m 0440 "$APP_DIR/deploy/dialexis-deploy.sudoers" "$SUDOERS_FILE"

systemctl daemon-reload
systemctl enable dialexis dialexis-harvester.timer >/dev/null
systemctl restart dialexis
systemctl restart dialexis-harvester.timer

health_tmp="$TMP_DIR/healthz.json"
headers_tmp="$TMP_DIR/healthz.headers"
health_error="$TMP_DIR/healthz.error"
health_attempts=30
health_ok=0
for ((attempt = 1; attempt <= health_attempts; attempt++)); do
  : > "$headers_tmp"
  : > "$health_error"
  if curl -fsS -D "$headers_tmp" -o "$health_tmp" http://127.0.0.1:8000/healthz 2>"$health_error"; then
    health_ok=1
    break
  fi
  if (( attempt < health_attempts )); then
    sleep 1
  fi
done
if (( health_ok == 0 )); then
  echo "public activation: healthzが${health_attempts}回の試行後も応答しません" >&2
  cat "$health_error" >&2
  systemctl --no-pager --full --lines=40 status dialexis.service >&2 || true
  exit 5
fi
grep -q '"public_instance":true' "$health_tmp" || { echo "public activation: public_instance確認に失敗" >&2; cat "$health_tmp" >&2; exit 5; }
grep -q '"session_secret_configured":true' "$health_tmp" || { echo "public activation: session secret確認に失敗" >&2; cat "$health_tmp" >&2; exit 5; }
grep -qi '^set-cookie:.*dialexis_workspace=' "$headers_tmp" || { echo "public activation: workspace cookie確認に失敗" >&2; cat "$headers_tmp" >&2; exit 5; }

echo "public activation: ok"
echo "public mode: enabled"
echo "workspace cookie: issued"
echo "healthz attempts: $attempt"
echo "healthz: $(tr -d '\n' < "$health_tmp")"
echo "next: curl -fsS http://127.0.0.1:8000/healthz"
