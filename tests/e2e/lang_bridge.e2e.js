// 言語の橋のカード（/origin）を、実ブラウザで確かめる（2026-10-14・P9）。
// 外部の辞書・Wikidata に依らないよう、/api/origin と /api/pivot と /api/backgloss の応答は
// 固定の値で差し替える（決定論。デプロイgate対象）。実際の外部応答での挙動は tools/pivot_probe.py が測る。
//
// 守ること（所有者 2026-10-14 の指示から）:
//   1. 入力の言語・検索に使う言語・表示の言語の三つが、別々の段として画面に出る
//   2. 検索に使う言語は、応答のヒット数の多い順に並ぶ（固定の中心言語を置かない）
//   3. 展開した先の語を ↩ で開くと、利用者の言語の語義と、外部の機械翻訳（新しいタブ・未確認）が出る
//   4. 展開した先の語を押すと、その語で新しく探す（P11 作用の普遍性）
//   5. 辞書に見出しも概念も無い語では、カードを出さない（空の枠を残さない）
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
const BASE = process.argv[2] || "http://127.0.0.1:8099";

const ORIGIN = (q) => ({
  query: q, lang: "ja", queried_at: "2026-10-14T00:00:00+00:00", word: { query: q }, found: true,
  language_bridge: { applied: true, from: q, to: "自由", to_lang: "ja", display_is_ui_lang: true,
    qid: "Q2979", input_lang: "sw", input_lang_name_en: "Swahili", confirmed: false, basis: "" },
  resolved_from: null, resolved_to: "自由", suggestions: [], dimensions: [], general_meaning: [],
  segment_layers: [], collapse_warning: null, concept_origin: [], originators: [], associated: [],
  relations: { near: [], opposite: [] }, named_after: [], word_origin: null, chain: [], senses: [],
  polysemy: false, breadth: [], breadth_count: 0, qid: "Q2979", canon: {}, sources: [], confidence: {},
});
const PIVOT = (q) => ({ source: "langpivot", retrieved_at: "t", error: null, data: {
  input: q, script: "LATIN",
  dictionary: { source: "en.wiktionary", url: "https://en.wiktionary.org/wiki/uhuru", retrieved_at: "t" },
  input_candidates: [
    { code: "sw", name_en: "Swahili", name: "スワヒリ語", glosses: ["freedom", "independence"], en_lemmas: ["freedom"] },
    { code: "en", name_en: "English", name: "英語", glosses: ["freedom"], en_lemmas: [] }],
  identified: { code: "sw", name_en: "Swahili", name: "スワヒリ語", confirmed: false, same_as_ui: false, basis: "" },
  concept: { qid: "Q2979", url: "https://www.wikidata.org/wiki/Q2979", label_ui: "自由",
    description_ui: "外的束縛が無く、自らの意思に従うこと", routes: ["gloss"], confirmed_in: [], retrieved_at: "t" },
  alternatives: [{ qid: "Q37055", label_ui: "独立", ui_title: "独立", routes: ["gloss"], confirmed_in: [] }],
  // わざとヒット数の少ない順に返す。画面は多い順に並べ直すはず。
  retrieval: [
    { lang: "la", name: "ラテン語", term: "libertas", article_title: "Libertas", article_url: "https://la.wikipedia.org/wiki/Libertas", wiktionary_url: "https://en.wiktionary.org/wiki/libertas", hits: 900, bytes: 4000 },
    { lang: "de", name: "ドイツ語", term: "Freiheit", article_title: "Freiheit", article_url: "https://de.wikipedia.org/wiki/Freiheit", wiktionary_url: "https://en.wiktionary.org/wiki/Freiheit", hits: 120000, bytes: 90000 },
    { lang: "ja", name: "日本語", term: "自由", article_title: "自由", article_url: "https://ja.wikipedia.org/wiki/自由", wiktionary_url: "https://en.wiktionary.org/wiki/自由", hits: 50000, bytes: 30000 }],
  display: { lang: "ja", title: "自由" }, steps: [] } });

