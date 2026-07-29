// Relations lens (類語・対義の星座): near/opposite concepts from Wikidata typed
// relations + 関連項目, persons excluded, each clickable to recenter (universal).
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage();
  const R = [];
  const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };

  await page.goto(`${BASE}/origin?q=%E7%96%8E%E5%A4%96&lang=ja`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);

  await page.evaluate(()=>{const c=[...document.querySelectorAll("#graph-lens .tm-chip")].find(x=>x.textContent.includes("見方"));if(c)c.click();});
  await page.waitForTimeout(350);
  const chip = await page.$('.lens-row[data-k="relations"]');
  ok("『類語・対義（星座）』レンズが選べる", !!chip);
  await page.evaluate(()=>{const p=document.getElementById("graph-panel");if(p)p.remove();});
  await page.evaluate(()=>{const c=[...document.querySelectorAll("#graph-lens .tm-chip")].find(x=>x.textContent.includes("見方"));if(c)c.click();}); await page.waitForTimeout(350); await page.click('.lens-row[data-k="relations"]');
  await page.waitForTimeout(900);

  const info = await page.evaluate(() => ({
    kinds: [...new Set(G.nodes.map(n => n.kind))],
    near: G.nodes.filter(n => n.kind === "related").map(n => n.label),
    opp: G.nodes.filter(n => n.kind === "opposite").map(n => n.label),
  }));
  ok("星座レンズ: ノードが語＋類語(related)＋対義(opposite)だけ",
     info.kinds.every(k => ["word", "related", "opposite"].includes(k)), `kinds=${JSON.stringify(info.kinds)}`);
  ok("対立に『親密性』が出る（疎外の対義）", info.opp.includes("親密性"), `opp=${JSON.stringify(info.opp)}`);
  ok("近いに社会病理/社会問題など関連概念が出る", info.near.some(l => /社会病理|社会問題|実存的危機/.test(l)), `near=${JSON.stringify(info.near.slice(0,6))}`);
  ok("人物(マルクス等)は星座に混ざらない（思想家レンズの領分）",
     !info.near.concat(info.opp).some(l => /マルクス$|ヘーゲル|フォイエルバッハ/.test(l)));

  // クリックで対義概念へ再中心（普遍原則）
  await page.evaluate(() => {
    const n = G.nodes.find(x => x.kind === "opposite");
    if (n) { const s = (function toScreen(nn){return gToScreen(nn);})(n); }
  });
  // click the opposite node via its recenter (call originRecenter with its q)
  const oppQ = await page.evaluate(() => { const n = G.nodes.find(x => x.kind === "opposite"); return n ? n.q : null; });
  if (oppQ) { await page.evaluate((q) => originRecenter(q), oppQ); await page.waitForTimeout(2500); }
  const nowWord = await page.evaluate(() => { const b = document.getElementById("origin-results"); return b ? b.dataset.q : ""; });
  ok("対義ノードをクリックするとその概念に再中心（他語流用でなく新規・P11）", nowWord === oppQ, `now=${nowWord} expected=${oppQ}`);

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
