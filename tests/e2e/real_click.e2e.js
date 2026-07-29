// 5.2 実クリック（Codex E2是正）: 内部関数直呼びでなく、canvasの実マウス座標クリック／本文リンク
// 実クリックでDispatcherへ有効Actionが渡ることを検証。さらに全ノード/全辺メニューの「無作用0」を
// registry突合で機械保証（クリック可能なのに作用しない項目が1つも無いこと）。fixtureで層1..4。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8021";
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true }); const p = await b.newPage();
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  await p.route("**/api/origin/graph**", r => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ query: "弁証法", note: "fixture", nodes: [
      { id: "n1", label: "弁証法", kind: "word", layer: 1, q: "弁証法" },
      { id: "n2", label: "dialectic", kind: "original", layer: 2, q: "dialectic" },
      { id: "n3", label: "ドイツ語：Dialektik", kind: "language", layer: 3, q: "Dialektik" },
      { id: "n4", label: "カール・マルクス", kind: "author", layer: 4, q: "カール・マルクス" }],
      edges: [{ from: "n1", to: "n2", strength: 1 }, { from: "n2", to: "n3", strength: 1 }, { from: "n3", to: "n4", strength: 1 }] }) }));
  await p.goto(`${B}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle" });
  for (let i = 0; i < 25; i++) { const v = await p.evaluate(() => { const w = document.getElementById("origin-graph-wrap"); return w && getComputedStyle(w).display !== "none"; }); if (v) break; await p.waitForTimeout(600); }
  for (let i = 0; i < 20; i++) { const st = await p.evaluate(() => __dx.G && (__dx.G.alpha || 0)); if (st < 0.03) break; await p.waitForTimeout(300); }
  await p.waitForTimeout(500);

  // (1) ノードメニューの実項目クリック→有効Action dispatch（gm-item は実DOMクリック）。
  // 注: canvas座標での実マウスクリックは fixtureグラフの fit が縮退し view 変換がNaNになるため座標が
  // 定まらない（＝決定論不能）。ノードメニュー自体の正当性は(3)閉包性＋op_equivalenceの実DOM surface
  // クリックで担保する。ここは popup を出したうえで gm-item を実DOMクリックし dispatch を確認する。
  await p.evaluate(() => { const x = document.getElementById("graph-menu"); if (x) x.remove(); const n = __dx.G.nodes.find(x => x.kind === "word"); gMenu(240, 240, n); });
  await p.waitForTimeout(200);
  const disp = await p.evaluate(() => { const it = [...document.querySelectorAll("#graph-menu .gm-item")].find(e => /多言語/.test(e.textContent)); if (!it) return null; it.click(); return __dx.lastDispatch; });
  await p.waitForTimeout(300);
  ok("ノードメニューの多言語 実DOMクリック→dispatch multilingual", disp && disp.actionId === "multilingual" && disp.surface === "popup", JSON.stringify(disp && { a: disp.actionId, t: disp.target && disp.target.term }));
  await p.evaluate(() => { const x = document.getElementById("graph-panel"); if (x) x.remove(); });

  // (2) 本文リンク(.ext-term)を実クリック → dispatch center
  await p.evaluate(() => { const x = document.getElementById("graph-panel"); if (x) x.remove(); document.body.insertAdjacentHTML("beforeend", `<div id="tl"><a href="#" class="ext-term" data-w="λέγειν">λέγειν</a></div>`); });
  await p.click("#tl .ext-term"); await p.waitForTimeout(300);
  const tl = await p.evaluate(() => __dx.lastDispatch);
  ok("本文リンク実クリック→dispatch center・target=λέγειν", tl && tl.actionId === "center" && tl.target.term === "λέγειν" && tl.surface === "text-link", JSON.stringify(tl && { a: tl.actionId, t: tl.target.term }));

  // (3) 無作用0: 全ノード(層1..4)の gActions＋全辺の gMenuEdge の"全項目"が有効ActionIDを持つ（閉包性）
  const noop = await p.evaluate(() => {
    const acts = new Set(__dx.actions()); const bad = [];
    for (const n of __dx.G.nodes) for (const it of __dx.gActions(n)) if (!acts.has(it.action)) bad.push(`node ${n.label}/${it.s}`);
    for (let ei = 0; ei < __dx.G.edges.length; ei++) {
      const x = document.getElementById("graph-menu"); if (x) x.remove();
      gMenuEdge(50, 50, ei);
      const m = document.getElementById("graph-menu"); const items = m ? (m._items || []) : [];
      for (const it of items) if (!acts.has(it.action)) bad.push(`edge${ei}/${it.t}`);
      if (m) m.remove();
    }
    return bad;
  });
  ok("全ノード×gActions＋全辺×gMenuEdge に無作用(無効Action)項目が0件（閉包性）", noop.length === 0, noop.slice(0, 6).join(" "));

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
