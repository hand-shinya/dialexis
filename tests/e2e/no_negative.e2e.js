// 逆側logic（半田様2026-07-29）: 「〜できません/見つかりません/失敗」等の否定表示を絶対に出さない。
// 空/失敗の検出点をtriggerに、建設的な代替（続行フッター or nomiss）へ差し替わることを機械検査。
const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8016";
// 禁止する否定表現（日英）。これらが panel/graph 領域に現れたら FAIL。
const BAD = ["できませんでした", "できません", "見つかりませんでした", "見つかりません", "特定できません",
  "失敗しました", "取得できませんでした", "ありませんでした", "出題できません",
  "no data", "no result", "no usage", "no series", "no etymology", "not found", "not available", "failed"];
// 解剖が原語を辿れない語(和語/かな/記号)＝以前「特定できません」が出た類
const TERMS = ["矛盾", "ありがとう", "たそがれ", "###", "自由", "διαλεκτική"];
const PANELS = ["gAnatomyPanel", "gContrastPanel", "gColloc", "gCombinePanel", "gPerspectivePanel"];
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const p = await b.newPage();
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  await p.goto(`${BASE}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle" });
  for (let i = 0; i < 20; i++) { const v = await p.evaluate(() => { const w = document.getElementById("origin-graph-wrap"); return w && getComputedStyle(w).display !== "none"; }); if (v) break; await p.waitForTimeout(600); }

  let clean = true, hits = [];
  for (const term of TERMS) {
    for (const fn of PANELS) {
      const txt = await p.evaluate(async ([fn, term]) => {
        const old = document.getElementById("graph-panel"); if (old) old.remove();
        try { window[fn](term); } catch (e) { return "ERR:" + e.message; }
        await new Promise(r => setTimeout(r, 2600));   // 取得完了まで待つ（失敗経路も含め最終表示を見る）
        const b = document.querySelector("#graph-panel .gp-body");
        return b ? b.textContent : "(no panel)";
      }, [fn, term]);
      const bad = BAD.filter(w => txt.toLowerCase().includes(w.toLowerCase()));
      // 続行手段(フッター or nomiss)が在るか
      const hasCont = await p.evaluate(() => document.querySelectorAll("#graph-panel .gp-cont-b, #graph-panel .nomiss-b").length >= 3);
      if (bad.length) { clean = false; hits.push(`${term}/${fn}:[${bad.join("|")}]`); }
      if (!hasCont) { clean = false; hits.push(`${term}/${fn}:続行手段なし`); }
    }
  }
  ok(`全パネル×否定が出やすい語(${TERMS.length}×${PANELS.length}=${TERMS.length*PANELS.length})で否定表示ゼロ＋続行手段あり`, clean, hits.slice(0, 8).join(" "));

  // lens空表示(graph-alt)を決定論的に検証: 空データを描画関数に直接渡し、否定ゼロ＋nomissボタンが出る
  const altR = await p.evaluate((BAD) => {
    const alt = document.getElementById("graph-alt");
    // usage/timeline の空データ → 否定でなく nomiss へ
    renderUsageCards({ query: "矛盾", cards: [], scholars: [] });
    const t1 = alt.textContent.toLowerCase(); const bad1 = BAD.filter(w => t1.includes(w.toLowerCase()));
    const n1 = alt.querySelectorAll(".nomiss-b").length;
    renderTimeline({ query: "矛盾", series: [] });
    const t2 = alt.textContent.toLowerCase(); const bad2 = BAD.filter(w => t2.includes(w.toLowerCase()));
    const n2 = alt.querySelectorAll(".nomiss-b").length;
    return { bad1, n1, bad2, n2 };
  }, BAD);
  ok("lens空表示(使用例/時代)も否定ゼロ＋nomissボタンへ差替", altR.bad1.length === 0 && altR.n1 >= 3 && altR.bad2.length === 0 && altR.n2 >= 3, JSON.stringify(altR));

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
