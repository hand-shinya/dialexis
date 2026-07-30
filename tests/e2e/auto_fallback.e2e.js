// A3 自動代替の「別源」規律検証（半田様2026-07-30の是正）:
//   ①anatomy(主=/api/anatomy)が空→代替は未試行の /api/origin を実走行し実データ＋実提供元(Wikidata/Wiktionary)＋時刻を表示（維持）
//   ②meaning(主=/api/origin)が空→代替は /api/origin を再利用せず未試行の /api/anatomy を使い、出所は実提供元(Wiktionary)
//   ③contrast(/api/origin＋/api/anatomy を両方試済)が空→未試行の第三経路が無い＝虚偽の切替文言を出さず続行操作を即表示
//   共通: 出所表示に内部endpoint名(/api/…)を出さない・捏造しない。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8021";

const EMPTY_ANAT = { term: "", components: [], chain: [] };
const REAL_ANAT = { term: "dialectic", components: [{ part: "διά", meaning: "through" }], chain: [{ lang: "Ancient Greek", term: "διαλεκτική", gloss: "" }], summary: "From Ancient Greek.", queried_at: "2026-07-30T00:00:00+00:00", wiktionary_url: "https://en.wiktionary.org/wiki/dialectic" };
const EMPTY_ORIG = { query: "x" };
const REAL_ORIG = { query: "x", general_meaning: ["代替源の実際の意味テキスト"], breadth: [{ name: "独", term: "Testbegriff" }], concept_origin: [{ name: "羅", term: "probare" }], queried_at: "2026-07-30T00:00:00+00:00", wikidata_url: "https://www.wikidata.org/wiki/Q1", sources: [{ source: "concept-node", retrieved_at: "2026-07-30T00:00:00+00:00", error: null }, { source: "wiktionary:trace", retrieved_at: "2026-07-30T00:00:00+00:00", error: null }] };

(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true }); const p = await b.newPage();
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const mode = { anat: EMPTY_ANAT, orig: REAL_ORIG };
  await p.route("**/api/origin/graph**", r => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ query: "テスト語", note: "fx", nodes: [{ id: "n1", label: "テスト語", kind: "word", layer: 1, q: "テスト語" }], edges: [] }) }));
  await p.route("**/api/anatomy**", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(mode.anat) }));
  await p.route("**/api/origin?**", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(mode.orig) }));

  await p.goto(`${B}/origin?q=%E3%83%86%E3%82%B9%E3%83%88%E8%AA%9E&lang=ja`, { waitUntil: "networkidle" });
  await p.waitForTimeout(500);
  const disp = async (a) => { await p.evaluate(() => { const x = document.getElementById("graph-panel"); if (x) x.remove(); }); await p.evaluate((aa) => __dx.dispatch(aa, { term: "テスト語" }, { surface: "test" }), a); await p.waitForTimeout(700); };
  const body = () => p.evaluate(() => { const el = document.querySelector("#graph-panel .gp-body"); return el ? el.innerHTML : ""; });
  const lastLog = () => p.evaluate(() => { const l = __dx.fallbackLog(); return l[l.length - 1] || {}; });

  // ① anatomy(主=/api/anatomy)空 → 代替 /api/origin（未試行）で実データ
  mode.anat = EMPTY_ANAT; mode.orig = REAL_ORIG;
  await disp("anatomy");
  let lg = await lastLog(), h = await body();
  ok("①anatomy空→代替は/api/origin・outcome=success", lg.kind === "anatomy" && lg.alt === "/api/origin" && lg.outcome === "success", JSON.stringify(lg));
  ok("①代替の実データが出て出所は実提供元(Wikidata/Wiktionary)・endpoint名を出さない", /代替源の実際の意味テキスト/.test(h) && /出所：(Wikidata|Wiktionary)/.test(h) && !/\/api\//.test(h), h.match(/自動代替[^<]*/) ? h.match(/自動代替[^<]*/)[0] : "no-line");

  // ② meaning(主=/api/origin)空 → 代替は/api/originを再利用せず/api/anatomy（未試行）
  mode.orig = EMPTY_ORIG; mode.anat = REAL_ANAT;
  await disp("meaning");
  lg = await lastLog(); h = await body();
  ok("②meaning空→代替は/api/anatomy（originを別源として再利用しない）", lg.kind === "meaning" && lg.alt === "/api/anatomy" && lg.outcome === "success", JSON.stringify(lg));
  ok("②出所はWiktionary・endpoint名や/api/originを出さない", /出所：Wiktionary/.test(h) && !/\/api\//.test(h) && /διά/.test(h), h.match(/自動代替[^<]*/) ? h.match(/自動代替[^<]*/)[0] : "no-line");

  // ③ contrast(/api/origin＋/api/anatomy 両方試済)空 → 第三経路なし＝虚偽の切替文言なし・続行操作を即表示
  mode.orig = EMPTY_ORIG; mode.anat = EMPTY_ANAT;
  await disp("contrast");
  lg = await lastLog(); h = await body();
  ok("③contrast空→outcome=no-alt（origin/anatomyを別源として再試行しない）", lg.kind === "contrast" && lg.outcome === "no-alt", JSON.stringify(lg));
  ok("③虚偽の切替文言を出さず、続行操作(nomiss)を即表示", !/自動代替|切り替え/.test(h) && /nomiss-lead/.test(h), h ? "len=" + h.length : "empty");

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
