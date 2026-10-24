// 所有者の写し（2026-10-24 10:49〜10:56・資本論）から（プレビュー）。応答は固定値（決定論）。
//  ① 地図の最初の取得が失敗しても1回は取り直し、「上の入口から…」で止まらず地図を出す
//     （初めての語は20秒を超えることがあり、最初は地図が出ず「原語から問い直す」で出た）
//  ② この語を立てた・著した人（Wikidata 著者 P50 等）は、分類の箱を介さず中心から直結の太い線と関係の名で描き、円を大きくする
//  ③ 関係パネルは「派生項目」でなく「著者」と言い、証拠を「Wikidata の記載」と示す。凡例が直結の線の意味を言う
//  ④ 通常表示は従来のまま
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
const BASE = process.argv[2] || "http://127.0.0.1:8099";
const ORIGIN = (q) => ({ query: q, lang: "ja", queried_at: "t", word: { query: q }, found: true, resolved_from: null, resolved_to: q, suggestions: [], dimensions: [],
  general_meaning: ["意味"], concept_origin: [], collapse_warning: null, chain: [], relations_typed: [], breadth: [], breadth_count: 0, originators: [], associated: [],
  relations: { near: [], opposite: [] }, named_after: [], senses: [], canon: {}, sources: [], confidence: {}, language_bridge: { applied: false }, qid: "Q1", segment_layers: [] });
