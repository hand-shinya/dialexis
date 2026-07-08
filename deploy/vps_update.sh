#!/usr/bin/env bash
# Dialexis VPS update — pull latest main, install deps, run the offline Level-0
# test suite. Runs AS the `dialexis` app user (never root):
#
#     sudo -u dialexis /opt/dialexis/deploy/vps_update.sh
#
# The service restart needs root and is a SEPARATE, exact-match sudo command
# (see deploy/vps_deploy.sh and deploy/dialexis-deploy.sudoers). Keeping the two
# apart is deliberate: only one root-privileged command is ever granted.
set -euo pipefail
cd /opt/dialexis
git pull --ff-only origin main
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -m pytest tests/ -q
echo "vps_update: ok ($(git rev-parse --short HEAD))"
