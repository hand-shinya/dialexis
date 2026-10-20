// メニューの結果の価値（所有者 2026-10-21・プレビュー ?preview=1）を実ブラウザで確かめる。応答は固定値（決定論）。
// 所有者:「選んだメニューの結果が伴っていない。意味不明なボックスが開き、フランス語などの展開が多いが価値が認められない」。
// 守ること:
//  ①データの無い見方（埋もれた原語など）は、別の欄の中身を写さず「0件」と、データの在る見方（数つき）を示す
//  ②その「データの在る見方」を押すと、その見方が開く（dispatchAction・surface=emptyPanel）
//  ③多言語は「その言語の言葉で言い直した語」を先に、綴りの近い借用は畳んで後に置く
//  ④Wikipedia の転送（実存→実存主義）を、語のカードと意味のパネルで明示する
//  ⑤円形メニューは結果の数を示し、0件の見方を内側の輪に置かない
//  ⑥通常表示（プレビューでない）は従来のまま
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
const BASE = process.argv[2] || "http://127.0.0.1:8099";
const ORIGIN = (q) => ({ query: q, lang: "ja", queried_at: "t", word: { query: q }, found: true, resolved_from: null, resolved_to: "テスト主義",
  redirected_to: "テスト主義", dict_gloss_en: ["testness"], suggestions: [], dimensions: [],
  general_meaning: ["実際にテストであること。"], concept_origin: [{ name: "英語", term: "testism" }], collapse_warning: null, chain: [],
  relations_typed: [{ qid: "Q2", label: "上位の語", rel: "P279", direction: "out", declared_by: "this", reading: "{a} は {b} の下位概念", source: "https://www.wikidata.org/wiki/Q1#P279" }],
  breadth: [
    { name: "アイスランド語", term: "prófstefna", kind: "own", via: "wikidata" },
    { name: "ウェールズ語", term: "Profiaeth", kind: "own", via: "wikidata" },
    { name: "中国語", term: "测试主义", kind: "unknown", via: "wikidata" },
    { name: "スペイン語", term: "testismo", kind: "loan", via: "wikidata" },
    { name: "イタリア語", term: "testismo", kind: "loan", via: "wikidata" }],
  breadth_count: 5, segment_layers: [], originators: [], associated: [], relations: { near: [], opposite: [] }, named_after: [], senses: [],
  canon: {}, sources: [], confidence: {}, language_bridge: { applied: false }, qid: "Q1" });
