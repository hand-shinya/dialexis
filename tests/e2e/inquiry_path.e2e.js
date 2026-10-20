// 第1段「探求の経路」（所有者 2026-10-20 承認・プレビュー ?preview=1）を実ブラウザで確かめる。応答は固定値（決定論）。
// 所有者の操作記録（10/20）: 人物を押す→定型文／共起語を押す→その語だけで検索し直し、語1つの行き止まり。
// 守ること:
//  ①関係パネルに、地図のデータの事実と、本文の文（出所つき）が出る
//  ②共起語は、元の語との組のまま読む（中心は変わらない・dispatchAction を通る）
//  ③語の少ない地図に着いたら、元の地図へ戻って組を読み直す道を示す
//  ④探求の軌跡が残り、押すとその段をもう一度開ける
//  ⑤複合語は意味のまとまりに分けて示し、地図にも並べる（語の地図が作れない語でも分けたまとまりから始められる）
//  ⑥地図の中の複合語は、円形メニューの「語を分ける」でその場で分けられる
//  ⑦通常表示（プレビューでない）は従来のまま
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
const BASE = process.argv[2] || "http://127.0.0.1:8099";
const SEG = { "哲学草稿": [{ text: "哲学", role: "lexical_unit", gloss: "", source: "ja.wiktionary" }, { text: "草稿", role: "lexical_unit", gloss: "", source: "ja.wiktionary" }] };
const ORIGIN = (q) => ({ query: q, lang: "ja", queried_at: "t", word: { query: q }, found: q !== "哲学草稿", resolved_from: null, resolved_to: q,
  suggestions: [], dimensions: [], general_meaning: ["意味"], concept_origin: q === "中心語" ? [{ name: "ドイツ語", term: "Zentralwort" }] : [],
  segment_layers: SEG[q] ? [{ level: "whole", units: [{ text: q }] }, { level: "semantic", label: "意味のまとまり", units: SEG[q] }] : [],
  originators: [], associated: [], relations: { near: [], opposite: [] }, named_after: [], chain: [], senses: [], breadth: [], breadth_count: 0,
  canon: {}, sources: [], confidence: {}, language_bridge: { applied: false }, qid: "Q1" });
const GRAPH = {
  "中心語": { query: "中心語", note: "fx", nodes: [
    { id: "root", label: "中心語", kind: "word", layer: 1, weight: 3, q: "中心語" },
    { id: "d1", label: "専門・思想の意味", kind: "domain", layer: 2, weight: 1.4 },
    { id: "a1", label: "ある思想家", kind: "author", layer: 3, weight: 1.5, work: "著作X", year: 1807, term_de: "Urwort" },
    { id: "r1", label: "概念分析方法", kind: "related", layer: 3, weight: 1, q: "概念分析方法" },
    { id: "r2", label: "別の語", kind: "related", layer: 3, weight: 1, q: "別の語" }],
    edges: [{ from: "root", to: "d1" }, { from: "d1", to: "a1" }, { from: "d1", to: "r1" }, { from: "d1", to: "r2" }] },
  "ひとり語": { query: "ひとり語", note: "fx", nodes: [
    { id: "root", label: "ひとり語", kind: "word", layer: 1, weight: 3, q: "ひとり語" },
    { id: "l1", label: "German", kind: "language", layer: 2, weight: 1 }], edges: [{ from: "root", to: "l1" }] },
};
const REL = { center: "中心語", target: "ある思想家", lang: "ja", errors: [],
  forward: { article: "中心語", url: "https://ja.wikipedia.org/wiki/中心語", retrieved_at: "2026-10-20T00:00:00+00:00", sentences: ["ある思想家は中心語を著作Xで論じた。"], looked_for: ["ある思想家"] },
  backward: { article: "ある思想家", url: "https://ja.wikipedia.org/wiki/ある思想家", retrieved_at: "2026-10-20T00:00:00+00:00", sentences: ["彼の中心語の議論はよく知られる。"], looked_for: ["中心語"] } };