(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const ctx = await b.newContext(); const p = await ctx.newPage();
  const calls = { backgloss: 0 };
  // 地図の API も固定値にする。外部へ取りに行かせると、冷えたサーバでは地図の取得に20秒以上かかり、
  // その後に描かれる言語の橋のカードを15秒で待ちきれずに落ちていた（10/17・10/19・10/20 の verify 1回目）。
  await p.route(/\/api\/origin\/graph\?/, r => {
    const q = new URL(r.request().url()).searchParams.get("q");
    r.fulfill({ contentType: "application/json", body: JSON.stringify({ query: q, note: "fx", nodes: [
      { id: "root", label: q, kind: "word", layer: 1, weight: 3, q }, { id: "l1", label: "Swahili", kind: "language", layer: 2, weight: 1 }],
      edges: [{ from: "root", to: "l1" }] }) });
  });
  await p.route(/\/api\/origin\?/, r => {
    const q = new URL(r.request().url()).searchParams.get("q");
    r.fulfill({ contentType: "application/json", body: JSON.stringify(ORIGIN(q)) });
  });
  await p.route(/\/api\/pivot\?/, r => {
    const q = new URL(r.request().url()).searchParams.get("q");
    const body = q === "ことばの無い句" ? { source: "langpivot", error: null, data: { input_candidates: [], concept: null } } : PIVOT(q);
    r.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
  await p.route(/\/api\/backgloss\?/, r => {
    calls.backgloss += 1;
    const u = new URL(r.request().url());
    r.fulfill({ contentType: "application/json", body: JSON.stringify({ source: "backgloss", error: null, data: {
      term: u.searchParams.get("term"), glosses: ["自由"], gloss_lang: "ja",
      dictionary_url: "https://ja.wiktionary.org/wiki/Freiheit",
      machine_translation_url: "https://translate.google.com/?sl=de&tl=ja&text=Freiheit&op=translate", note: "" } }) });
  });

  await p.goto(`${BASE}/origin?q=uhuru&lang=ja`, { waitUntil: "domcontentloaded" });
  await p.waitForSelector("#lang-bridge .bridge-tbl", { timeout: 15000 }).catch(() => {});
  const card = await p.$("#lang-bridge");
  const text = card ? await card.innerText() : "";

  // 1. 三つの段が別々に出る
  ok("①入力の言語の段が出て、判定した言語と根拠がある", /①/.test(text) && /スワヒリ語/.test(text) && /根拠/.test(text), text.slice(0, 120));
  ok("推定であることが札で示される（照合済みと偽らない）", /推定/.test(text) && !/照合済み/.test(text));
  ok("③検索に使う言語の段が出る", /③/.test(text) && /検索に使う言語/.test(text));
  ok("④表示の言語の段が出て、利用者の言語の記事へ戻したと書かれる", /④/.test(text) && /自由/.test(text));
  ok("検索の言語と表示の言語を別々に決めていると明示される", /別々に決めています/.test(text));

  // 2. ヒット数の多い順
  const order = await p.$$eval("#lang-bridge .bridge-tbl tr td:first-child", tds => tds.map(t => t.textContent.trim()));
  ok("検索に使う言語が、ヒット数の多い順に並ぶ", JSON.stringify(order) === JSON.stringify(["ドイツ語", "日本語", "ラテン語"]), JSON.stringify(order));

  // 3. ↩ で利用者の言語へ戻す
  const back = await p.$("#lang-bridge details.bridge-back[data-term='Freiheit']");
  ok("利用者の言語の行には ↩ を置かず、ほかの言語の行には置く",
    !!back && !(await p.$("#lang-bridge details.bridge-back[data-term='自由']")));
  if (back) {
    await back.click("summary");
    await p.waitForFunction(() => {
      const d = document.querySelector("#lang-bridge details.bridge-back[data-term='Freiheit'] div");
      return d && /辞書の語義/.test(d.textContent);
    }, null, { timeout: 8000 }).catch(() => {});
    const inner = await back.innerText();
    ok("↩ を開くと、利用者の言語の辞書の語義が出る", /辞書の語義/.test(inner) && /自由/.test(inner), inner.slice(0, 80));
    const mt = await back.$("a[href^='https://translate.google.com']");
    ok("機械翻訳は外部への新しいタブのリンクで、未確認と書かれる",
      !!mt && (await mt.getAttribute("target")) === "_blank" && /未確認/.test(inner));
    await back.click("summary"); await back.click("summary");
    await p.waitForTimeout(300);
    ok("↩ を開き直しても、語義を取りに行くのは1回だけ", calls.backgloss === 1, String(calls.backgloss));
  }

  // 4. 展開した先の語を押すと、その語で新しく探す
  const link = await p.$("#lang-bridge .bridge-tbl a[href^='/origin?q=Freiheit']");
  ok("展開した先の語は、その語で新しく探すリンクになっている（P11）", !!link);

  // 5. 否定の結末文を出さない
  ok("カードに否定の結末文が無い", !/できません|見つかりません|失敗/.test(text));

  // 6. 辞書にも概念にも着かない語では、カードを出さない
  await p.goto(`${BASE}/origin?q=${encodeURIComponent("ことばの無い句")}&lang=ja`, { waitUntil: "domcontentloaded" });
  await p.waitForSelector(".word-card", { timeout: 15000 }).catch(() => {});
  await p.waitForTimeout(1500);
  ok("辞書にも概念にも着かない語では、言語の橋のカードを残さない", !(await p.$("#lang-bridge")));

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
