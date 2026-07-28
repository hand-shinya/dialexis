const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true }); const p = await b.newPage();
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  await p.goto(`${BASE}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle" });
  await p.waitForTimeout(1500);
  ok("メニューに『語源と構成要素を解剖する』がある", await p.evaluate(() => gActions({ kind: "word", label: "弁証法", q: "弁証法" }).some(i => /解剖/.test(i.t))));
  await p.evaluate(() => gAnatomyPanel("弁証法"));
  await p.waitForFunction(() => { const g = document.querySelector("#graph-panel .gp-body"); return g && /構成要素|語源を辿れる/.test(g.textContent); }, null, { timeout: 12000 }).catch(() => {});
  const t = await p.$eval("#graph-panel .gp-body", el => el.textContent).catch(() => "");
  ok("解剖: 構成要素 dia(διά) と legein(λέγειν) が復元される", /διά|λέγειν|through|speak/.test(t), t.slice(0,50));
  ok("解剖: 失われた対話性(art of argument/questioning)が連鎖に出る", /argument|questioning|dialektik|διαλεκτ/.test(t));
  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
