// Fix2 回帰（実DOMクリック・履歴一回性）: Origin中心経路で soon次元の「探究の次元」ボタンを
// 実際に page.click でDOMクリックすると、説明だけの「整備中／準備中／coming」で止まらず、
// 現在語×次元名を既存の組合せ探索(実データ)へ渡して同一操作内で実行し、履歴増分がちょうど1件であること
// （一操作一commit＝gDimActが非同期をreturnしdispatchAが settle後に1回だけcommit）を検証する。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8021";
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true }); const p = await b.newPage();
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  let combineHits = 0, combineArgs = "";
  await p.route("**/api/origin/graph**", r => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ query: "疎外", note: "fx", nodes: [{ id: "n1", label: "疎外", kind: "word", layer: 1, q: "疎外" }], edges: [] }) }));
  // 主結果（/api/origin）に soon次元を1件だけ含める＝実描画された .dim を実クリックする
  await p.route("**/api/origin?**", r => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ query: "疎外", lang: "ja", found: true, word: { query: "疎外" },
      general_meaning: ["疎外の意味テキスト"], breadth: [], concept_origin: [], collapse_warning: null,
      dimensions: [{ label: "応用領域", status: "soon", act: "" }], sources: [], queried_at: "2026-07-30T00:00:00+00:00" }) }));
  await p.route("**/api/dimensions**", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ query: "疎外", found: false, dimensions: [] }) }));
  await p.route("**/api/combine**", r => { combineHits++; combineArgs = r.request().url(); r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ query: "疎外×応用領域", note: "combine", nodes: [
      { id: "c1", label: "疎外", kind: "word", layer: 1, q: "疎外" },
      { id: "c2", label: "応用領域", kind: "word", layer: 1, q: "応用領域" },
      { id: "c3", label: "共通概念", kind: "related", layer: 2, q: "共通概念" }],
      edges: [{ from: "c1", to: "c3", strength: 1 }, { from: "c2", to: "c3", strength: 1 }] }) }); });

  await p.goto(`${B}/origin?q=%E7%96%8E%E5%A4%96&lang=ja`, { waitUntil: "networkidle" });
  // soon次元ボタンが実描画されるまで待つ（実UIの .dim）
  let dimReady = false;
  for (let i = 0; i < 25; i++) { dimReady = await p.evaluate(() => !!document.querySelector("#origin-results .dim")); if (dimReady) break; await p.waitForTimeout(400); }
  ok("soon次元ボタン(.dim)が実UIに描画された", dimReady);
  const label = await p.evaluate(() => { const el = document.querySelector("#origin-results .dim"); return el ? el.textContent : ""; });
  ok("バッジは停止型『整備中』でなく実行操作『組合せで探索』", /組合せで探索/.test(label) && !/整備中|coming/.test(label), label.trim());

  const lenBefore = await p.evaluate(() => __dx.nav.len);
  await p.click("#origin-results .dim");   // ← 実DOMクリック（__dx.dispatch直呼びでない）
  await p.waitForTimeout(1200);

  ok("実クリックで組合せ探索(/api/combine)が実行された", combineHits >= 1, combineArgs.replace(B, ""));
  const vs = await p.evaluate(() => __dx.viewState());
  ok("実データが返り組合せ状態が確定（説明で止まらない）", !!(vs && vs.combine && vs.combine.a === "疎外" && vs.combine.b === "応用領域"), JSON.stringify(vs && vs.combine));
  const lenAfter = await p.evaluate(() => __dx.nav.len);
  ok("履歴増分がちょうど1件（一操作一commit）", lenAfter - lenBefore === 1, `len ${lenBefore}→${lenAfter}`);
  const stop = await p.evaluate(() => { const el = document.querySelector("#graph-panel .gp-body"); const t = el ? el.innerText : ""; return /整備中|準備中|coming|この次元は/.test(t); });
  ok("『整備中／準備中／coming』の停止型パネルが出ない", stop === false);

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
