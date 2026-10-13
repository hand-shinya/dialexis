// Critic（§8.4 の「監査」層）。Actor と別の model で trace を認知的 walkthrough として読む。
// 出すのは「どの手で・何が・なぜ詰まったか」の候補だけで、根拠は trace の step 番号と逐語の引用に限る。
// 引用が trace に実在しない所見は、この file が機械的に捨てる（A6: 申告を検証の代わりにしない）。
// 走り終えた後の感想は根拠にしない（§8.6）。根拠は各手の時点で同期記録された note_now・expect・observed だけ。
//
// usage: node tools/sim/critic.js <trace_dir> [model]   → <trace_dir>/critic.jsonl
"use strict";
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const { readTrace } = require("./checker");

const dir = process.argv[2];
const MODEL = process.argv[3] || process.env.SIM_CRITIC_MODEL || "claude-sonnet-5-5";
const SCHEMA = {
  type: "object", additionalProperties: false, required: ["findings"],
  properties: { findings: { type: "array", items: {
    type: "object", additionalProperties: false,
    required: ["step", "kind", "surface", "what", "quote", "severity"],
    properties: {
      step: { type: "integer" },
      kind: { type: "string", enum: ["not_discoverable", "feedback_mismatch", "dead_end", "language_barrier", "jargon", "loop_trap", "lost_context", "error_shown", "harness_artifact"] },
      surface: { type: "string", description: "画面の path（例 /origin）" },
      what: { type: "string", description: "何が起きたか（60字以内）" },
      quote: { type: "string", description: "その手の note_now または desc からの逐語の引用（20字以上）" },
      severity: { type: "integer", minimum: 1, maximum: 3 },
    } } } },
};

function compact(ev) {
  const st = ev.find(e => e.ev === "start"), en = ev.find(e => e.ev === "end");
  const steps = ev.filter(e => e.ev === "step").map(s => ({
    step: s.step, at: s.from, action: s.actor.action, desc: s.desc, note_now: s.actor.note_now,
    expect: s.expect, observed: s.observed, rejected: s.rejected, to: s.to,
    api_errors: (s.net || []).filter(n => n.p.startsWith("/api/") && (n.s >= 400 || n.s === 0)).map(n => `${n.m} ${n.p} ${n.s}`),
  }));
  return { persona_group: st.group, max_steps: st.max_steps, end: en && en.end, steps };
}

const PROMPT = `あなたはユーザビリティの監査者です。下は、あるウェブサイトを一人の利用者役が操作した記録です。
各手には、その瞬間に利用者役が考えていたこと（note_now）、起きると思ったこと（expect）、実際に起きたこと（observed）があります。
この記録だけを根拠に、利用者が詰まった・迷った・誤解した手を挙げてください。
規則:
- quote には、その step の note_now か desc から、20字以上を一字も変えずに写す。写せない所見は出さない。
- 利用者役（AI）の判断の誤りで、画面の側に原因が無いものは kind=harness_artifact にする。
- 推測で画面の内容を補わない。記録に無いことは書かない。
- 何も無ければ findings を空にする。

記録:
`;

const files = fs.readdirSync(dir).filter(f => f.endsWith(".jsonl") && f !== "critic.jsonl").sort();
const out = fs.openSync(path.join(dir, "critic.jsonl"), "a");
const done = new Set(fs.existsSync(path.join(dir, "critic.jsonl")) ? fs.readFileSync(path.join(dir, "critic.jsonl"), "utf8").split("\n").filter(Boolean).map(l => JSON.parse(l)).filter(x => !x.error).map(x => x.run) : []);   // 失敗行は済みに数えず再試行する
const cwd = path.join(require("os").tmpdir(), "dx-sim-critic"); fs.mkdirSync(cwd, { recursive: true });
for (const f of files) {
  const run = f.replace(/\.jsonl$/, ""); if (done.has(run)) continue;
  const ev = readTrace(path.join(dir, f));
  if (!ev.find(e => e.ev === "start")) { fs.writeSync(out, JSON.stringify({ run, error: "trace_without_start" }) + "\n"); continue; }
  const c = compact(ev);
  const r = spawnSync("claude", ["-p", "--restricted", "--strict-mcp-config", "--no-session-persistence", "--tools", "",
    "--model", MODEL, "--output-format", "json", "--json-schema", JSON.stringify(SCHEMA)],
    { input: PROMPT + JSON.stringify(c, null, 1), cwd, encoding: "utf8", timeout: 300000, maxBuffer: 16 << 20 });
  let d; try { d = JSON.parse(r.stdout); } catch (e) { fs.writeSync(out, JSON.stringify({ run, error: (r.stderr || "").slice(0, 300) }) + "\n"); continue; }
  if (d.is_error || !d.structured_output) { fs.writeSync(out, JSON.stringify({ run, error: "critic_no_structured_output" }) + "\n"); continue; }
  const raw = d.structured_output.findings || [];
  // 引用の実在を機械で照合する。実在しない引用の所見は捨て、捨てた数を残す
  const kept = [], dropped = [];
  for (const x of raw) {
    const s = c.steps.find(t => t.step === x.step);
    const ok = s && x.quote && x.quote.length >= 20 && ((s.note_now || "").includes(x.quote) || (s.desc || "").includes(x.quote));
    (ok ? kept : dropped).push(x);
  }
  fs.writeSync(out, JSON.stringify({ run, model: Object.keys(d.modelUsage || {}), cost: d.total_cost_usd, kept, dropped_unquoted: dropped.length }) + "\n");
  console.log(`${run}\tkept=${kept.length}\tdropped=${dropped.length}`);
}
fs.closeSync(out);
