"""欠陥台帳の素案を作る。決定論 checker の値を上位に、Critic の所見を下位に置く（§8.4）。

usage: python3 tools/sim/defects.py <trace_dir>   → <trace_dir>/defects.md

Critic の所見は「何本の走行で・何人のペルソナ群で」同じ画面×種類が出たかで束ね、
1本だけの所見は候補として残すが上位に置かない（Actor 1体の癖を欠陥と呼ばない）。
harness_artifact は画面の欠陥から除き、harness 側の課題として別に数える。
"""
import collections
import json
import pathlib
import re
import sys

d = pathlib.Path(sys.argv[1])
metrics = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
crit = [json.loads(l) for l in (d / "critic.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()] \
    if (d / "critic.jsonl").exists() else []
group_of = {m["run"]: m["group"] for m in metrics}

L = ["# 欠陥台帳の素案（機械生成）", "", f"走行 {len(metrics)} 本。Critic 済み {len(crit)} 本。", ""]

# 1) 決定論の値（偽装されない層）
L += ["## 1. 決定論で数えた値（上位の根拠）", ""]
by_g = collections.defaultdict(list)
for m in metrics:
    by_g[m["group"]].append(m)
L.append("| 群 | 本数 | 問いに到達 | 行き止まり計 | 拒否計 | 空転≥半分 | 記録へ接続 | APIエラー計 | 文字なしボタンを押した |")
L.append("|---|---|---|---|---|---|---|---|---|")
for g, ms in sorted(by_g.items()):
    L.append(f"| {g} | {len(ms)} | {sum(m['reached_query'] for m in ms)}/{len(ms)} | {sum(m['dead_end'] for m in ms)} | "
             f"{sum(m['rejected'] for m in ms)} | {sum(m['idle_ratio'] >= 0.5 for m in ms)} | {sum(m['record_writes'] > 0 for m in ms)} | "
             f"{sum(m['api_errors'] for m in ms)} | {sum(m.get('empty_label_clicks', 0) for m in ms)} |")
rej = collections.Counter(r for m in metrics for r in m["rejected_reasons"])
L += ["", "拒否の理由（JS が受け付けなかった手）: " + "、".join(f"{k} {v}" for k, v in rej.most_common()), ""]

# 2) Critic の所見を束ねる
def norm_surface(s):
    s = re.sub(r"\?.*$", "", s or "")
    return s or "/"

groups = collections.defaultdict(lambda: {"runs": set(), "pgroups": set(), "sev": [], "what": [], "quotes": []})
artifacts = collections.Counter()
dropped = 0
for c in crit:
    dropped += c.get("dropped_unquoted", 0)
    for f in c.get("kept", []):
        if f["kind"] == "harness_artifact":
            artifacts[f["what"][:40]] += 1
            continue
        k = (norm_surface(f["surface"]), f["kind"])
        g = groups[k]
        g["runs"].add(c["run"]); g["pgroups"].add(group_of.get(c["run"], "?"))
        g["sev"].append(f["severity"]); g["what"].append(f["what"]); g["quotes"].append((c["run"], f["step"], f["quote"]))

L += ["## 2. Critic の所見（下位の根拠・画面×種類で束ねた）", "",
      f"引用が trace に実在せず機械が捨てた所見: {dropped} 件。harness 側の誤り（Actor の記憶違い等）: {sum(artifacts.values())} 件。", "",
      "| 順 | 画面 | 種類 | 走行数 | 群 | 重さ計 | 代表 |", "|---|---|---|---|---|---|---|"]
ranked = sorted(groups.items(), key=lambda kv: (-len(kv[1]["runs"]), -len(kv[1]["pgroups"]), -sum(kv[1]["sev"])))
for i, ((surf, kind), g) in enumerate(ranked, 1):
    L.append(f"| {i} | `{surf}` | {kind} | {len(g['runs'])} | {','.join(sorted(g['pgroups']))} | {sum(g['sev'])} | {g['what'][0]} |")
L += ["", "### 上位10件の引用（trace の逐語）", ""]
for (surf, kind), g in ranked[:10]:
    L.append(f"- `{surf}` {kind}")
    for run, step, q in g["quotes"][:3]:
        L.append(f"  - {run} 手{step}: 「{q}」")
(d / "defects.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L[:40]))
