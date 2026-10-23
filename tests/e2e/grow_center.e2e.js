// 所有者の写し（2026-10-23 09:51）から（プレビュー）。応答は固定値（決定論）。
// 所有者の操作: 実存 → ポストモダンを「その場で広げる」→ 出てきたフロイトの「関係」。
// パネルは「中心命題 実存 → 派生項目 フロイト」と書き、実存主義とフロイトの記事で根拠の文を探して両方0件だった。
// 本番の /api/relation で確かめると、ポストモダンとフロイトなら「ニーチェ、フロイト、ハイデッガーらの思想を源泉とし」の文が在る。
// 守ること:
//  ①広げて出た語の関係は、広げた元の語との関係として探す（地図の中心の語ではなく）
//  ②パネルの見出しに「地図の中心 → 広げた語 → この項目」の道筋が出る
//  ③対象の種類を英語の内部名（author）でなく日本語で出す
//  ④深掘りのプロンプトも、広げた元の語とのつながりとして作る
//  ⑤地図にもとからある語の関係は、従来どおり地図の中心の語と探す
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
const BASE = process.argv[2] || "http://127.0.0.1:8099";
const ORIGIN = (q) => ({ query: q, lang: "ja", queried_at: "t", word: { query: q }, found: true, resolved_from: null, resolved_to: q, suggestions: [], dimensions: [],
  general_meaning: ["意味"], concept_origin: [], collapse_warning: null, chain: [], relations_typed: [], breadth: [], breadth_count: 0, associated: [], originators: [],
  relations: { near: [], opposite: [] }, named_after: [], senses: [], canon: {}, sources: [], confidence: {}, segment_layers: [], language_bridge: { applied: false }, qid: "Q1" });
