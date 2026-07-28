// B: 視点・目的・難易度＝同じ概念を選んだ見方で。合う入口＋その見方のAI用プロンプトを出す。
const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage();
  const R = [];
  const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };

  await page.goto(`${BASE}/origin?q=%E7%96%8E%E5%A4%96&lang=ja`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  // メニュー共通コアに『見方を選ぶ』があることを確認（gActionsのword相当）
  const hasView = await page.evaluate(() => gActions({ kind: "word", label: "疎外", q: "疎外" }).some(i => /見方を選ぶ/.test(i.t)));
  ok("メニュー共通コアに『見方を選ぶ』がある（普遍）", hasView);

  await page.evaluate(() => gPerspectivePanel("疎外"));
  await page.waitForTimeout(500);
  ok("視点/目的/難易度パネルが出る", (await page.$$eval(".psp-chip", els => els.length)) >= 10);
  // 専門家向け＋レポート＋専門的 を選ぶ
  await page.$$eval(".psp-chip", els => { const s = els.find(e => e.textContent === "専門家向け"); if (s) s.click(); });
  await page.$$eval(".psp-chip", els => { const s = els.find(e => e.textContent === "専門的"); if (s) s.click(); });
  await page.click("#psp-go");
  await page.waitForFunction(() => { const t = document.querySelector(".psp-prompt"); return t && t.value.length > 200; }, null, { timeout: 12000 }).catch(() => {});
  const prompt = await page.$eval(".psp-prompt", el => el.value).catch(() => "");
  ok("この見方で見る→AI用プロンプトが生成される", prompt.length > 200, `len=${prompt.length}`);
  ok("プロンプトが専門家の見方を反映（一次文献/原語/論争）", /一次文献|原語|論争|専門/.test(prompt));
  const entries = await page.$$eval("#psp-out .ext-link", els => els.map(e => e.textContent));
  ok("専門家向けの入口（SEP/PhilPapers等）が出る", entries.some(e => /SEP|PhilPapers|OpenAlex/.test(e)), `entries=${JSON.stringify(entries)}`);

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
