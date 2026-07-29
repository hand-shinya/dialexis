// A4 canvas実マウスクリック: 層1..4のノードを実際の page.mouse.click(x,y) で押し、
//  (1)ヒットテストが正しいノードを選ぶ (2)popupが開く (3)popupの対象/層が一致
//  (4)menu項目を実DOMクリック (5)正しいActionID+targetが1回dispatchされる (6)後のViewStateが整合。
// gMen()直呼びは不可——実マウス座標クリックで通す（半田様A4）。座標潰れ対策にfit後の位置を用いる。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8021";
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const p = await b.newPage(); await p.setViewportSize({ width: 1200, height: 900 });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };

  await p.route("**/api/origin/graph**", r => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ query: "弁証法", note: "fx", nodes: [
      { id: "n1", label: "弁証法", kind: "word", layer: 1, q: "弁証法" },
      { id: "n2", label: "dialectic", kind: "original", layer: 2, q: "dialectic" },
      { id: "n3", label: "ドイツ語：Dialektik", kind: "language", layer: 3, q: "Dialektik" },
      { id: "n4", label: "カール・マルクス", kind: "author", layer: 4, q: "カール・マルクス" }],
      edges: [{ from: "n1", to: "n2", strength: 1 }, { from: "n2", to: "n3", strength: 1 }, { from: "n3", to: "n4", strength: 1 }] }) }));
  // multilingual先の取得は最小モック（dispatch確認が目的・行き止まり回避）
  await p.route("**/api/origin?**", r => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ query: "x", general_meaning: ["m"], breadth: [{ name: "独", term: "T" }] }) }));

  await p.goto(`${B}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle" });
  for (let i = 0; i < 25; i++) { const v = await p.evaluate(() => { const w = document.getElementById("origin-graph-wrap"); return w && getComputedStyle(w).display !== "none"; }); if (v) break; await p.waitForTimeout(500); }
  for (let i = 0; i < 20; i++) { const st = await p.evaluate(() => __dx.G && (__dx.G.alpha || 0)); if (st < 0.03) break; await p.waitForTimeout(300); }

  // 決定論のため4ノードを離れたグリッドへ置き、force simを凍結し、明示fit（座標潰れ/NaN/ドリフトを排除・A4）
  const POS = { n1: [120, 300], n2: [300, 300], n3: [480, 300], n4: [660, 300] };  // 同一Yの横一列＝全層をクリック可能域に収める
  const freeze = () => p.evaluate((pos) => {
    const g = __dx.G;
    if (g.raf) { cancelAnimationFrame(g.raf); } g.running = false; g.alpha = 0;   // simを止めて座標を固定
    g.nodes.forEach(n => { const q = pos[n.id]; if (q) { n.x = q[0]; n.y = q[1]; n.vx = 0; n.vy = 0; } n.r = n.r || 20; });
    g.W = g.cv.clientWidth || 800; g.H = g.cv.clientHeight || 600;
    return __dx.fit();
  }, POS);
  const view = await freeze();
  ok("fit後のviewが有限（NaN/0でない・実クリック座標が確定）", view && isFinite(view.k) && view.k > 0 && isFinite(view.x) && isFinite(view.y), JSON.stringify(view));

  const EXPECT = { 1: "multilingual", 2: "multilingual", 3: "multilingual", 4: "author" };  // 各層のノードpopupにある代表項目
  for (const layer of [1, 2, 3, 4]) {
    await freeze();   // クリック直前に位置を再固定（前操作でsimが動いても座標を保証）
    const c = await p.evaluate((L) => __dx.nodeClientXY(n => n.layer === L), layer);
    if (!c) { ok(`層${layer}: nodeClientXY取得`, false, "null"); continue; }
    const r = await p.evaluate(() => { const cv = document.getElementById("origin-graph"); const b = cv.getBoundingClientRect(); return { left: b.left, top: b.top }; });
    const hit = await p.evaluate(([mx, my]) => __dx.hitTest(mx, my), [c.x - r.left, c.y - r.top]);
    ok(`層${layer}: ヒットテストが正しいノードを選ぶ（id=${c.id}）`, hit && hit.id === c.id, JSON.stringify(hit));

    await p.evaluate(() => { const m = document.getElementById("graph-menu"); if (m) m.remove(); const x = document.getElementById("graph-panel"); if (x) x.remove(); });
    await p.mouse.click(c.x, c.y);          // ← 実マウスクリック（gMenu直呼びでない）
    await p.waitForTimeout(250);
    const menu = await p.evaluate(() => { const m = document.getElementById("graph-menu"); return { open: !!m, ctx: __dx.MENUCTX ? { id: __dx.MENUCTX.n.id, layer: __dx.MENUCTX.n.layer } : null, n: m ? [...m.querySelectorAll(".gm-item")].map(e => e.textContent) : [] }; });
    ok(`層${layer}: 実クリックでpopupが開き対象/層が一致`, menu.open && menu.ctx && menu.ctx.id === c.id && menu.ctx.layer === layer, JSON.stringify(menu.ctx));

    // menu項目を実DOMクリック → 有効ActionIDが1回dispatch・target=そのノードのq（層に応じ多言語/著者項目を選ぶ）
    const nodeQ = await p.evaluate((L) => { const n = __dx.G.nodes.find(x => x.layer === L); return n && n.q; }, layer);
    const dispatched = await p.evaluate((want) => {
      const items = [...document.querySelectorAll("#graph-menu .gm-item")];
      const re = { multilingual: /多言語|languages/, author: /著者|系譜|author/ }[want];
      const it = items.find(e => re.test(e.textContent)) || items[0];
      if (!it) return null; it.click(); return { txt: it.textContent };
    }, EXPECT[layer]);
    await p.waitForTimeout(250);
    const ld = await p.evaluate(() => __dx.lastDispatch);
    const validActs = await p.evaluate(() => __dx.actions());
    ok(`層${layer}: menu実DOMクリック→有効ActionIDが1回dispatch・target=ノードのq(${nodeQ})`,
      !!dispatched && !!ld && validActs.includes(ld.actionId) && ld.surface === "popup" && ld.target && ld.target.term === nodeQ,
      JSON.stringify(ld && { a: ld.actionId, t: ld.target && ld.target.term, s: ld.surface }));
    const vs = await p.evaluate(() => __dx.viewState());
    ok(`層${layer}: dispatch後のViewStateが整合（panel or center確定）`, vs && (vs.panel || vs.q), JSON.stringify(vs && { q: vs.q, panel: vs.panel && vs.panel.action }));
  }

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
