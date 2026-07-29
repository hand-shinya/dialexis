// 5.4 履歴モデル: 固定操作列の各段の確定 ViewState を保存し、最後→開始へ戻り、開始→最後へ進み、
// 各段の状態が保存値と一致することを検証。combine は決定論 fixture で mock（SearXNG非依存）。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8021";
const canon = (v) => JSON.stringify({ q: v.q, lens: v.lens, focus: v.focus, panel: v.panel, combine: v.combine });
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true }); const p = await b.newPage();
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  // combine を決定論 fixture に固定（3ノード）
  await p.route("**/api/combine**", r => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ query: "矛盾", note: "fixture", nodes: [
      { id: "root", label: "矛盾", kind: "word", layer: 1, q: "矛盾" },
      { id: "x", label: "労働", kind: "word", layer: 2, q: "労働" },
      { id: "y", label: "交差", kind: "related", layer: 2, q: "交差" }], edges: [{ from: "root", to: "x", strength: 1 }] }) }));
  const waitG = async () => { for (let i = 0; i < 25; i++) { const v = await p.evaluate(() => { const w = document.getElementById("origin-graph-wrap"); return w && getComputedStyle(w).display !== "none"; }); if (v) return; await p.waitForTimeout(600); } };
  await p.goto(`${B}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle" }); await waitG();

  const snap = async () => { await p.waitForTimeout(300); return canon(await p.evaluate(() => __dx.viewState())); };
  const states = [await snap()];   // step0: 初期(弁証法)
  // 固定操作列（2.B に対応: 中心→別語→多言語パネル→見方→組合せ結果）
  const seq = [
    ["center", { term: "矛盾" }, 2200],           // 1 中心語を別語へ
    ["multilingual", { term: "矛盾" }, 1600],     // 2 その語の多言語パネル
    ["applyLens", { term: "矛盾" }, 1600, { lensKey: "languages" }],  // 3 見方を変更
    ["combine", { term: "矛盾" }, 800],           // 4 組合せフォーム（パネル）
  ];
  for (const [act, tgt, wait, ctx] of seq) {
    await p.evaluate(async ([act, tgt, ctx]) => { await __dx.dispatch(act, tgt, ctx || {}); }, [act, tgt, ctx]);
    await p.waitForTimeout(wait); states.push(await snap());
  }
  // 5 組合せ結果を実行（fixture）＝combine確定状態
  await p.evaluate(async () => { const x = document.getElementById("graph-panel"); if (x) x.remove(); await gCombineRun("矛盾", "労働", "and"); });
  await p.waitForTimeout(1200); states.push(await snap());

  const n = states.length;
  ok(`固定操作列で ${n} 段の確定状態が記録された（各段が別状態）`, new Set(states).size >= n - 1, `states=${n}`);

  // 最後→開始へ「戻る」で1段ずつ一致
  let backOk = true, blog = [];
  for (let i = n - 2; i >= 0; i--) {
    await p.evaluate(() => navGo(-1)); await p.waitForTimeout(1800);
    const cur = await snap();
    if (cur !== states[i]) { backOk = false; blog.push(`back@${i}: got ${cur} want ${states[i]}`); }
  }
  ok("戻るで開始状態まで各段一致（往路の逆再生）", backOk, blog[0] || "");
  // 開始→最後へ「進む」で1段ずつ一致
  let fwdOk = true, flog = [];
  for (let i = 1; i < n; i++) {
    await p.evaluate(() => navGo(1)); await p.waitForTimeout(1800);
    const cur = await snap();
    if (cur !== states[i]) { fwdOk = false; flog.push(`fwd@${i}: got ${cur} want ${states[i]}`); }
  }
  ok("進むで最終状態まで各段一致（往路の再生）", fwdOk, flog[0] || "");

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
