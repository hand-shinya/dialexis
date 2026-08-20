// 操作レビュー回帰:
// 1) Menu/Actionの広いヘッダ領域をドラッグできる
// 2) Action→Actionの置換後に×で直前のActionへ戻る
// 3) 翻訳・受容史の「保存→台帳を開く」から戻った時、Map/ViewStateを初期化しない
// 外部情報はfixtureに固定し、UIの帰路契約だけを検証する。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8831";

const graph = { query: "弁証法", nodes: [
  { id: "root", label: "弁証法", kind: "word", layer: 1, q: "弁証法" },
  { id: "orig", label: "Dialektik", kind: "original", layer: 2, q: "Dialektik", lang: "de" },
  { id: "author", label: "ヘーゲル", kind: "author", layer: 2, q: "ヘーゲル" },
], edges: [{ from: "root", to: "orig" }, { from: "root", to: "author" }] };
const origin = { query: "弁証法", word: { query: "弁証法" }, general_meaning: ["fixtureの意味"], breadth: [],
  concept_origin: [], word_origin: null, chain: [], relations: { near: [], opposite: [] }, associated: [], sources: [],
  collapse_warning: null, confidence: {} };
const dossier = { status: "ready", query: "弁証法", domain: "philosophy", verified_at: "fixture",
  honesty: "候補と証拠を分ける", evidence_levels: [], saved_ledgers: [],
  dossier: { title: "弁証法の台帳", center_question: "誰がどの版で使ったか", scope_note: "fixture",
    sources: [], term_map: [{ source_term: "Dialektik", language: "ドイツ語", kind: "原語", japanese_candidates: ["弁証法"], distinction: "fixture", preserved: "", lost_or_shifted: "", added: "" }],
    timeline: [], transformations: [], reception_ledger: [], counterchecks: [], source_plan: [], next_actions: [] },
  source_candidates: [], next_actions: [] };