const GRAPH = (q) => q === "中心語" ? { query: q, note: "fx", nodes: [{ id: "root", label: q, kind: "word", layer: 1, weight: 3, q },
  { id: "d1", label: "専門・思想の意味", kind: "domain", layer: 2, weight: 1.4 },
  { id: "p1", label: "ある哲学者", kind: "author", layer: 3, weight: 2 },
  { id: "a2", label: "広げる語", kind: "related", layer: 3, weight: 1, q: "広げる語" }, { id: "a3", label: "子3", kind: "related", layer: 3, weight: 1, q: "子3" }],
  edges: [{ from: "root", to: "d1" }, { from: "d1", to: "p1" }, { from: "d1", to: "a2" }, { from: "d1", to: "a3" }] }
  : { query: q, note: "fx", nodes: [{ id: "root", label: q, kind: "word", layer: 1, weight: 3, q }, { id: "d1", label: "専門・思想の意味", kind: "domain", layer: 2, weight: 1.4 },
    { id: "g1", label: "別の思想家", kind: "author", layer: 3, weight: 2 }], edges: [{ from: "root", to: "d1" }, { from: "d1", to: "g1" }] };
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const ctx = await b.newContext({ viewport: { width: 1600, height: 1000 } }); const p = await ctx.newPage();
  p.on("pageerror", e => console.log("pageerror", e.message.slice(0, 200)));
  const json = (r, o) => r.fulfill({ contentType: "application/json", body: JSON.stringify(o) });
  const relQ = [], dsBodies = [];
  await p.route(/\/api\/origin\/graph\?/, r => json(r, GRAPH(new URL(r.request().url()).searchParams.get("q"))));
  await p.route(/\/api\/origin\?/, r => json(r, ORIGIN(new URL(r.request().url()).searchParams.get("q"))));
  await p.route(/\/api\/relation\?/, r => { const u = new URL(r.request().url()); relQ.push({ c: u.searchParams.get("center"), t: u.searchParams.get("target") });
    return json(r, { forward: { article: u.searchParams.get("center"), url: "u", retrieved_at: "t", sentences: [], looked_for: [] }, backward: null, errors: [] }); });
  await p.route(/\/api\/deepsearch\/services/, r => json(r, [{ id: "generic", label: "汎用" }]));
  await p.route(/\/api\/deepsearch$/, r => { const body = JSON.parse(r.request().postData() || "{}"); dsBodies.push(body); return json(r, { service: body.service, level0: `# 調査依頼: 「${body.center}」と「${body.topic}」`, level2: null }); });
  await p.route(/\/api\/(pivot|dimensions|anatomy|bridge|collocations|author)\?/, r => json(r, { data: { input_candidates: [], concept: null }, found: false, dimensions: [], relations: {}, keyless: [], llm: [] }));
  await p.goto(`${BASE}/origin?q=${encodeURIComponent("中心語")}&lang=ja&preview=1`, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => window.__dx && window.__dx.G && window.__dx.G.nodes.length >= 5, null, { timeout: 20000 });
  await p.waitForTimeout(1500);
  await p.evaluate(() => { const G = window.__dx.G; const i = G.nodes.findIndex(x => x.label === "広げる語");
    return dispatchAction("expand", G.nodes[i], currentViewState(), { surface: "radial", node: G.nodes[i], nodeIdx: i }); });
  await p.waitForFunction(() => window.__dx.G.nodes.some(x => x.label === "別の思想家"), null, { timeout: 8000 }).catch(() => {});
  await p.evaluate(() => { const G = window.__dx.G; const n = G.nodes.find(x => x.label === "別の思想家");
    return dispatchAction("relationship", n, currentViewState(), { surface: "radial", node: n }); });
  await p.waitForTimeout(1200);
  const last = relQ[relQ.length - 1] || {};
  ok("① 広げて出た語の関係は、広げた元の語との関係として探す", last.c === "広げる語" && last.t === "別の思想家", JSON.stringify(last));
  const hero = await p.$eval(".rel-route", e => e.innerText).catch(() => "");
  ok("② 見出しに「地図の中心 → 広げた語 → この項目」の道筋が出る", /地図の中心\s*中心語\s*→\s*広げた語\s*広げる語\s*→\s*この項目\s*別の思想家/.test(hero), hero.replace(/\s+/g, " "));
  const kind = await p.evaluate(() => { const dl = [...document.querySelectorAll(".rel-dl dt")].find(x => x.textContent === "対象の種類"); return dl ? dl.nextElementSibling.textContent : ""; });
  ok("③ 対象の種類を日本語で出す（author と出さない）", kind === "人物", kind);
  await p.evaluate(() => document.querySelectorAll(".gp-x").forEach(x => x.click()));
  await p.evaluate(() => { const G = window.__dx.G; const n = G.nodes.find(x => x.label === "別の思想家");
    return dispatchAction("deepsearch", { term: n.label, kind: n.kind }, currentViewState(), { surface: "radial", node: n }); });
  await p.waitForTimeout(1200);
  const ds = dsBodies[dsBodies.length - 1] || {};
  ok("④ 深掘りのプロンプトも、広げた元の語とのつながりとして作る", ds.center === "広げる語" && ds.topic === "別の思想家", JSON.stringify({ c: ds.center, t: ds.topic }));
  await p.evaluate(() => document.querySelectorAll(".gp-x").forEach(x => x.click()));
  await p.evaluate(() => { const G = window.__dx.G; const n = G.nodes.find(x => x.label === "ある哲学者");
    return dispatchAction("relationship", n, currentViewState(), { surface: "radial", node: n }); });
  await p.waitForTimeout(1200);
  const l2 = relQ[relQ.length - 1] || {};
  const hero2 = await p.$eval(".rel-route", e => e.innerText).catch(() => "");
  ok("⑤ 地図にもとからある語の関係は、従来どおり地図の中心の語と探す", l2.c === "中心語" && l2.t === "ある哲学者" && /中心命題/.test(hero2), JSON.stringify(l2));
  await ctx.close();
  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
