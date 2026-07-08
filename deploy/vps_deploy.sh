#!/usr/bin/env bash
# Hands-free Dialexis deploy, run FROM the VPS by user `ubuntu`. Uses only the
# two NOPASSWD-scoped sudo commands granted in /etc/sudoers.d/dialexis-deploy,
# so it needs no password once that file is installed (see README below).
#
# Remote one-liner (from a workstation):
#   ssh -i ~/.ssh/dialexis_vps ubuntu@219.94.244.239 /opt/dialexis/deploy/vps_deploy.sh
set -euo pipefail
# 1. update code + deps + tests, as the app user (not root):
sudo -n -u dialexis /opt/dialexis/deploy/vps_update.sh
# 2. restart the service, the single root-privileged exact command:
sudo -n /usr/bin/systemctl restart dialexis
sleep 2
curl -s -o /dev/null -w "healthz %{http_code}\n" http://127.0.0.1:8000/healthz
