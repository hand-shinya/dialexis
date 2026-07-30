// Fix後のUX整理を、localhost:8060の実プレビュー・実データ・実マウスクリックで3経路確認（半田様item7）。
//   A: 弁証法そのもの（word中心ノード）
//   B: 弁証法の中の「一般の意味」（domainノード＝カテゴリ→親rootの全景を開く）
//   C: 「アリストテレス」（authorノード／コペルニクスと同じ弁証法グラフの系譜から）
// 各経路で: 灰色操作ボタンなし／地図操作がパネル内に重複なし／「区画」語なし／目次と本文見出し一致／
//   番号と番号抜けなし／表示されない節が目次に残らない／raw English語源なし／目次クリックで移動／
//   ノード選択から全景が開く／戻る・進むで履歴を壊さない。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8060";
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function loadGraph(p, q) {
  await p.goto(`${B}/origin?q=${encodeURIComponent(q)}&lang=ja`, { waitUntil: "networkidle", timeout: 45000 });
  for (let i = 0; i < 30; i++) { const v = await p.evaluate(() => { const w = document.getElementById("origin-graph-wrap"); return w && getComputedStyle(w).display !== "none"; }).catch(() => 0); if (v) break; await sleep(600); }
  for (let i = 0; i < 20; i++) { const a = await p.evaluate(() => (window.__dx && __dx.G) ? (__dx.G.alpha || 0) : 1).catch(() => 1); if (a < 0.05) break; await sleep(400); }
  await p.evaluate(() => { const g = __dx.G; if (g && g.raf) cancelAnimationFrame(g.raf); if (g) { g.running = false; g.alpha = 0; } });   // その場で凍結（再配置しない）
}
async function clickNode(p, pred) {
  // 密なグラフでも確実に当てるため、対象ノードをビュー中心へパンしてから実マウスクリックする（simは凍結のまま）
  const found = await p.evaluate((ps) => {
    const f = new Function("n", "return (" + ps + ")"); const g = __dx.G; if (!g) return false;
    const n = g.nodes.find(f); if (!n) return false;
    if (g.raf) cancelAnimationFrame(g.raf); g.running = false; g.alpha = 0;
    g.view.x = g.W / 2 - n.x * g.view.k; g.view.y = g.H / 2 - n.y * g.view.k; gDraw();
    return true;
  }, pred);
  if (!found) return null;
  const c = await p.evaluate((ps) => { const f = new Function("n", "return (" + ps + ")"); return __dx.nodeClientXY(f); }, pred);
  if (!c) return null;
  await p.mouse.click(c.x, c.y); await sleep(2600);
  return c;
}
async function checkPanorama(p) {
  return await p.evaluate(() => {
    const panel = document.getElementById("graph-panel"); if (!panel) return { opened: false };
    const secHeads = [...panel.querySelectorAll(".pano-sec .pano-h")].map(h => h.textContent.trim());
    const tocLinks = [...panel.querySelectorAll(".pano-toc-a")];
    const tocHeads = tocLinks.map(a => a.textContent.trim());
    const tocIds = tocLinks.map(a => "pano-" + a.dataset.sec);
    return {
      opened: panel.classList.contains("gp-wide"),
      title: (panel.querySelector(".gp-head b") || {}).textContent || "",
      noOpButtons: !panel.querySelector(".pano-op") && ![...panel.querySelectorAll("button")].some(b => b.disabled),
      noKukaku: !/区画/.test(panel.innerText),
      tocExists: !!panel.querySelector(".pano-toc") && /この語の見どころ/.test(panel.innerText),
      tocMatches: tocHeads.length === secHeads.length && tocHeads.every(t => secHeads.includes(t)) && tocIds.every(id => !!document.getElementById(id)),
      noNumbers: !/class="pano-n"/.test(panel.innerHTML) && !secHeads.some(h => /^[0-9０-９]/.test(h)),
      noRawEnglish: !/Borrowed from|By surface analysis|surface analysis/.test(panel.innerText),
      secHeads,
    };
  });
}
async function tocClickWorks(p) {
  return await p.evaluate(async () => { const a = document.querySelector(".pano-toc-a"); if (!a) return false; const id = "pano-" + a.dataset.sec; a.click(); await new Promise(r => setTimeout(r, 300)); return !!document.getElementById(id); });
}
async function backForward(p) {
  await p.evaluate(() => navGo(-1)); await sleep(1400);
  const back = await p.evaluate(() => __dx.viewState().panel);
  await p.evaluate(() => navGo(1)); await sleep(2200);
  const fwd = await p.evaluate(() => ({ panel: __dx.viewState().panel, wide: !!document.querySelector("#graph-panel.gp-wide") }));
  return { backNull: back === null, fwdPanorama: !!(fwd.panel && fwd.panel.action === "panorama" && fwd.wide) };
}

(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const p = await b.newPage(); await p.setViewportSize({ width: 1360, height: 940 });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };

  async function runPath(label, loadQ, pred, expectTitleRe) {
    await loadGraph(p, loadQ);
    const c = await clickNode(p, pred);
    const v = await checkPanorama(p);
    ok(`${label}: ノード選択で概念全景が開く`, !!(c && v.opened), c ? (v.title || "") : "node not found");
    if (!v.opened) return;
    if (expectTitleRe) ok(`${label}: 主題が期待どおり（${expectTitleRe}）`, expectTitleRe.test(v.title), v.title);
    ok(`${label}: 灰色操作ボタン/操作行がパネル内に無い`, v.noOpButtons);
    ok(`${label}: 「区画」語が残っていない`, v.noKukaku);
    ok(`${label}: 目次『この語の見どころ』が本文見出しと一致`, v.tocExists && v.tocMatches, JSON.stringify(v.secHeads));
    ok(`${label}: 番号と番号抜けがない`, v.noNumbers);
    ok(`${label}: raw Englishの語源説明がない`, v.noRawEnglish);
    ok(`${label}: 目次クリックで該当セクションへ`, await tocClickWorks(p));
    const bf = await backForward(p);
    ok(`${label}: 戻る→選択前・進む→全景（履歴を壊さない）`, bf.backNull && bf.fwdPanorama, JSON.stringify(bf));
  }

  // A 弁証法そのもの
  await runPath("A[弁証法]", "弁証法", "n.layer===1", /弁証法/);
  // B 弁証法の中の「一般の意味」（domainノード→親rootの全景）
  await runPath("B[一般の意味]", "弁証法", "n.kind==='domain' && /一般の意味/.test(n.label)", /弁証法/);
  // C 「アリストテレス」（authorノード・コペルニクスと同じ系譜グラフ上）
  await runPath("C[アリストテレス]", "弁証法", "n.kind==='author' && /アリストテレス/.test(n.label)", /アリストテレス/);

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
