// D: 収集・経路保存・自分のレンズ（localStorage）。棚に集める・道を保存・観点を作る。
const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage();
  const R = [];
  const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };

  await page.goto(`${BASE}/origin?q=%E7%96%8E%E5%A4%96&lang=ja`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  await page.evaluate(() => { try { localStorage.clear(); } catch (e) {} });

  ok("メニュー共通コアに『棚に追加』がある（普遍）", await page.evaluate(() => gActions({ kind: "word", label: "疎外", q: "疎外" }).some(i => /棚に追加/.test(i.t))));
  ok("グラフ上部に『棚』ボタンがある", !!(await page.$("#graph-shelf")));

  await page.click("#graph-shelf"); await page.waitForTimeout(300);
  ok("棚パネル（集める・道・自分のレンズ）が出る", !!(await page.$("#shelf-add")) && !!(await page.$("#lens-save")));
  // 今の語を棚に追加
  await page.click("#shelf-add"); await page.waitForTimeout(300);
  const shelf = await page.evaluate(() => JSON.parse(localStorage.getItem("dx_shelf") || "[]"));
  ok("今の概念（疎外）が棚に保存される", shelf.includes("疎外"), `shelf=${JSON.stringify(shelf)}`);
  const inList = await page.$$eval(".shelf-go", els => els.map(e => e.textContent));
  ok("棚の一覧に表示される（クリックで再訪）", inList.includes("疎外"));

  // 自分のレンズを保存
  await page.fill("#lens-name", "労働から"); await page.fill("#lens-words", "労働,搾取,賃金");
  await page.click("#lens-save"); await page.waitForTimeout(300);
  const lenses = await page.evaluate(() => JSON.parse(localStorage.getItem("dx_lenses") || "[]"));
  ok("自分のレンズ（観点）が保存される", lenses.length >= 1 && lenses[0].name === "労働から", `lenses=${JSON.stringify(lenses)}`);

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
