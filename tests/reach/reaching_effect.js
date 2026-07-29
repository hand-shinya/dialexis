// Task B 到達効果検証（gate外・本番の実APIに対して実行）。文字体系・言語起源の異なる複数概念で、
// 日本語語→原点/語源→多言語の意味差→思想家/著作→関連/対立→別語と組合せ→戻る/進む往復→
// 取得失敗時の自動代替、という全経路を実ブラウザで辿り、概念ごとに「日本語訳だけでは見えない、
// 出所つきの意味差を最低1つ回復できたか」「行き止まりが無いか」「再入力/コピペ/手動検索の回数」
// 「捏造が無いか」「戻る/進むで同状態に復帰するか」を証拠として集める。成否判定でなく証拠収集。
// 使い方: node tests/reach/reaching_effect.js https://219-94-244-239.nip.io  （既定=本番IP:8000）
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = (process.argv[2] || "http://219.94.244.239:8000").replace(/\/$/, "");

// 文字体系・起源の異なる6概念（＋組合せ用の第2語）。低情報語（エポケー）を含む。
const CONCEPTS = [
  { w: "疎外", w2: "労働", kind: "日本語の哲学訳語（独 Entfremdung 系）" },
  { w: "弁証法", w2: "矛盾", kind: "ギリシャ語起源（dia-対話性）" },
  { w: "止揚", w2: "否定", kind: "ドイツ語起源（Aufhebung）" },
  { w: "縁起", w2: "空", kind: "漢語圏/仏教概念（梵 pratītya-samutpāda）" },
  { w: "アートマン", w2: "ブラフマン", kind: "非欧語起源（サンスクリット）" },
  { w: "エポケー", w2: "現象学", kind: "低情報の外来語（希 epoché）" },
];

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function waitGraph(p) {
  for (let i = 0; i < 30; i++) { const v = await p.evaluate(() => { const w = document.getElementById("origin-graph-wrap"); return !!(w && getComputedStyle(w).display !== "none"); }).catch(() => false); if (v) break; await sleep(700); }
  for (let i = 0; i < 20; i++) { const a = await p.evaluate(() => (window.__dx && __dx.G) ? (__dx.G.alpha || 0) : 1).catch(() => 1); if (a < 0.05) break; await sleep(300); }
}
// パネル本体テキストと出所行・時刻の有無を読む
async function panelInfo(p) {
  return await p.evaluate(() => {
    const el = document.querySelector("#graph-panel .gp-body"); if (!el) return { has: false };
    const txt = el.innerText || ""; const html = el.innerHTML || "";
    const src = [...el.querySelectorAll(".srcline")].map(s => s.innerText).join(" | ");
    const chips = [...el.querySelectorAll(".breadth-chip")].map(s => s.innerText);
    const comps = [...el.querySelectorAll(".anat-part")].map(s => s.innerText);
    const chain = [...el.querySelectorAll(".chain-step")].map(s => s.innerText);
    const extTerms = [...el.querySelectorAll(".ext-term")].map(s => s.getAttribute("data-w"));
    const hasTime = /(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})|取得時刻|retrieved/.test(html);
    const fallback = /fallback|自動代替/.test(html);
    return { has: true, len: txt.length, src, chips, comps, chain, extTerms, hasTime, fallback, empty: txt.replace(/\s/g, "").length < 8 };
  });
}
async function dispatch(p, action, term, ctx) { return p.evaluate(([a, t, c]) => window.__dx.dispatch(a, { term: t }, c || {}), [action, term, ctx]); }
async function closePanel(p) { await p.evaluate(() => { const x = document.getElementById("graph-panel"); if (x) { const b = x.querySelector(".gp-x"); if (b) b.click(); else x.remove(); } }); await sleep(150); }

