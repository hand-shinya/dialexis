// sim2 の5人（3人の専門家の螺旋型検討・第3巡で確定。2026-10-21）。すべて規則で動く（LLM なし・合否も出さない）。
// 次に進む語は「地図の重みが最大の人物・著作・原語」＝専門家が要の語を選ぶことの、再現可能な近似（第2巡 A の反論への答え）。
// 「失望」は止める条件にしない（打ち切りの偏り・第2巡 B）。失望した手を記録するだけ。手数は固定予算。
// 画面の条件は全員に掛け、1人が動かす軸は1つ（第2巡 B・C の止揚）。
"use strict";
const { chromium } = require(require("path").join(__dirname, "..", "..", "node_modules", "playwright-core"));
const { Driver } = require("./driver");
const EXE = process.env.DX_CHROMIUM || `${process.env.HOME}/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome`;
const SWEEP = ["relationship", "meaning", "anatomy", "collapse", "multilingual", "colloc", "contrast", "panorama", "translationHistory", "author", "authorNote"];
const pickKey = (labels, visited) => labels.filter(n => n.layer > 1 && !visited.has(n.label) && ["author", "work", "original", "related"].includes(n.kind))
  .sort((a, b) => ["author", "work", "original", "related"].indexOf(a.kind) - ["author", "work", "original", "related"].indexOf(b.kind))[0];

const PERSONAS = {
  // ① 連鎖して掘る人（所有者の型）: 1366x768・マウス・待てる30秒。中心→要の語→関係→その場で広げる→…を6段。共起語は組で読み、さらにその語へ
  chain: { vp: { width: 1366, height: 768 }, touch: false, lang: "ja", wait: 30000, words: ["疎外", "世間"], async run(d, base, w) {
    await d.open(base, w, "ja", true, 60000);
    const visited = new Set([w]);
    for (let depth = 0; depth < 6; depth++) {
      const labs = await d.labels(); const n = pickKey(labs, visited); if (!n) { d.steps.push({ step: ++d.n, kind: "no-next", depth }); break; }
      visited.add(n.label);
      if (!await d.openNodeMenu(n.label)) continue;
      const items = await d.menuItems();
      d.steps.push({ step: ++d.n, kind: "menu", node: n.label, nodeKind: n.kind, items });
      if (items.some(i => i.action === "relationship")) { await d.choose("relationship", 30000); await d.closePanels(); await d.openNodeMenu(n.label); }
      if (items.some(i => i.action === "expand")) await d.choose("expand", 45000);   // 中心を変えずに、その語の先を広げる（子・孫へ）
      else if (items.some(i => i.action === "center")) await d.choose("center", 60000);
      await d.closePanels();
    }
    // 共起の連鎖（10/20 に所有者が辿った道）
    await d.open(base, w, "ja", true, 60000);
    await d.p.click("#tm-radial").catch(() => {}); await d.p.waitForTimeout(500);
    if (await d.choose("colloc", 30000)) {
      const pairs = await d.p.$$(".colloc-pair"); let pair = null;
      for (const a of pairs) if ((await a.innerText()).trim() === "entgegenwirken") pair = a; pair = pair || pairs[0];
      // 修正前の版: 共起語はその語だけの検索へのリンク（新しいタブで開くことがある）。利用者が着く先＝リンク先を同じ画面で開いて見る
      const plains = pair ? [] : await d.p.$$(".orig-collo a");
      let plain = null; for (const a of plains) if ((await a.innerText()).trim() === "entgegenwirken") plain = a; plain = plain || plains[0];
      if (plain) { const t0 = Date.now(); const w2 = (await plain.innerText()).trim(); const href = await plain.getAttribute("href");
        await d.p.goto(new URL(href, base).href + "&preview=1", { waitUntil: "domcontentloaded" });
        await d.p.waitForFunction(() => window.__dx && window.__dx.G && window.__dx.G.nodes.length >= 1, null, { timeout: 60000 }).catch(() => {});
        await d.p.waitForTimeout(3000); await d.rec("pair-solo", { b: w2, plainLink: true }, t0); }
      if (pair) { const t0 = Date.now(); await pair.click(); await d.p.waitForTimeout(6000); await d.rec("pair", { b: await pair.innerText() }, t0);
        const solo = await d.p.$(".pair-solo"); if (solo) { const t1 = Date.now(); await solo.click(); await d.p.waitForTimeout(25000); await d.rec("pair-solo", {}, t1); } }
    }
  } },
  // ② 幅で総点検する人: 1920x1080。語ごとに、中心の語と要の語1つで、メニューを全部開く
  sweep: { vp: { width: 1920, height: 1080 }, touch: false, lang: "ja", wait: 30000, words: ["疎外", "実存", "親密性", "哲学草稿", "自然", "了解"], async run(d, base, w) {
    await d.open(base, w, "ja", true, 60000);
    const labs = await d.labels(); const root = labs.find(n => n.layer === 1); const key = pickKey(labs, new Set([w]));
    for (const n of [root, key].filter(Boolean)) {
      if (!await d.openNodeMenu(n.label)) continue;
      const items = await d.menuItems(); d.steps.push({ step: ++d.n, kind: "menu", node: n.label, nodeKind: n.kind, items });
      await d.p.keyboard.press("Escape");
      for (const a of SWEEP.filter(a => items.some(i => i.action === a))) {
        await d.closePanels(); await d.openNodeMenu(n.label);
        const s = await d.choose(a, 30000); if (s) { s.node = n.label; s.nodeKind = n.kind; }
      }
      await d.closePanels();
    }
  } },
  // ③ 取り違えを探す査読者: 1920x1080。正解札（一次資料）のある語だけ。意味・多言語・全体像を開き、着いた対象を照合する
  identity: { vp: { width: 1920, height: 1080 }, touch: false, lang: "ja", wait: 30000, words: ["実存", "親密性", "空", "主体", "道", "気", "現存在", "無為"], async run(d, base, w) {
    await d.open(base, w, "ja", true, 60000);
    d.steps[d.steps.length - 1].originApi = await d.p.evaluate(async (q) => { try { const r = await fetch(`/api/origin?q=${encodeURIComponent(q)}&lang=ja&preview=1`); const j = await r.json();
      return { resolved_to: j.resolved_to, redirected_to: j.redirected_to, rejected_article: j.rejected_article, qid: j.qid, article_url: j.article_url, originators: (j.originators || []).map(o => o.name || o), associated: (j.associated || []).map(o => o.name || o).slice(0, 8) }; } catch (e) { return { error: String(e) }; } }, w);
    for (const a of ["meaning", "multilingual"]) { await d.closePanels(); await d.p.click("#tm-radial").catch(() => {}); await d.p.waitForTimeout(400); await d.choose(a, 30000); }
  } },
  // ④ 多言語の研究者: 英語の画面・1920x1080。原語・非ラテン文字の語。多言語・並置・源
  multi: { vp: { width: 1920, height: 1080 }, touch: false, lang: "en", wait: 30000, words: ["Verantwortung", "仁", "dharma", "alienation"], async run(d, base, w) {
    await d.open(base, w, "en", true, 60000);
    for (const a of ["multilingual", "contrast", "anatomy"]) { await d.closePanels(); await d.p.click("#tm-radial").catch(() => {}); await d.p.waitForTimeout(400); await d.choose(a, 30000); }
  } },
  // ⑤ 時間の無いスマホの人: 390x844・タッチ（hover なし）・待てる15秒。複合語・日常語・冷えた語。最初の画面と、分解の帯の1語だけ
  phone: { vp: { width: 390, height: 844 }, touch: true, lang: "ja", wait: 15000, words: ["非有機的肉体", "生きづらさ", "超越論的主観性", "無為"], async run(d, base, w) {
    const s = await d.open(base, w, "ja", true, 15000);
    s.patience = { firstOk: s.firstMs != null && s.firstMs <= 15000, mapOk: s.mapMs != null && s.mapMs <= 15000 };
    const part = await d.p.$("#decomp-strip .ds-part");
    if (part) { const t0 = Date.now(); await part.tap().catch(() => part.click()); await d.p.waitForTimeout(800); await d.rec("tap-part", { part: await part.innerText() }, t0, { items: await d.menuItems() }); }
    const labs = await d.labels(); const n = pickKey(labs, new Set([w]));
    if (n) { const pos = await d.openNodeMenu(n.label, true); if (pos) { const t0 = Date.now(); await d.rec("tap-node", { node: n.label }, t0, { items: await d.menuItems() }); } }
  } },
};

