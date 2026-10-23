// 所有者の写し（2026-10-23 17:27〜17:34）から（プレビュー）。応答は固定値（決定論）。
//  ① 記事の本文に出てこない（案内枠のリンクだけの）思想家は、消さずに、関係パネルでそう告げる
//  ② 地図ではその枝を破線で描き、凡例が破線の意味を言う／原点の欄の名前にも印が付く
//  ③ 助詞「の」は、分解の帯で押せる部分にせず、地図の枝にもしない（ライプニッツ＋の＋記法）
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
const BASE = process.argv[2] || "http://127.0.0.1:8099";
const ORIGIN = (q) => ({ query: q, lang: "ja", queried_at: "t", word: { query: q }, found: true, resolved_from: null, resolved_to: q, suggestions: [], dimensions: [],
  general_meaning: ["意味"], concept_origin: [], collapse_warning: null, chain: [], relations_typed: [], breadth: [], breadth_count: 0, originators: [],
  associated: [{ label: "本文の人", is_person: true, in_body: true }, { label: "枠の人", is_person: true, in_body: false }],
  relations: { near: [], opposite: [] }, named_after: [], senses: [], canon: {}, sources: [], confidence: {}, language_bridge: { applied: false }, qid: "Q1",
  segment_layers: q === "人名の記法" ? [{ level: "whole", units: [{ text: q }] }, { level: "semantic", label: "意味のまとまり", units: [
    { text: "人名", role: "unresolved_unit" }, { text: "の", role: "particle" }, { text: "記法", role: "lexical_unit" }] }] : [] });
