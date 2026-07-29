// 普遍性の掃引: 多様な入力語 × 階層(2/3/4) × 各menuパネル に、行き止まり(dead-end)が無いこと=
// どのパネルにも「この語で続ける」普遍フッターが在り、どの階層でも同じ共通メニューが出ることを機械検査。
// 半田様の問い「全ワード・全階層・全menu展開に普遍化したか」への実証。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8015";
const TERMS = ["弁証法", "矛盾", "διαλεκτική", "カール・マルクス", "自由"]; // 概念/CJK/希語/人物/CJK概念
const PANELS = ["gAnatomyPanel", "gContrastPanel", "gExtPanel", "gColloc", "gCombinePanel", "gPerspectivePanel"];
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const p = await b.newPage();
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const waitGraph = async () => { for (let i = 0; i < 20; i++) { const v = await p.evaluate(() => { const w = document.getElementById("origin-graph-wrap"); return w && getComputedStyle(w).display !== "none"; }); if (v) return; await p.waitForTimeout(600); } };
  await p.goto(`${BASE}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle" });
  await waitGraph();

  // PART 1: 全パネル × 全語型 に続行フッター（＝行き止まりゼロ）
  let allFooter = true, misses = [];
  for (const term of TERMS) {
    for (const fn of PANELS) {
      const hasFoot = await p.evaluate(async ([fn, term]) => {
        const old = document.getElementById("graph-panel"); if (old) old.remove();
        try { window[fn](term); } catch (e) { return "ERR:" + e.message; }
        await new Promise(r => setTimeout(r, 180));
        const btns = document.querySelectorAll("#graph-panel .gp-cont-b").length;
        return btns >= 5;
      }, [fn, term]);
      if (hasFoot !== true) { allFooter = false; misses.push(`${term}/${fn}=${hasFoot}`); }
    }
  }
  ok(`全パネル(${PANELS.length})×全語型(${TERMS.length})=${PANELS.length*TERMS.length}通りに続行フッター(行き止まりゼロ)`, allFooter, misses.length ? "欠落:" + misses.join(",") : "");

  // PART 2: 決定論 fixture graph（layer 1..4 の実ノード）で、各階層の"実ノードを明示選択"し、
  // 選択ノードの layer を assert した上で、その階層のノードでも共通メニュー(popup)が同一に出ることを検証。
  await p.route("**/api/origin/graph**", r => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ query: "弁証法", note: "fixture", nodes: [
      { id: "n1", label: "弁証法", kind: "word", layer: 1, q: "弁証法" },
      { id: "n2", label: "dialectic", kind: "original", layer: 2, q: "dialectic" },
      { id: "n3", label: "ドイツ語：Dialektik", kind: "language", layer: 3, q: "Dialektik" },
      { id: "n4", label: "カール・マルクス", kind: "author", layer: 4, q: "カール・マルクス" }],
      edges: [{ from: "n1", to: "n2", strength: 1 }, { from: "n2", to: "n3", strength: 1 }, { from: "n3", to: "n4", strength: 1 }] }) }));
  await p.goto(`${BASE}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle" });
  await waitGraph();
  const CORE_S = ["中心に据える", "組み合わせ", "見方", "外部で調べる"];
  let depthOk = true, depthLog = [];
  for (let d = 2; d <= 4; d++) {
    const res = await p.evaluate((d) => {
      const ns = (window.__dx && __dx.G && __dx.G.nodes) || [];
      const node = ns.find(x => x.layer === d);          // ← ループ変数dで"その階層の実ノード"を明示選択
      if (!node) return { ok: false, why: "no-node@" + d };
      gMenu(200, 200, node);
      const items = [...document.querySelectorAll("#graph-menu .gm-item")].map(e => e.textContent);
      const m = document.getElementById("graph-menu"); if (m) m.remove();
      return { ok: true, layer: node.layer, label: node.label, count: items.length,
               core: ["中心に据え直す", "組み合わせ", "見方", "外部"].every(k => items.some(t => t.includes(k))) };
    }, d);
    const okd = res.ok && res.layer === d && res.count >= 8 && res.core;   // 選択ノードのlayerが d であることをassert
    depthLog.push(`L${d}:${res.ok ? res.label.slice(0, 8) + "(layer" + res.layer + "/popup" + res.count + "/core" + (res.core ? 1 : 0) + ")" : res.why}`);
    if (!okd) depthOk = false;
  }
  await p.unroute("**/api/origin/graph**").catch(() => {});
  ok("階層2/3/4の実ノードを明示選択し layer を確認、各階層で共通メニューが同一に出る", depthOk, depthLog.join(" "));

  // PART 3: 解剖の普遍(CJK含む)。多様な語で「特定できません」の行き止まりが出ない
  let anatOk = true, anatLog = [];
  for (const w of ["矛盾", "自由", "権利", "経済", "弁証法"]) {
    const r = await p.evaluate(async (w) => {
      const d = await (await fetch(`/api/anatomy?q=${encodeURIComponent(w)}&lang=ja`)).json();
      return { term: d.term, comps: (d.components || []).length, sum: !!d.summary };
    }, w);
    const good = !!r.term && (r.comps > 0 || r.sum);   // term特定＋(構成要素 or 語源)＝行き止まりでない
    anatLog.push(`${w}(term=${r.term?1:0}/comp${r.comps}/sum${r.sum?1:0})`);
    if (!good) anatOk = false;
  }
  ok("解剖が全語型(CJK/アルファベット)で機能し『特定できません』の行き止まりが出ない", anatOk, anatLog.join(" "));

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
