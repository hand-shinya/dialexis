// Narrow-screen smoke gate for the public validation path and the graph shell.
// External scholarly APIs are replaced with a minimal grounded fixture here:
// this test measures browser geometry and reachable controls, not live-source
// availability (which is covered by the existing integration suites).
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  const R = [];
  const ok = (name, condition, detail = "") => {
    R.push(Boolean(condition));
    console.log(`${condition ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
  };
  const noHorizontalOverflow = async () => page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));

  await page.goto(`${BASE}/validation?lang=ja`, { waitUntil: "networkidle" });
  ok("第三者検証ページがスマホ幅で表示される", await page.locator("#validation-title").isVisible());
  ok("viewport設定が端末幅を使う", await page.$eval('meta[name="viewport"]', el => /width=device-width/.test(el.content)));
  const validationGeometry = await noHorizontalOverflow();
  ok("検証ページに横スクロールの破綻がない", validationGeometry.scrollWidth <= validationGeometry.clientWidth + 1,
    `${validationGeometry.scrollWidth}/${validationGeometry.clientWidth}`);
  ok("検証ガイドの実行リンクが操作可能", await page.locator('a[href*="/origin?q=Karl%20Marx"]').isVisible());

  await page.route("**/api/origin/graph**", route => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({
      query: "Karl Marx", research_mode: "person", entity_kind: "person",
      nodes: [{ id: "root", label: "カール・マルクス", kind: "author", layer: 1, q: "Karl Marx", weight: 5 }],
      edges: [], note: "mobile fixture", sources: []
    })
  }));
  await page.route("**/api/origin?*", route => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({
      query: "Karl Marx", found: true, subject_kind: "person", general_meaning: [],
      breadth: [], concept_origin: [], associated: [], relations: { near: [], opposite: [] },
      sources: [], dimensions: [], person_profile: null, queried_at: new Date().toISOString()
    })
  }));
  await page.goto(`${BASE}/origin?q=Karl%20Marx&lang=ja`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#origin-shell", { state: "visible", timeout: 15000 });
  await page.waitForTimeout(300);
  const originGeometry = await noHorizontalOverflow();
  ok("意味Mapのスマホ表示に横スクロールの破綻がない", originGeometry.scrollWidth <= originGeometry.clientWidth + 1,
    `${originGeometry.scrollWidth}/${originGeometry.clientWidth}`);
  ok("スマホの主要操作ボタンがタップ可能サイズを持つ", await page.evaluate(() => {
    const ids = ["nav-back", "nav-fwd", "graph-play", "graph-shelf", "graph-fit"];
    return ids.every(id => { const e = document.getElementById(id); if (!e) return false; const r = e.getBoundingClientRect(); return r.height >= 36 && r.width > 0; });
  }));

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
