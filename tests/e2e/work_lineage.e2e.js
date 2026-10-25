// 著作の題の系譜（所有者 2026-10-25 承認・プレビュー）。応答は固定値（決定論）。
//  ① 著作なら、翻訳・受容史の結果の先頭に「題の系譜（原題 → 各国語の題 → 日本語の訳題）」を出す
//  ② 題の語ごとの対応を、原語の辞書の訳語・訳題での語として表で示す（別の題の言語も、そうと分かる）
//  ③ 題を一つの語として分けた従来の欄は、消さずに畳む
//  ④ 著作でない語（applies=false）には何も足さない
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
const BASE = process.argv[2] || "http://127.0.0.1:8099";
const LIN = { applies: true, original: { title: "Les Mots et les Choses", lang: "fr", lang_name: "フランス語", year: "1966", authors: ["ミシェル・フーコー"], wikidata_url: "https://www.wikidata.org/wiki/Q1215306" },
  ja_title: "言葉と物", ja_editions: [{ title: "言葉と物", translators: ["渡辺一民", "佐々木明"], publisher: "新潮社", year: "1974", url: "u" }],
  titles_by_lang: [{ lang: "en", lang_name: "英語", title: "The Order of Things" }, { lang: "it", lang_name: "イタリア語", title: "Le parole e le cose" }],
  route: { known: false, text: "経路は書誌に書かれていません。" },
  align_ja: [{ orig: "Mots", lemma: "mot", candidates: ["語", "言葉"], matched: "言葉", dict_url: "u" }, { orig: "et", lemma: "et", candidates: ["と"], matched: "と", dict_url: "u" }, { orig: "Choses", lemma: "chose", candidates: ["事", "物"], matched: "物", dict_url: "u" }],
  align_ja_verdict: "逐語（原題の語がそろって現れる）",
  align_others: [{ lang: "en", verdict: "一部が逐語", align: [{ orig: "Mots", matched: "" }, { orig: "et", matched: "" }, { orig: "Choses", matched: "thing" }] }],
  align_source: "fr.wiktionary（原語の辞書の訳語）" };
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const ctx = await b.newContext({ viewport: { width: 1400, height: 1000 } });
  const json = (r, o) => r.fulfill({ contentType: "application/json", body: JSON.stringify(o) });
  await ctx.route(/\/api\/work-lineage\?/, r => json(r, new URL(r.request().url()).searchParams.get("q") === "言葉と物" ? LIN : { applies: false, item_kind: "concept" }));
  await ctx.route(/\/api\/(origin|origin\/graph|pivot|dimensions|anatomy|bridge|collocations|author|segments)\?/, r => json(r, { query: "x", nodes: [{ id: "root", label: "x", kind: "word", layer: 1, weight: 3 }], edges: [], found: false, dimensions: [], data: {} }));
  const p = await ctx.newPage(); p.on("pageerror", e => console.log("pageerror", e.message.slice(0, 200)));
  await p.goto(`${BASE}/origin?q=${encodeURIComponent("言葉と物")}&lang=ja&preview=1`, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => typeof _thWorkLineage === "function", null, { timeout: 15000 });
  const run = (w) => p.evaluate(async (w) => {
    const box = document.createElement("div"); box.id = "t-" + w; box.innerHTML = `<section class="th-section"><h3>原語・翻訳語の対応</h3><p>言葉 / 物</p></section>`;
    document.body.appendChild(box); await _thWorkLineage(box, w);
    const lin = box.querySelector(".th-lineage");
    return { first: box.firstElementChild && box.firstElementChild.className, text: lin ? lin.innerText : "", rows: lin ? [...lin.querySelectorAll(".lin-table tbody tr")].map(tr => [...tr.cells].map(c => c.innerText)) : [],
      folded: !!box.querySelector("details.dx-fold .th-section h3"), oldVisible: !!box.querySelector(":scope > .th-section:not(.th-lineage)") };
  }, w);
  const r = await run("言葉と物");
  ok("① 著作なら、結果の先頭に題の系譜（原題 → 各国語の題 → 日本語の訳題）を出す", /th-lineage/.test(r.first) && /Les Mots et les Choses/.test(r.text) && /The Order of Things/.test(r.text) && /渡辺一民・佐々木明 訳/.test(r.text), r.text.slice(0, 80));
  ok("② 題の語ごとの対応を表で示す（原題の語・辞書の見出し・辞書の日本語訳・訳題での語）", JSON.stringify(r.rows.map(x => [x[0], x[3]])) === '[["Mots","言葉"],["et","と"],["Choses","物"]]', JSON.stringify(r.rows));
  ok("② 別の題の言語は、そうと分かる（英語：一部が逐語 Choses→thing）", /一部が逐語（Choses→thing）/.test(r.text));
  ok("③ 題を一つの語として分けた従来の欄は、消さずに畳む", r.folded && !r.oldVisible, JSON.stringify({ f: r.folded, v: r.oldVisible }));
  const c = await run("実存");
  ok("④ 著作でない語には何も足さない", !c.text && c.oldVisible && !c.folded);
  await ctx.close();
  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
