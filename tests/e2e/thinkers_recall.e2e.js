// Thinkers-recall E2E: for concepts with no P50/P61 (資本主義) the obvious figures
// normal search surfaces (Marx…) must still appear, and the 思想家 lens must not be 0.
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage();
  const R = [];
  const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };

  for (const [q, enc] of [["資本主義", "%E8%B3%87%E6%9C%AC%E4%B8%BB%E7%BE%A9"], ["資本論", "%E8%B3%87%E6%9C%AC%E8%AB%96"]]) {
    await page.goto(`${BASE}/origin?q=${enc}&lang=ja`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1600);
    const card = await page.$eval("#card-origin", el => el.textContent);
    ok(`${q}: 原点カードにカール・マルクスが出る（通常検索の筆頭に到達）`, /マルクス/.test(card), "");
    const authors = await page.evaluate(() => (G && G.nodes ? G.nodes.filter(n => n.kind === "author").length : 0));
    ok(`${q}: 思想家ノードが0でない（思想家レンズがグレーアウトしない）`, authors >= 1, `authors=${authors}`);
    // 思想家レンズが選べる（グレーアウトしない）
    await page.evaluate(()=>{const c=[...document.querySelectorAll("#graph-lens .tm-chip")].find(x=>x.textContent.includes("見方"));if(c)c.click();});
    await page.waitForTimeout(350);
    const thinkersRow = await page.$('.lens-row[data-k="thinkers"]');
    ok(`${q}: 思想家と著作レンズが選択可能（見方に列挙）`, !!thinkersRow);
    await page.evaluate(()=>{const p=document.getElementById("graph-panel");if(p)p.remove();});
  }

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
