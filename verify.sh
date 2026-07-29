#!/usr/bin/env bash
# 公式検証コマンド（半田様 Step6・2026-07-29）: 全UI不変条件テストを1コマンドで実行する。
#   - Python tests（静的gate: 否定表示ゼロ / 単一Dispatcher強制 / ACTIONS被覆）
#   - 全 Playwright E2E（操作同値性 / 履歴モデル / failure injection / 普遍性 / 回帰）
# どれか1つでも失敗したら非ゼロ終了＝この検証を通らない commit はデプロイしない運用にする。
# Chromium path は DX_CHROMIUM 環境変数に集約（各テストにハードコードしない）。
set -uo pipefail
cd "$(dirname "$0")"

PORT="${DX_PORT:-8099}"
BASE="http://127.0.0.1:${PORT}"
export DX_CHROMIUM="${DX_CHROMIUM:-/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome}"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-/home/handa/.claude/jobs/b4518c70/tmp/alsa_ext/ext/usr/lib/x86_64-linux-gnu}"
export NODE_PATH="${NODE_PATH:-/home/handa/.npm/_npx/e41f203b7505f1fb/node_modules}"

fail=0
[ -d .venv ] && source .venv/bin/activate 2>/dev/null

echo "══ 1) Python tests（静的gate含む）══"
python -m pytest -q || fail=1

echo "══ 2) サーバ起動（:${PORT}）══"
python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT}" >/tmp/dx_verify_uv.log 2>&1 &
SRV=$!
trap 'kill -9 "$SRV" 2>/dev/null' EXIT
for i in $(seq 1 15); do
  code=$(curl -s -m 3 -o /dev/null -w "%{http_code}" "${BASE}/healthz" 2>/dev/null || true)
  [ "$code" = "200" ] && break; sleep 1
done
[ "$code" = "200" ] || { echo "server not ready"; exit 1; }

echo "══ 3) 全 Playwright E2E（各テストの終了コードで判定）══"
for t in tests/e2e/*.e2e.js; do
  name=$(basename "$t")
  out=$(node "$t" "${BASE}" 2>&1); rc=$?
  line=$(echo "$out" | grep -E "/[0-9]+ PASS" | tail -1)
  if [ "$rc" = "0" ]; then
    echo "PASS  ${name}  (${line})"
  else
    echo "FAIL  ${name}  (rc=${rc} ${line:-no-summary})"; echo "$out" | grep -E "FAIL|ERR" | head -3
    fail=1
  fi
done

[ "$fail" = "0" ] && echo "══ 検証すべて成功（この commit はデプロイ可）══" || echo "══ 検証に失敗あり（デプロイ不可）══"
exit "$fail"
