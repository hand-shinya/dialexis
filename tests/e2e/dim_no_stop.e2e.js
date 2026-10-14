// 資料の源が未接続の次元（soon）は、押せない札として名前だけを示す（所有者 2026-10-14 決裁）。
// 以前（2026-07-30 Fix2）は、押すと「語×次元名」で組合せ探索へ渡していた。しかし次元名の文言そのもので
// 検索するため、語と無関係な記事（責任×時代性→平成・浪曲）を、その次元の答えに見せていた。
// 07-30 の2つの指示の衝突は「契約を満たす源が無い区画は出さない・別カテゴリで穴埋めしない」を採った。
// この試験は、実DOMで押しても組合せ探索が走らず、履歴も増えず、停止型の説明パネルも出ないことを確かめる。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
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
  let ready = false;
  for (let i = 0; i < 25; i++) { ready = await p.evaluate(() => !!document.querySelector("#origin-results .dim-off")); if (ready) break; await p.waitForTimeout(400); }
  ok("源が未接続の次元が、押せない札（.dim-off）として描画された", ready);
  const info = await p.evaluate(() => { const el = document.querySelector("#origin-results .dim-off");
    return el ? { text: el.textContent, tag: el.tagName, dis: el.getAttribute("aria-disabled"), isDim: el.classList.contains("dim") } : null; });
  ok("札はボタンでなく、aria-disabled で、押せる .dim の扱いを受けない",
    !!info && info.tag !== "BUTTON" && info.dis === "true" && !info.isDim, JSON.stringify(info));
  ok("札は実際の状態（資料の源は未接続）を示し、組合せ探索を名乗らない",
    !!info && /未接続/.test(info.text) && !/組合せで探索/.test(info.text), info && info.text.trim());

  const lenBefore = await p.evaluate(() => __dx.nav.len);
  await p.click("#origin-results .dim-off", { force: true });   // ← 実DOMクリック
  await p.waitForTimeout(1200);
  ok("押しても組合せ探索（/api/combine）は走らない", combineHits === 0, String(combineHits));
  const lenAfter = await p.evaluate(() => __dx.nav.len);
  ok("押しても履歴は増えない", lenAfter === lenBefore, `len ${lenBefore}→${lenAfter}`);
  const stop = await p.evaluate(() => { const el = document.querySelector("#graph-panel .gp-body"); const t = el ? el.innerText : ""; return /整備中|準備中|coming|この次元は/.test(t); });
  ok("『整備中／準備中／coming』の停止型パネルも出ない", stop === false);

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
