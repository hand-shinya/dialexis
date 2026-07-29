// 応用・波及レンズ: 作品への応用に加え、社会体制・思想・運動への波及（資本論→共産主義/
// マルクス主義…）が出ること。半田様指摘「社会体制のきっかけが表現されていない」の是正。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage();
  const R = [];
  const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };

  await page.goto(`${BASE}/origin?q=%E8%B3%87%E6%9C%AC%E8%AB%96&lang=ja`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  await page.evaluate(()=>{const c=[...document.querySelectorAll("#graph-lens .tm-chip")].find(x=>x.textContent.includes("見方"));if(c)c.click();}); await page.waitForTimeout(350); await page.click('.lens-row[data-k="applications"]');
  await page.waitForTimeout(3500);

  const info = await page.evaluate(() => ({
    doms: G.nodes.filter(n => n.kind === "appdomain").map(n => n.label),
    labels: G.nodes.map(n => n.label),
  }));
  ok("応用・波及に『思想・体制・運動への波及』の枝が出る",
     info.doms.some(d => /波及/.test(d)), `doms=${JSON.stringify(info.doms)}`);
  ok("資本論→共産主義/マルクス主義など社会体制への波及が出る（半田様指摘の是正）",
     info.labels.some(l => /共産主義|マルクス主義|マルクス経済学/.test(l)),
     `labels=${JSON.stringify(info.labels.filter(l => /主義|経済学|学派/.test(l)).slice(0,5))}`);
  ok("作品への応用も併存する（P921・分野別）",
     info.doms.some(d => /文学|芸術|著作/.test(d)), `doms=${JSON.stringify(info.doms)}`);

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
