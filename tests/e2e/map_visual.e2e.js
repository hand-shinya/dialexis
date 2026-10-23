// 地図の見た目（所有者 2026-10-23「世界の言語の枝が面積を占め、右の詳しい部分が小さくなる。親だけ出して押せば開くように。
// 任意に設定できるとよい」「円の大きさ・枝や幹の太さや色を、関係性を象徴するように」）。プレビュー・応答は固定値（決定論）。
// 守ること:
//  ①世界の言語の枝は、はじめ親の円だけ（言語の語は消さずに畳む＝地図のデータには残る）
//  ②畳んだ円を押すと開き、もう一度押すと畳む（中心は変えない）
//  ③「見方」で「はじめから開く」を選ぶと端末に覚え、次に開いた地図でははじめから開いている
//  ④凡例が地図の下に出て、語を覆わない。線の太さは「測った強さではない」と書く
//  ⑤線の色は枝ごと（言語の枝と思想の枝で違う）／円の大きさは先につながる語の数（中心が最大）
//  ⑥枝の角度は、見えている先の語の数に応じて配る（畳んだ枝は狭く、大きな枝は広く）
//  ⑦凡例と食い違う従来の注記（重力＝密度の代理指標）を言い換える
//  ⑧通常表示は従来のまま（畳まない・凡例なし）
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
const BASE = process.argv[2] || "http://127.0.0.1:8099";
const ORIGIN = (q) => ({ query: q, lang: "ja", queried_at: "t", word: { query: q }, found: true, resolved_from: null, resolved_to: q, suggestions: [], dimensions: [],
  general_meaning: ["意味"], concept_origin: [], collapse_warning: null, chain: [], relations_typed: [], breadth: [], breadth_count: 0, associated: [], originators: [],
  relations: { near: [], opposite: [] }, named_after: [], senses: [], canon: {}, sources: [], confidence: {}, segment_layers: [], language_bridge: { applied: false }, qid: "Q1" });
