// Full lens-menu E2E: all user-selectable lenses incl. the special-render ones
// (応用=graph, 使用例=cards, 時代変遷=timeline, 文化圏=region). Same word, many views.
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

  const chipKeys = await page.$$eval("#graph-lens .lens-chip", els => els.map(e => e.dataset.k));
  ok("メニューに全レンズが並ぶ（10枚: 俯瞰/思想家/原語/言語/意味/星座/文化圏/応用/使用例/時代）",
     ["all","thinkers","original","languages","domains","relations","spheres","applications","usage","era"].every(k => chipKeys.includes(k)),
     `keys=${JSON.stringify(chipKeys)}`);

  // 文化圏（region・グラフ再投影）
  await page.click('#graph-lens .lens-chip[data-k="spheres"]'); await page.waitForTimeout(900);
  const regs = await page.evaluate(() => G.nodes.filter(n => n.kind === "appdomain").map(n => n.label));
  ok("文化圏レンズ: 言語が圏（欧/漢字圏/日本/その他）で束ねられる", regs.some(r => ["欧", "漢字圏", "日本", "その他"].includes(r)), `regs=${JSON.stringify(regs)}`);

  // 応用・波及（lazy-graph）
  await page.click('#graph-lens .lens-chip[data-k="applications"]'); await page.waitForTimeout(3000);
  const appInfo = await page.evaluate(() => ({
    doms: (G && G.nodes ? G.nodes.filter(n => n.kind === "appdomain").map(n => n.label) : []),
    works: (G && G.nodes ? G.nodes.filter(n => n.kind === "application").length : 0),
  }));
  ok("応用レンズ: 分野別の枝＋作品の点が出る", appInfo.works >= 2 && appInfo.doms.length >= 1, `doms=${JSON.stringify(appInfo.doms)} works=${appInfo.works}`);

  // 使用例・引用（cards）
  await page.click('#graph-lens .lens-chip[data-k="usage"]'); await page.waitForTimeout(3500);
  const altVisible = await page.$eval("#graph-alt", el => el.style.display !== "none");
  const nCards = await page.$$eval("#graph-alt .ucard", els => els.length);
  ok("使用例レンズ: 引用カードが専用領域に出る（canvasでなくカード）", altVisible && nCards >= 3, `cards=${nCards}`);
  const cardHasSource = await page.$$eval("#graph-alt .ucard a", els => els.length > 0);
  ok("引用カードに出典リンク（新タブ）がある", cardHasSource);

  // 時代・変遷（timeline chart）
  await page.click('#graph-lens .lens-chip[data-k="era"]'); await page.waitForTimeout(3500);
  const tl = await page.$("#tl-canvas");
  const legend = await page.$$eval("#graph-alt .tl-legend span", els => els.map(e => e.textContent));
  ok("時代・変遷レンズ: 時間軸チャート＋凡例（原語・最盛年）が出る", !!tl && legend.length >= 1, `legend=${JSON.stringify(legend.slice(0,2))}`);

  // 俯瞰に戻すとグラフ（canvas）復帰
  await page.click('#graph-lens .lens-chip[data-k="all"]'); await page.waitForTimeout(800);
  const canvasBack = await page.$eval("#origin-graph", el => el.style.display !== "none");
  const altHidden = await page.$eval("#graph-alt", el => el.style.display === "none");
  ok("俯瞰に戻すとグラフ（canvas）が復帰し専用領域は隠れる", canvasBack && altHidden);

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
