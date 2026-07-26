// Lens E2E: the same word/data must be viewable through several selectable maps
// (半田様提案). Switching a lens re-projects the SAME fetched data (no refetch) —
// widening the doorway for curiosity.
const { chromium } = require("playwright-core");
const EXE = "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const BASE = process.argv[2] || "http://127.0.0.1:8012";

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage();
  const R = [];
  const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const kinds = () => page.evaluate(() => (G && G.nodes ? G.nodes.map(n => n.kind) : []));
  const labels = () => page.evaluate(() => (G && G.nodes ? G.nodes.map(n => n.label) : []));

  await page.goto(`${BASE}/origin?q=%E3%83%AA%E3%82%BE%E3%83%BC%E3%83%A0&lang=ja`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);

  const chips = await page.$$eval("#graph-lens .lens-chip", els => els.map(e => e.textContent.trim()));
  ok("レンズ選択チップが複数出る（見方を選べる）", chips.length >= 4, `chips=${JSON.stringify(chips)}`);
  ok("既定は俯瞰（すべて）がonで、全種別が見える",
     await page.$eval("#graph-lens .lens-chip.on", e => e.dataset.k) === "all");

  // 思想家と著作レンズ
  let reqDuring = 0;
  page.on("request", r => { if (/\/api\/origin\/graph/.test(r.url())) reqDuring++; });
  const before = reqDuring;
  await page.click('#graph-lens .lens-chip[data-k="thinkers"]');
  await page.waitForTimeout(900);
  const tk = await kinds(), tl = await labels();
  ok("思想家レンズ: ノードが語＋思想家/著作だけに絞られる",
     tk.every(k => ["word", "author", "work"].includes(k)) && tk.includes("author"), `kinds=${JSON.stringify([...new Set(tk)])}`);
  ok("思想家レンズにドゥルーズ/ガタリが出る", tl.some(l => /ドゥルーズ/.test(l)) && tl.some(l => /ガタリ/.test(l)));
  ok("レンズ切替は再取得しない（同じデータを再投影）", reqDuring === before, `graph reqs during switch=${reqDuring - before}`);

  // 世界の言語レンズ
  await page.click('#graph-lens .lens-chip[data-k="languages"]');
  await page.waitForTimeout(900);
  const lk = await kinds();
  ok("言語レンズ: ノードが語＋言語だけに絞られる",
     lk.every(k => ["word", "language"].includes(k)) && lk.includes("language"), `kinds=${JSON.stringify([...new Set(lk)])}`);

  // 俯瞰に戻す
  await page.click('#graph-lens .lens-chip[data-k="all"]');
  await page.waitForTimeout(700);
  const ak = await kinds();
  ok("俯瞰に戻すと全種別が復活する", new Set(ak).size >= 3, `kinds=${JSON.stringify([...new Set(ak)])}`);

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
