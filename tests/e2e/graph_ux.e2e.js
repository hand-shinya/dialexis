// Graph UX: 著者を中心に据えて展開＝2件でなく豊かに再中心し、中心（root）がその著者になる。
// メニューはノードを覆わず横にずれて出る。半田様指摘(視認性・普遍性)の是正。
const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage();
  const R = [];
  const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const canvasBox = async () => await page.$eval("#origin-graph", el => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
  const clickNode = async (kind) => {
    await page.$eval("#origin-graph", el => el.scrollIntoView({ block: "center" }));
    const box = await canvasBox();
    const pt = await page.evaluate((k) => { const n = G.nodes.find(x => x.kind === k); if (!n) return null; return { x: n.x * G.view.k + G.view.x, y: n.y * G.view.k + G.view.y, label: n.label }; }, kind);
    if (!pt) return null;
    await page.mouse.click(box.x + pt.x, box.y + pt.y);
    return pt;
  };

  await page.goto(`${BASE}/origin?q=%E7%96%8E%E5%A4%96&lang=ja`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);

  // 著者ノードをクリック→メニュー
  const pt = await clickNode("author");
  await page.waitForTimeout(500);
  const menu = await page.$("#graph-menu");
  ok("著者ノードのメニューが出る", !!menu, pt ? `node=${pt.label}` : "no author node");
  if (menu) {
    const box = await canvasBox();
    const ml = await page.$eval("#graph-menu", el => el.getBoundingClientRect().x);
    ok("メニューがノード中心を覆わずに横へずれて出る", Math.abs(ml - (box.x + pt.x)) > 12, `menuLeft=${Math.round(ml)} node=${Math.round(box.x + pt.x)}`);
    // 「中心に据えて展開」を実クリック（bounding box経由でメニュー委譲ハンドラを確実に発火）
    const before = await page.evaluate(() => G.rootQ);
    const ib = await page.evaluate(() => {
      const el = [...document.querySelectorAll("#graph-menu .gm-item")].find(e => /中心に据えて展開/.test(e.textContent));
      if (!el) return null; const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    });
    if (ib) await page.mouse.click(ib.x, ib.y);
    await page.waitForTimeout(8000);
    const after = await page.evaluate(() => ({ root: G.rootQ, n: G.nodes.length }));
    ok("著者を中心に据えると豊かに再中心（2件でなく）", after.n > 3, `nodes=${after.n}`);
    ok("中心（root）がその著者になり、以前と変わる", after.root !== before && !!after.root, `root: ${before} → ${after.root}`);
  }

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
