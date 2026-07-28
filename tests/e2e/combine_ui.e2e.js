// A: 組み合わせ探索のUI導線＝ノードmenu→『別の語と組み合わせる』→語入力→AND→グラフ再描画。
// SearXNG依存のため本番(219.94.244.239)で検証する。
const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://219.94.244.239:8000";

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage();
  const R = [];
  const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };

  await page.goto(`${BASE}/origin?q=%E7%96%8E%E5%A4%96&lang=ja`, { waitUntil: "networkidle" });
  // レイアウトが沈静するまで待つ（強化した力学で settle が長め）
  await page.waitForFunction(() => typeof G !== "undefined" && G && G.running === false, null, { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(800);
  // 語ノード(root)をクリック→メニュー（座標はクリック直前に取得）
  const box = await page.$eval("#origin-graph", el => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y }; });
  const pt = await page.evaluate(() => { const n = G.nodes.find(x => x.kind === "word"); return { x: n.x * G.view.k + G.view.x, y: n.y * G.view.k + G.view.y }; });
  await page.mouse.click(box.x + pt.x, box.y + pt.y);
  await page.waitForTimeout(600);
  ok("語ノードのメニューが出る", !!(await page.$("#graph-menu")));
  await page.$$eval("#graph-menu .gm-item", els => { const t = els.find(e => /組み合わせる/.test(e.textContent)); if (t) { const r = t.getBoundingClientRect(); t.dispatchEvent(new MouseEvent("click", { bubbles: true })); } });
  await page.waitForTimeout(600);
  const panel = await page.$("#cmb-b");
  ok("『別の語と組み合わせる』でパネル＋入力が出る", !!panel);
  if (panel) {
    await page.fill("#cmb-b", "労働");
    await page.$$eval(".cmb-op", els => { const t = els.find(e => /AND/.test(e.textContent)); if (t) t.click(); });
    // グラフが 労働 との組み合わせで再描画されるのを待つ
    await page.waitForFunction(() => { const nt = document.getElementById("graph-note"); return nt && /労働/.test(nt.textContent); }, null, { timeout: 15000 }).catch(() => {});
    const note = await page.$eval("#graph-note", el => el.textContent);
    ok("ANDでグラフが『疎外＋労働』に再描画される", /労働/.test(note) && /絞り込み|AND/.test(note), `note=${note.slice(0, 30)}`);
    const labels = await page.evaluate(() => G.nodes.map(n => n.label).join(" "));
    ok("結果に労働×疎外の交差（マルクス/労働疎外など）が出る", /労働|マルクス/.test(labels), "");
  }

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