const GRAPH = (q) => {
  const nodes = [{ id: "root", label: q, kind: "word", layer: 1, weight: 3, q },
    { id: "dom:general", label: "一般の意味", kind: "domain", layer: 2, weight: 1.4 },
    { id: "dom:phil", label: "専門・思想の意味", kind: "domain", layer: 2, weight: 2.4 },
    { id: "dom:breadth", label: "世界の言語 10", kind: "domain", layer: 2, weight: 1.9 },
    { id: "g1", label: "一般の語", kind: "related", layer: 3, weight: 1, q: "一般の語" }];
  const edges = [{ from: "root", to: "dom:general" }, { from: "root", to: "dom:phil" }, { from: "root", to: "dom:breadth" }, { from: "dom:general", to: "g1" }];
  for (let i = 1; i <= 6; i++) { nodes.push({ id: "p" + i, label: "思想の語" + i, kind: i <= 3 ? "author" : "related", layer: 3, weight: 1, q: "思想の語" + i }); edges.push({ from: "dom:phil", to: "p" + i }); }
  for (let i = 1; i <= 10; i++) { nodes.push({ id: "lang:x" + i + ":w", label: "言語" + i + "：word" + i, kind: "language", layer: 3, weight: 0.85, q: "word" + i }); edges.push({ from: "dom:breadth", to: "lang:x" + i + ":w", strength: 0.4 }); }
  return { query: q, note: "重力(nodeの大きさ)・関係(edge)は密度の代理指標＝推定。データのある枝は濃く、無い枝は薄い（捏造しない）。著者順は史的順。", nodes, edges };
};
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const ctx = await b.newContext({ viewport: { width: 1600, height: 1000 } });
  const json = (r, o) => r.fulfill({ contentType: "application/json", body: JSON.stringify(o) });
  await ctx.route(/\/api\/origin\/graph\?/, r => json(r, GRAPH(new URL(r.request().url()).searchParams.get("q"))));
  await ctx.route(/\/api\/origin\?/, r => json(r, ORIGIN(new URL(r.request().url()).searchParams.get("q"))));
  await ctx.route(/\/api\/(pivot|dimensions|anatomy|bridge|collocations|relation|author)\?/, r => json(r, { data: { input_candidates: [], concept: null }, found: false, dimensions: [], relations: {}, keyless: [], llm: [] }));
  const open = async (p, pv) => {
    await p.goto(`${BASE}/origin?q=${encodeURIComponent("中心語")}&lang=ja&preview=${pv}`, { waitUntil: "domcontentloaded" });
    await p.waitForFunction(() => window.__dx && window.__dx.G && window.__dx.G.nodes.length >= 20, null, { timeout: 20000 });
    await p.waitForTimeout(2200);
  };
  const state = (p) => p.evaluate(() => { const G = window.__dx.G; const L = G.nodes.filter(n => n.kind === "language");
    const B = G.nodes.find(n => n.id === "dom:breadth"), P = G.nodes.find(n => n.id === "dom:phil");
    return { langs: L.length, hidden: L.filter(n => n.hidden).length, folded: !!B.folded, rootQ: G.rootQ, spanB: B.layoutSpan, spanP: P.layoutSpan }; });
  const clickNode = async (p, id) => { const pos = await p.evaluate((id) => { const G = window.__dx.G, r = G.cv.getBoundingClientRect(); const n = G.nodes.find(x => x.id === id);
    return { x: r.left + n.x * G.view.k + G.view.x, y: r.top + n.y * G.view.k + G.view.y }; }, id); await p.mouse.click(pos.x, pos.y); await p.waitForTimeout(2600); };

  let p = await ctx.newPage(); p.on("pageerror", e => console.log("pageerror", e.message.slice(0, 200)));
  await open(p, "1");
  let s = await state(p);
  ok("① 世界の言語の枝は、はじめ親の円だけ（10語は地図のデータに残したまま畳む）", s.langs === 10 && s.hidden === 10 && s.folded, JSON.stringify(s));
  ok("⑥ 畳んだ言語の枝より、大きな思想の枝に広い角度を配る", s.spanP > s.spanB * 1.5, `phil ${s.spanP.toFixed(2)} / breadth ${s.spanB.toFixed(2)}`);
  await clickNode(p, "dom:breadth");
  s = await state(p);
  const ld = await p.evaluate(() => { const d = window.__dx.lastDispatch; return d && { a: d.actionId, s: d.surface }; });
  ok("② 畳んだ円を押すと開く（中心は変えない・dispatchAction 経由）", s.hidden === 0 && !s.folded && s.rootQ === "中心語" && ld && ld.a === "branch" && ld.s === "node", JSON.stringify({ s, ld }));
  await clickNode(p, "dom:breadth");
  s = await state(p);
  ok("② もう一度押すと畳む", s.hidden === 10 && s.folded, JSON.stringify(s));
  const lg = await p.evaluate(() => { const l = document.querySelector(".dx-legend"), c = document.getElementById("origin-graph");
    if (!l) return null; const a = l.getBoundingClientRect(), b = c.getBoundingClientRect(); return { t: l.innerText, below: a.top >= b.bottom - 1 }; });
  ok("④ 凡例が地図の下に出て、語を覆わない", !!lg && lg.below, lg && lg.t.slice(0, 40));
  ok("④ 凡例は、線の太さを「測った強さではない」と書き、畳んだ枝と件数を示す", !!lg && /測った値ではありません/.test(lg.t) && /世界の言語 10（10 語）/.test(lg.t), lg && lg.t.replace(/\s+/g, " ").slice(0, 160));
  const vis = await p.evaluate(() => { const G = window.__dx.G, br = _dxBranches(); const i = (id) => G.nodes.findIndex(n => n.id === id);
    const r = (id) => G.nodes[i(id)].r;
    return { cLang: br.color[i("lang:x1:w")], cPhil: br.color[i("p1")], cGen: br.color[i("g1")], rRoot: r("root"), rPhil: r("dom:phil"), rGen: r("dom:general"), rLeaf: r("p1") }; });
  ok("⑤ 線の色は枝ごと（言語・思想・一般で違う）", vis.cLang !== vis.cPhil && vis.cPhil !== vis.cGen && vis.cLang !== vis.cGen, JSON.stringify(vis));
  ok("⑤ 円の大きさは先につながる語の数（中心 > 思想の枝 > 一般の枝 > 枝先）", vis.rRoot > vis.rPhil && vis.rPhil > vis.rGen && vis.rGen > vis.rLeaf, JSON.stringify(vis));
  const note = await p.$eval("#graph-note", e => e.textContent);
  ok("⑦ 凡例と食い違う従来の注記（密度の代理指標）を言い換える", !/代理指標/.test(note) && /凡例/.test(note), note);
  // ③ 見方の設定
  await p.evaluate(() => dispatchAction("lens", { term: "中心語" }, currentViewState(), { surface: "topbar" }));
  await p.waitForSelector(".lens-lang-open", { timeout: 4000 }).catch(() => {});
  await p.click(".lens-lang-open"); await p.waitForTimeout(2600);
  s = await state(p);
  ok("③ 「見方」で「はじめから開く」を選ぶと、いまの地図でも開く", s.hidden === 0, JSON.stringify(s));
  await p.close();
  p = await ctx.newPage(); await open(p, "1");
  s = await state(p);
  ok("③ 選んだ設定を端末に覚え、次に開いた地図でははじめから開いている", s.hidden === 0 && !s.folded, JSON.stringify(s));
  await p.evaluate(() => localStorage.removeItem("dx_lang_open"));
  await p.close();
  // ⑧ 通常表示
  p = await ctx.newPage(); await open(p, "0");
  s = await state(p);
  const lg0 = await p.$(".dx-legend");
  ok("⑧ 通常表示は従来のまま（畳まない・凡例なし）", s.hidden === 0 && !lg0, JSON.stringify(s));
  await ctx.close();
  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
