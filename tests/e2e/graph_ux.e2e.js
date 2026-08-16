// Graph UX: 著者を中心に据え直す＝2件でなく豊かに再中心し、中心（root）がその著者になる。
// メニューはノードを覆わず横にずれて出る。半田様指摘(視認性・普遍性)の是正。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
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
    const pt = await page.evaluate((k) => { if (!G || !G.nodes) return null; const n = G.nodes.find(x => x.kind === k); if (!n) return null; return { x: n.x * G.view.k + G.view.x, y: n.y * G.view.k + G.view.y, label: n.label }; }, kind);
    if (!pt) return null;
    await page.mouse.click(box.x + pt.x, box.y + pt.y);
    return pt;
  };

  // 著者中心化のUI契約は外部APIの揺れから分離する。検索語ごとにrootが変わる
  // こと、著者ノードが実際に選べること、中心化後に豊かなMapになることを固定する。
  const fixtureGraph = (q) => q === "カール・マルクス" ? {
    query: q, nodes: [
      { id: "root", label: q, kind: "author", layer: 1, q, weight: 3 },
      { id: "w1", label: "資本論", kind: "work", layer: 2, q: "資本論", weight: 2 },
      { id: "r1", label: "疎外", kind: "related", layer: 2, q: "疎外", weight: 1 },
      { id: "r2", label: "弁証法", kind: "related", layer: 2, q: "弁証法", weight: 1 },
    ], edges: [{ from: "root", to: "w1" }, { from: "root", to: "r1" }, { from: "root", to: "r2" }], note: "fixture"
  } : {
    query: q, nodes: [
      { id: "root", label: q, kind: "word", layer: 1, q, weight: 3 },
      { id: "a1", label: "カール・マルクス", kind: "author", layer: 2, weight: 2 },
      { id: "r1", label: "疎外論", kind: "related", layer: 2, q: "疎外論", weight: 1 },
    ], edges: [{ from: "root", to: "a1" }, { from: "root", to: "r1" }], note: "fixture"
  };
  await page.route("**/api/origin/graph**", route => {
    const q = new URL(route.request().url()).searchParams.get("q") || "疎外";
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(fixtureGraph(q)) });
  });
  await page.route("**/api/origin?**", route => {
    const q = new URL(route.request().url()).searchParams.get("q") || "疎外";
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      query: q, general_meaning: [`${q}の意味（fixture）`], breadth: [], concept_origin: [],
      collapse_warning: null, relations: { near: [], opposite: [] }, associated: [], sources: []
    }) });
  });
  await page.goto(`${BASE}/origin?q=%E7%96%8E%E5%A4%96&lang=ja`, { waitUntil: "networkidle" });
  // 外部sourceの応答順は固定しない。Mapが構築されるまで待ってから著者ノードを探す。
  await page.waitForFunction(() => !!(window.G && G.nodes && G.nodes.length), null, { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(500);

  // 著者ノードをクリック→メニュー
  const pt = await clickNode("author");
  await page.waitForTimeout(500);
  const menu = await page.$("#graph-menu");
  ok("著者ノードのメニューが出る", !!menu, pt ? `node=${pt.label}` : "no author node");
  if (menu) {
    const box = await canvasBox();
    const ml = await page.$eval("#graph-menu", el => el.getBoundingClientRect().x);
    ok("メニューがノード中心を覆わずに横へずれて出る", Math.abs(ml - (box.x + pt.x)) > 12, `menuLeft=${Math.round(ml)} node=${Math.round(box.x + pt.x)}`);
    // 「中心に据え直す」を実クリック（bounding box経由でメニュー委譲ハンドラを確実に発火）
    const before = await page.evaluate(() => G && G.rootQ);
    const ib = await page.evaluate(() => {
      const el = [...document.querySelectorAll("#graph-menu .gm-item")].find(e => /中心に据え直す/.test(e.textContent));
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
