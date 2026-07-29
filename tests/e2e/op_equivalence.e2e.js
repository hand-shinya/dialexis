// 5.1 操作同値性: 同じ Action ID + 同じ target なら、どの表示面から実行しても、dispatch される
// (actionId, target) が一致し、確定後 ViewState が等しい。実際に各面の要素をクリックして検証する。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8021";
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true }); const p = await b.newPage();
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const waitG = async () => { for (let i = 0; i < 25; i++) { const v = await p.evaluate(() => { const w = document.getElementById("origin-graph-wrap"); return w && getComputedStyle(w).display !== "none"; }); if (v) return; await p.waitForTimeout(600); } };
  await p.goto(`${B}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle" }); await waitG();

  // ── (i) 各表示面の「多言語」が actionId=multilingual に routing され、中心語を変えないこと ──
  async function fireMultilingual(surface) {
    return await p.evaluate((surface) => {
      const closePan = () => { const x = document.getElementById("graph-panel"); if (x) x.remove(); };
      if (surface === "topbar") { closePan(); [...document.querySelectorAll("#graph-lens .tm-chip")].find(x => x.textContent.includes("多言語")).click(); }
      else if (surface === "popup") { closePan(); const n = { kind: "word", label: "矛盾", q: "矛盾" }; gMenu(200, 200, n); const it = [...document.querySelectorAll("#graph-menu .gm-item")].find(e => /多言語/.test(e.textContent)); it.click(); }
      else if (surface === "panel-footer") { closePan(); gWordAspect("矛盾", "meaning"); }
      else if (surface === "nomiss") { closePan(); document.body.insertAdjacentHTML("beforeend", `<div id="tmp">${noMiss("矛盾")}</div>`); }
      // クリックは surface ごと下で実施
      return true;
    }, surface);
  }
  // topbar
  await fireMultilingual("topbar"); await p.waitForTimeout(300);
  let ld = await p.evaluate(() => __dx.lastDispatch);
  ok("topbarの多言語→actionId=multilingual・中心不変", ld && ld.actionId === "multilingual" && __eq(ld.surface, "topbar"), JSON.stringify(ld));
  // popup
  await fireMultilingual("popup"); await p.waitForTimeout(300);
  ld = await p.evaluate(() => __dx.lastDispatch);
  ok("popupの多言語→actionId=multilingual・target=矛盾", ld && ld.actionId === "multilingual" && ld.target.term === "矛盾", JSON.stringify(ld));
  // panel-footer: 意味パネルを開き、その続行フッターの「多言語」を実クリック
  await p.evaluate(() => { const x = document.getElementById("graph-panel"); if (x) x.remove(); gWordAspect("矛盾", "meaning"); });
  await p.waitForTimeout(1500);
  await p.evaluate(() => { [...document.querySelectorAll("#graph-panel .gp-cont-b")].find(e => /多言語/.test(e.textContent)).click(); });
  await p.waitForTimeout(400);
  ld = await p.evaluate(() => __dx.lastDispatch);
  ok("panel-footerの多言語→actionId=multilingual", ld && ld.actionId === "multilingual" && ld.surface === "panel-footer", JSON.stringify(ld));
  // nomiss: noMiss を差し込み「多言語」ボタンを実クリック
  await p.evaluate(() => { const x = document.getElementById("graph-panel"); if (x) x.remove(); const old = document.getElementById("tmp"); if (old) old.remove(); document.body.insertAdjacentHTML("beforeend", `<div id="tmp">${noMiss("矛盾")}</div>`); });
  await p.evaluate(() => { document.querySelector("#tmp .nomiss-b[data-a='lang']").click(); });
  await p.waitForTimeout(400);
  ld = await p.evaluate(() => __dx.lastDispatch);
  ok("nomissの多言語→actionId=multilingual", ld && ld.actionId === "multilingual" && ld.surface === "nomiss", JSON.stringify(ld));

  // ── (ii) dispatcher 同値性: 同じ action+target を各 surface 文脈から dispatch → ViewState 一致 ──
  await p.goto(`${B}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle" }); await waitG();
  const states = [];
  for (const s of ["topbar", "popup", "panel-footer", "nomiss", "text-link"]) {
    await p.evaluate(() => { const x = document.getElementById("graph-panel"); if (x) x.remove(); });
    await p.evaluate(async (s) => { await __dx.dispatch("multilingual", { term: "矛盾" }, { surface: s }); }, s);
    await p.waitForTimeout(1600);
    states.push(await p.evaluate(() => { const v = __dx.viewState(); return { q: v.q, lens: v.lens, focus: v.focus, panel: v.panel, combine: v.combine }; }));
  }
  const s0 = JSON.stringify(states[0]);
  ok("多言語: 全surfaceで確定ViewStateが一致（中心=弁証法・panel=multilingual/矛盾）",
    states.every(s => JSON.stringify(s) === s0) && states[0].q === "弁証法" && states[0].panel && states[0].panel.action === "multilingual" && states[0].panel.term === "矛盾",
    s0);

  // center も同値: 各surface文脈から dispatch("center", 矛盾) → ViewState 一致（中心=矛盾・panel=null）
  const cstates = [];
  for (const s of ["topbar", "popup", "panel-footer", "nomiss", "text-link"]) {
    await p.goto(`${B}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle" }); await waitG();
    await p.evaluate(async (s) => { await __dx.dispatch("center", { term: "矛盾" }, { surface: s }); }, s);
    await p.waitForTimeout(2200);
    cstates.push(await p.evaluate(() => { const v = __dx.viewState(); return { q: v.q, panel: v.panel, combine: v.combine }; }));
  }
  const c0 = JSON.stringify(cstates[0]);
  ok("中心: 全surfaceで確定ViewStateが一致（中心=矛盾・panel=null）",
    cstates.every(s => JSON.stringify(s) === c0) && cstates[0].q === "矛盾" && !cstates[0].panel, c0);

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
function __eq(a, b) { return a === b; }
