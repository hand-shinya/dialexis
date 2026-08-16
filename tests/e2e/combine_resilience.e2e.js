// 組み合わせ探索の結果契約。
// 内部検索源が空でも、元Mapを黙って残して次の提案だけに落とさず、
// 条件・理由・同条件の外部検索・再試行を同じAction面に残す。
// メニュー選択は実マウス操作（DOMの element.click() は使わない）。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8143";

(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const p = await b.newPage();
  const R = [];
  const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? " — " + d : ""}`); };
  const graph = { query: "カール・マルクス", nodes: [
    { id: "root", label: "カール・マルクス", kind: "word", layer: 1, q: "カール・マルクス", weight: 3 },
    { id: "related", label: "弁証法", kind: "related", layer: 2, q: "弁証法", weight: 1 },
  ], edges: [{ from: "root", to: "related", strength: 1 }] };
  await p.route("**/api/origin/graph**", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(graph) }));
  await p.route("**/api/origin?**", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ query: "カール・マルクス", general_meaning: [], breadth: [], concept_origin: [], sources: [] }) }));
  await p.goto(`${BASE}/origin?q=%E3%82%AB%E3%83%BC%E3%83%AB%E3%83%BB%E3%83%9E%E3%83%AB%E3%82%AF%E3%82%B9&lang=ja`, { waitUntil: "networkidle" });
  await p.waitForSelector("#origin-graph", { timeout: 15000 });
  await p.waitForFunction(() => window.__dx && __dx.G && __dx.G.nodes && __dx.G.nodes.some(n => n.layer === 1), null, { timeout: 15000 });
  await p.evaluate(() => __dx.fit()); await p.waitForTimeout(300);

  const chooseCombine = async () => {
    const pt = await p.evaluate(() => __dx.nodeClientXY(n => n.layer === 1));
    if (!pt) throw new Error("root node coordinate unavailable");
    await p.mouse.click(pt.x, pt.y);
    await p.waitForSelector("#graph-menu", { timeout: 5000 });
    await p.locator("#graph-menu .gm-item", { hasText: "組み合わせ" }).click();
    await p.locator("#cmb-b").fill("吉本隆明");
  };

  // 成功経路：同じUIが結果Mapへ進む。
  await p.route("**/api/combine**", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    query: "カール・マルクス", has_results: true, note: "AND実データ・出所：fixture", nodes: [
      { id: "r", label: "カール・マルクス＋吉本隆明", kind: "word", layer: 1, q: "カール・マルクス＋吉本隆明", weight: 3 },
      { id: "x", label: "共同幻想", kind: "application", layer: 2, q: "共同幻想", weight: 1 },
    ], edges: [{ from: "r", to: "x", strength: 1 }] }) }));
  await chooseCombine();
  await p.locator("#graph-panel .cmb-op", { hasText: "AND" }).click();
  await p.waitForFunction(() => !document.querySelector("#graph-busy") || getComputedStyle(document.querySelector("#graph-busy")).display === "none");
  ok("AND成功: 結果Mapへ進む", await p.evaluate(() => !!__dx.G_raw && __dx.G_raw.nodes.length === 2), "nodes=" + await p.evaluate(() => (__dx.G_raw && __dx.G_raw.nodes.length) || 0));

  // 空/退避経路：元の弁証法Mapを成功結果のように見せず、説明付きAction面へ収束する。
  await p.unroute("**/api/combine**");
  await p.route("**/api/combine**", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    query: "カール・マルクス", has_results: false, note: "内部検索源から結果なし。出所：検索源未応答。",
    nodes: [{ id: "root", label: "カール・マルクス＋吉本隆明", kind: "word", layer: 1, q: "カール・マルクス＋吉本隆明", weight: 3 }], edges: []
  }) }));
  await p.goto(`${BASE}/origin?q=%E3%82%AB%E3%83%BC%E3%83%AB%E3%83%BB%E3%83%9E%E3%83%AB%E3%82%AF%E3%82%B9&lang=ja`, { waitUntil: "networkidle" });
  await p.waitForSelector("#origin-graph", { timeout: 15000 });
  await p.waitForFunction(() => window.__dx && __dx.G && __dx.G.nodes && __dx.G.nodes.some(n => n.layer === 1), null, { timeout: 15000 });
  await p.evaluate(() => __dx.fit()); await p.waitForTimeout(300);
  await chooseCombine();
  await p.locator("#graph-panel .cmb-op", { hasText: "AND" }).click();
  await p.waitForSelector("#graph-panel .combine-outcome", { timeout: 10000 });
  const out = await p.locator("#graph-panel").innerText();
  ok("AND空/退避: 実行結果の説明が表示される", /検索条件|出所|結果なし|検索源/.test(out), out.slice(0, 180));
  ok("AND空/退避: 正確な2語条件が残る", out.includes("カール・マルクス") && out.includes("吉本隆明"));
  ok("AND空/退避: 外部の同条件検索と再試行が残る",
    (await p.locator("#graph-panel a.ext-link").count()) >= 5 && await p.locator("#combine-edit").count() === 1);
  ok("AND空/退避: 共通の次アクションも残る", await p.locator("#graph-panel .gp-cont-b").count() >= 5);
  ok("AND空/退避: 元の中心Mapを結果Mapと偽って置換しない", await p.evaluate(() => __dx.G && __dx.G.rootQ === "カール・マルクス"));

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
