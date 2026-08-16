// Regression: the human's normal entry path must land on the meaning-space
// Map, not the older source-search surface. The latter remains reachable but
// must explain how to return to the Map.
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8820";
const results = [];

function log(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? " — " + detail : ""}`);
}

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));

  await page.goto(`${BASE}/?lang=ja`, { waitUntil: "domcontentloaded", timeout: 45000 });
  const homeForm = page.locator("form.searchbox").first();
  log("home search action is /origin", (await homeForm.getAttribute("action")) === "/origin");
  log("home names the actual destination", (await homeForm.locator("button").innerText()).includes("意味Map"));
  log("home exposes the Map nav", (await page.locator('a[href="/origin"]').count()) >= 1);
  log("Question Doors point to /origin", (await page.locator('a.qdoor[href^="/origin?q="]').count()) >= 5);

  const q = "非有機的肉体";
  await homeForm.locator('input[name="q"]').fill(q);
  await Promise.all([
    page.waitForURL(u => u.pathname === "/origin" && u.searchParams.get("q") === q, { timeout: 45000 }),
    homeForm.locator("button").click(),
  ]);
  await page.locator("#origin-shell").waitFor({ state: "visible", timeout: 30000 });
  log("home search reaches /origin", new URL(page.url()).pathname === "/origin");
  log("Map shell is visible after home search", await page.locator("#origin-shell").isVisible());
  log("Canvas and common menu surface exist", (await page.locator("#origin-graph").count()) === 1 && (await page.locator("#graph-lens").count()) === 1);

  await page.goto(`${BASE}/explore?q=${encodeURIComponent(q)}&lang=ja`, { waitUntil: "domcontentloaded", timeout: 45000 });
  const bridge = page.locator(".route-bridge");
  const bridgeHref = await bridge.locator("a").getAttribute("href");
  log("secondary /explore identifies itself", (await page.locator("h1").innerText()).includes("資料探索"));
  log("secondary /explore offers a Map return", /意味空間の相関図/.test(await bridge.innerText()) && bridgeHref.includes("/origin?q="));

  log("entry routing has no page errors", errors.length === 0, errors.slice(0, 2).join(" | "));
  const passed = results.filter(x => x.ok).length;
  console.log(`\n=== ${passed}/${results.length} PASS ===`);
  await browser.close();
  process.exit(passed === results.length ? 0 : 2);
})().catch(async e => {
  console.error("E2E ERROR", e);
  process.exit(3);
});
