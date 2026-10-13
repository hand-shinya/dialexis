// 決定論 checker（§8.4 の「抽出」層）。trace の jsonl から数えるだけで、判断はしない。
// Actor の自己申告（stop_reason・note_now）は「申告」として別欄に置き、数えた値と混ぜない（A6）。
//
// usage: node tools/sim/checker.js <trace_dir> [--md]
"use strict";
const fs = require("fs");
const path = require("path");

const RECORD_RE = /^\/api\/(projects|ledgers|ledger-entries|nodes|edges|arguments|premises|watches)(\/|$)/;

function readTrace(f) {
  return fs.readFileSync(f, "utf8").split("\n").filter(Boolean).map(l => JSON.parse(l));
}

function metrics(ev) {
  const start = ev.find(e => e.ev === "start") || {};
  const end = ev.find(e => e.ev === "end") || {};
  const steps = ev.filter(e => e.ev === "step");
  const acted = steps.filter(s => s.actor && s.actor.action && s.actor.action.kind !== "stop");
  const m = {
    run: start.run, persona: start.persona, group: start.group, seed: start.seed, concept: start.concept,
    condition: start.condition, mutate: start.mutate || null,
    end: end.end || (ev.some(e => e.ev === "harness_error") ? "harness_error" : "incomplete"),
    steps: acted.length, wall_s: end.wall_ms ? +(end.wall_ms / 1000).toFixed(1) : null,
  };
  const pathOf = (p) => (p || "").split("?")[0];
  m.rejected = acted.filter(s => s.rejected).length;
  m.rejected_reasons = acted.filter(s => s.rejected).map(s => s.rejected.split(":")[0]);
  m.dead_end = acted.filter(s => s.observed === "nothing_changes").length;
  m.backtrack = acted.filter(s => s.actor.action.kind === "back").length;
  const typed = acted.filter(s => s.actor.action.kind === "type_submit" && !s.rejected).map(s => (s.actor.action.text || "").trim());
  m.typed = typed.length;
  m.re_input = typed.length - new Set(typed).size;
  const tri = acted.map(s => `${s.from}|${s.desc}|${s.to}`);
  m.loop = tri.length - new Set(tri).size;
  m.distinct_pages = new Set(acted.map(s => pathOf(s.to))).size;
  m.reached_query = acted.some(s => /[?&]q=[^&]/.test(s.to || ""));   // 空の q= は問いではない（smoke2 で誤計数）
  m.first_query_step = (acted.find(s => /[?&]q=[^&]/.test(s.to || "")) || {}).step || null;
  m.empty_label_clicks = acted.filter(s => s.desc === "「」を押した").length;
  const baseHost = (() => { try { return new URL(start.base).host; } catch (e) { return ""; } })();
  m.external = acted.reduce((a, s) => a + (s.popups || []).filter(h => h !== baseHost).length, 0) + acted.filter(s => s.observed === "external_site" && !(s.popups || []).length).length;
  const net = acted.flatMap(s => s.net || []);
  m.api_calls = net.filter(n => n.p.startsWith("/api/")).length;
  m.api_errors = net.filter(n => n.p.startsWith("/api/") && (n.s >= 400 || n.s === 0)).length;   // s=0 は応答なしの失敗
  m.record_writes = net.filter(n => ["POST", "PATCH", "PUT"].includes(n.m) && RECORD_RE.test(n.p) && n.s >= 200 && n.s < 300).length;   // s=0（応答なしの失敗）を成功に数えない
  m.page_errors = acted.reduce((a, s) => a + (s.page_errors || []).length, 0);
  const judged = acted.filter(s => !s.rejected && s.observed);
  m.pred_mismatch = judged.length ? +(judged.filter(s => s.expect !== s.observed).length / judged.length).toFixed(2) : null;
  m.masked_ratio = acted.length ? +(acted.reduce((a, s) => a + (s.masked_ratio || 0), 0) / acted.length).toFixed(2) : 0;
  // 空転: 3手以上、新しい q にも記録にもつながらない連続
  let run = 0, maxRun = 0; const seenQ = new Set();
  for (const s of acted) {
    const q = (/[?&]q=([^&]+)/.exec(s.to || "") || [])[1];
    const progressed = (q && !seenQ.has(q)) || (s.net || []).some(n => RECORD_RE.test(n.p) && n.m !== "GET" && n.s >= 200 && n.s < 300);
    if (q) seenQ.add(q);
    run = progressed ? 0 : run + 1; maxRun = Math.max(maxRun, run);
  }
  m.idle_run_max = maxRun;
  m.idle_ratio = acted.length ? +(maxRun / acted.length).toFixed(2) : 0;
  m.distinct_queries = seenQ.size;
  m.actor_errors = ev.filter(e => e.ev === "actor_error").length;
  m.actor_cost_usd = +steps.reduce((a, s) => a + (s.cost || 0), 0).toFixed(4);
  // 以下は Actor の申告。数えた値ではない
  m.claimed_stop = (end.end || "").startsWith("stop:") ? end.end.slice(5) : null;
  return m;
}