const GRAPH = (q) => ({ query: q, note: "fx", nodes: [{ id: "root", label: q, kind: "word", layer: 1, weight: 3, q },
  { id: "dom:phil", label: "専門・思想の意味", kind: "domain", layer: 2, weight: 2.4 },
  { id: "auth:本文の人", label: "本文の人", kind: "author", layer: 4, weight: 2, in_body: true, via_article: "中心語の記事" },
  { id: "auth:枠の人", label: "枠の人", kind: "author", layer: 4, weight: 2, in_body: false, via_article: "中心語の記事" },
  { id: "r1", label: "子", kind: "related", layer: 3, weight: 1, q: "子" }],
  edges: [{ from: "root", to: "dom:phil" }, { from: "dom:phil", to: "auth:本文の人" }, { from: "dom:phil", to: "auth:枠の人" }, { from: "dom:phil", to: "r1" }] });
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const ctx = await b.newContext({ viewport: { width: 1600, height: 1000 } });
  const json = (r, o) => r.fulfill({ contentType: "application/json", body: JSON.stringify(o) });
  await ctx.route(/\/api\/origin\/graph\?/, r => json(r, GRAPH(new URL(r.request().url()).searchParams.get("q"))));
  await ctx.route(/\/api\/origin\?/, r => json(r, ORIGIN(new URL(r.request().url()).searchParams.get("q"))));
  await ctx.route(/\/api\/relation\?/, r => json(r, { forward: { article: "中心語の記事", url: "u", retrieved_at: "t", sentences: [], looked_for: [] }, backward: null, errors: [] }));
  await ctx.route(/\/api\/(pivot|dimensions|anatomy|bridge|collocations|author|segments)\?/, r => json(r, { data: { input_candidates: [], concept: null }, found: false, dimensions: [], relations: {}, keyless: [], llm: [], units: [] }));
  const p = await ctx.newPage(); p.on("pageerror", e => console.log("pageerror", e.message.slice(0, 200)));
  await p.goto(`${BASE}/origin?q=${encodeURIComponent("中心語")}&lang=ja&preview=1`, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => window.__dx && window.__dx.G && window.__dx.G.nodes.length >= 5, null, { timeout: 20000 });
  await p.waitForTimeout(2000);
  const rel = async (label) => { await p.evaluate(() => document.querySelectorAll(".gp-x").forEach(x => x.click()));
    await p.evaluate((lb) => { const G = window.__dx.G; const n = G.nodes.find(x => x.label === lb); return dispatchAction("relationship", n, currentViewState(), { surface: "radial", node: n }); }, label);
    await p.waitForTimeout(1200); return p.$eval(".rel-via-tpl", e => e.innerText).catch(() => ""); };
  const t1 = await rel("枠の人");
  ok("① 本文に出てこない思想家は、関係パネルでそう告げる（記事名つき）", /本文には出てきません/.test(t1) && /中心語の記事/.test(t1), t1.slice(0, 60));
  const t2 = await rel("本文の人");
  ok("① 本文でリンクされている思想家には、その告知を出さない", t2 === "");
  const lg = await p.$eval(".dx-legend", e => e.innerText).catch(() => "");
  ok("② 凡例が破線の意味（案内枠のリンクだけ）を言う", /案内枠のリンクだけ/.test(lg));
  await p.waitForSelector(".assoc-line", { timeout: 8000 }).catch(() => {});
  const card = await p.evaluate(() => [...document.querySelectorAll(".via-tpl")].map(e => (e.previousElementSibling || {}).textContent));
  ok("② 原点の欄で、案内枠だけの名前に印が付く（本文の人には付かない）", card.length === 1 && card[0] === "枠の人", JSON.stringify(card));
  // ④ 所有者の承認（10/23 18:1x）: 本文に出てくる人を先に、案内枠だけの人は消さずに件数つきで畳む
  const grp = await p.evaluate(() => { const G = window.__dx.G; const g = G.nodes.find(n => n.tplGroup); const w = G.nodes.find(n => n.label === "枠の人"), h = G.nodes.find(n => n.label === "本文の人");
    return g && { label: g.label, folded: g.folded, wHidden: !!w.hidden, hHidden: !!h.hidden }; });
  ok("④ 地図: 案内枠だけの思想家は件数つきの束に畳み、本文の人は出したまま", !!grp && /案内枠のリンクだけの思想家 1/.test(grp.label) && grp.folded && grp.wHidden && !grp.hHidden, JSON.stringify(grp));
  const gpos = await p.evaluate(() => { const G = window.__dx.G, r = G.cv.getBoundingClientRect(); const n = G.nodes.find(x => x.tplGroup); return { x: r.left + n.x * G.view.k + G.view.x, y: r.top + n.y * G.view.k + G.view.y }; });
  await p.mouse.click(gpos.x, gpos.y); await p.waitForTimeout(2200);
  const opened = await p.evaluate(() => { const G = window.__dx.G; return !G.nodes.find(n => n.label === "枠の人").hidden && !G.nodes.find(n => n.label === "本文の人").hidden; });
  ok("④ 束を押すと開き、本文の人は隠れない", opened);
  const listOrder = await p.evaluate(() => { const d = document.querySelector(".assoc-line"); if (!d) return null; const f = d.querySelector("details.dx-fold");
    return { head: [...d.querySelectorAll(":scope > a.origin-thinker")].map(a => a.textContent), folded: f ? [...f.querySelectorAll("a.origin-thinker")].map(a => a.textContent) : [], sum: f ? f.querySelector("summary").textContent : "" }; });
  ok("④ 原点の欄: 本文の人を先に出し、案内枠だけの人は件数と理由つきで畳む", !!listOrder && JSON.stringify(listOrder.head) === '["本文の人"]' && JSON.stringify(listOrder.folded) === '["枠の人"]' && /消してはいません/.test(listOrder.sum), JSON.stringify(listOrder));
  await p.goto(`${BASE}/origin?q=${encodeURIComponent("人名の記法")}&lang=ja&preview=1`, { waitUntil: "domcontentloaded" });
  await p.waitForSelector("#decomp-strip", { timeout: 20000 }).catch(() => {});
  await p.waitForTimeout(2500);
  const strip = await p.evaluate(() => { const s = document.getElementById("decomp-strip"); return s && { btn: [...s.querySelectorAll(".ds-part b")].map(x => x.textContent), par: [...s.querySelectorAll(".ds-particle")].map(x => x.textContent) }; });
  ok("③ 助詞「の」は帯に見えるが、押せる部分にしない", !!strip && JSON.stringify(strip.btn) === '["人名","記法"]' && JSON.stringify(strip.par) === '["の"]', JSON.stringify(strip));
  const parts = await p.evaluate(() => window.__dx.G.nodes.filter(n => n.kind === "part").map(n => n.label));
  ok("③ 地図の枝にも「の」を出さない", !parts.includes("の") && parts.includes("記法"), JSON.stringify(parts));
  await ctx.close();
  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
