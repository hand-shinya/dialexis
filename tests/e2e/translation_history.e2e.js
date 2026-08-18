// 翻訳・受容史の特別Actionを、Menu→実DOMクリック→専用API→次の分野、の順で検証する。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8028";
(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage();
  const R = [];
  const ok = (name, condition, detail) => { R.push(condition); console.log(`${condition ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`); };

  await page.route("**/api/origin/graph**", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ query: "非有機的肉体", note: "fixture", nodes: [
      { id: "root", label: "非有機的肉体", kind: "word", layer: 1, q: "非有機的肉体" },
      { id: "leib", label: "Leib", kind: "original", layer: 2, q: "Leib", lang: "de" },
      { id: "koerper", label: "Körper", kind: "original", layer: 2, q: "Körper", lang: "de" }],
      edges: [{ from: "root", to: "leib", strength: 1 }, { from: "root", to: "koerper", strength: 1 }] })
  }));
  await page.goto(`${B}/origin?q=${encodeURIComponent("非有機的肉体")}&lang=ja`, { waitUntil: "networkidle" });
  await page.waitForSelector("#origin-graph-wrap", { state: "visible", timeout: 15000 });
  await page.waitForTimeout(500);

  const rootBefore = await page.evaluate(() => __dx.G && __dx.G.rootQ);
  await page.evaluate(() => {
    const n = __dx.G.nodes.find(x => x.kind === "word");
    gMenu(240, 240, n);
  });
  const menuHas = await page.locator("#graph-menu .gm-item").allTextContents();
  ok("語のMenuに専用の『翻訳・受容史』Actionがある", menuHas.some(x => x.includes("翻訳・受容史")), `items=${menuHas.length}`);

  await page.locator("#graph-menu .gm-item").filter({ hasText: "翻訳・受容史" }).click();
  await page.waitForSelector("#graph-panel .th-ready", { state: "visible", timeout: 15000 });
  const first = await page.evaluate(() => ({
    root: __dx.G && __dx.G.rootQ,
    panel: __dx.lastDispatch && __dx.lastDispatch.actionId,
    body: (document.querySelector("#graph-panel .gp-body") || {}).textContent || "",
    back: !!document.querySelector("#graph-panel .gp-back"),
    footer: document.querySelectorAll("#graph-panel .gp-cont-b").length
  }));
  ok("実DOMクリックがtranslationHistoryへ到達する", first.panel === "translationHistory", JSON.stringify(first.panel));
  ok("専用面が地図の中心を変えない", first.root === rootBefore, `root=${first.root}`);
  ok("原語・翻訳語の対応と証拠階層が表示される", /原語・翻訳語の対応/.test(first.body) && /unorganischer Leib/.test(first.body) && /Körper/.test(first.body) && /証拠階層/.test(first.body));
  ok("時系列5W1H・受容史台帳・反証・出所が同じ面に出る", /時系列 5W1H/.test(first.body) && /受容史の人物台帳/.test(first.body) && /最強の反証/.test(first.body) && /参照先/.test(first.body));
  ok("特別面にも通常の次アクションとMenuへの戻りがある", first.back && first.footer >= 5, `back=${first.back} footer=${first.footer}`);
  ok("通常フッターからも同じ翻訳・受容史Actionへ進める", /翻訳・受容史/.test(first.body) || first.footer >= 7, `footer=${first.footer}`);

  await page.selectOption("#th-domain", "science");
  await page.click(".th-run");
  await page.waitForSelector("#graph-panel .th-discovery, #graph-panel .th-unseeded", { state: "visible", timeout: 30000 });
  const empty = await page.locator("#graph-panel .gp-body").textContent();
  ok("未整備の科学分野でも予備台帳または調査計画を出す", /自動予備台帳|初回調査/.test(empty) && /情報源の選定計画|最初に揃える証拠/.test(empty) && !/unorganischer Leib/.test(empty));

  await page.locator("#graph-panel .gp-back").click();
  await page.waitForSelector("#graph-menu", { state: "visible", timeout: 5000 });
  ok("←メニューで同じ語のMenuへ戻り、次の選択ができる", await page.locator("#graph-menu .gm-item").count() > 0);

  const otherKinds = await page.evaluate(() => ["author", "work", "original", "language", "related"].map(kind => {
    const items = gActions({ kind, label: "自由", q: "自由" });
    return [kind, items.some(x => x.action === "translationHistory")];
  }));
  ok("人物・著作・原語・言語・関連語のMenuにも同じActionがある", otherKinds.every(([, v]) => v), JSON.stringify(otherKinds));

  await page.evaluate(() => {
    const n = { id: "unknown", label: "自由", q: "自由", kind: "word", layer: 1 };
    gMenu(240, 240, n);
  });
  await page.locator("#graph-menu .gm-item").filter({ hasText: "翻訳・受容史" }).click();
  await page.waitForSelector("#graph-panel .th-discovery, #graph-panel .th-unseeded", { state: "visible", timeout: 30000 });
  const unknown = await page.locator("#graph-panel .gp-body").textContent();
  const candidateLinks = await page.locator("#graph-panel .th-source-card a").count();
  ok("未登録の別語でも無反応にならず、自動予備台帳または調査台帳が開く", /自由/.test(unknown) && /自動予備台帳|調査台帳/.test(unknown) && candidateLinks >= 3);

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