(async () => {
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const R = [];
  const ok = (name, condition, detail) => { R.push(!!condition); console.log(`${condition ? "PASS" : "FAIL"}  ${name}${detail ? " — " + detail : ""}`); };

  await page.route("**/api/origin/graph**", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(graph) }));
  await page.route("**/api/origin?**", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(origin) }));
  await page.route("**/api/anatomy?**", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ term: "弁証法", segment_layers: [], components: [], chain: [] }) }));
  await page.route("**/api/translation-history?**", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(dossier) }));
  await page.route("**/api/projects**", r => r.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  // The HTML route is served by the real local app, so create one real row first;
  // only the slow/history payload is fixture-controlled. This keeps the test
  // focused on route restoration without depending on a pre-existing database.
  const seedResponse = await page.request.post(`${B}/api/ledgers`, { data: {
    title: "弁証法の帰路fixture", subject: "弁証法", central_question: "誰がどの版で使ったか", subject_type: "term"
  } });
  const seedPayload = await seedResponse.json();
  const ledgerId = Number(seedPayload.ledger && seedPayload.ledger.id);
  if (!ledgerId) throw new Error("fixture ledger was not created");
  await page.route("**/api/ledgers/from-translation-history", r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: ledgerId, ledger: { id: ledgerId, title: "弁証法の台帳" } }) }));
  await page.route(`**/api/ledgers/${ledgerId}`, r => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ledger: { id: ledgerId, title: "弁証法の台帳", status: "active", version: 1, central_question: "誰がどの版で使ったか" }, entries: [], sources: [], entry_sources: [], linked_projects: [], counts: { entries: 0, projects: 0, confirmed: 0, candidate: 0 } }) }));

  await page.goto(`${B}/origin?q=${encodeURIComponent("弁証法")}&lang=ja`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => !!(window.__dx && __dx.G && __dx.G.nodes && __dx.G.nodes.length), null, { timeout: 15000 });
  ok("前編の境界宣言がMap入口に表示される", await page.locator("#scope-boundary").innerText().then(x => /人類の知を網羅する装置ではありません/.test(x) && /自動抽出は証拠ではなく候補/.test(x)));
  ok("後編の長文入口と出典第一級欄がある", await page.locator("#long-text-entry").count() === 1 && await page.locator("#long-text-entry input").count() >= 5);

  await page.evaluate(() => gMenu(220, 220, { id: "word:弁証法", label: "弁証法", q: "弁証法", kind: "word", layer: 1 }));
  const m0 = await page.locator("#graph-menu").boundingBox();
  await page.mouse.move(m0.x + m0.width / 2, m0.y + 14); await page.mouse.down();
  await page.mouse.move(m0.x + 90, m0.y + 84); await page.mouse.up();
  const m1 = await page.locator("#graph-menu").boundingBox();
  ok("Menuは左上の把手に限定されず、タイトル中央から移動できる", m1 && (Math.abs(m1.x - m0.x) > 5 || Math.abs(m1.y - m0.y) > 5), `${JSON.stringify(m0)} → ${JSON.stringify(m1)}`);

  await page.locator("#graph-menu .gm-item").filter({ hasText: "解剖" }).click();
  await page.waitForSelector("#graph-panel", { state: "visible" });
  const p0 = await page.locator("#graph-panel").boundingBox();
  await page.mouse.move(p0.x + p0.width / 2, p0.y + 15); await page.mouse.down();
  await page.mouse.move(p0.x + 80, p0.y + 80); await page.mouse.up();
  const p1 = await page.locator("#graph-panel").boundingBox();
  ok("Action面もヘッダ中央の広い領域から移動できる", p1 && (Math.abs(p1.x - p0.x) > 5 || Math.abs(p1.y - p0.y) > 5), `${JSON.stringify(p0)} → ${JSON.stringify(p1)}`);

  await page.locator("#graph-panel .gp-cont-b").filter({ hasText: "多言語" }).click();
  await page.waitForTimeout(150);
  await page.locator("#graph-panel .gp-x").click();
  const parent = await page.evaluate(() => ({ action: __dx.viewState().panel && __dx.viewState().panel.action, title: document.querySelector("#graph-panel .gp-head b")?.textContent || "" }));
  ok("展開先を閉じると直前のAction面へ戻る", parent.action === "anatomy" && /解剖/.test(parent.title), JSON.stringify(parent));

  // 翻訳・受容史面を開き、Actionの位置を変えてから保存→台帳→帰路を実行する。
  await page.evaluate(async () => { await __dx.dispatch("translationHistory", { term: "弁証法" }, {}); });
  await page.waitForSelector("#graph-panel .th-ready", { state: "visible", timeout: 10000 });
  const th0 = await page.locator("#graph-panel").boundingBox();
  await page.mouse.move(th0.x + th0.width / 2, th0.y + 15); await page.mouse.down();
  await page.mouse.move(th0.x + 60, th0.y + 65); await page.mouse.up();
  const savedState = await page.evaluate(() => __dx.viewState());
  await page.locator(".th-save-ledger").click();
  await page.waitForFunction((id) => document.querySelector(".th-save-ledger")?.dataset.savedLedgerId === String(id), ledgerId, { timeout: 10000 });
  ok("台帳保存後のボタンが再び有効な『台帳を開く』操作になる", await page.locator(".th-save-ledger").isEnabled() && /保存しました/.test(await page.locator(".th-save-ledger").innerText()));
  await Promise.all([
    page.waitForURL(u => u.pathname === `/ledger/${ledgerId}` && !!u.searchParams.get("return_token"), { timeout: 10000 }),
    page.locator(".th-save-ledger").click(),
  ]);
  ok("保存→台帳を開くが元画面の帰路tokenを持つ", new URL(page.url()).searchParams.has("return_token"));
  const back = page.locator("[data-route-back]");
  const backHref = await back.getAttribute("href");
  ok("台帳画面の戻る先が元のMap URLである", backHref.includes("/origin?") && decodeURIComponent(backHref).includes("弁証法"), JSON.stringify({ href: backHref, url: page.url() }));
  await Promise.all([
    page.waitForURL(u => u.pathname === "/origin" && !u.searchParams.has("return_token"), { timeout: 15000 }),
    back.click(),
  ]);
  await page.waitForSelector("#graph-panel .th-ready", { state: "visible", timeout: 15000 });
  const restored = await page.evaluate(() => ({ root: G && G.rootQ, view: __dx.viewState(), rect: __dx.surfaces().rects.action }));
  ok("台帳から戻っても中心語・翻訳受容史Actionが復元される", restored.root === "弁証法" && restored.view.panel && restored.view.panel.action === "translationHistory", JSON.stringify(restored.view));
  ok("帰路後もActionの移動位置が保存される", savedState.panel_position && restored.rect && Math.abs(savedState.panel_position.x - restored.rect.left) < 8 && Math.abs(savedState.panel_position.y - restored.rect.top) < 8, JSON.stringify({ saved: savedState.panel_position, restored: restored.rect }));

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await browser.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
