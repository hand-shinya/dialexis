const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true }); const p = await b.newPage();
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  await p.goto(`${BASE}/origin?q=%E5%BC%81%E8%A8%BC%E6%B3%95&lang=ja`, { waitUntil: "networkidle" });
  await p.waitForTimeout(1500);
  await p.evaluate(() => gContrastPanel("弁証法"));
  await p.waitForFunction(() => document.querySelector("#graph-panel .ext-term"), null, { timeout: 12000 }).catch(() => {});
  const terms = await p.$$eval("#graph-panel .ext-term", els => els.map(e => e.getAttribute("data-w")));
  ok("並置カードの原語（διά/λέγειν/dialectica）がクリック可能な.ext-term", terms.some(t => /διά|λέγειν|dialect/.test(t || "")), `terms=${JSON.stringify(terms.slice(0,4))}`);
  // λέγειν をクリック→サイト内で再中心（copy&paste不要）
  const target = "λέγειν";
  const clicked = await p.evaluate((w) => { const a = [...document.querySelectorAll("#graph-panel .ext-term")].find(e => e.getAttribute("data-w") === w); if (a) { a.click(); return true; } return false; }, target);
  await p.waitForTimeout(3500);
  const boxq = await p.evaluate(() => { const i = document.querySelector('.searchbox input[name=q]'); return i ? i.value : ""; });
  ok("原語クリックでサイト内探索が始まる（検索欄がその語に・行き止まりでない）", clicked && boxq === target, `clicked=${clicked} box=${boxq}`);
  ok("クリックでパネルが閉じ、探索へ移る", !(await p.$("#graph-panel .ext-term")));
  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
