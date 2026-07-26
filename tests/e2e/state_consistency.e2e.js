// State-consistency E2E (root-A): proves the stale-response discard.
// We force the FIRST word's /api/origin response to arrive AFTER a second word's,
// then assert the screen shows the LAST-selected word — never the stale one.
// Without the request-token guard, the late first response overwrites the second (the bug).
const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8011";
const W1 = "Entfremdung", W2 = "Freiheit";

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage();
  const results = [];
  const ok = (n, c, d) => { results.push({ n, c, d }); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };

  // Delay the FIRST cards request (/api/origin?q=...) so W1 resolves late; others pass through.
  let delayedFirst = false;
  await page.route("**/api/origin**", async (route) => {
    const u = route.request().url();
    const isCards = /\/api\/origin\?q=/.test(u);
    if (isCards && !delayedFirst) {
      delayedFirst = true;
      await new Promise(r => setTimeout(r, 1800));   // W1 cards arrive AFTER W2
    }
    return route.continue();
  });

  // Load W1 (its cards request is the delayed one).
  await page.goto(`${BASE}/origin?q=${W1}&lang=ja`, { waitUntil: "domcontentloaded" });
  // Before W1 resolves, select W2 (the universal recenter). W2 must win.
  await page.waitForFunction(() => typeof window.__ozReady !== "undefined" || typeof originRecenter === "function", null, { timeout: 8000 }).catch(()=>{});
  await page.evaluate((w) => originRecenter(w), W2);

  // Wait past the W1 delay so the stale response has definitely arrived.
  await page.waitForTimeout(2600);

  const subject = await page.evaluate(() => {
    const tw = document.querySelector(".word-card .theword");
    const box = document.getElementById("origin-results");
    return { theword: tw ? tw.textContent : "", dsq: box ? box.dataset.q : "",
             ozq: (typeof OZ !== "undefined") ? OZ.q : null,
             oztoken: (typeof OZ !== "undefined") ? OZ.token : null };
  });

  ok("最後に選んだ語(W2)がカード主役に表示される（古いW1で上書きされない）",
     subject.theword.includes(W2), `theword=${subject.theword}`);
  ok("dataset.q が W2（stale W1 応答が破棄された）",
     subject.dsq === W2, `dataset.q=${subject.dsq}`);
  ok("単一真実源 OZ.q が W2 を指す", subject.ozq === W2, `OZ.q=${subject.ozq}`);
  ok("W1 の遅延応答が主役を W1 に戻していない（回帰なし）",
     !subject.theword.includes(W1), `theword=${subject.theword}`);

  // ── Negative control (A2): disable the guard → the OLD bug must reappear (W1 overwrites W2).
  // Proves the request-token guard is load-bearing, not that the test passes trivially.
  const page2 = await browser.newPage();
  let delayed2 = false;
  await page2.route("**/api/origin**", async (route) => {
    const u = route.request().url();
    if (/\/api\/origin\?q=/.test(u) && !delayed2) { delayed2 = true; await new Promise(r => setTimeout(r, 1800)); }
    return route.continue();
  });
  await page2.goto(`${BASE}/origin?q=${W1}&lang=ja`, { waitUntil: "domcontentloaded" });
  await page2.evaluate(() => { window.originStale = () => false; });   // neuter the guard (simulate pre-fix)
  await page2.evaluate((w) => originRecenter(w), W2);
  await page2.waitForTimeout(2600);
  const neg = await page2.evaluate(() => {
    const tw = document.querySelector(".word-card .theword"); return tw ? tw.textContent : "";
  });
  ok("負コントロール: ガード無効化で旧バグ再現（W1がW2を上書き）＝ガードが効いている証明",
     neg.includes(W1), `guard-off theword=${neg}`);

  const pass = results.filter(r => r.c).length;
  console.log(`\n${pass}/${results.length} PASS`);
  await browser.close();
  process.exit(pass === results.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
