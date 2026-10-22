// O9 黙って消えた情報／O10 件数の無い畳み（所有者 2026-10-22「必要・不要を先に分けて出さないのは危険。全部出して利用者が取捨選択」）。
// サーバが返したデータ（/api/origin）の各項目が、画面のどこか（畳んだ中も含む DOM の文字）に在るかを照合する。
// 在れば「出ている」（畳んでいてもよい）。無ければ「黙って消えた」。畳む <details> の見出しに件数が無ければ O10。
// usage: node completeness.js <baseURL> <outJson> 語...
"use strict";
const fs = require("fs"), path = require("path");
const { chromium } = require(path.join(__dirname, "..", "..", "node_modules", "playwright-core"));
const EXE = process.env.DX_CHROMIUM || `${process.env.HOME}/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome`;
const [base, out, ...words] = process.argv.slice(2);
const norm = (s) => String(s || "").replace(/\s+/g, "").toLowerCase();
function items(d) {
  const it = [];
  const add = (kind, v) => { if (v && String(v).trim()) it.push({ kind, v: String(v).trim() }); };
  (d.general_meaning || []).forEach(x => add("意味", String(x).slice(0, 24)));
  (d.breadth || []).filter(b => b.term).forEach(b => add("多言語", b.term));
  (d.concept_origin || []).forEach(o => add("原語", o.term));
  (d.associated || []).forEach(a => add("関連する人", a.label || a.name || a));
  (d.originators || []).forEach(a => add("立てた人", a.label || a.name || a));
  (d.relations_typed || []).forEach(r => add("型つき関係", r.label));
  ((d.collapse_warning || {}).lemmas || []).forEach(l => add("埋没した原語", l.lemma));
  add("別の記事", d.rejected_article); add("転送先", d.redirected_to);
  ((d.segment_layers || []).find(x => x.level === "character") || { units: [] }).units.forEach(u => add("字", u.text));
  return it;
}
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const res = [];
  for (const w of words) {
    const p = await (await b.newContext({ viewport: { width: 1920, height: 1080 } })).newPage();
    await p.goto(`${base}/origin?q=${encodeURIComponent(w)}&lang=ja&preview=1`, { waitUntil: "domcontentloaded" });
    await p.waitForSelector(".word-card:not(.origin-loading-card)", { timeout: 120000 }).catch(() => {});
    await p.waitForFunction(() => window.__dx && window.__dx.G, null, { timeout: 120000 }).catch(() => {});
    await p.waitForTimeout(2500);
    const d = await p.evaluate(async (q) => (await fetch(`/api/origin?q=${encodeURIComponent(q)}&lang=ja&preview=1`)).json(), w);
    // 利用者が開ける面を開く（円形メニューと同じ受け口から）: 意味・多言語・埋没・全体像
    for (const a of ["meaning", "multilingual", "collapse", "panorama"]) {
      await p.evaluate((a) => dispatchAction(a, { term: (window.__dx.G && window.__dx.G.rootQ) || "", kind: "word" }, currentViewState(), { surface: "radial" }), a).catch(() => {});
      await p.waitForTimeout(3500);
    }
    // 全体像の中の「全ての表記を見る」のような追加読み込みは押さない（畳んだ中身は DOM に在る前提を試す）
    // 観測できたかの確認: 語のカードと地図が出ていなければ「黙って消えた」と判定せず「観測できず」とする（空の画面で全件を欠落と数えた誤り・10-22）
    const loaded = await p.evaluate(() => !!document.querySelector(".word-card:not(.origin-loading-card)"));
    if (!loaded) { res.push({ word: w, unobserved: true }); console.log(`${w}: 観測できず（語のカードか地図が出ていない）`); await p.close(); continue; }
    const dom = await p.evaluate(() => document.documentElement.textContent);
    const folds = await p.evaluate(() => [...document.querySelectorAll(".gp-body details, .pano details, [class*=context] details")].map(x => {
      const s = x.querySelector("summary"); return s ? s.textContent.trim().slice(0, 80) : "(見出しなし)"; }));
    const D = norm(dom);
    const all = items(d), missing = all.filter(x => !D.includes(norm(x.v)));
    const noCount = folds.filter(t => !/\d/.test(t));
    res.push({ word: w, items: all.length, missing, noCountFolds: noCount, folds: folds.length });
    console.log(`${w}: 項目 ${all.length}・画面に無い ${missing.length}・件数の無い畳み ${noCount.length}/${folds.length}`);
    missing.slice(0, 8).forEach(x => console.log(`   O9 黙って消えた [${x.kind}] ${x.v}`));
    noCount.slice(0, 5).forEach(x => console.log(`   O10 件数の無い畳み「${x}」`));
    await p.close();
  }
  fs.writeFileSync(out, JSON.stringify(res, null, 1)); await b.close();
})().catch(e => { console.error(e); process.exit(2); });
