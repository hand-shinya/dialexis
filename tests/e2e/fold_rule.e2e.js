// 畳み方の決まり（所有者 2026-10-22「サービス側が必要・不要を先に分けて出さないのは危険。全部出して利用者が取捨選択する」）。
// プレビュー（?preview=1）で、応答は固定値（決定論）。守ること:
//  ①サーバが返した項目は、黙って消えない（畳んでいても画面の文字として在る）
//  ②畳むときは見出しに件数と理由がある
//  ③漢字1字の辞書義の層は消さず、件数つきで畳む
//  ④概念として使わなかった記事（映画など）は、名札をつけて開ける形で示す
//  ⑤通常表示は従来のまま（先頭の件数だけ）
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
const BASE = process.argv[2] || "http://127.0.0.1:8099";
const PEOPLE = Array.from({ length: 30 }, (_, i) => ({ label: `思想家${String(i + 1).padStart(2, "0")}`, is_person: true, qid: "Q9" + i }));
const REL = Array.from({ length: 20 }, (_, i) => ({ qid: "Q8" + i, label: `関係語${String(i + 1).padStart(2, "0")}`, rel: "P279", direction: "out", declared_by: "this", reading: "{a} は {b} の下位概念", source: "https://www.wikidata.org/wiki/Q1" }));
const BR = Array.from({ length: 40 }, (_, i) => ({ name: `言語${i + 1}`, term: `wordform${i + 1}`, kind: i < 5 ? "own" : (i < 15 ? "unknown" : "loan"), via: "wikidata" }));
const ORIGIN = (q) => ({ query: q, lang: "ja", queried_at: "t", word: { query: q }, found: true, resolved_from: null, resolved_to: q,
  rejected_article: "同名の映画", rejected_qid: "Q17231549", suggestions: [], dimensions: [], general_meaning: ["語の意味その一。"],
  concept_origin: [{ name: "英語", term: "testword" }], collapse_warning: null, chain: [], relations_typed: REL, breadth: BR, breadth_count: 40,
  associated: PEOPLE, originators: [], relations: { near: [], opposite: [] }, named_after: [], senses: [], canon: {}, sources: [], confidence: {},
  segment_layers: [{ level: "whole", units: [{ text: q }] }, { level: "semantic", label: "意味のまとまり", units: [{ text: q, role: "whole_term" }] },
    { level: "character", label: "文字構成（補助）", units: [{ text: "試", gloss: "try" }, { text: "験", gloss: "examine" }, { text: "語", gloss: "word" }] }],
  language_bridge: { applied: false }, qid: "Q1" });
