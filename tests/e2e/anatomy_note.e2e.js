// 字義の注記と「内側」の印が、実際に画面へ出ていることを実描画で測る（2026-10-09）。
//
// なぜ必要か（公理7）:
//   最初は tests/test_known_harms.py が app.js と style.css を grep していた。
//   2026-10-09 の敵対的検証で、12件の破壊のうち10件がその試験を全緑のまま通った。
//   とくに次の3件は画面に何も出なくなるのに緑だった。
//     ・_compNote を `return "";` で潰す
//     ・.anat-compnote { display:none }
//     ・内側の印を空の span にする
//   文字列がsourceに在ることは、画面に出ていることを意味しない。
//
// 決定論: /api/anatomy を route で差し替える。外部取得に依存しない。
const { chromium } = require("playwright");
const BASE = process.argv[2] || "http://127.0.0.1:8099";
const R = [];
const ok = (n, c, x) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${x ? "  — " + x : ""}`); };

// 実測値（非有機的肉体・2026-10-09）: 6字のうち5字が「有機的」「肉体」の内側
const MULTI = {
  term: "非有機的肉体", chain: [], summary: "",
  components: [
    { part: "非", meaning: "not be", in_unit: "", unit_kind: "", applies_to_term: true },
    { part: "有", meaning: "to have", in_unit: "有機的", unit_kind: "lexical", applies_to_term: false },
    { part: "機", meaning: "weaving machine", in_unit: "有機的", unit_kind: "lexical", applies_to_term: false },
    { part: "的", meaning: "bright", in_unit: "有機的", unit_kind: "lexical", applies_to_term: false },
    { part: "肉", meaning: "meat", in_unit: "肉体", unit_kind: "lexical", applies_to_term: false },
    { part: "体", meaning: "alternative form of 笨", in_unit: "肉体", unit_kind: "lexical", applies_to_term: false },
  ],
  components_note: "下は1字ごとの辞書義です。うち 5 字は「有機的」「肉体」という意味のまとまりの内側にある字です。語の意味は「意味のまとまり」の層で見てください。",
  components_note_parts: { inside_count: 5, lexical_units: ["有機的", "肉体"], unresolved_units: [], whole_is_one_unit: false },
  segment_layers: [],
};

// 矛盾は1単位。矛=spear・盾=shield は語の由来そのものなので、印も注記も出してはならない。
const WHOLE = {
  term: "矛盾", chain: [], summary: "From a tale in Han Feizi.",
  components: [
    { part: "矛", meaning: "spear", in_unit: "", unit_kind: "", applies_to_term: true },
    { part: "盾", meaning: "shield", in_unit: "", unit_kind: "", applies_to_term: true },
  ],
  components_note: "",
  components_note_parts: { inside_count: 0, lexical_units: [], unresolved_units: [], whole_is_one_unit: true },
  segment_layers: [],
};

// 超越論的は「越論的」が未解決の残り（機械推定・低確度）。語と断定してはならない。
const UNRES = {
  term: "超越論的", chain: [], summary: "",
  components: [
    { part: "超", meaning: "to jump over", in_unit: "", unit_kind: "", applies_to_term: true },
    { part: "越", meaning: "to pass over", in_unit: "越論的", unit_kind: "unresolved", applies_to_term: false },
    { part: "論", meaning: "to discuss", in_unit: "越論的", unit_kind: "unresolved", applies_to_term: false },
    { part: "的", meaning: "bright", in_unit: "越論的", unit_kind: "unresolved", applies_to_term: false },
  ],
  components_note: "",
  components_note_parts: { inside_count: 3, lexical_units: [], unresolved_units: ["越論的"], whole_is_one_unit: false },
  segment_layers: [],
};

async function panel(p, payload, lang) {
  await p.route("**/api/anatomy**", r => r.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify(payload),
  }));
  await p.goto(`${BASE}/?q=${encodeURIComponent(payload.term)}&lang=${lang}`, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => typeof gAnatomyPanel === "function", null, { timeout: 15000 });
  await p.evaluate(t => gAnatomyPanel(t), payload.term);
  await p.waitForTimeout(900);
  // 見えているか（offsetHeight>0）まで測る。display:none は文字列検査では捕まらない。
  return await p.evaluate(() => {
    const vis = sel => [...document.querySelectorAll(sel)]
      .filter(e => e.offsetHeight > 0 && (e.textContent || "").trim().length > 0)
      .map(e => (e.textContent || "").trim());
    return { note: vis(".anat-compnote"), inunit: vis(".anat-inunit"),
             body: ((document.querySelector("#graph-panel .gp-body") || {}).textContent || "").trim() };
  });
}

(async () => {
  const b = await chromium.launch({ executablePath: process.env.DX_CHROMIUM });

  // 1) 複数単位の語: 注記が見え、内側の印が5つ見える（日本語）
  let p = await b.newPage();
  let v = await panel(p, MULTI, "ja");
  ok("注記が見えて出る(ja)", v.note.length === 1 && v.note[0].includes("有機的"), v.note[0] ? v.note[0].slice(0, 46) : "(なし)");
  ok("内側の印が5つ見える(ja)", v.inunit.length === 5, `count=${v.inunit.length}`);
  ok("印に単位名が入る(ja)", v.inunit.some(x => x.includes("有機的")) && v.inunit.some(x => x.includes("肉体")), v.inunit[1] || "");
  ok("字義そのものは消えていない", v.body.includes("weaving machine") && v.body.includes("spear") === false, "");
  await p.close();

  // 2) 英語UI: 読める言語で出る
  p = await b.newPage();
  v = await panel(p, MULTI, "en");
  ok("注記が英語で出る(en)", v.note.length === 1 && /inside the unit/.test(v.note[0]), v.note[0] ? v.note[0].slice(0, 56) : "(なし)");
  ok("注記に日本語が混ざらない(en)", v.note.length === 1 && !/下は1字ごとの/.test(v.note[0]), "");
  ok("印が英語で出る(en)", v.inunit.length === 5 && /inside/.test(v.inunit[0]), v.inunit[0] || "");
  await p.close();

  // 3) 1単位の語（矛盾）: 印も注記も出さない
  p = await b.newPage();
  v = await panel(p, WHOLE, "ja");
  ok("1単位の語に注記を出さない", v.note.length === 0, `count=${v.note.length}`);
  ok("1単位の語に内側の印を出さない", v.inunit.length === 0, `count=${v.inunit.length}`);
  ok("矛と盾の字義は出る", v.body.includes("spear") && v.body.includes("shield"), "");
  await p.close();

  // 4) 未解決の残り: 「意味のまとまり」と断定しない
  p = await b.newPage();
  v = await panel(p, UNRES, "ja");
  ok("未解決の残りをそう呼ぶ", v.note.length === 1 && v.note[0].includes("切り分けられていない"), v.note[0] ? v.note[0].slice(0, 50) : "(なし)");
  ok("未解決を意味のまとまりと断定しない", v.note.length === 1 && !/「越論的」という意味のまとまり/.test(v.note[0]), "");
  ok("印に機械推定と書く", v.inunit.length === 3 && v.inunit.every(x => x.includes("機械推定")), v.inunit[0] || "");
  await p.close();

  const pass = R.filter(Boolean).length;
  console.log(`\n${pass}/${R.length} PASS`);
  await b.close();
  process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