async function runPersona(key, base, outdir, words) {
  const P = PERSONAS[key]; const b = await chromium.launch({ executablePath: EXE, headless: true });
  const res = [];
  for (const w of (words || P.words)) {
    const ctx = await b.newContext({ viewport: P.vp, hasTouch: P.touch, isMobile: P.touch, locale: P.lang === "en" ? "en-US" : "ja-JP" });
    const page = await ctx.newPage(); page.setDefaultTimeout(P.wait + 15000);
    const errs = []; page.on("pageerror", e => errs.push(e.message.slice(0, 200)));
    const d = new Driver(page, outdir, `${key}_${w.replace(/[^\p{L}\p{N}]/gu, "")}`);
    const t0 = Date.now();
    try { await P.run(d, base, w); } catch (e) { d.steps.push({ step: ++d.n, kind: "error", error: String(e).slice(0, 300) }); }
    d.steps.push({ step: ++d.n, kind: "end", totalMs: Date.now() - t0, pageErrors: errs });
    d.save(); res.push({ word: w, steps: d.steps.length, ms: Date.now() - t0 }); console.log(key, w, d.steps.length, "steps", Math.round((Date.now() - t0) / 1000) + "s", errs.length ? "pageerrors:" + errs.length : "");
    await ctx.close();
  }
  await b.close(); return res;
}
module.exports = { PERSONAS, runPersona };
if (require.main === module) {
  const [key, base, outdir, ...words] = process.argv.slice(2);
  runPersona(key, base, outdir, words.length ? words : null).catch(e => { console.error(e); process.exit(2); });
}
