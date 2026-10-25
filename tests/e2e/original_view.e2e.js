// 原語版の記事から見る（所有者 2026-10-25 承認・プレビュー）。応答は固定値（決定論）。
//  ① 語の操作（円形メニューの項目）に「原語版から見る」が在り、押すとパネルが開く
//  ② 原語版の記事の本文がリンクする項目数と、日本語版の本文にも在る数・無い数を示す
//  ③ 節見出しは原語のまま、項目は日本語の名前と原語、日本語版にも在るものに印
//  ④ 「日本語版の本文に無いものだけ」で、在るものを隠せる
//  ⑤ ほかの言語版へ切り替えられる（src を渡す）
//  ⑥ 通常表示のメニューには出ない
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || ((process.env.HOME || "") + "/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome");
const BASE = process.argv[2] || "http://127.0.0.1:8099";
const OV = (src) => ({ applies: true, lang: src || "fr", lang_name: src === "en" ? "英語" : "フランス語", title: src === "en" ? "The Order of Things" : "Les Mots et les Choses", url: "u", retrieved_at: "t",
  orig_lang: "fr", orig_by: "work", ja_title: "中心語", choices: [{ lang: "en", lang_name: "英語" }, { lang: "fr", lang_name: "フランス語" }],
  sections: [{ heading: "", items: [{ orig: "Michel Foucault", qid: "Q44272", ja: "ミシェル・フーコー", in_ja_article: true }] },
    { heading: "Notion d’épistémè", items: [{ orig: "Diego Vélasquez", qid: "Q297", ja: "ディエゴ・ベラスケス", in_ja_article: false }, { orig: "Wörter und Sachen", qid: "", ja: "", in_ja_article: false }] }],
  counts: { items: 3, in_ja: 1, only_here: 2 } });
const GRAPH = (q) => ({ query: q, note: "fx", nodes: [{ id: "root", label: q, kind: "word", layer: 1, weight: 3, q }, { id: "d1", label: "専門・思想の意味", kind: "domain", layer: 2, weight: 1.4 },
  { id: "a1", label: "子", kind: "related", layer: 3, weight: 1, q: "子" }], edges: [{ from: "root", to: "d1" }, { from: "d1", to: "a1" }] });
(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  const ctx = await b.newContext({ viewport: { width: 1600, height: 1000 } });
  const json = (r, o) => r.fulfill({ contentType: "application/json", body: JSON.stringify(o) });
  const srcs = [];
  await ctx.route(/\/api\/original-view\?/, r => { const s = new URL(r.request().url()).searchParams.get("src") || ""; srcs.push(s); return json(r, OV(s)); });
  await ctx.route(/\/api\/origin\/graph\?/, r => json(r, GRAPH(new URL(r.request().url()).searchParams.get("q"))));
  await ctx.route(/\/api\/(origin|pivot|dimensions|anatomy|bridge|collocations|author|segments)\?/, r => json(r, { found: false, dimensions: [], data: {}, query: "x" }));
  let p = await ctx.newPage(); p.on("pageerror", e => console.log("pageerror", e.message.slice(0, 200)));
  await p.goto(`${BASE}/origin?q=${encodeURIComponent("中心語")}&lang=ja&preview=1`, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => window.__dx && window.__dx.G && window.__dx.G.nodes.length >= 3, null, { timeout: 20000 });
  await p.waitForTimeout(1200);
  const inMenu = await p.evaluate(() => { const G = window.__dx.G; return gActions(G.nodes.find(n => n.label === "子")).some(i => i.action === "originalView"); });
  await p.evaluate(() => { const G = window.__dx.G; const n = G.nodes.find(x => x.layer === 1); return gRadialOpen(n); });
  await p.waitForSelector("#radial-menu .rad-item", { timeout: 4000 });
  await p.click("#radial-menu .rad-more").catch(() => {}); await p.waitForTimeout(250);
  await p.click("#radial-menu .rad-item[data-action='originalView']");
  await p.waitForFunction(() => { const b = document.querySelector(".ov-body"); return b && !b.querySelector(".spin"); }, null, { timeout: 8000 }).catch(() => {});
  const t = await p.$eval(".ov-body", e => e.innerText).catch(() => "");
  ok("① 語の操作に「原語版から見る」が在り、押すとパネルが開く", inMenu && /Les Mots et les Choses/.test(t));
  ok("② リンクする項目数と、日本語版の本文にも在る数・無い数を示す", /リンクしている 3 項目のうち、日本語版『中心語』の本文にもあるのは 1。残りの 2/.test(t.replace(/\s+/g, " ")), t.slice(0, 90));
  const sec = await p.evaluate(() => ({ heads: [...document.querySelectorAll(".ov-sec h4")].map(h => h.textContent), badge: [...document.querySelectorAll(".ov-item.ov-in-ja")].map(x => x.textContent) }));
  ok("③ 節見出しは原語のまま、日本語版にも在る項目に印", JSON.stringify(sec.heads) === '["（導入部）","Notion d’épistémè"]' && sec.badge.length === 1 && /ミシェル・フーコー/.test(sec.badge[0]), JSON.stringify(sec));
  await p.check(".ov-only-cb");
  const hidden = await p.evaluate(() => getComputedStyle(document.querySelector(".ov-item.ov-in-ja")).display === "none" && getComputedStyle([...document.querySelectorAll(".ov-item")].find(x => !x.classList.contains("ov-in-ja"))).display !== "none");
  ok("④ 「日本語版の本文に無いものだけ」で、在るものを隠せる", hidden);
  await p.click(".ov-lang:not(.on)"); await p.waitForTimeout(800);
  const t2 = await p.$eval(".ov-body", e => e.innerText).catch(() => "");
  ok("⑤ ほかの言語版へ切り替えられる", srcs.includes("en") && /The Order of Things/.test(t2), JSON.stringify(srcs));
  await p.close();
  p = await ctx.newPage();
  await p.goto(`${BASE}/origin?q=${encodeURIComponent("中心語")}&lang=ja&preview=0`, { waitUntil: "domcontentloaded" });
  await p.waitForFunction(() => window.__dx && window.__dx.G && window.__dx.G.nodes.length >= 3, null, { timeout: 20000 });
  const inMenu0 = await p.evaluate(() => { const G = window.__dx.G; return gActions(G.nodes.find(n => n.label === "子")).some(i => i.action === "originalView"); });
  ok("⑥ 通常表示のメニューには出ない", !inMenu0);
  await ctx.close();
  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("E2E ERROR", e); process.exit(2); });
