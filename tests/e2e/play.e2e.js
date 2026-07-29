// E: 遊び＝おみくじ(ランダム概念へ再中心)・2語をつなぐ(AND)・クイズ(Wikidataから機械生成)。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage();
  const R = [];
  const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };

  await page.goto(`${BASE}/origin?q=%E7%96%8E%E5%A4%96&lang=ja`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  ok("グラフ上部に『遊ぶ』ボタンがある", !!(await page.$("#graph-play")));
  await page.click("#graph-play");
  await page.waitForTimeout(400);
  ok("遊びパネル（つなぐ・おみくじ・クイズ）が出る", (await page.$("#play-omi")) && (await page.$("#play-quiz")) && (await page.$("#play-bridge")));

  // クイズ（疎外）
  await page.click("#play-quiz");
  await page.waitForFunction(() => { const b = document.querySelector("#quiz-rev"); return !!b; }, null, { timeout: 12000 }).catch(() => {});
  const qtext = await page.$eval("#play-out", el => el.textContent).catch(() => "");
  ok("クイズが出題される", /思想家|対立|由来|区別/.test(qtext), `q=${qtext.slice(0, 30)}`);
  await page.click("#quiz-rev").catch(() => {});
  await page.waitForTimeout(300);
  const ans = await page.$eval("#quiz-ans", el => el.textContent).catch(() => "");
  ok("答えを見ると答えが出る", ans.includes("→") && ans.length > 2, `ans=${ans}`);

  // おみくじ（ランダム概念へ再中心）
  const before = await page.evaluate(() => G.rootQ);
  await page.$eval("#play-omi", el => el.click());
  await page.waitForTimeout(8000);
  const after = await page.evaluate(() => G.rootQ);
  ok("おみくじでランダムな概念に再中心する", after && after !== before, `${before} → ${after}`);

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
