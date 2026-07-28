// Real-browser E2E: reproduce clicking the graph menu and the dimension nav,
// so we stop guessing whether "it works". Uses cached chromium.
const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8820";

const results = [];
function log(name, ok, detail) { results.push({ name, ok, detail }); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`); }

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errs = [];
  page.on("pageerror", e => errs.push(String(e)));
  page.on("console", m => { if (m.type() === "error") errs.push("console:" + m.text()); });

  await page.goto(`${BASE}/origin?q=${encodeURIComponent("疎外")}&lang=ja`, { waitUntil: "networkidle" });

  // 1. graph settled with nodes
  let settled = false;
  for (let i = 0; i < 60; i++) {
    settled = await page.evaluate(() => typeof G !== "undefined" && G && !G.running && G.nodes && G.nodes.length > 1);
    if (settled) break;
    await page.waitForTimeout(300);
  }
  log("graph loaded & settled", settled, settled ? await page.evaluate(() => G.nodes.length + " nodes") : "no G/settle");
  if (!settled) { console.log("ERRORS:", errs.slice(0, 5)); await browser.close(); process.exit(1); }

  const canvasBox = await page.locator("#origin-graph").boundingBox();
  async function screenOf(pred) {
    return await page.evaluate((p) => {
      const n = G.nodes.find(new Function("n", "return " + p)) || null;
      if (!n) return null;
      return { sx: n.x * G.view.k + G.view.x, sy: n.y * G.view.k + G.view.y, label: n.label, kind: n.kind };
    }, pred);
  }
  async function waitSettle() {
    for (let i = 0; i < 40; i++) { if (await page.evaluate(() => typeof G !== "undefined" && G && !G.running && G.nodes && G.nodes.length > 1)) return; await page.waitForTimeout(300); }
  }
  async function clickNode(pred, name) {
    await waitSettle();
    await page.locator("#origin-graph").scrollIntoViewIfNeeded();   // canvas may have scrolled off
    const box = await page.locator("#origin-graph").boundingBox();   // fresh box (never stale)
    const s = await screenOf(pred);
    if (!s) { log(name + " (locate)", false, "node not found"); return null; }
    await page.mouse.move(box.x + s.sx, box.y + s.sy);
    await page.mouse.down(); await page.mouse.up();
    await page.waitForTimeout(200);
    const menu = await page.locator("#graph-menu").count();
    log(name + " → menu opens", menu > 0, `node="${s.label}" (${s.kind}) menuCount=${menu}`);
    return menu > 0;
  }

  // jittery click (human finger moves a few px) — must STILL open the menu
  async function clickNodeJitter(pred, name, jitter) {
    const s = await screenOf(pred);
    if (!s) { log(name, false, "node not found"); return; }
    await page.mouse.move(canvasBox.x + s.sx, canvasBox.y + s.sy);
    await page.mouse.down();
    await page.mouse.move(canvasBox.x + s.sx + jitter, canvasBox.y + s.sy + jitter);
    await page.mouse.up();
    await page.waitForTimeout(200);
    const menu = await page.locator("#graph-menu").count();
    log(name, menu > 0, `jitter=${jitter}px menuCount=${menu}`);
    await page.evaluate(() => { const m = document.getElementById("graph-menu"); if (m) m.remove(); });
  }
  await clickNodeJitter("n.kind==='word'", "click w/ 5px jitter → menu still opens", 5);
  // a deliberate drag (15px) must NOT open the menu (it repositions instead)
  {
    const s = await screenOf("n.kind==='word'");
    await page.mouse.move(canvasBox.x + s.sx, canvasBox.y + s.sy);
    await page.mouse.down();
    await page.mouse.move(canvasBox.x + s.sx + 40, canvasBox.y + s.sy + 40, { steps: 4 });
    await page.mouse.up();
    await page.waitForTimeout(150);
    const menu = await page.locator("#graph-menu").count();
    log("deliberate 40px drag → NO menu (drag, not click)", menu === 0, `menuCount=${menu}`);
    await page.evaluate(() => { const m = document.getElementById("graph-menu"); if (m) m.remove(); });
  }

  // 2. click ROOT node → menu
  await clickNode("n.kind==='word'", "click root word");
  // click a menu item: '深く調べる'
  let clicked = false;
  if (await page.locator("#graph-menu").count()) {
    const item = page.locator(".gm-item", { hasText: "詳細へ" });
    if (await item.count()) { await item.first().click(); await page.waitForTimeout(400); clicked = true; }
  }
  log("menu item (詳細へ) clickable", clicked);

  // 3. click an ORIGINAL node (Entfremdung) → menu → 共起
  await page.waitForTimeout(500);
  await clickNode("n.kind==='original'", "click original node");
  let colloc = false;
  if (await page.locator("#graph-menu").count()) {
    const item = page.locator(".gm-item", { hasText: "共起" });
    if (await item.count()) {
      await item.first().click();
      // wait for panel to load collocations
      for (let i = 0; i < 20; i++) { if (await page.locator("#graph-panel .orig-collo").count()) { colloc = true; break; } await page.waitForTimeout(300); }
    }
  }
  log("menu '共起' → collocation panel with data", colloc);
  await page.evaluate(() => { const p = document.getElementById("graph-panel"); if (p) p.remove(); });

  // 3b. KARL MARX node specifically → '調べる' → real data (bio + works + source)
  await page.waitForTimeout(400);
  const marxPred = "n.kind==='author' && /マルクス/.test(n.label)";
  const openedMarx = await clickNode(marxPred, "click KARL MARX node");
  let investigated = false, hasWorks = false, hasSource = false, extractLen = 0;
  if (openedMarx) {
    const item = page.locator(".gm-item", { hasText: "調べる" });
    if (await item.count()) {
      await item.first().click();
      for (let i = 0; i < 25; i++) { if (await page.locator("#graph-panel table.plain").count()) { investigated = true; break; } await page.waitForTimeout(300); }
      if (investigated) {
        const body = await page.locator("#graph-panel .gp-body").innerText();
        extractLen = (body || "").length;
        hasWorks = /資本論|共産党宣言|経済学/.test(body);   // real works appeared
        hasSource = await page.locator("#graph-panel a[href*='wikipedia']").count() > 0;
      }
    }
  }
  log("Marx '調べる' → panel with real bio+works", investigated && extractLen > 40, `extractLen=${extractLen}`);
  log("Marx panel shows actual works (資本論 等)", hasWorks);
  log("Marx panel shows a source link (Wikipedia)", hasSource);
  // external resources fan inside the Marx investigate panel — links, new tab
  let extLinks = 0, extNewTab = 0;
  if (investigated) {
    extLinks = await page.locator("#graph-panel .ext-link").count();
    extNewTab = await page.locator("#graph-panel .ext-link[target='_blank']").count();
  }
  log("Marx panel has external-resource links (≥15)", extLinks >= 15, `links=${extLinks}`);
  log("external links open in a NEW TAB (target=_blank)", extLinks > 0 && extNewTab === extLinks, `newtab=${extNewTab}/${extLinks}`);
  await page.evaluate(() => { const p = document.getElementById("graph-panel"); if (p) p.remove(); });
  // '中心に' must keep the graph (not blank it)
  await clickNode(marxPred, "re-click Marx for center");
  let centered = false;
  if (await page.locator("#graph-menu").count()) {
    const c = page.locator(".gm-item", { hasText: "中心に" });
    if (await c.count()) { await c.first().click(); await page.waitForTimeout(600); }
  }
  centered = await page.evaluate(() => { const w = document.getElementById("origin-graph-wrap"); return w && w.style.display !== "none" && typeof G !== "undefined" && G.nodes.length >= 1; });
  log("Marx '中心に' keeps graph (no blank)", centered);

  // 4. dimension navigator buttons (DOM)
  const dimCount = await page.locator(".dim").count();
  log("dimension buttons present", dimCount >= 5, dimCount + " dims");
  // 4a. click '関連概念' dim → collocation panel
  let dimColloc = false;
  const relBtn = page.locator(".dim", { hasText: "関連概念" });
  if (await relBtn.count()) {
    await relBtn.first().click();
    for (let i = 0; i < 20; i++) { if (await page.locator("#graph-panel .orig-collo").count()) { dimColloc = true; break; } await page.waitForTimeout(300); }
  }
  log("dim '関連概念' → collocation panel", dimColloc);
  await page.evaluate(() => { const p = document.getElementById("graph-panel"); if (p) p.remove(); });
  // 4b. click '批判・異論' dim → counter panel
  let crit = false;
  const critBtn = page.locator(".dim", { hasText: "批判" });
  if (await critBtn.count()) {
    await critBtn.first().click();
    for (let i = 0; i < 25; i++) { if (await page.locator("#graph-panel .gp-h").count()) { crit = true; break; } await page.waitForTimeout(300); }
  }
  log("dim '批判・異論' → counter panel", crit);
  await page.evaluate(() => { const p = document.getElementById("graph-panel"); if (p) p.remove(); });
  // 4c. click a 'soon' dim (時代性) → note panel
  let soon = false;
  const soonBtn = page.locator(".dim", { hasText: "時代性" });
  if (await soonBtn.count()) { await soonBtn.first().click(); await page.waitForTimeout(300); soon = await page.locator("#graph-panel").count() > 0; }
  log("dim '時代性'(soon) → note panel", soon);

  // #1 concept-specific DISCOVERED dimensions (from the concept's own article)
  let discCount = 0, discSpecific = false;
  for (let i = 0; i < 30; i++) { discCount = await page.locator("#dim-discovered .dim-disc-l").count(); if (discCount > 0) break; await page.waitForTimeout(300); }
  if (discCount > 0) { const t = await page.locator("#dim-discovered").innerText(); discSpecific = /マルクス|思想史|サルトル/.test(t); }
  log("疎外: concept-specific facets discovered (≥2)", discCount >= 2, `facets=${discCount}`);
  log("疎外 facets are concept-specific (マルクス/思想史)", discSpecific);
  // load 縁起 → facets must DIFFER (Buddhist), proving dynamic per-concept discovery
  await page.goto(`${BASE}/origin?q=${encodeURIComponent("縁起")}&lang=ja`, { waitUntil: "networkidle" });
  let engi = "";
  for (let i = 0; i < 30; i++) { if (await page.locator("#dim-discovered .dim-disc-l").count() > 0) { engi = await page.locator("#dim-discovered").innerText(); break; } await page.waitForTimeout(300); }
  const engiDiff = /仏教|中観|唯識|華厳|釈迦/.test(engi) && !/マルクス/.test(engi);
  log("縁起: DIFFERENT concept-specific facets (仏教系・not fixed)", engiDiff);

  // UNIVERSAL: clicking a node + a menu action must start FRESH from THAT word
  // (recenter search box + cards on it), never reuse the originally-entered word.
  await page.goto(`${BASE}/origin?q=${encodeURIComponent("疎外")}&lang=ja`, { waitUntil: "networkidle" });
  for (let i = 0; i < 40; i++) { if (await page.evaluate(() => typeof G !== "undefined" && G && !G.running && G.nodes && G.nodes.length > 1)) break; await page.waitForTimeout(300); }
  const box2 = await page.locator("#origin-graph").boundingBox();
  const es = await page.evaluate(() => { const n = G.nodes.find(x => x.kind === "original" && /Entfremdung/.test(x.label)); return n ? { sx: n.x * G.view.k + G.view.x, sy: n.y * G.view.k + G.view.y } : null; });
  let freshWord = "", sb = "";
  if (es) {
    await page.mouse.move(box2.x + es.sx, box2.y + es.sy); await page.mouse.down(); await page.mouse.up();
    await page.waitForTimeout(200);
    const item = page.locator(".gm-item", { hasText: "中心に据え直す" });
    if (await item.count()) {
      await item.first().click();
      for (let i = 0; i < 30; i++) { freshWord = await page.evaluate(() => { const t = document.querySelector(".theword"); return t ? t.textContent : ""; }); if (/Entfremdung/.test(freshWord)) break; await page.waitForTimeout(300); }
      sb = await page.evaluate(() => { const i = document.querySelector(".searchbox input"); return i ? i.value : ""; });
    }
  }
  log("UNIVERSAL: node action recenters FRESH on that word (Entfremdung, not 疎外)", /Entfremdung/.test(freshWord) && /Entfremdung/.test(sb), `word="${freshWord.trim()}" box="${sb}"`);

  console.log("\nPAGE ERRORS:", errs.length ? errs.slice(0, 8) : "none");
  const pass = results.filter(r => r.ok).length;
  console.log(`\n=== ${pass}/${results.length} PASS ===`);
  await browser.close();
  process.exit(pass === results.length ? 0 : 2);
})().catch(e => { console.error("E2E crash:", e); process.exit(3); });
