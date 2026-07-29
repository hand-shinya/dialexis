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
# ── 全検証gate（半田様 Step6）: ブラウザE2EはVPSのRAMで実行できないため、対象コードのSHAで
#    verify.sh（pytest＋全E2E＋failure injection＋履歴）が通った証跡を必須にする。verify.sh が
#    deploy/verified_sha.txt にHEADを記録する。検証SHAがHEADの祖先で、それ以降の差分がマーカー
#    のみ（＝未検証のコード変更が無い）でなければデプロイを止める。
# 【この gate の正確な効力（A5・過剰主張しない）】: 「公式デプロイ経路（vps_update.sh）では、記録された
#  検証SHA以降のコード差分を拒否する」ことだけを保証する。手動迂回を全面的に不可にするものではなく、
#  検証の実行自体を完全に保証するものでもない（このスクリプトを介さず直接編集・再起動する経路は対象外）。
VS="$(cat deploy/verified_sha.txt 2>/dev/null || true)"
[ -n "$VS" ] || { echo "deploy blocked: verified_sha.txt が無い（ローカルで ./verify.sh を実行せよ）"; exit 3; }
git merge-base --is-ancestor "$VS" HEAD || { echo "deploy blocked: 検証SHA $VS はHEADの祖先でない"; exit 3; }
CHANGED="$(git diff --name-only "$VS" HEAD | grep -v '^deploy/verified_sha.txt$' || true)"
[ -z "$CHANGED" ] || { echo "deploy blocked: 検証SHA $VS 以降に未検証のコード変更あり:"; echo "$CHANGED"; exit 3; }
echo "verify gate ok: コードは $VS で全検証済み"
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -m pytest tests/ -q
echo "vps_update: ok ($(git rev-parse --short HEAD))"
