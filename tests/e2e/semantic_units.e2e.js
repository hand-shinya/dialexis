// 意味単位の実API形状と、解剖/意味Actionの表示優先順位を確認する。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8815";

const LAYERS = [
  { level: "whole", label: "語全体", priority: 0, units: [{ text: "非有機的肉体", role: "whole_term", children: ["非", "有", "機", "的", "肉", "体"], source: "user-term", confidence: "high" }] },
  { level: "semantic", label: "意味のまとまり", priority: 1, units: [
    { text: "非", role: "prefix", gloss: "否定・非〜", children: ["非"], source: "curated-semantic-boundary", confidence: "high" },
    { text: "有機的", role: "lexical_unit", children: ["有", "機", "的"], source: "curated-semantic-boundary", confidence: "high" },
    { text: "肉体", role: "lexical_unit", children: ["肉", "体"], source: "curated-semantic-boundary", confidence: "high" },
  ] },
  { level: "character", label: "文字構成（補助）", priority: 3, units: [
    { text: "非", role: "character", gloss: "not", children: [], source: "Wiktionary", confidence: "grounded" },
    { text: "有", role: "character", gloss: "have", children: [], source: "Wiktionary", confidence: "grounded" },
    { text: "機", role: "character", gloss: "machine", children: [], source: "Wiktionary", confidence: "grounded" },
    { text: "的", role: "character", gloss: "target", children: [], source: "Wiktionary", confidence: "grounded" },
    { text: "肉", role: "character", gloss: "flesh", children: [], source: "Wiktionary", confidence: "grounded" },
    { text: "体", role: "character", gloss: "body", children: [], source: "Wiktionary", confidence: "grounded" },
  ] },
];

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const R = [];
  const ok = (name, condition, detail) => { R.push(condition); console.log(`${condition ? "PASS" : "FAIL"}  ${name}${detail ? " — " + detail : ""}`); };

  const apiResponse = await fetch(`${BASE}/api/anatomy?q=${encodeURIComponent("非有機的肉体")}&lang=ja&own=1`);
  const apiData = await apiResponse.json();
  const apiSemantic = (apiData.segment_layers || []).find(x => x.level === "semantic");
  ok("実API: 意味層が返る", apiResponse.ok && !!apiSemantic, `status=${apiResponse.status}`);
  ok("実API: 非/有機的/肉体の順序", JSON.stringify((apiSemantic && apiSemantic.units || []).map(x => x.text)) === JSON.stringify(["非", "有機的", "肉体"]));
  ok("実API: character層は別の補助層", (apiData.segment_layers || []).some(x => x.level === "character" && x.priority > apiSemantic.priority));

  await page.route("**/api/origin/graph**", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ query: "非有機的肉体", nodes: [{ id: "root", label: "非有機的肉体", kind: "word", layer: 1, q: "非有機的肉体", weight: 3 }], edges: [], note: "fixture" }) }));
  await page.route("**/api/origin?**", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ query: "非有機的肉体", general_meaning: ["身体をめぐる概念"], segment_layers: LAYERS, breadth: [], concept_origin: [], sources: [] }) }));
  await page.route("**/api/anatomy**", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ query: "非有機的肉体", term: "非有機的肉体", segment_layers: LAYERS, components: LAYERS[2].units.map(u => ({ part: u.text, meaning: u.gloss })), chain: [], summary: "", wiktionary_url: "https://en.wiktionary.org/wiki/%E9%9D%9E%E6%9C%89%E6%A9%9F%E7%9A%84%E8%82%89%E4%BD%93" }) }));
  await page.goto(`${BASE}/origin?q=${encodeURIComponent("非有機的肉体")}&lang=ja`, { waitUntil: "networkidle" });
  await page.evaluate(() => gAnatomyPanel("非有機的肉体"));
  await page.waitForSelector("#graph-panel .segment-primary", { timeout: 8000 });
  const body = await page.locator("#graph-panel .gp-body").innerText();
  ok("解剖Action: 意味のまとまりを主表示", /意味のまとまり（優先）/.test(body));
  ok("解剖Action: 非/有機的/肉体が連続して表示", /非[\s\S]*有機的[\s\S]*肉体/.test(body));
  ok("解剖Action: 文字辞書義は補助の開閉面", /文字辞書義（補助）を開く/.test(body));

  await page.evaluate(() => __dx.dispatch("meaning", { term: "非有機的肉体" }, { surface: "test" }));
  await page.waitForSelector("#graph-panel .segment-primary", { timeout: 8000 });
  const meaning = await page.locator("#graph-panel .gp-body").innerText();
  ok("意味Action: 同じ意味層を再利用", /意味のまとまり（優先）/.test(meaning) && /有機的/.test(meaning));

  await page.evaluate(() => gContrastPanel("非有機的肉体"));
  await page.waitForSelector("#graph-panel .contrast .segment-primary", { timeout: 8000 });
  const contrast = await page.locator("#graph-panel .gp-body").innerText();
  ok("並置Action: 意味層だけでも結果面を構築", /原語の意味空間/.test(contrast) && /意味のまとまり（優先）/.test(contrast));
  ok("並置Action: 意味単位を文字義へ降格しない", /非[\s\S]*有機的[\s\S]*肉体/.test(contrast));

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
