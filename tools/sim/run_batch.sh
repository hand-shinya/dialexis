#!/usr/bin/env bash
# シミュレーションを並列で流す。usage: tools/sim/run_batch.sh <outdir> <base> <condition> <seeds> <parallel> [scenario...]
# 例: tools/sim/run_batch.sh sim_runs/20261013_A http://127.0.0.1:8098 A "0 1 2 3 4" 4
# 並列数は外部 API の rate limit を見て決める（Wikidata は 6 並列で 429 を返した実測がある）。
set -uo pipefail
cd "$(dirname "$0")/../.."
OUT="$1"; BASE="$2"; COND="$3"; SEEDS="$4"; PAR="$5"; shift 5
SCEN=("$@"); [ ${#SCEN[@]} -eq 0 ] && SCEN=(tests/scenarios/*.json)
mkdir -p "$OUT"
# harness の自己試験に落ちたら走らせない（2026-10-13: 可視判定の欠陥で本走Aを無効にした）
node tools/sim/selftest.js > "$OUT/selftest.log" 2>&1 || { echo "harness 自己試験に失敗（$OUT/selftest.log）"; exit 4; }
(cd tests/scenarios && sha256sum -c scenarios.sha256 --quiet) || { echo "scenarios.sha256 不一致: 修理中にペルソナが書き換えられている"; exit 3; }
jobs_list=()
for s in "${SCEN[@]}"; do for seed in $SEEDS; do jobs_list+=("$s $seed"); done; done
printf '%s\n' "${jobs_list[@]}" | xargs -P "$PAR" -L 1 bash -c 'node tools/sim/sim.js "$0" "$1" '"$BASE"' '"$OUT"' '"$COND"' >> '"$OUT"'/runs.tsv 2>> '"$OUT"'/errors.log'
node tools/sim/checker.js "$OUT" --md > "$OUT/metrics.md"
echo "done: $(wc -l < "$OUT/runs.tsv") runs → $OUT/metrics.md"