const GRAPH = (q) => ({ query: q, note: "fx", nodes: [{ id: "root", label: q, kind: "word", layer: 1, weight: 3, q },
  { id: "dom:phil", label: "専門・思想の意味", kind: "domain", layer: 2, weight: 2.4 },
  { id: "auth:著した人", label: "著した人", kind: "author", layer: 4, weight: 4, role: "originator", role_prop: "P50", role_label: "著者", search: "著した人" },
  { id: "w1", label: "その人の別の著作", kind: "work", layer: 5, weight: 0.8, q: "その人の別の著作" },
  { id: "auth:関連の人", label: "関連の人", kind: "author", layer: 4, weight: 2, in_body: true },
  { id: "auth:枠の人", label: "枠の人", kind: "author", layer: 4, weight: 2, in_body: false },
  { id: "opp", label: "別物の語", kind: "opposite", layer: 3, weight: 1.1, q: "別物の語" },
  { id: "r1", label: "子", kind: "related", layer: 3, weight: 1, q: "子" }],
  edges: [{ from: "root", to: "dom:phil" }, { from: "dom:phil", to: "auth:著した人", strength: 1.4 }, { from: "auth:著した人", to: "w1" },
    { from: "dom:phil", to: "auth:関連の人" }, { from: "dom:phil", to: "r1" }, { from: "dom:phil", to: "auth:枠の人" },
    { from: "auth:関連の人", to: "auth:枠の人", strength: 1.1 }, { from: "root", to: "opp", strength: 0.7 }] });
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const mk = async (failFirst) => {
    const ctx = await b.newContext({ viewport: { width: 1600, height: 1000 } });
    const json = (r, o) => r.fulfill({ contentType: "application/json", body: JSON.stringify(o) });
    let n = 0;
    await ctx.route(/\/api\/origin\/graph\?/, r => { n++; if (failFirst && n === 1) return r.fulfill({ status: 504, body: "timeout" }); return json(r, GRAPH(new URL(r.request().url()).searchParams.get("q"))); });
    await ctx.route(/\/api\/origin\?/, r => json(r, ORIGIN(new URL(r.request().url()).searchParams.get("q"))));
    await ctx.route(/\/api\/relation\?/, r => json(r, { forward: { article: "中心語", url: "u", retrieved_at: "t", sentences: ["中心語は著した人の著作である。"], looked_for: ["著した人"] }, backward: null, errors: [] }));
    await ctx.route(/\/api\/(pivot|dimensions|anatomy|bridge|collocations|author|segments)\?/, r => json(r, { data: { input_candidates: [], concept: null }, found: false, dimensions: [], relations: {}, keyless: [], llm: [], units: [] }));
    const p = await ctx.newPage(); p.on("pageerror", e => console.log("pageerror", e.message.slice(0, 200)));
    return { ctx, p, count: () => n };
  };
  let { ctx, p, count } = await mk(true);
  await p.goto(`${BASE}/origin?q=${encodeURIComponent("中心語")}&lang=ja&preview=1`, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => window.__dx && window.__dx.G && window.__dx.G.nodes.length >= 5, null, { timeout: 25000 }).catch(() => {});
  await p.waitForTimeout(2000);
  const thin = await p.evaluate(() => { const t = document.getElementById("graph-thin"); return !!t && t.style.display === "block"; });
  const hasMap = await p.evaluate(() => !!(window.__dx.G && window.__dx.G.nodes.length >= 5));
  ok("① 地図の最初の取得が失敗しても取り直して地図を出す（「上の入口から…」で止まらない）", hasMap && !thin && count() >= 2, `requests=${count()} thin=${thin}`);
  const o = await p.evaluate(() => { const G = window.__dx.G; const i = G.nodes.findIndex(n => n.label === "著した人"), j = G.nodes.findIndex(n => n.label === "関連の人"), root = G.nodes.findIndex(n => n.layer === 1);
    const e = G.edges.find(e => (e.a === root && e.b === i) || (e.b === root && e.a === i));
    return { direct: !!e, rel: e && e.rel, label: e && e.label, layer: G.nodes[i].layer, r: G.nodes[i].r, rOther: G.nodes[j].r, viaDomain: G.edges.some(x => G.nodes[x.a].kind === "domain" && x.b === i), workParent: G.nodes[G.parent[G.nodes.findIndex(n => n.label === "その人の別の著作")]].label }; });
  ok("② 著者は分類の箱を介さず中心から直結し、線に関係の名（著者）を持つ", o.direct && o.rel === "originator" && o.label === "著者" && !o.viaDomain && o.layer === 2, JSON.stringify(o));
  ok("② 著者の円は、ほかの思想家より大きい／著作は著者の先に残る", o.r >= 17 && o.r > o.rOther && o.workParent === "著した人", JSON.stringify(o));
  await p.evaluate(() => { const G = window.__dx.G; const n = G.nodes.find(x => x.label === "著した人"); return dispatchAction("relationship", n, currentViewState(), { surface: "radial", node: n }); });
  await p.waitForTimeout(1200);
  const hero = await p.$eval(".rel-route", e => e.innerText).catch(() => ""), ev = await p.$eval(".rel-evidence", e => e.innerText).catch(() => "");
  ok("③ 関係パネルは「著者」と言い、証拠を「Wikidata の記載」と示す", /著者/.test(hero) && !/派生項目/.test(hero) && ev === "Wikidata の記載", hero.replace(/\s+/g, " ") + " / " + ev);
  const lg = await p.$eval(".dx-legend .lg-orig", e => e.innerText).catch(() => "");
  ok("③ 凡例が直結の太い線の意味（Wikidata 著者 P50 等）を言う", /著者 P50/.test(lg), lg.slice(0, 50));
  // ⑤ 所有者の写し 11:12: 戻る・進む・見方の切替でも、最初の描画と同じ組み直し（案内枠だけの思想家の束・著者の直結）を通す
  await p.evaluate(() => document.querySelectorAll(".gp-x").forEach(x => x.click()));
  await p.evaluate(() => applyLensBuild("all"));
  await p.waitForTimeout(800);
  const re = await p.evaluate(() => { const G = window.__dx.G; const w = G.nodes.find(n => n.label === "枠の人"), g = G.nodes.find(n => n.tplGroup), i = G.nodes.findIndex(n => n.label === "著した人");
    return { group: !!g, hidden: !!(w && w.hidden), direct: G.edges.some(e => e.rel === "originator" && (e.a === i || e.b === i)) }; });
  ok("⑤ 戻る・進む・見方の切替の経路でも、束（線ごと畳む）と著者の直結が保たれる", re.group && re.hidden && re.direct, JSON.stringify(re));
  // ⑥ 中心に直接つながる個々の語（対立・区別）は幹の太さにしない
  const w = await p.evaluate(() => ({ opp: _dxEdgeWidth(1, { kind: "opposite" }), trunk: _dxEdgeWidth(1, { kind: "domain" }) }));
  ok("⑥ 対立・区別の語への線は細く（幹の太さは中心→分類の箱だけ）、凡例がそう言う", w.opp < 2 && w.trunk > 4 && /強い結びつきではありません/.test(await p.$eval(".dx-legend", e => e.innerText)), JSON.stringify(w));
  // ⑦ 一度開いた語の印は灰色の点線（著者の二重の輪と別）で、凡例がそう言う
  await p.evaluate(() => { const G = window.__dx.G; const n = G.nodes.find(x => x.label === "子"); return dispatchAction("meaning", { term: "子", label: "子", kind: "related" }, currentViewState(), { surface: "radial", node: n }); });
  await p.waitForTimeout(1200);
  ok("⑦ 一度開いた語の印を、凡例が「関係の強さとは別の印」と言う", /灰色の点線の輪＝この探求で一度開いた語/.test(await p.$eval(".dx-legend", e => e.innerText)));
  await ctx.close();
  ({ ctx, p } = await mk(false));
  await p.goto(`${BASE}/origin?q=${encodeURIComponent("中心語")}&lang=ja&preview=0`, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => window.__dx && window.__dx.G && window.__dx.G.nodes.length >= 5, null, { timeout: 20000 }).catch(() => {});
  await p.waitForTimeout(1500);
  const o0 = await p.evaluate(() => { const G = window.__dx.G; const i = G.nodes.findIndex(n => n.label === "著した人"); return G.edges.some(x => G.nodes[x.a].kind === "domain" && x.b === i); });
  ok("④ 通常表示は従来のまま（著者も分類の箱の下）", o0);
  await ctx.close();
  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
