// sim2 判定: 走行の記録（personas.js の出力）に8つのオラクルを掛ける。合否は決定論だけで出す。
// usage: node analyze.js <rundir> <truth.json> [--json out.json]
"use strict";
const fs = require("fs"), path = require("path");
const O = require("./oracles");
const [dir, truthPath, , outJson] = process.argv.slice(2);
const truth = truthPath && fs.existsSync(truthPath) ? JSON.parse(fs.readFileSync(truthPath, "utf8")) : {};
const runs = fs.readdirSync(dir).filter(f => f.endsWith(".json")).map(f => { const st = JSON.parse(fs.readFileSync(path.join(dir, f), "utf8")); let prev = [];
  for (const s of st) if (s.obs && s.obs.panels) { s._prev = prev.map(p => p.title + "#" + p.text.length); prev = s.obs.panels; }
  return { id: f.replace(/\.json$/, ""), steps: st }; });
const findings = []; const fire = (o, run, step, msg, ev) => findings.push({ oracle: o, run, step, msg, evidence: ev });
// 結果のパネル＝その手の前から開いていたパネル（右の全体像など）を除いた中で最も長いもの
const resultPanel = (s) => { let ps = (s.obs && s.obs.panels) || []; if (!ps.length) return null;
  const old = new Set(s._prev || []); const fresh = ps.filter(p => !old.has(p.title + "#" + p.text.length)); if (fresh.length) ps = fresh;
  return ps.slice().sort((a, b) => b.text.length - a.text.length)[0]; };
// O2 の索引: 同じ操作の結果を、異なる語どうしで比べる
const tIndex = {};
const termsOf = (s) => [s.node, s.obs && s.obs.map && s.obs.map.root, (resultPanel(s) || {}).title && resultPanel(s).title.replace(/^.*：/, "").replace(/（.*$/, "")].filter(Boolean);
for (const r of runs) for (const s of r.steps) if (s.kind === "choose") { const p = resultPanel(s); if (!p) continue; const a = s.detail.action;
  (tIndex[a] = tIndex[a] || new O.TemplateIndex()).add((s.node || r.id) + "@" + r.id, O.normTerms(p.text, termsOf(s))); }