const GRAPH = (q) => ({ query: q, note: "fx", nodes: [{ id: "root", label: q, kind: "word", layer: 1, weight: 3, q },
  { id: "d1", label: "専門・思想の意味", kind: "domain", layer: 2, weight: 1.4 }, { id: "a1", label: "子", kind: "related", layer: 3, weight: 1, q: "子" },
  { id: "a2", label: "子2", kind: "related", layer: 3, weight: 1, q: "子2" }, { id: "a3", label: "子3", kind: "related", layer: 3, weight: 1, q: "子3" }],
  edges: [{ from: "root", to: "d1" }, { from: "d1", to: "a1" }, { from: "d1", to: "a2" }, { from: "d1", to: "a3" }] });
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const fresh = async () => {
    const ctx = await b.newContext({ viewport: { width: 1600, height: 1000 } }); const p = await ctx.newPage();
    p.on("pageerror", e => console.log("pageerror", e.message.slice(0, 200)));
    const json = (r, o) => r.fulfill({ contentType: "application/json", body: JSON.stringify(o) });
    await p.route(/\/api\/origin\/graph\?/, r => json(r, GRAPH(new URL(r.request().url()).searchParams.get("q"))));
    await p.route(/\/api\/origin\?/, r => json(r, ORIGIN(new URL(r.request().url()).searchParams.get("q"))));
    await p.route(/\/api\/(pivot|dimensions|anatomy|bridge|collocations)\?/, r => json(r, { data: { input_candidates: [], concept: null }, found: false, dimensions: [], relations: {}, keyless: [], llm: [] }));
    return { ctx, p };
  };
  const open = async (p, pv) => {
    await p.goto(`${BASE}/origin?q=${encodeURIComponent("試験語")}&lang=ja${pv}`, { waitUntil: "domcontentloaded" });
    await p.waitForSelector(".word-card:not(.origin-loading-card)", { timeout: 20000 }).catch(() => {});
    await p.waitForFunction(() => window.__dx && window.__dx.G, null, { timeout: 20000 }).catch(() => {});
    await p.waitForTimeout(1500);
    let ch = null;
    for (const a of ["meaning", "multilingual", "panorama"]) {
      await p.evaluate((a) => dispatchAction(a, { term: "試験語", kind: "word" }, currentViewState(), { surface: "radial" }), a);
      await p.waitForTimeout(1200);
      // 意味のパネルは次の見方で置き換わるので、開いた直後に字の層を確かめる
      if (a === "meaning") ch = await p.evaluate(() => { const d = [...document.querySelectorAll("details.segment-secondary")][0]; return d ? { open: d.open, sum: d.querySelector("summary").textContent, has: d.textContent.includes("examine") } : null; });
    }
    return ch;
  };
  let { ctx, p } = await fresh();
  const ch = await open(p, "&preview=1");
  const dom = await p.evaluate(() => document.documentElement.textContent);
  const missP = PEOPLE.filter(x => !dom.includes(x.label)).map(x => x.label);
  const missR = REL.filter(x => !dom.includes(x.label)).map(x => x.label);
  const missB = BR.filter(x => !dom.includes(x.term)).map(x => x.term);
  ok("① 30人の思想家が、畳んだ中も含めて全員画面に在る（8人で切り捨てない）", missP.length === 0, missP.slice(0, 3).join(","));
  const pano = await p.evaluate(() => { const w = [...document.querySelectorAll(".gp-wide")].pop(); return w ? w.textContent : ""; });
  const missPano = PEOPLE.filter(x => !pano.includes(x.label)).map(x => x.label);
  ok("① 全体像のパネルの中でも、30人全員が在る（ページの別の欄に在るだけでは足りない）", pano.length > 0 && missPano.length === 0, missPano.slice(0, 3).join(","));
  ok("① 20件の型つき関係が全部在る（16件で切り捨てない）", missR.length === 0, missR.slice(0, 3).join(","));
  ok("① 40言語の語形が全部在る", missB.length === 0, missB.slice(0, 3).join(","));
  const folds = await p.evaluate(() => [...document.querySelectorAll(".gp-body details, .gp-wide details")].map(x => (x.querySelector("summary") || {}).textContent || ""));
  const bad = folds.filter(t => !/\d/.test(t) || !/畳/.test(t));
  ok("② 畳んだ見出しには件数と「畳んでいる」理由がある", folds.length >= 3 && bad.length === 0, `${folds.length} 個・不備 ${bad.length}: ${bad.slice(0, 2).join(" | ")}`);
  ok("③ 漢字1字の辞書義の層は消さず、件数つきで畳む", !!ch && !ch.open && /3字/.test(ch.sum) && ch.has, JSON.stringify(ch));
  const note = await p.$eval(".word-card .redirect-note", e => ({ t: e.innerText, a: !!e.querySelector('a[href*="/origin?q="]') })).catch(() => null);
  ok("④ 概念として使わなかった映画の記事を、名札をつけて開ける形で示す", !!note && /同名の映画/.test(note.t) && /消してはいません/.test(note.t) && note.a, note && note.t.slice(0, 80));
  await ctx.close();
  ({ ctx, p } = await fresh());
  await open(p, "&preview=0");
  const dom0 = await p.evaluate(() => document.documentElement.textContent);
  ok("⑤ 通常表示は従来どおり（件数と理由つきの畳みは追加しない）", dom0.includes("思想家08") && !(await p.$(".dx-fold")));
  await ctx.close();
  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
