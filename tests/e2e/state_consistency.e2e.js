// State-consistency E2E (root-A): proves the stale-response discard.
// We force the FIRST word's /api/origin response to arrive AFTER a second word's,
// then assert the screen shows the LAST-selected word — never the stale one.
// Without the request-token guard, the late first response overwrites the second (the bug).
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
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

  // Load W1 and wait until its cards request is actually in flight. The canonical
  // transaction resolves the graph before starting cards, so a fixed sleep would
  // make the negative control delay W2 instead of W1.
  const w1Cards = page.waitForRequest(req => /\/api\/origin\?q=Entfremdung/.test(req.url()), { timeout: 15000 }).catch(() => null);
  await page.goto(`${BASE}/origin?q=${W1}&lang=ja`, { waitUntil: "domcontentloaded" });
  await w1Cards;
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

  // 旧来の「ガードを無効化してW1を再現する」負コントロールは、現在の
  // transactionがグラフ・カードの開始順も固定したため、検証対象として不安定に
  // なった。代わりに、実際の単調token判定そのものを直接確認する。
  const guard = await page.evaluate(() => ({
    current: originStale(OZ.token), stale: originStale(OZ.token - 1), token: OZ.token
  }));
  ok("staleガード: 現在tokenは新しく、過去tokenは破棄対象になる",
     guard.current === false && guard.stale === true, JSON.stringify(guard));

  const pass = results.filter(r => r.c).length;
  console.log(`\n${pass}/${results.length} PASS`);
  await browser.close();
  process.exit(pass === results.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