const LEAK = /mw-parser-output|[a-z-]+\s*:\s*[^;{}]{1,40};|\{[^}]{0,80}:[^}]{0,80}\}|rgba?\(/;
for (const r of runs) {
  const opens = r.steps.filter(s => s.kind === "open");
  // O1 第一画面の地図
  for (const s of opens) { const o = s.obs || {};
    // 利用者が見ている画面（自動で地図へスクロールした後）で、地図の見えている割合
    if (o.mapVisibleFrac != null ? o.mapVisibleFrac < 0.5 : (o.mapTopAbs != null && !o.mapInFirstScreen)) fire("O1", r.id, s.step, `読み込み後の画面で、地図が見えている割合 ${o.mapVisibleFrac != null ? Math.round(o.mapVisibleFrac * 100) + "%" : "—"}（地図の上端 ${o.mapTopAbs}px・画面 ${o.vw}x${o.vh}）`, s.shot);
    if (s.mapMs == null || s.mapMs > 15000) fire("O1", r.id, s.step, `地図が描かれるまで ${s.mapMs == null ? "待ち時間内に描かれず" : Math.round(s.mapMs / 1000) + "秒"}（初めの文 ${s.firstMs == null ? "—" : Math.round(s.firstMs / 1000) + "秒"}）`, s.shot); }
  // 語ごとに、同じ語の異なる操作の結果を集める
  const byNode = {};
  for (const s of r.steps.filter(x => x.kind === "choose")) {
    const p = resultPanel(s); if (!p) continue; const a = s.detail.action; const node = s.node || (s.obs.map && s.obs.map.root) || "?";
    // O2 定型文率
    const ratio = tIndex[a].ratio(O.normTerms(p.text, termsOf(s)), 3);
    if (ratio > 0.5 && p.text.length > 200) fire("O2", r.id, s.step, `「${a}」の結果の ${Math.round(ratio * 100)}% が、ほかの3語以上と同じ文（定型文）`, s.shot);
    // パネルの中での反復: 6字以上の行のうち、同じパネルで3回以上くり返す行の割合
    const lines = p.text.split(/\n+/).map(x => x.trim()).filter(x => x.length >= 6);
    const cnt = lines.reduce((m, x) => (m[x] = (m[x] || 0) + 1, m), {});
    const rep = lines.filter(x => cnt[x] >= 3).length / Math.max(1, lines.length);
    if (lines.length >= 20 && rep > 0.4) fire("O2", r.id, s.step, `「${a}」のパネルの行の ${Math.round(rep * 100)}% が同じパネル内で3回以上くり返す同じ文（例「${Object.keys(cnt).sort((x, y) => cnt[y] - cnt[x])[0].slice(0, 30)}」×${Math.max(...Object.values(cnt))}）`, s.shot);
    if (a === "relationship") { const center = s.obs.map && s.obs.map.root; const tgt = (p.title || "").replace(/^.*：/, "");
      // 根拠の文＝2つの語を同じ文で述べ、かつ語を伏せ字にすると他の語の関係パネルに同じ文が無いもの（定型文は根拠に数えない）
      const k = O.sentences(p.text).filter(x => O.specificity(x, center, tgt) > 0 && (tIndex[a].seen.get(O.sentences(O.normTerms(x, [center, tgt]))[0]) || new Set()).size < 2).length;
      if (k === 0) fire("O2", r.id, s.step, `関係のパネルに「${center}」と「${tgt}」を同じ文で述べた根拠が0文`, s.shot); }
    // O6 漏出
    const m = p.text.match(LEAK); if (m) fire("O6", r.id, s.step, `画面の文に CSS などの断片: 「${m[0].slice(0, 50)}」`, s.shot);
    // O7 多言語の並び
    if (a === "multilingual") { const lines = (p.text.match(/^.{1,40}[：:].+$/gm) || []).slice(0, 10).map(l => l.split(/[：:]/));
      const terms = lines.map(x => (x[1] || "").trim().toLowerCase()).filter(Boolean);
      let similar = 0; for (let i = 1; i < terms.length; i++) if (O.jaccard(terms[0], terms[i]) > 0.25) similar++;
      const names = lines.map(x => x[0].trim()); const sorted = names.slice().sort((x, y) => x.localeCompare(y, "en"));
      const asc = names.length >= 5 && names.join("|") === sorted.join("|");
      if (terms.length >= 5 && (similar / (terms.length - 1) > 0.6 || asc)) fire("O7", r.id, s.step, `多言語の先頭${terms.length}件: ${asc ? "言語名の順に並ぶ" : ""}${similar / (terms.length - 1) > 0.6 ? `／同じ綴りの近い語が ${similar}/${terms.length - 1}` : ""}（${terms.slice(0, 4).join(", ")}…）`, s.shot); }
    (byNode[node] = byNode[node] || []).push({ label: a, text: p.text, step: s.step, shot: s.shot });
  }
  // O3 重複（同じ語の、異なる操作の結果どうし）
  for (const [node, list] of Object.entries(byNode)) for (let i = 0; i < list.length; i++) {
    if (/0 件でした/.test(list[i].text)) continue;   // 0件の明示どうしは「写し」でない（データが無いことを正直に示す同じ形の文）
    const others = list.filter((x, j) => j < i && x.label !== list[i].label && !/0 件でした/.test(x.text));
    const d = O.duplicate(list[i].text, others, 0.7);
    if (d.fail) fire("O3", r.id, list[i].step, `「${node}」の「${list[i].label}」が「${d.with}」とほぼ同じ中身（類似 ${d.sim.toFixed(2)}）`, list[i].shot);
  }
  // O6 漏出（ページ全体。言語の橋のカードなどパネルの外も見る）
  const leakStep = r.steps.find(x => x.obs && x.obs.leak); if (leakStep) fire("O6", r.id, leakStep.step, `画面に CSS の断片: 「${leakStep.obs.leak.slice(0, 60)}」`, leakStep.shot);
  // O5 文脈の喪失・行き止まり（中心を移した後）
  for (const s of r.steps.filter(x => x.kind === "choose" && x.detail.action === "center" || x.kind === "pair-solo")) {
    const dd = O.deadEnd(s.obs || {}); if (dd.fail) fire("O5", r.id, s.step, `移った先の地図が語 ${dd.n} つで、元の文脈へ戻る道の表示が無い`, s.shot); }
  // O8 経路と到達
  const chooses = r.steps.filter(x => x.kind === "choose");
  if (r.id.startsWith("chain") && chooses.length >= 3) { const last = chooses[chooses.length - 1];
    if (!(last.obs.trail || []).length) fire("O8", r.id, last.step, `${chooses.length} 手進んだ後も、来た道（軌跡）が画面に無い`, last.shot); }
  for (const s of r.steps.filter(x => x.kind === "menu" && (x.items || []).some(i => i.action))) { const nonRoot = s.nodeKind !== "word";
    if (nonRoot && !s.items.some(i => i.action === "expand") && s.items.length) fire("O8", r.id, s.step, `派生の語「${s.node}」のメニューに、中心を変えずに先を広げる操作が無い（中心に据え直す必要）`, null); }
  for (const s of r.steps) if (s.obs && s.obs.radialClipped > 0) fire("O8", r.id, s.step, `円形メニューの項目 ${s.obs.radialClipped} 個が画面の外にはみ出す`, s.shot);
  for (const s of r.steps.filter(x => (x.kind === "tap-node" || x.kind === "tap-part"))) if (!(s.items || []).length) fire("O8", r.id, s.step, `タッチ（hover なし）で語を押してもメニューが開かない`, s.shot);
  // O4 同一性（正解札と照合）
  const st = r.steps.find(x => x.originApi); if (st) { const w = st.detail.q, t = truth[w], a = st.originApi, o = st.obs || {};
    if (t) { const shown = r.steps.map(x => ((x.obs && x.obs.redirectNote) || []).join(" ")).join(" ");   // 画面が出そろった後も含めて見る（最初の観測だけだと本文の到着前）
      if (t.redirected_to && !shown.includes(t.redirected_to)) fire("O4", r.id, st.step, `一次資料: ja.wikipedia は「${w}」を「${t.redirected_to}」へ転送。画面にその表示が無い`, st.shot);
      if (t.missing) { const art = decodeURIComponent(String(a.article_url || "").split("/wiki/").pop() || "");
        if (art && art !== w && !shown) fire("O4", r.id, st.step, `一次資料: 「${w}」の記事は無い。画面は記事「${art}」のデータを、その表示なしに使用（関連する思想家: ${(a.associated || []).slice(0, 3).map(x => (x && (x.label || x.name)) || x).join("・") || "—"}）`, st.shot); } }
    if (t && (t.p31 || []).includes("Q4167410") && a.qid === t.qid) fire("O4", r.id, st.step, `一次資料: ja.wikipedia の「${w}」は曖昧さ回避の項目（${t.qid}）。画面はそれを概念として使用`, st.shot);
    if (t && a.qid && t.qid && a.qid !== t.qid) findings.push({ oracle: "O4観察", run: r.id, step: st.step, msg: `「${w}」: ja.wikipedia の記事は ${t.qid}（${t.label_en || "—"}）、画面が使った項目は ${a.qid}（記事 ${decodeURIComponent(String(a.article_url || "").split("/wiki/").pop() || "—")}）`, evidence: st.shot });
    if (t && a.qid && a.qid === t.qid && t.label_en) findings.push({ oracle: "O4観察", run: r.id, step: st.step, msg: `「${w}」: 画面が使った項目は ${a.qid}＝${t.label_en}。関連する思想家として出した人: ${(a.associated || []).slice(0, 4).map(x => (x && (x.label || x.name)) || x).join("・") || "—"}`, evidence: st.shot });
    const notes = r.steps.map(x => (x.obs && x.obs.panels || []).map(p => p.text).join(" ")).join(" ");
    if (/記事は無いため/.test(notes + " " + JSON.stringify(r.steps.map(x => x.obs && x.obs.ctxText))) && t && !t.missing) fire("O4", r.id, st.step, `一次資料: 「${w}」の記事（または転送）は在る。画面は「記事は無いため…」と表示`, st.shot);
    if (!t) fire("O4", r.id, st.step, `正解札が無い（一次資料を取得できず判定を見送り）`, null); }
  const end = r.steps.find(x => x.kind === "end"); if (end && end.pageErrors && end.pageErrors.length) fire("ERR", r.id, end.step, `画面のJSエラー ${end.pageErrors.length} 件: ${end.pageErrors[0]}`, null);
}
const by = findings.reduce((m, f) => ((m[f.oracle] = (m[f.oracle] || 0) + 1), m), {});
console.log(`runs ${runs.length}  findings ${findings.length}`, JSON.stringify(by));
for (const f of findings) console.log(`${f.oracle}\t${f.run}#${f.step}\t${f.msg}`);
if (outJson) fs.writeFileSync(outJson, JSON.stringify({ runs: runs.map(r => r.id), by, findings }, null, 1));