function median(xs) { const a = xs.filter(x => x != null).sort((p, q) => p - q); if (!a.length) return null; const k = a.length >> 1; return a.length % 2 ? a[k] : +((a[k - 1] + a[k]) / 2).toFixed(2); }

function aggregate(rows, key) {
  const g = {};
  for (const r of rows) (g[r[key]] = g[r[key]] || []).push(r);
  return Object.entries(g).map(([k, rs]) => ({
    [key]: k, n: rs.length,
    steps: median(rs.map(r => r.steps)), wall_s: median(rs.map(r => r.wall_s)),
    reached_query: rs.filter(r => r.reached_query).length + "/" + rs.length,
    dead_end: median(rs.map(r => r.dead_end)), rejected: median(rs.map(r => r.rejected)),
    loop: median(rs.map(r => r.loop)), re_input: median(rs.map(r => r.re_input)),
    idle_ratio: median(rs.map(r => r.idle_ratio)), distinct_queries: median(rs.map(r => r.distinct_queries)),
    record_writes: rs.reduce((a, r) => a + r.record_writes, 0), api_errors: rs.reduce((a, r) => a + r.api_errors, 0),
    pred_mismatch: median(rs.map(r => r.pred_mismatch)), masked_ratio: median(rs.map(r => r.masked_ratio)),
    gave_up_or_confused: rs.filter(r => ["gave_up", "confused"].includes(r.claimed_stop)).length,
  }));
}

function table(objs) {
  if (!objs.length) return "";
  const ks = Object.keys(objs[0]);
  return [`| ${ks.join(" | ")} |`, `|${ks.map(() => "---").join("|")}|`, ...objs.map(o => `| ${ks.map(k => Array.isArray(o[k]) ? o[k].join(",") : o[k]).join(" | ")} |`)].join("\n");
}

if (require.main === module) {
  const dir = process.argv[2];
  const rows = fs.readdirSync(dir).filter(f => f.endsWith(".jsonl") && f !== "critic.jsonl").sort().map(f => metrics(readTrace(path.join(dir, f))));
  fs.writeFileSync(path.join(dir, "metrics.json"), JSON.stringify(rows, null, 1));
  if (process.argv.includes("--md")) {
    const cols = rows.map(({ run, end, steps, wall_s, reached_query, first_query_step, distinct_queries, dead_end, rejected, loop, re_input, idle_ratio, external, api_errors, record_writes, pred_mismatch, masked_ratio, claimed_stop }) =>
      ({ run, end, steps, wall_s, reached_query, first_query_step, distinct_queries, dead_end, rejected, loop, re_input, idle_ratio, external, api_errors, record_writes, pred_mismatch, masked_ratio, claimed_stop }));
    console.log("## 走行ごと\n\n" + table(cols) + "\n\n## 群ごと（中央値。記録・APIエラーは合計）\n\n" + table(aggregate(rows, "group")) + "\n\n## ペルソナごと\n\n" + table(aggregate(rows, "persona")));
  } else console.log(JSON.stringify(rows, null, 1));
}
module.exports = { metrics, readTrace, aggregate, median, table };