const GRAPH = (q) => ({ query: q, note: "fx", nodes: [
  { id: "root", label: q, kind: "word", layer: 1, weight: 3, q },
  { id: "d1", label: "専門・思想の意味", kind: "domain", layer: 2, weight: 1.4 },
  { id: "a1", label: "子の語", kind: "related", layer: 3, weight: 1, q: "子の語" },
  { id: "a2", label: "別の子", kind: "related", layer: 3, weight: 1, q: "別の子" },
  { id: "a3", label: "三つ目", kind: "related", layer: 3, weight: 1, q: "三つ目" }],
  edges: [{ from: "root", to: "d1" }, { from: "d1", to: "a1" }, { from: "d1", to: "a2" }, { from: "d1", to: "a3" }] });
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const fresh = async () => {
    const ctx = await b.newContext({ viewport: { width: 1366, height: 900 } }); const p = await ctx.newPage();
    p.on("pageerror", e => console.log("pageerror", e.message.slice(0, 200)));
    const json = (r, o) => r.fulfill({ contentType: "application/json", body: JSON.stringify(o) });
    await p.route(/\/api\/origin\/graph\?/, r => json(r, GRAPH(new URL(r.request().url()).searchParams.get("q"))));
    await p.route(/\/api\/origin\?/, r => json(r, ORIGIN(new URL(r.request().url()).searchParams.get("q"))));
    await p.route(/\/api\/anatomy\?/, r => json(r, { term: "testism", chain: [], components: [{ part: "test", meaning: "試験" }], summary: "From test + -ism.", segment_layers: [] }));
    await p.route(/\/api\/(pivot|dimensions|bridge|collocations)\?/, r => json(r, { data: { input_candidates: [], concept: null }, found: false, dimensions: [], relations: {}, keyless: [], llm: [] }));
    return { ctx, p };
  };
  const ready = async (p, pv) => {
    await p.goto(`${BASE}/origin?q=${encodeURIComponent("テスト語")}&lang=ja${pv}`, { waitUntil: "domcontentloaded" });
    await p.waitForFunction(() => window.__dx && window.__dx.G && window.__dx.G.nodes.length >= 5, null, { timeout: 20000 });
    await p.waitForSelector(".word-card", { timeout: 15000 }).catch(() => {});
    await p.waitForTimeout(1800);
  };
  const panelText = (p, re) => p.evaluate((src) => { const r = new RegExp(src); const ps = [...document.querySelectorAll(".gp-head b")].filter(b => r.test(b.textContent));
    const h = ps[ps.length - 1]; return h ? h.closest("div").parentElement.querySelector(".gp-body").innerText : ""; }, re.source);
  const closePanels = (p) => p.evaluate(() => document.querySelectorAll(".gp-x").forEach(x => x.click()));

  let { ctx, p } = await fresh();
  await ready(p, "&preview=1");
  // ④ 転送の明示
  const card = await p.$eval(".word-card", e => e.innerText).catch(() => "");
  ok("④ 語のカードに Wikipedia の転送（→テスト主義）と辞書の意味が示される", /記事「テスト主義」に転送/.test(card) && /testness/.test(card), card.slice(0, 120));
  // ① 0件の見方
  await p.evaluate(() => dispatchAction("collapse", { term: "テスト語", label: "テスト語", kind: "word" }, currentViewState(), { surface: "radial" }));
  await p.waitForSelector(".empty-aspect", { timeout: 8000 }).catch(() => {});
  const empty = await panelText(p, /埋没した原語/);
  ok("① 埋もれた原語が0件なら、別の欄（解剖）の中身を写さず0件と示す", /0 件/.test(empty) && !/From test/.test(empty) && !/語源的/.test(empty), empty.slice(0, 100));
  const alts = await p.$$eval(".empty-alt", xs => xs.map(x => x.innerText.replace(/\s+/g, "")));
  ok("① データの在る見方が数つきで示される（意味と関係・多言語）", alts.some(s => /意味と関係2/.test(s)) && alts.some(s => /多言語5/.test(s)) && !alts.some(s => /埋もれた原語/.test(s)), JSON.stringify(alts));
  // ②
  await p.click(".empty-alt[data-a='multilingual']"); await p.waitForTimeout(800);
  const ld = await p.evaluate(() => { const d = window.__dx.lastDispatch; return d && { a: d.actionId, s: d.surface }; });
  ok("② 示された見方を押すと、その見方が開く（surface=emptyPanel）", ld && ld.a === "multilingual" && ld.s === "emptyPanel", JSON.stringify(ld));
  // ③ 多言語
  const multi = await panelText(p, /多言語/);
  const ownIdx = multi.indexOf("言い直した語"), loanIdx = multi.indexOf("借用");
  const loanOpen = await p.evaluate(() => { const d = [...document.querySelectorAll(".bg-more")].find(x => /借用/.test(x.textContent)); return d ? d.open : null; });
  ok("③ 多言語は「その言語の言葉で言い直した語」が先で、借用は後ろに畳まれている", ownIdx >= 0 && loanIdx > ownIdx && /prófstefna/.test(multi) && loanOpen === false, `${ownIdx}/${loanIdx}/${loanOpen}`);
  await closePanels(p);
  // ④ 意味のパネル
  await p.evaluate(() => dispatchAction("meaning", { term: "テスト語", label: "テスト語", kind: "word" }, currentViewState(), { surface: "radial" }));
  await p.waitForTimeout(1200);
  const mean = await panelText(p, /この語の意味/);
  ok("④ 意味のパネルに転送の明示と、型つきの関係（何の下位概念か）が出る", /転送/.test(mean) && /テスト語 は 上位の語 の下位概念/.test(mean), mean.slice(0, 160));
  await closePanels(p);
  // ⑤ 円形メニューの数
  await p.click("#tm-radial"); await p.waitForSelector("#radial-menu .rad-in", { timeout: 4000 });
  await p.waitForTimeout(600);
  const inner = await p.$$eval("#radial-menu .rad-in", xs => xs.map(x => x.dataset.action));
  const counts = await p.$$eval("#radial-menu .rad-item .rad-count", xs => xs.map(x => x.closest(".rad-item").dataset.action + ":" + x.textContent));
  ok("⑤ 円形メニューは0件の見方（埋もれた原語）を内側の輪に置かない", !inner.includes("collapse") && inner.includes("multilingual"), JSON.stringify(inner));
  ok("⑤ 円形メニューに結果の数が付く", counts.includes("multilingual:5") && counts.includes("meaning:2"), JSON.stringify(counts));
  await ctx.close();

  // ⑥ 通常表示
  ({ ctx, p } = await fresh());
  await ready(p, "&preview=0");
  await p.evaluate(() => dispatchAction("collapse", { term: "テスト語", label: "テスト語", kind: "word" }, currentViewState(), { surface: "popup" }));
  await p.waitForTimeout(2500);
  ok("⑥ 通常表示では、0件の見方は従来どおり（0件の表示・数の札・分けた多言語は出ない）", !(await p.$(".empty-aspect")) && !(await p.$(".breadth-grouped")));
  await ctx.close();

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