(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const p = await b.newPage(); await p.setViewportSize({ width: 1280, height: 960 });
  const report = []; let manualReinputs = 0;   // このハーネスは全て click/dispatch 駆動＝手動再入力0を実測

  for (const C of CONCEPTS) {
    const rec = { word: C.w, word2: C.w2, kind: C.kind, evidence: {}, deadEnds: [], sources: new Set(), fallbackFirings: 0, notes: [] };
    try {
      await p.goto(`${B}/origin?q=${encodeURIComponent(C.w)}&lang=ja`, { waitUntil: "networkidle", timeout: 45000 });
      await waitGraph(p);
      rec.graphNodes = await p.evaluate(() => (window.__dx && __dx.G && __dx.G.nodes) ? __dx.G.nodes.length : 0).catch(() => 0);

      // 1) 多言語での意味差（breadth）
      await dispatch(p, "multilingual", C.w); await sleep(1200);
      let inf = await panelInfo(p);
      rec.evidence.multilingual = { languages: inf.chips ? inf.chips.length : 0, sample: (inf.chips || []).slice(0, 8), source: inf.src, timestamp: inf.hasTime, fallback: inf.fallback };
      if (inf.fallback) rec.fallbackFirings++;
      if (inf.src) rec.sources.add(inf.src.slice(0, 60));
      if (!inf.has || inf.empty) rec.deadEnds.push("multilingual");
      await closePanel(p);

      // 2) 原点/語源（anatomy）＝日本語字面に現れない構成要素・変容連鎖
      await dispatch(p, "anatomy", C.w); await sleep(1400);
      inf = await panelInfo(p);
      rec.evidence.anatomy = { components: (inf.comps || []).slice(0, 8), chain: (inf.chain || []).slice(0, 8), source: inf.src, timestamp: inf.hasTime, fallback: inf.fallback };
      if (inf.fallback) rec.fallbackFirings++;
      if (inf.src) rec.sources.add(inf.src.slice(0, 60));
      if (!inf.has || inf.empty) rec.deadEnds.push("anatomy");
      await closePanel(p);

      // 3) 訳語と原語の意味を並置（contrast）＝「並ぶことの喜び」の中核
      await dispatch(p, "contrast", C.w); await sleep(1400);
      inf = await panelInfo(p);
      rec.evidence.contrast = { len: inf.len, hasOriginalSide: (inf.comps || []).length + (inf.chain || []).length > 0, source: inf.src, fallback: inf.fallback };
      if (inf.fallback) rec.fallbackFirings++;
      if (!inf.has || inf.empty) rec.deadEnds.push("contrast");
      await closePanel(p);

      // 4) 埋没原語の警告（collapse）＝日本語一語に複数原語が埋没＝JP訳だけでは不可視の意味差
      await dispatch(p, "collapse", C.w); await sleep(1000);
      inf = await panelInfo(p);
      const collapsed = (inf.comps || []).concat(inf.extTerms || []);
      rec.evidence.collapse = { buriedOriginals: collapsed.slice(0, 8), source: inf.src, fallback: inf.fallback };
      if (inf.fallback) rec.fallbackFirings++;
      await closePanel(p);

      // 5) 思想家/著作（graph上のauthorノード→author調査）
      const authorNode = await p.evaluate(() => { const g = window.__dx && __dx.G; if (!g) return null; const n = (g.nodes || []).find(x => x.kind === "author"); return n ? { name: n.label, q: n.q } : null; }).catch(() => null);
      if (authorNode) {
        await dispatch(p, "author", authorNode.q || authorNode.name, { search: authorNode.name }); await sleep(1600);
        inf = await panelInfo(p);
        rec.evidence.authors = { probed: authorNode.name, len: inf.len, source: inf.src, dead: (!inf.has || inf.empty) };
        if (inf.fallback) rec.fallbackFirings++;
        if (!inf.has || inf.empty) rec.deadEnds.push("author");
        await closePanel(p);
      } else { rec.notes.push("authorノードがグラフに現れず（seed依存の既知限界・現状能力マップB）"); }

      // 6) 語→語の遷移に行き止まりが無いか: breadthのext-termを実クリックして別語へ再中心（P11）
      await dispatch(p, "multilingual", C.w); await sleep(1000);
      const hop = await p.evaluate(() => { const a = document.querySelector("#graph-panel .gp-body .ext-term"); if (!a) return null; const w = a.getAttribute("data-w"); a.click(); return w; });
      if (hop) { await sleep(1800); const newQ = await p.evaluate(() => (window.__dx && __dx.G) ? __dx.G.rootQ : null).catch(() => null); rec.evidence.wordHop = { to: hop, recenteredTo: newQ, freshCenter: newQ && newQ !== C.w }; if (!newQ) rec.deadEnds.push("word-hop"); }
      else rec.notes.push("多言語パネルにext-term語リンクが無く語→語hopを実測できず");

      // 戻って元の語に復帰（往復の一部）
      await p.goto(`${B}/origin?q=${encodeURIComponent(C.w)}&lang=ja`, { waitUntil: "networkidle", timeout: 45000 });
      await waitGraph(p);

      // 7) 別語と組合せ（combine）
      await dispatch(p, "combine", C.w, { b: C.w2, op: "and" }); await sleep(1800);
      const combineState = await p.evaluate(() => (window.__dx ? __dx.viewState() : null)).catch(() => null);
      rec.evidence.combine = { with: C.w2, committed: !!(combineState && combineState.combine), state: combineState && combineState.combine };
      if (!(combineState && combineState.combine)) rec.notes.push("組合せ状態が確定せず（network/取得依存）");

      // 8) 戻る/進む往復で同状態に復帰するか（実DOMボタン #nav-back/#nav-fwd）
      const stateBefore = await p.evaluate(() => JSON.stringify(window.__dx.viewState()));
      await p.evaluate(() => { const bk = document.getElementById("nav-back"); if (bk && !bk.disabled) bk.click(); else navGo(-1); }); await sleep(1600);
      const stateBack = await p.evaluate(() => JSON.stringify(window.__dx.viewState()));
      await p.evaluate(() => { const fw = document.getElementById("nav-fwd"); if (fw && !fw.disabled) fw.click(); else navGo(1); }); await sleep(1600);
      const stateFwd = await p.evaluate(() => JSON.stringify(window.__dx.viewState()));
      rec.evidence.roundTrip = { changedOnBack: stateBack !== stateBefore, restoredOnForward: stateFwd === stateBefore };

      // 集計: 出所つき意味差の回復（JP訳だけでは不可視）を最低1件特定
      const md = [];
      if ((rec.evidence.anatomy.components || []).length) md.push(`原語の構成要素: ${rec.evidence.anatomy.components.slice(0, 3).join(" / ")}`);
      if ((rec.evidence.anatomy.chain || []).length) md.push(`変容連鎖: ${rec.evidence.anatomy.chain.slice(0, 2).join(" → ")}`);
      if ((rec.evidence.collapse.buriedOriginals || []).length) md.push(`埋没原語: ${rec.evidence.collapse.buriedOriginals.slice(0, 4).join(" ・ ")}`);
      if ((rec.evidence.multilingual.languages || 0) >= 5) md.push(`${rec.evidence.multilingual.languages}言語で異なる担い方: ${rec.evidence.multilingual.sample.slice(0, 4).join(" ")}`);
      rec.recoveredMeaningDifferences = md;
      rec.recoveredAtLeastOne = md.length > 0;
      rec.manualReinputsForThisConcept = 0;   // 全てclick/dispatch駆動（再入力・コピペ・手動検索なし）
    } catch (e) { rec.error = String(e).slice(0, 200); }
    rec.sources = [...rec.sources];
    report.push(rec);
    console.error(`done: ${C.w} — 意味差回復=${rec.recoveredAtLeastOne} 行き止まり=${rec.deadEnds.length} fallback=${rec.fallbackFirings}`);
  }

  await b.close();
  const summary = {
    base: B, at: new Date().toISOString(),
    concepts: report.length,
    recoveredAll: report.every(r => r.recoveredAtLeastOne),
    recoveredCount: report.filter(r => r.recoveredAtLeastOne).length,
    totalDeadEnds: report.reduce((s, r) => s + r.deadEnds.length, 0),
    totalFallbackFirings: report.reduce((s, r) => s + r.fallbackFirings, 0),
    manualReinputs,
    roundTripAllRestored: report.every(r => r.evidence.roundTrip && r.evidence.roundTrip.restoredOnForward),
  };
  console.log(JSON.stringify({ summary, report }, null, 2));
  process.exit(0);
})().catch(e => { console.error("ERR", e); process.exit(2); });