const PAIR = { a: "Zentralwort", b: "ひとり語", lang: "de", total: 5, retrieved_at: "2026-10-20T00:00:00+00:00", search_url: "https://de.wikipedia.org/w/index.php?search=x",
  examples: [{ text: "Dem Zentralwort ひとり語 entgegen", article: "Beispiel", url: "https://de.wikipedia.org/wiki/Beispiel" }] };
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const fresh = async () => {
    const ctx = await b.newContext({ viewport: { width: 1366, height: 900 } }); const p = await ctx.newPage();
    p.on("pageerror", e => console.log("pageerror", e.message.slice(0, 200)));
    const json = (r, o, status) => r.fulfill({ status: status || 200, contentType: "application/json", body: JSON.stringify(o) });
    await p.route(/\/api\/origin\/graph\?/, r => { const q = new URL(r.request().url()).searchParams.get("q"); return GRAPH[q] ? json(r, GRAPH[q]) : json(r, { detail: "x" }, 500); });
    await p.route(/\/api\/origin\?/, r => json(r, ORIGIN(new URL(r.request().url()).searchParams.get("q"))));
    await p.route(/\/api\/relation\?/, r => json(r, REL));
    await p.route(/\/api\/pair\?/, r => json(r, PAIR));
    await p.route(/\/api\/collocations\?/, r => json(r, { term: "Zentralwort", relations: { "hat Objekt": [{ word: "ひとり語", freq: 9 }] }, note: "fx" }));
    await p.route(/\/api\/segments\?/, r => json(r, { query: "概念分析方法", units: [{ text: "概念", role: "lexical_unit" }, { text: "分析", role: "lexical_unit" }, { text: "方法", role: "lexical_unit" }] }));
    await p.route(/\/api\/(pivot|dimensions|anatomy|bridge)\?/, r => json(r, { data: { input_candidates: [], concept: null }, found: false, dimensions: [], components: [], keyless: [], llm: [] }));
    return { ctx, p };
  };
  const nodeAt = (p, label) => p.evaluate((lb) => { const G = window.__dx.G, r = G.cv.getBoundingClientRect();
    const n = G.nodes.find(x => x.label === lb); if (!n) return null; return { x: r.left + n.x * G.view.k + G.view.x, y: r.top + n.y * G.view.k + G.view.y }; }, label);
  const ready = async (p, q, pv, min) => {
    await p.goto(`${BASE}/origin?q=${encodeURIComponent(q)}&lang=ja${pv}`, { waitUntil: "domcontentloaded" });
    await p.waitForFunction((m) => window.__dx && window.__dx.G && window.__dx.G.nodes.length >= m, min || 5, { timeout: 20000 });
    await p.waitForTimeout(2200);
  };
  const ld = (p) => p.evaluate(() => { const d = window.__dx.lastDispatch; return d && { a: d.actionId, s: d.surface, t: d.target && d.target.term }; });
  const closePanels = (p) => p.evaluate(() => document.querySelectorAll(".gp-x").forEach(x => x.click()));

  let { ctx, p } = await fresh();
  await ready(p, "中心語", "&preview=1");
  // ① 関係パネル
  let pos = await nodeAt(p, "ある思想家");
  await p.mouse.click(pos.x, pos.y); await p.waitForSelector("#radial-menu .rad-in", { timeout: 4000 });
  await p.click("#radial-menu .rad-item[data-action='relationship']");
  await p.waitForFunction(() => { const e = document.querySelector(".rel-ev"); return e && e.dataset.count != null; }, null, { timeout: 8000 }).catch(() => {});
  const relText = await p.evaluate(() => { const h = document.querySelector(".rel-hero"); return h ? h.closest(".gp-body").innerText : ""; });
  ok("① 関係パネルに、地図のデータの事実（著作・年・原語）が出る", /著作X/.test(relText) && /1807/.test(relText) && /Urwort/.test(relText));
  ok("① 関係パネルに、本文の文が出所と取得時刻つきで出る（定型文でない）", /ある思想家は中心語を著作Xで論じた/.test(relText) && /Wikipedia「中心語」/.test(relText) && /取得 2026-10-20/.test(relText) && !/ここで分けて読むこと/.test(relText));
  await closePanels(p);
  // ② 共起語を組で読む
  await p.click("#tm-radial"); await p.waitForSelector("#radial-menu .rad-in", { timeout: 4000 });
  await p.click("#radial-menu .rad-more");
  await p.click("#radial-menu .rad-item[data-action='colloc']");
  await p.waitForSelector(".colloc-pair", { timeout: 8000 });
  await p.click(".colloc-pair");
  await p.waitForFunction(() => { const e = document.querySelector(".pair-ex"); return e && e.dataset.count != null; }, null, { timeout: 8000 }).catch(() => {});
  let d = await ld(p);
  ok("② 共起語を押すと、組のまま読むパネルが開く（dispatchAction・surface=colloc）", d && d.a === "pair" && d.s === "colloc" && d.t === "ひとり語", JSON.stringify(d));
  ok("② 組の用例文が出て、中心は変わらない", /Dem Zentralwort ひとり語 entgegen/.test(await p.$eval(".pair-ex", e => e.innerText).catch(() => "")) && await p.evaluate(() => window.__dx.G.rootQ) === "中心語");
  // ③ 行き止まりの回避
  await p.click(".pair-solo");
  await p.waitForFunction(() => window.__dx.G && window.__dx.G.rootQ === "ひとり語", null, { timeout: 10000 }).catch(() => {});
  await p.waitForSelector("#dx-small-map .sm-back", { timeout: 6000 }).catch(() => {});
  const sm = await p.$eval("#dx-small-map", e => e.innerText).catch(() => "");
  ok("③ 語の少ない地図に着くと、元の地図に戻って組で読む道が示される", /小さめ/.test(sm) && /「中心語」に戻り/.test(sm) && /組で読む/.test(sm), sm.slice(0, 80));
  await p.click("#dx-small-map .sm-back");
  await p.waitForFunction(() => window.__dx.G && window.__dx.G.rootQ === "中心語", null, { timeout: 10000 }).catch(() => {});
  await p.waitForTimeout(800);
  d = await ld(p);
  ok("③ 戻ると、元の地図の上で組のパネルが開き直る", await p.evaluate(() => window.__dx.G.rootQ) === "中心語" && d && d.a === "pair" && d.s === "trail", JSON.stringify(d));
  await closePanels(p);
  // ④ 探求の軌跡
  const steps = await p.$$eval("#dx-trail .tr-step", xs => xs.map(x => x.textContent));
  ok("④ 探求の軌跡に、中心・関係・組・移った語が順に残る", steps.length >= 4 && /中心語/.test(steps[0]) && steps.some(s => /関係.*ある思想家/.test(s)) && steps.some(s => /組.*ひとり語/.test(s)) && steps.some(s => s === "ひとり語"), JSON.stringify(steps));
  const relIdx = steps.findIndex(s => /関係/.test(s));
  await p.click(`#dx-trail .tr-step[data-i="${relIdx}"]`);
  await p.waitForTimeout(800);
  d = await ld(p);
  ok("④ 軌跡の段を押すと、その段をもう一度開く（surface=trail）", d && d.a === "relationship" && d.s === "trail" && d.t === "ある思想家", JSON.stringify(d));
  await closePanels(p);
  // ⑥ 語を分ける
  const n0 = await p.evaluate(() => window.__dx.G.nodes.length);
  pos = await nodeAt(p, "概念分析方法");
  await p.mouse.click(pos.x, pos.y); await p.waitForSelector("#radial-menu .rad-in", { timeout: 4000 });
  const hasSplit = !!(await p.$("#radial-menu .rad-item[data-action='split']"));
  if (hasSplit) await p.click("#radial-menu .rad-item[data-action='split']");
  await p.waitForFunction((n) => window.__dx.G.nodes.length > n, n0, { timeout: 6000 }).catch(() => {});
  const parts = await p.evaluate(() => window.__dx.G.nodes.filter(x => x.part).map(x => x.label));
  ok("⑥ 地図の中の複合語は「語を分ける」で、中心を変えずにまとまりを並べられる", hasSplit && parts.join() === "概念,分析,方法" && await p.evaluate(() => window.__dx.G.rootQ) === "中心語", JSON.stringify(parts));
  // ⑤ 複合語の分解（語の地図が作れない語）
  await p.goto(`${BASE}/origin?q=${encodeURIComponent("哲学草稿")}&lang=ja&preview=1`, { waitUntil: "domcontentloaded" });
  await p.waitForSelector("#decomp-strip .ds-part", { timeout: 15000 }).catch(() => {});
  await p.waitForFunction(() => window.__dx && window.__dx.G && window.__dx.G.nodes.some(x => x.part), null, { timeout: 15000 }).catch(() => {});
  const strip = await p.$$eval("#decomp-strip .ds-part b", xs => xs.map(x => x.textContent)).catch(() => []);
  const mapParts = await p.evaluate(() => window.__dx.G ? window.__dx.G.nodes.filter(x => x.part).map(x => x.label) : []);
  ok("⑤ 複合語は、地図の上の帯で意味のまとまりに分けて示される（哲学＋草稿）", strip.join() === "哲学,草稿", JSON.stringify(strip));
  ok("⑤ 語の地図が作れない語でも、分けたまとまりを並べた地図から始められる", mapParts.join() === "哲学,草稿" && await p.evaluate(() => getComputedStyle(document.getElementById("origin-graph-wrap")).display) !== "none", JSON.stringify(mapParts));
  await p.click("#decomp-strip .ds-part");
  ok("⑤ 分けたまとまりを押すと、その語の円形メニューが開く", !!(await p.waitForSelector("#radial-menu .rad-in", { timeout: 3000 }).catch(() => null)));
  await ctx.close();

  // ⑦ 通常表示
  ({ ctx, p } = await fresh());
  await ready(p, "中心語", "&preview=0");
  pos = await nodeAt(p, "ある思想家");
  await p.mouse.click(pos.x, pos.y); await p.waitForTimeout(500);
  const relItem = await p.$(".gm-item[data-action='relationship'], .gm-item");
  ok("⑦ 通常表示では、軌跡・分解の帯・円形メニューは出ない", !(await p.$("#dx-trail")) && !(await p.$("#decomp-strip")) && !(await p.$("#radial-menu")) && !!relItem);
  await ctx.close();

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
