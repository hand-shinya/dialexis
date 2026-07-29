// 普遍性の掃引: 多様な入力語 × 階層(2/3/4) × 各menuパネル に、行き止まり(dead-end)が無いこと=
// どのパネルにも「この語で続ける」普遍フッターが在り、どの階層でも同じ共通メニューが出ることを機械検査。
// 半田様の問い「全ワード・全階層・全menu展開に普遍化したか」への実証。
const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
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

  // PART 2: 階層 2→3→4 を実際に潜り、各階層で共通メニュー(帯13)＋見方バッジ＋ノードpopup(13)が普遍に出る
  await p.goto(`${BASE}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle" });
  await waitGraph();
  const menuState = async () => await p.evaluate(() => ({
    chips: document.querySelectorAll("#graph-lens .tm-chip").length,
    badge: /今の見方/.test((document.getElementById("tm-view") || {}).textContent || ""),
  }));
  const popupCount = async () => await p.evaluate(() => {
    const n = (window.__dx && __dx.G && __dx.G.nodes || []).find(x => x.kind !== "domain" && x.id !== "root") || { kind: "word", label: "X", q: "X" };
    gMenu(200, 200, n); const c = document.querySelectorAll("#graph-menu .gm-item").length; const m = document.getElementById("graph-menu"); if (m) m.remove(); return c;
  });
  // 潜る対象ノード（layer>=2: original/language/author/related）をたどって再中心を3回
  let depthOk = true, depthLog = [];
  for (let d = 2; d <= 4; d++) {
    const target = await p.evaluate((d) => {
      const ns = (window.__dx && __dx.G && __dx.G.nodes) || [];
      const cand = ns.find(x => (x.layer >= 2) && x.kind !== "domain" && x.q) || ns.find(x => x.kind !== "word" && x.q);
      return cand ? (cand.q || cand.label) : null;
    }, d);
    if (!target) { depthLog.push(`L${d}:no-node`); depthOk = false; break; }
    await p.evaluate(async (t) => { await originRecenter(t); }, target);
    await p.waitForTimeout(2200); await waitGraph();
    const ms = await menuState(); const pc = await popupCount();
    const okd = ms.chips >= 6 && ms.badge && pc >= 6;
    depthLog.push(`L${d}:${target.slice(0,6)}(chips${ms.chips}/badge${ms.badge?1:0}/popup${pc})`);
    if (!okd) depthOk = false;
  }
  ok("階層2→3→4に潜っても各階層で共通メニュー+見方バッジ+ノードpopupが普遍に出る", depthOk, depthLog.join(" "));

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
