// 所有者の写し（2026-10-23 02:49〜02:51）から直したもの（プレビュー）。応答は固定値（決定論）。
//  A 語から円形メニュー・パネルへ移ったあと、地図の強調（ほかの語が薄くなる）が残らない
//  B 関係のパネルで、同じ定型の一文を2回出さない
//  C 著作の系譜（人物）に、生没年・主要著作・職業を出す（「整備中」だけにしない）
//  D 翻訳・受容史の自動予備台帳の前置き（どの語でも同じ説明）を、名札と件数つきで畳む
//  E 開いたパネルが、押した語を覆わない
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
const BASE = process.argv[2] || "http://127.0.0.1:8099";
const ORIGIN = (q) => ({ query: q, lang: "ja", queried_at: "t", word: { query: q }, found: true, resolved_from: null, resolved_to: q, suggestions: [], dimensions: [],
  general_meaning: ["意味"], concept_origin: [], collapse_warning: null, chain: [], relations_typed: [], breadth: [], breadth_count: 0, associated: [], originators: [],
  relations: { near: [], opposite: [] }, named_after: [], senses: [], canon: {}, sources: [], confidence: {}, segment_layers: [], language_bridge: { applied: false }, qid: "Q1" });
const GRAPH = (q) => ({ query: q, note: "fx", nodes: [{ id: "root", label: q, kind: "word", layer: 1, weight: 3, q },
  { id: "d1", label: "専門・思想の意味", kind: "domain", layer: 2, weight: 1.4 },
  { id: "p1", label: "ある哲学者", kind: "author", layer: 3, weight: 2, search: "ある哲学者" },
  { id: "a2", label: "子2", kind: "related", layer: 3, weight: 1, q: "子2" }, { id: "a3", label: "子3", kind: "related", layer: 3, weight: 1, q: "子3" }],
  edges: [{ from: "root", to: "d1" }, { from: "d1", to: "p1" }, { from: "d1", to: "a2" }, { from: "d1", to: "a3" }] });
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const ctx = await b.newContext({ viewport: { width: 1600, height: 1000 } }); const p = await ctx.newPage();
  p.on("pageerror", e => console.log("pageerror", e.message.slice(0, 200)));
  const json = (r, o) => r.fulfill({ contentType: "application/json", body: JSON.stringify(o) });
  await p.route(/\/api\/origin\/graph\?/, r => json(r, GRAPH(new URL(r.request().url()).searchParams.get("q"))));
  await p.route(/\/api\/origin\?/, r => json(r, ORIGIN(new URL(r.request().url()).searchParams.get("q"))));
  await p.route(/\/api\/author\?/, r => json(r, { found: true, name: "ある哲学者", works: ["著作甲", "著作乙", "著作丙", "著作丁", "著作戊", "著作己", "著作庚", "著作辛", "著作壬", "著作癸"], born: ["-0384-00-0"], died: ["-0322-00-0"], occupation: ["哲学者", "論理学者"], wikipedia_url: "https://ja.wikipedia.org/wiki/x", wikidata_url: "https://www.wikidata.org/wiki/Q1", queried_at: "2026-10-23T00:00:00" }));
  await p.route(/\/api\/relation\?/, r => json(r, { forward: { article: "中心語", url: "u", retrieved_at: "t", sentences: [], looked_for: [] }, backward: null, errors: [] }));
  await p.route(/\/api\/(pivot|dimensions|anatomy|bridge|collocations)\?/, r => json(r, { data: { input_candidates: [], concept: null }, found: false, dimensions: [], relations: {}, keyless: [], llm: [] }));
  await p.goto(`${BASE}/origin?q=${encodeURIComponent("中心語")}&lang=ja&preview=1`, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => window.__dx && window.__dx.G && window.__dx.G.nodes.length >= 5, null, { timeout: 20000 });
  await p.waitForTimeout(2000);
  const at = await p.evaluate(() => { const G = window.__dx.G, r = G.cv.getBoundingClientRect(); const n = G.nodes.find(x => x.label === "ある哲学者"); return { x: r.left + n.x * G.view.k + G.view.x, y: r.top + n.y * G.view.k + G.view.y }; });
  // A
  await p.mouse.move(at.x - 30, at.y - 30); await p.mouse.move(at.x, at.y, { steps: 4 }); await p.mouse.click(at.x, at.y);
  await p.waitForSelector("#radial-menu .rad-item", { timeout: 4000 });
  await p.click("#radial-menu .rad-more"); await p.waitForTimeout(200);
  await p.click("#radial-menu .rad-item[data-action='relationship']");
  await p.waitForTimeout(1200);
  const hl = await p.evaluate(() => !!window.__dx.G.hl);
  ok("A 円形メニューから項目を選んだあと、地図の強調が残らない（ほかの語が薄いままにならない）", !hl);
  // B
  const relTxt = await p.evaluate(() => { const h = document.querySelector(".rel-hero"); return h ? h.closest(".gp-body").innerText : ""; });
  const lines = relTxt.split(/\n+/).map(x => x.trim()).filter(x => x.length > 20);
  const dup = lines.filter((x, i) => lines.indexOf(x) !== i);
  ok("B 関係のパネルで、同じ文を2回出さない", relTxt.length > 0 && dup.length === 0, dup[0] || "");
  // E
  const cover = await p.evaluate((pt) => { const ps = [...document.querySelectorAll(".gp-body")].map(b => b.parentElement.getBoundingClientRect());
    return ps.some(r => pt.x >= r.left && pt.x <= r.right && pt.y >= r.top && pt.y <= r.bottom); }, at);
  ok("E 開いたパネルが、押した語を覆わない", !cover);
  await p.evaluate(() => document.querySelectorAll(".gp-x").forEach(x => x.click()));
  // C
  await p.evaluate(() => { const G = window.__dx.G; const n = G.nodes.find(x => x.label === "ある哲学者"); return dispatchAction("authorNote", n, currentViewState(), { surface: "radial", node: n }); });
  await p.waitForSelector(".author-facts-t", { timeout: 5000 }).catch(() => {});
  const au = await p.evaluate(() => { const t = document.querySelector(".author-facts-t"); const box = t && t.closest(".gp-body"); return box ? { text: box.innerText, dom: box.textContent } : null; });
  ok("C 著作の系譜に、生没年・主要著作・職業が出る（10件の著作は8件＋残りを畳む）", !!au && /前384年/.test(au.text) && /著作甲/.test(au.text) && au.dom.includes("著作癸") && /論理学者/.test(au.text), au && au.text.slice(0, 80));
  ok("C 「整備中」の一文だけで終わらない", !!au && !/整備中です/.test(au.text));
  // D
  const th = await p.evaluate(() => _thResponseHtml({ status: "discovery", query: "語", note: "自動整理の注記。", honesty: "読み方。", dossier: { title: "語", center_question: "「語」は、誰が、いつ…", scope_note: "範囲の注記。", term_map: [], timeline: [], transformations: [], sources: [], evidence_levels: [] } }));
  ok("D 自動予備台帳の前置きを、名札と件数つきで畳む（消さない）", /dx-fold/.test(th) && /自動予備台帳の前置き/.test(th) && /自動整理の注記/.test(th) && /範囲の注記/.test(th));
  await ctx.close();
  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
