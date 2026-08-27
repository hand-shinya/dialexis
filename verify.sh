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

# 統合(network依存)スイート＝外部サービス(SearXNG/DWDS/Wikidata works)や乱数×取得に依存し、ローカルで
# 決定論的にできないもの。デプロイgateには使わない（情報表示）。それ以外は不変条件スイート＝gate対象。
# 外部サービス／ネットワーク応答に依存するスイート。ローカル環境で応答が欠けても、
# 内部の不変条件gateを偽陽性で止めないよう情報表示へ分離する。
INTEGRATION="applications_wave combine_ui extterm lenses_full origin play thinkers_graph thinkers_recall"
echo "══ 3a) 不変条件スイート（決定論・デプロイgate対象）══"
for t in tests/e2e/*.e2e.js; do
  name=$(basename "$t"); stem="${name%.e2e.js}"
  case " $INTEGRATION " in *" $stem "*) continue;; esac
  out=$(node "$t" "${BASE}" 2>&1); rc=$?
  line=$(echo "$out" | grep -E "/[0-9]+ PASS" | tail -1)
  if [ "$rc" = "0" ]; then echo "PASS  ${name}  (${line})"
  else echo "FAIL  ${name}  (rc=${rc} ${line:-no-summary})"; echo "$out" | grep -E "FAIL|ERR" | head -3; fail=1; fi
done
echo "══ 3b) 統合スイート（network依存・情報表示・gate非対象）══"
for stem in $INTEGRATION; do
  t="tests/e2e/${stem}.e2e.js"; [ -f "$t" ] || continue
  out=$(node "$t" "${BASE}" 2>&1); rc=$?
  line=$(echo "$out" | grep -E "/[0-9]+ PASS" | tail -1)
  [ "$rc" = "0" ] && echo "PASS  ${stem}  (${line})" || echo "info  ${stem}  (${line:-no-summary}・network依存/本番で再確認)"
done

if [ "$fail" = "0" ]; then
  # 検証済みマーカー: このHEADのコードで全検証が通ったことを記録。デプロイgate(vps_update.sh)が参照する。
  git rev-parse HEAD > deploy/verified_sha.txt
  echo "══ 検証すべて成功（verified_sha=$(cat deploy/verified_sha.txt) をコミットしてデプロイ可）══"
else
  echo "══ 検証に失敗あり（デプロイ不可）══"
fi
exit "$fail"
