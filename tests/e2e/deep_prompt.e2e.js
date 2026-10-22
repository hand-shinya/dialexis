// 深掘りのプロンプトの原型を、その場に文脈つきで出す（所有者 2026-10-23・プレビュー ?preview=1）。応答は固定値（決定論）。
// 所有者の操作: 実存 → アリストテレス → 深掘り探索プロンプト で、別ページに名前だけが入り、目的は空、プロンプトは未表示だった。
// 守ること:
//  ①地図の語の「深掘り」は、ページを移らずにパネルで開き、押す前からプロンプトの原型が出る
//  ②原型の依頼には、地図の中心の語・辿った経路・関係の根拠の文が渡される
//  ③パネルの中の「深掘り探索プロンプト」リンクも、ページを移らずにその場で開く
//  ④別ページ（/deepsearch）も、語が入って着いたら押す前に原型を出し、中心の語を渡す
//  ⑤通常表示では、従来の「深掘り」（視点を選ぶ面）のまま
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
const BASE = process.argv[2] || "http://127.0.0.1:8099";
const ORIGIN = (q) => ({ query: q, lang: "ja", queried_at: "t", word: { query: q }, found: true, resolved_from: null, resolved_to: q,
  suggestions: [], dimensions: [], general_meaning: ["意味"], concept_origin: [], collapse_warning: null, chain: [], relations_typed: [], breadth: [],
  breadth_count: 0, associated: [], originators: [], relations: { near: [], opposite: [] }, named_after: [], senses: [], canon: {}, sources: [],
  confidence: {}, segment_layers: [], language_bridge: { applied: false }, qid: "Q1" });
const GRAPH = (q) => ({ query: q, note: "fx", nodes: [{ id: "root", label: q, kind: "word", layer: 1, weight: 3, q },
  { id: "d1", label: "専門・思想の意味", kind: "domain", layer: 2, weight: 1.4 },
  { id: "p1", label: "ある哲学者", kind: "author", layer: 3, weight: 2, work: "ある著作", year: 300 },
  { id: "a2", label: "子2", kind: "related", layer: 3, weight: 1, q: "子2" }, { id: "a3", label: "子3", kind: "related", layer: 3, weight: 1, q: "子3" }],
  edges: [{ from: "root", to: "d1" }, { from: "d1", to: "p1" }, { from: "d1", to: "a2" }, { from: "d1", to: "a3" }] });
