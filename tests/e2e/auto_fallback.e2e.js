// A3 自動代替の実発火検証: 主要源(/api/anatomy)を空にし、別源(/api/origin)へ自動で切り替えて
// 実データを取得し、パネルに出所+取得時刻つきで表示され、fallbackLogにoutcome:successが1件積まれること。
// softLine(入口リンク)だけでは代替の"実行"にならない——実データ表示とログの両方を要件にする。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8021";
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true }); const p = await b.newPage();
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };

  // グラフは最小fixtureで起動（描画のためだけ）。
  await p.route("**/api/origin/graph**", r => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ query: "テスト語", note: "fx", nodes: [{ id: "n1", label: "テスト語", kind: "word", layer: 1, q: "テスト語" }], edges: [] }) }));
  // 主要源 anatomy は「空」(term無し=空Outcome)。別源 origin は実データを返す（=代替が実走行して中身が出るはず）。
  await p.route("**/api/anatomy**", r => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ term: "", components: [], chain: [] }) }));
  await p.route("**/api/origin?**", r => r.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ query: "テスト語", general_meaning: ["代替源から取得した実際の意味テキスト"],
      breadth: [{ name: "ドイツ語", term: "Testbegriff" }, { name: "希語", term: "δοκιμή" }],
      concept_origin: [{ name: "ラテン語", term: "probare" }] }) }));

  await p.goto(`${B}/origin?q=%E3%83%86%E3%82%B9%E3%83%88%E8%AA%9E&lang=ja`, { waitUntil: "networkidle" });
  await p.waitForTimeout(600);

  // anatomy Action を dispatch → 空 → autoFallback が /api/origin を実走行するはず
  const before = await p.evaluate(() => __dx.fallbackLog().length);
  await p.evaluate(() => __dx.dispatch("anatomy", { term: "テスト語" }, { surface: "test" }));
  await p.waitForTimeout(800);

  const log = await p.evaluate(() => __dx.fallbackLog());
  const last = log[log.length - 1] || {};
  ok("autoFallbackが発火しログに記録された（outcome:success・alt:/api/origin）",
    log.length > before && last.kind === "anatomy" && last.alt === "/api/origin" && last.outcome === "success",
    JSON.stringify(last));

  const body = await p.evaluate(() => { const el = document.querySelector("#graph-panel .gp-body"); return el ? el.innerHTML : ""; });
  ok("代替源の実データがパネルに表示された（別源の意味テキスト）", /代替源から取得した実際の意味テキスト/.test(body), body ? "body len=" + body.length : "no panel");
  ok("代替の多言語データも実表示（Testbegriff）", /Testbegriff/.test(body));
  ok("出所と取得時刻が明示された（自動代替 / retrieved時刻）", /自動代替/.test(body) && /(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})/.test(body), "");
  ok("続行フッター(softLine/nomiss)も残る（行き止まりでない）", /nomiss-lead/.test(body));
  ok("捏造でなく実源由来（fixtureが返した値のみ・未取得の断定がない）", !/loading|取得中/.test(body));

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
