// Fix2 回帰: Origin中心経路で soon次元・未知actの「探究の次元」をクリックしても、説明だけの
// 「整備中／準備中／coming」パネルで止まらず、現在語×次元名を既存の組合せ探索(実データ)へ渡して
// 同一操作内で実行する（新機構なし・既存Action/APIの再利用）。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8021";
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true }); const p = await b.newPage();
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  let combineHits = 0, combineArgs = "";
  await p.route("**/api/origin/graph**", r => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ query: "疎外", note: "fx", nodes: [{ id: "n1", label: "疎外", kind: "word", layer: 1, q: "疎外" }], edges: [] }) }));
  // 組合せ探索(実データ)を返す＝soon次元クリックがここへ実際に到達することを確認する
  await p.route("**/api/combine**", r => { combineHits++; combineArgs = r.request().url(); r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ query: "疎外×応用領域", note: "combine", nodes: [
      { id: "c1", label: "疎外", kind: "word", layer: 1, q: "疎外" },
      { id: "c2", label: "応用領域", kind: "word", layer: 1, q: "応用領域" },
      { id: "c3", label: "共通概念", kind: "related", layer: 2, q: "共通概念" }],
      edges: [{ from: "c1", to: "c3", strength: 1 }, { from: "c2", to: "c3", strength: 1 }] }) }); });

  await p.goto(`${B}/origin?q=%E7%96%8E%E5%A4%96&lang=ja`, { waitUntil: "networkidle" });
  await p.waitForTimeout(500);

  // soon次元をクリック（dimension Action 経由＝実UIと同じ単一Dispatcher）
  await p.evaluate(() => { const x = document.getElementById("graph-panel"); if (x) x.remove(); });
  await p.evaluate(() => __dx.dispatch("dimension", { term: "疎外" }, { dm: { status: "soon", label: "応用領域", act: "" } }));
  await p.waitForTimeout(900);
  ok("soon次元クリックで組合せ探索(/api/combine)が実行された", combineHits >= 1, combineArgs.replace(B, ""));
  let vs = await p.evaluate(() => __dx.viewState());
  ok("実データが返り組合せ状態が確定（説明で止まらない）", !!(vs && vs.combine && vs.combine.a === "疎外" && vs.combine.b === "応用領域"), JSON.stringify(vs && vs.combine));
  let stop = await p.evaluate(() => { const el = document.querySelector("#graph-panel .gp-body"); const t = el ? el.innerText : ""; return /整備中|準備中|coming|この次元は/.test(t); });
  ok("『整備中／準備中／coming』の停止型パネルが出ない", stop === false);

  // 未知actの次元も同様に組合せ実データへ流れる（停止しない）
  const before = combineHits;
  await p.evaluate(() => { const x = document.getElementById("graph-panel"); if (x) x.remove(); });
  await p.evaluate(() => __dx.dispatch("dimension", { term: "疎外" }, { dm: { status: "ok", label: "他の伝統", act: "unknown:xyz" } }));
  await p.waitForTimeout(900);
  ok("未知actの次元クリックも組合せ実データへ（準備中で止めない）", combineHits > before);

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
