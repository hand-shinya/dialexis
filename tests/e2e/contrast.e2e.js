const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true }); const p = await b.newPage();
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  await p.goto(`${BASE}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle" });
  await p.waitForTimeout(1500);
  ok("メニューに『訳語と原語の意味を並べて比べる』がある", await p.evaluate(() => gActions({ kind: "word", label: "弁証法", q: "弁証法" }).some(i => /並べて比べる/.test(i.t))));
  await p.evaluate(() => gContrastPanel("弁証法"));
  await p.waitForFunction(() => { const c = document.querySelector(".contrast"); return c && c.textContent.length > 60; }, null, { timeout: 12000 }).catch(() => {});
  const cols = await p.$$eval(".ct-col", els => els.map(e => e.textContent));
  ok("2列（日本語訳の意味空間／原語の意味空間）が並ぶ", cols.length === 2, `cols=${cols.length}`);
  const ja = cols[0] || "", orig = cols[1] || "";
  ok("左＝日本語の意味（論理/方法/対立）が出る", /論理|方法|対立|矛盾|哲学/.test(ja));
  ok("右＝原語の意味（対話性 dia/λέγειν/argument）が出る", /λέγειν|διά|argument|speak|through|対話/.test(orig), orig.slice(0,50));
  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
