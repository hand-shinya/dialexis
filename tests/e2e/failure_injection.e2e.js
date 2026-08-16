// 5.3 failure injection: 主要API経路に timeout/abort/404/500/空/malformed/stale を注入し、
// (a) 生エラーがユーザー向けDOMに出ない (b) 自動代替(続行フッター)が出る (c) menu shell と戻る/進むが壊れない。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8021";
// 生エラー/技術文が本文に出ていないことの検査語
const RAWERR = ["Error", "error", "TypeError", "fetch", "undefined", "500", "404", "abort", "timeout", "NetworkError", "JSON", "stack", "e.message", "Failed to"];
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true }); const p = await b.newPage();
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const waitG = async () => { for (let i = 0; i < 25; i++) { const v = await p.evaluate(() => { const w = document.getElementById("origin-graph-wrap"); return w && getComputedStyle(w).display !== "none"; }); if (v) return; await p.waitForTimeout(600); } };
  await p.goto(`${B}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle" }); await waitG();

  const inject = async (pattern, mode) => {
    await p.unroute(pattern).catch(() => {});
    await p.route(pattern, async r => {
      if (mode === "abort") return r.abort();
      if (mode === "404") return r.fulfill({ status: 404, contentType: "application/json", body: "{}" });
      if (mode === "500") return r.fulfill({ status: 500, contentType: "text/plain", body: "Internal Server Error\n stacktrace e.message" });
      if (mode === "empty") return r.fulfill({ status: 200, contentType: "application/json", body: "{}" });
      if (mode === "malformed") return r.fulfill({ status: 200, contentType: "application/json", body: "<<<not json>>> TypeError" });
      if (mode === "partial") return r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ term: "弁証法", segment_layers: [] }) });
      if (mode === "timeout") { await new Promise(res => setTimeout(res, 6000)); return r.fulfill({ status: 200, contentType: "application/json", body: "{}" }); }
      return r.continue();
    });
  };

  // 解剖(anatomy)へ各失敗を注入 → 生エラー非露出＋続行フッター＋shell健全
  for (const mode of ["abort", "404", "500", "empty", "malformed", "timeout"]) {
    await inject("**/api/anatomy**", mode);
    await p.evaluate(() => { const x = document.getElementById("graph-panel"); if (x) x.remove(); gAnatomyPanel("弁証法"); });
    await p.waitForTimeout(mode === "timeout" ? 7000 : 2600);
    const s = await p.evaluate(() => ({
      body: (document.querySelector("#graph-panel .gp-body") || {}).textContent || "",
      cont: document.querySelectorAll("#graph-panel .gp-cont-b").length,
      shell: !!document.getElementById("origin-shell") && !!document.getElementById("nav-back"),
    }));
    const rawHit = RAWERR.filter(w => s.body.includes(w));
    ok(`anatomy/${mode}: 生エラー非露出＋続行フッター＋shell健全`, rawHit.length === 0 && s.cont >= 5 && s.shell, `raw=${JSON.stringify(rawHit)} cont=${s.cont}`);
  }
  // termだけ返る部分応答でも、配列欠落を理由に画面構築を停止しない。
  await inject("**/api/anatomy**", "partial");
  await p.evaluate(() => { const x = document.getElementById("graph-panel"); if (x) x.remove(); gAnatomyPanel("弁証法"); });
  await p.waitForTimeout(900);
  const partial = await p.evaluate(() => ({
    body: (document.querySelector("#graph-panel .gp-body") || {}).textContent || "",
    shell: !!document.getElementById("origin-shell") && !!document.getElementById("nav-back"),
  }));
  ok("anatomy/partial: 配列欠落でも画面構築を継続", !RAWERR.some(w => partial.body.includes(w)) && /原語へ辿り|Wiktionary/.test(partial.body) && partial.shell, `body=${partial.body.slice(0, 50)}`);
  await p.unroute("**/api/anatomy**").catch(() => {});

  // origin本体(originRun)へ 500 注入 → origin-status に生エラーでなく建設的代替(nomiss)
  await inject("**/api/origin?**", "500");
  await p.evaluate(() => originRun("弁証法"));
  await p.waitForTimeout(2000);
  const os = await p.evaluate(() => ({ st: (document.getElementById("origin-status") || {}).textContent || "", nomiss: document.querySelectorAll("#origin-status .nomiss-b").length }));
  ok("origin/500: 生エラー非露出＋建設的代替(nomiss)", RAWERR.filter(w => os.st.includes(w)).length === 0 && os.nomiss >= 3, `st=${os.st.slice(0, 40)} nomiss=${os.nomiss}`);
  await p.unroute("**/api/origin?**").catch(() => {});

  // stale: 遅いA→即Bで、確定状態がAで上書きされない（graph/api両方は state_consistency が担保・ここは要点のみ）
  await p.goto(`${B}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle" }); await waitG();
  await p.route("**/api/origin/graph?q=%E7%96%8E%E5%A4%96**", async r => { await new Promise(res => setTimeout(res, 3000)); return r.continue(); });
  await p.evaluate(async () => { originRecenter("疎外"); await new Promise(res => setTimeout(res, 200)); await originRecenter("自由"); });
  await p.waitForTimeout(4500);
  const finalQ = await p.evaluate(() => __dx.G ? __dx.G.rootQ : null);
  ok("stale: 遅いA応答が新Bの確定状態を上書きしない", finalQ === "自由", `finalQ=${finalQ}`);

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
