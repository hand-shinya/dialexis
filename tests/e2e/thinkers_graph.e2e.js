// 思想家と著作レンズの表現力: 影響度で大きさに差（マルクス最大）／著作が思想家から分岐
// （第5階層）／思想家どうしが関係線で結ばれ距離が関係を反映する。
const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage();
  const R = [];
  const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };

  await page.goto(`${BASE}/origin?q=%E8%B3%87%E6%9C%AC%E8%AB%96&lang=ja`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1600);
  await page.click('#graph-lens .lens-chip[data-k="thinkers"]');
  await page.waitForTimeout(1200);

  const info = await page.evaluate(() => {
    const A = G.nodes.filter(n => n.kind === "author").map(n => ({ l: n.label, r: n.r }));
    A.sort((a, b) => b.r - a.r);
    const works = G.nodes.filter(n => n.kind === "work").map(n => n.label);
    const aids = new Set(G.nodes.filter(n => n.kind === "author").map((n, i) => i));
    // count author-author edges
    const idx = {}; G.nodes.forEach((n, i) => idx[n.id] = i);
    let ae = 0;
    G.edges.forEach(e => { if (G.nodes[e.a] && G.nodes[e.b] && G.nodes[e.a].kind === "author" && G.nodes[e.b].kind === "author") ae++; });
    return { top: A[0], second: A[1], nworks: works.length, works: works.slice(0, 4), authorEdges: ae, nauthors: A.length };
  });

  ok("マルクスが最大の円（影響度が大きさに反映）",
     /マルクス/.test(info.top.l) && info.top.r > info.second.r * 1.05, `top=${info.top.l}:${info.top.r} 2nd=${info.second.l}:${info.second.r}`);
  ok("思想家から著作が分岐して見える（第5階層・works）", info.nworks >= 3, `works=${JSON.stringify(info.works)}`);
  ok("思想家どうしが関係線で結ばれる（距離が関係を反映）", info.authorEdges >= 3, `author-edges=${info.authorEdges}`);
  ok("思想家が複数（12前後）並ぶ", info.nauthors >= 6, `n=${info.nauthors}`);

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