const REL = { forward: { article: "中心語の記事", url: "u", retrieved_at: "2026-10-22T00:00:00+00:00", sentences: ["ある哲学者は中心語を本質に抗する概念とした。"], looked_for: ["ある哲学者"] }, backward: null, errors: [] };
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const fresh = async () => {
    const ctx = await b.newContext({ viewport: { width: 1600, height: 1000 } }); const p = await ctx.newPage();
    p.on("pageerror", e => console.log("pageerror", e.message.slice(0, 200)));
    const json = (r, o) => r.fulfill({ contentType: "application/json", body: JSON.stringify(o) });
    p._bodies = [];
    await p.route(/\/api\/deepsearch\/services/, r => json(r, [{ id: "generic", label: "汎用" }, { id: "claude", label: "Claude" }]));
    await p.route(/\/api\/deepsearch$/, r => { const body = JSON.parse(r.request().postData() || "{}"); p._bodies.push(body);
      return json(r, { service: body.service, level0: `# 調査依頼: 「${body.center}」と「${body.topic}」のつながり\n経路: ${(body.path || []).join(" → ")}\n根拠: ${(body.evidence || []).map(e => e.text).join(" / ")}`, level2: null }); });
    await p.route(/\/api\/origin\/graph\?/, r => json(r, GRAPH(new URL(r.request().url()).searchParams.get("q"))));
    await p.route(/\/api\/origin\?/, r => json(r, ORIGIN(new URL(r.request().url()).searchParams.get("q"))));
    await p.route(/\/api\/relation\?/, r => json(r, REL));
    await p.route(/\/api\/(pivot|dimensions|anatomy|bridge|collocations)\?/, r => json(r, { data: { input_candidates: [], concept: null }, found: false, dimensions: [], relations: {}, keyless: [], llm: [] }));
    return { ctx, p };
  };
  const ready = async (p, pv) => {
    await p.goto(`${BASE}/origin?q=${encodeURIComponent("中心語")}&lang=ja${pv}`, { waitUntil: "domcontentloaded" });
    await p.waitForFunction(() => window.__dx && window.__dx.G && window.__dx.G.nodes.length >= 5, null, { timeout: 20000 });
    await p.waitForTimeout(2000);
  };
  const nodeAt = (p, label) => p.evaluate((lb) => { const G = window.__dx.G, r = G.cv.getBoundingClientRect(); const n = G.nodes.find(x => x.label === lb);
    return { x: r.left + n.x * G.view.k + G.view.x, y: r.top + n.y * G.view.k + G.view.y }; }, label);

  let { ctx, p } = await fresh();
  await ready(p, "&preview=1");
  const url0 = p.url();
  let pos = await nodeAt(p, "ある哲学者");
  await p.mouse.click(pos.x, pos.y); await p.waitForSelector("#radial-menu .rad-item", { timeout: 4000 });
  await p.click("#radial-menu .rad-more"); await p.waitForTimeout(250);
  await p.click("#radial-menu .rad-item[data-action='deepsearch']");
  await p.waitForFunction(() => { const x = document.querySelector(".dsp-out"); return x && /調査依頼/.test(x.value); }, null, { timeout: 8000 }).catch(() => {});
  const out = await p.$eval(".dsp-out", e => e.value).catch(() => "");
  ok("① ページを移らず、パネルで開き、押す前から原型が出る", p.url() === url0 && /調査依頼: 「中心語」と「ある哲学者」のつながり/.test(out), out.slice(0, 60));
  const body = p._bodies[p._bodies.length - 1] || {};
  ok("② 依頼に中心の語・経路・根拠の文が渡される", body.center === "中心語" && body.topic === "ある哲学者" && (body.path || []).some(x => /中心語/.test(x)) && (body.evidence || []).some(e => /本質に抗する/.test(e.text) && e.article === "中心語の記事"), JSON.stringify({ c: body.center, p: body.path, e: (body.evidence || []).length }));
  const ctxText = await p.$eval(".dsp-ctx", e => e.innerText).catch(() => "");
  ok("② 依頼文に入れた文脈が、パネルに見える形で示される", /中心語/.test(ctxText) && /根拠の文：1/.test(ctxText), ctxText.replace(/\n/g, " / ").slice(0, 80));
  await p.fill(".dsp-goal", "第一の目的を書き足す。"); await p.click(".dsp-regen"); await p.waitForTimeout(600);
  ok("① 目的を書き足して作り直すと、目的も依頼に入る", (p._bodies[p._bodies.length - 1] || {}).goal === "第一の目的を書き足す。");
  // ③ パネルの中のリンク
  await p.evaluate(() => document.querySelectorAll(".gp-x").forEach(x => x.click()));
  await p.evaluate(() => { const G = window.__dx.G; const n = G.nodes.find(x => x.label === "ある哲学者"); return dispatchAction("authorNote", n, currentViewState(), { surface: "radial", node: n }); });
  await p.waitForSelector("a.ds-inline", { timeout: 4000 }).catch(() => {});
  const n0 = p._bodies.length;
  await p.click("a.ds-inline");
  await p.waitForFunction((n) => document.querySelector(".dsp-out") && window.__dx.lastDispatch && window.__dx.lastDispatch.actionId === "deepsearch", n0, { timeout: 6000 }).catch(() => {});
  await p.waitForTimeout(500);
  const ld = await p.evaluate(() => { const d = window.__dx.lastDispatch; return d && { a: d.actionId, s: d.surface }; });
  ok("③ パネルの中の「深掘り探索プロンプト」リンクも、ページを移らずその場で開く", p.url() === url0 && ld && ld.a === "deepsearch" && ld.s === "panelLink" && p._bodies.length > n0, JSON.stringify(ld));
  await ctx.close();
  // ④ 別ページ
  ({ ctx, p } = await fresh());
  await p.goto(`${BASE}/deepsearch?q=${encodeURIComponent("ある哲学者")}&center=${encodeURIComponent("中心語")}&lang=ja&preview=1`, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => /調査依頼/.test((document.getElementById("ds-result") || {}).innerText || ""), null, { timeout: 8000 }).catch(() => {});
  const pageOut = await p.$eval("#ds-result", e => e.innerText).catch(() => "");
  ok("④ 別ページも、着いたら押す前に原型を出し、中心の語を渡す", /「中心語」と「ある哲学者」のつながり/.test(pageOut) && (p._bodies[0] || {}).center === "中心語", pageOut.slice(0, 60));
  await ctx.close();
  // ⑤ 通常表示
  ({ ctx, p } = await fresh());
  await ready(p, "&preview=0");
  await p.evaluate(() => dispatchAction("deepsearch", { term: "中心語", kind: "word" }, currentViewState(), { surface: "popup" }));
  await p.waitForTimeout(1200);
  ok("⑤ 通常表示では、従来の深掘り（視点を選ぶ面）のまま", !(await p.$(".dsp-out")) && p._bodies.length === 0);
  await ctx.close();
  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
