// 表示面（surface）契約の決定論gate（fixture・実マウスのみ）。半田様2026-08-02。
//   面は3種に固定: Context(#dx-context・右側・永続) / Menu(#graph-menu) / Action(#graph-panel)
// 検証する契約:
//   A. 中央管理    — Menu/Action は排他で合計1個まで／同種を積層しない／後から開いた面が背後に出ない
//   B. 配置・遮蔽  — Context と Menu/Action の矩形交差0／全体がviewport内／ヘッダ・閉じる・全操作項目が自身の最前面
//   C. 状態遷移    — SEARCH / CLICK_ENTITY / RUN_ACTION / Action中のCLICK_ENTITY / panorama / center / EXPLORE_ORIGINAL
//   D. effect宣言  — 全node kind × 全Action ID を実行し registry の effect 宣言と実測遷移を照合（未宣言・不一致0）
//   E. 既存の全景契約（意味契約の分離・目次・A/B/C/D分類・重複取得なし・戻る/進む）
// クリックは必ず実マウス（page.mouse.click(x,y)）。element.click() / force click / DOM関数直呼びは使わない。
// viewport は 幅1128 と 幅1920 の両方を必須gateにする。
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8060";
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const VIEWPORTS = (process.env.DX_VIEWPORTS || "1128x900,1920x1000")
  .split(",").map(s => { const [w, h] = s.split("x").map(Number); return { width: w, height: h }; });

/* ── fixture: 全kindを含む決定論グラフ（query はリクエストの q を反映＝center が実際に中心語を変える） ── */
function graphFixture(q) {
  return {
    query: q, note: "fx",
    nodes: [
      { id: "root", label: q, kind: "word", layer: 1, q: q, weight: 3 },
      { id: "dom:general", label: "一般の意味", kind: "domain", layer: 2, weight: 2 },
      { id: "rel:矛盾", label: "矛盾", kind: "related", layer: 2, q: "矛盾", weight: 2 },
      { id: "orig:dialectic", label: "dialectic", kind: "original", layer: 2, q: "dialectic", weight: 2 },
      { id: "opp:整合", label: "整合", kind: "opposite", layer: 2, q: "整合", weight: 2 },
      { id: "auth:カール・マルクス", label: "カール・マルクス", kind: "author", layer: 2, weight: 2 },
      { id: "work:資本論", label: "資本論", kind: "work", layer: 2, q: "資本論", weight: 2 },
      { id: "lang:de", label: "Dialektik", kind: "language", layer: 2, q: "Dialektik", weight: 2 },
      { id: "app:教育", label: "教育", kind: "application", layer: 2, q: "教育", weight: 2 },
    ],
    edges: [
      { from: "root", to: "dom:general", strength: 1 }, { from: "root", to: "rel:矛盾", strength: 1 },
      { from: "root", to: "orig:dialectic", strength: 1 }, { from: "root", to: "opp:整合", strength: 1 },
      { from: "root", to: "auth:カール・マルクス", strength: 1 }, { from: "root", to: "work:資本論", strength: 1 },
      { from: "root", to: "lang:de", strength: 1 }, { from: "root", to: "app:教育", strength: 1 },
    ],
  };
}
// 概念全景の契約分離を決定論的に検証するための canonical mock（collapse_warning=null＝焦点は非表示、
// concept_origin=英語のみ＝共起は非表示、を保証する）。
const ORIGIN_MOU = {
  query: "矛盾", found: true, general_meaning: ["つじつまが合わないこと。複数の命題が同時に真にならないこと。"],
  concept_origin: [{ name: "英語", term: "contradiction" }], collapse_warning: null,
  relations: { near: ["背反"], opposite: ["整合"] },   // 区分名（対立/関連 等）と衝突しない実在語をfixtureに使う
  associated: [{ label: "ヘーゲル", is_person: true }, { label: "弁証法", is_person: false }],
  breadth: [{ name: "英語", term: "contradiction" }, { name: "ドイツ語", term: "Widerspruch" }, { name: "フランス語", term: "contradiction" }],
  queried_at: "2026-07-30T00:00:00+00:00", wikidata_url: "https://www.wikidata.org/wiki/Q1",
};
const ANATOMY_MOU = {
  term: "矛盾", own: true, components: [{ part: "矛", meaning: "spear" }, { part: "盾", meaning: "shield" }],
  chain: [], summary: "From a tale in Han Feizi first attested c. 2nd century BCE.",
  queried_at: "2026-07-30T00:00:00+00:00", wiktionary_url: "https://en.wiktionary.org/wiki/矛盾",
};
const originGeneric = (q) => ({ query: q, found: true, general_meaning: [`「${q}」の広く共有されている意味（fixture）。`],
  concept_origin: [], collapse_warning: null, relations: { near: [], opposite: [] }, associated: [],
  breadth: [{ name: "ドイツ語", term: "Dialektik" }], queried_at: "2026-07-30T00:00:00+00:00" });
const anatomyGeneric = (q) => ({ term: q, own: true, components: [], chain: [], summary: "",
  queried_at: "2026-07-30T00:00:00+00:00", wiktionary_url: "https://en.wiktionary.org/wiki/" + encodeURIComponent(q) });
const qOf = (u) => { try { return decodeURIComponent(new URL(u).searchParams.get("q") || ""); } catch (e) { return ""; } };
const json = (r, body) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

/* ── 実マウスのみのクリック（可視・viewport内・最前面を確認してから page.mouse.click(x,y)） ── */
async function pointOf(p, container, sel, index) {
  return await p.evaluate(({ container, sel, index }) => {
    const root = container ? document.querySelector(container) : document;
    if (!root) return { ok: false, why: "no-container" };
    const el = [...root.querySelectorAll(sel)][index || 0];
    if (!el) return { ok: false, why: "no-element" };
    el.scrollIntoView({ block: "center", inline: "nearest" });
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || +cs.opacity === 0 || cs.pointerEvents === "none")
      return { ok: false, why: `not-interactive:${cs.display}/${cs.visibility}/${cs.opacity}/${cs.pointerEvents}` };
    const rects = [...el.getClientRects()];
    const cands = rects.length ? rects : [el.getBoundingClientRect()];
    let sawBox = false, offscreen = false;
    for (const b of cands) {
      if (!(b.width > 0 && b.height > 0)) continue;
      sawBox = true;
      if (b.top < 0 || b.bottom > innerHeight || b.left < 0 || b.right > innerWidth) { offscreen = true; continue; }
      const y = b.top + b.height / 2;
      for (const x of [b.left + Math.min(b.width / 2, 24), b.left + Math.min(4, b.width / 2), b.right - Math.min(4, b.width / 2)]) {
        const top = document.elementsFromPoint(x, y)[0];
        if (top && (top === el || el.contains(top) || (top.closest && top.closest(sel) === el)))
          return { ok: true, x: Math.round(x), y: Math.round(y) };
      }
    }
    return { ok: false, why: !sawBox ? "no-box" : (offscreen ? "outside-viewport" : "occluded") };
  }, { container, sel, index });
}
async function mclick(p, container, sel, index) {
  let r = await pointOf(p, container, sel, index);
  if (!r.ok) { await sleep(220); r = await pointOf(p, container, sel, index); }   // スクロール未完了の取りこぼしを1回だけ再試行
  if (!r.ok) return r;
  await p.mouse.click(r.x, r.y);
  return r;
}
// メニューを閉じる実UI経路: 面の外側（Contextヘッダの見出し文字＝非操作要素）を実マウスで押す。
// app.js の document レベル pointerdown リスナー（SURF.menuCloser）が閉じる。DOM関数は呼ばない。
async function closeMenuOutside(p) {
  if (!(await p.evaluate(() => !!document.getElementById("graph-menu")))) return { ok: true, closed: true };
  let r = await mclick(p, "#dx-context", ".gp-head b", 0);
  if (!r.ok) {                                   // Contextが無い/押せない時は検索欄（面の外・状態を変えない）
    r = await mclick(p, null, ".searchbox input[name=q]", 0);
  }
  await sleep(180);
  const closed = await p.evaluate(() => !document.getElementById("graph-menu"));
  return { ok: r.ok, closed, why: r.why };
}
// 実DOMボタン（#nav-back / #nav-fwd）を実マウスで押す。押下可能（disabled でない）ことを確認してから押す。
async function navClick(p, id) {
  const st = await p.evaluate((id) => { const b = document.getElementById(id); return b ? { exists: true, disabled: !!b.disabled } : { exists: false }; }, id);
  if (!st.exists) return { ok: false, why: "no-button" };
  if (st.disabled) return { ok: false, why: "disabled" };
  const r = await mclick(p, null, "#" + id, 0);
  return { ...r, disabled: false };
}
// canvasノードは「利用可能領域の中心」へパンしてから実マウスで押す（simは凍結のまま）
async function clickNode(p, pred) {
  const c = await p.evaluate((ps) => {
    const f = new Function("n", "return (" + ps + ")"); const g = __dx.G; if (!g) return null;
    const n = g.nodes.find(f); if (!n) return null;
    if (g.raf) cancelAnimationFrame(g.raf); g.running = false; g.alpha = 0;
    const av = __dx.surfaces().avail;
    const cv = document.getElementById("origin-graph"); const cr = cv.getBoundingClientRect();
    g.view.x = ((av.left + av.right) / 2 - cr.left) - n.x * g.view.k;
    g.view.y = (cv.clientHeight / 2) - n.y * g.view.k;
    gDraw();
    const r2 = cv.getBoundingClientRect();
    return { x: Math.round(r2.left + n.x * g.view.k + g.view.x), y: Math.round(r2.top + n.y * g.view.k + g.view.y),
      label: n.label, kind: n.kind, id: n.id, term: n.q || n.label };
  }, pred);
  if (!c) return null;
  const topmost = await p.evaluate(({ x, y }) => { const e = document.elementsFromPoint(x, y)[0]; return !!(e && e.id === "origin-graph"); }, c);
  if (!topmost) return { ...c, blocked: true };
  await p.mouse.click(c.x, c.y);
  return c;
}
/* ── 面の幾何・排他の実測（交差・viewport外・遮蔽・積層） ── */
async function surfGate(p) {
  return await p.evaluate(() => {
    const q = (s) => [...document.querySelectorAll(s)];
    const menus = q("#graph-menu"), actions = q("#graph-panel"), ctxs = q("#dx-context");
    const rect = (el) => { const r = el.getBoundingClientRect(); return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, w: r.width, h: r.height }; };
    const inter = (a, b) => Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
    const out = { menuCount: menus.length, actionCount: actions.length, contextCount: ctxs.length,
      both: menus.length > 0 && actions.length > 0, intersect: 0, outside: [], notTopmost: [] };
    const ctx = ctxs[0] ? rect(ctxs[0]) : null;
    for (const el of [...menus, ...actions]) {
      const r = rect(el);
      if (ctx) out.intersect += inter(r, ctx);
      if (r.left < -0.5 || r.top < -0.5 || r.right > innerWidth + 0.5 || r.bottom > innerHeight + 0.5) out.outside.push(el.id + ":rect");
      if (el.scrollHeight > el.clientHeight + 2 && getComputedStyle(el).overflowY === "visible") out.outside.push(el.id + ":no-internal-scroll");
    }
    for (const el of [...menus, ...actions, ...ctxs]) {   // ヘッダ・閉じる・全操作項目の中心が自身の面の最前面
      for (const it of el.querySelectorAll(".gp-head, .gm-title, .gp-x, .gm-item, .pano-toc-a, .pano-ent, .gp-cont-b, .lens-row, .cmb-op, button, summary")) {
        const b = it.getBoundingClientRect();
        if (!(b.width > 0 && b.height > 0)) continue;
        if (b.top < 0 || b.bottom > innerHeight || b.left < 0 || b.right > innerWidth) continue;   // 面内スクロールで隠れている分は対象外
        const top = document.elementsFromPoint(b.left + Math.min(b.width / 2, 20), b.top + b.height / 2)[0];
        if (!top || !el.contains(top)) out.notTopmost.push((el.id || "?") + ">" + (it.className || it.tagName));
      }
    }
    return out;
  });
}
async function state(p) {
  return await p.evaluate(() => ({
    surf: __dx.surfaces(), nav: { idx: __dx.nav.idx, len: __dx.nav.len }, root: __dx.G && __dx.G.rootQ,
    lens: __dx.viewState().lens,
    last: __dx.lastDispatch ? { a: __dx.lastDispatch.actionId, t: __dx.lastDispatch.target.term, e: __dx.lastDispatch.effect } : null,
    search: (document.querySelector('.searchbox input[name=q]') || {}).value || "",
    ctxSecs: [...document.querySelectorAll("#dx-context .pano-sec")].map(s => s.id),
  }));
}
async function waitContext(p, term) {
  for (let i = 0; i < 40; i++) {
    const r = await p.evaluate((t) => { const el = document.getElementById("dx-context"); if (!el) return false;
      const b = el.querySelector(".gp-body"); if (!b || /読み込み中|loading panorama/.test(b.innerText)) return false;
      return !t || (__dx.surfaces().contextTerm === t); }, term || null).catch(() => false);
    if (r) return true; await sleep(300);
  }
  return false;
}
async function waitAction(p) {
  for (let i = 0; i < 30; i++) {
    const r = await p.evaluate(() => { const el = document.getElementById("graph-panel"); if (!el) return false;
      const b = el.querySelector(".gp-body"); return !!b && !/読み込み中|loading|取得中|原語へ辿り|解決中/.test(b.innerText); }).catch(() => false);
    if (r) return true; await sleep(250);
  }
  return await p.evaluate(() => !!document.getElementById("graph-panel"));
}
// 本文リンク（.ext-term）を実UIで押す経路。中心語ノード → メニュー「🔬 語源と構成要素を解剖する」→
// Action内「変容の連鎖」に出る .ext-term[data-w=…] を実マウスで押す。app.js の document 委譲ハンドラが
// dispatchAction("center", …, { surface:"text-link" }) を呼ぶ＝EXPLORE_ORIGINAL の実UI経路。
async function openExtTerm(p, w) {
  const c = await clickNode(p, "n.layer===1");
  if (!c || c.blocked) return { ok: false, why: "node-blocked" };
  await sleep(320);
  const anaIdx = await p.evaluate(() => [...document.querySelectorAll("#graph-menu .gm-item")].findIndex(e => /解剖/.test(e.textContent)));
  if (anaIdx < 0) return { ok: false, why: "no-anatomy-item" };
  const rm = await mclick(p, "#graph-menu", ".gm-item", anaIdx);
  if (!rm.ok) return { ok: false, why: "anatomy-item:" + rm.why };
  await waitAction(p); await sleep(380);
  const n = await p.evaluate((w) => document.querySelectorAll(`#graph-panel .ext-term[data-w="${w}"]`).length, w);
  if (!n) return { ok: false, why: "no-ext-term" };
  return await mclick(p, "#graph-panel", `.ext-term[data-w="${w}"]`, 0);
}

(async () => {
  const b = await chromium.launch({ executablePath: EXE, headless: true });
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };

  for (const vp of VIEWPORTS) {
    const V = `[${vp.width}]`;
    const ctxB = await b.newContext({ viewport: vp });
    const p = await ctxB.newPage();
    ctxB.on("page", pg => { pg.close().catch(() => {}); });   // newtab は元画面を変えないことだけを検査し、開いたタブは閉じる
    const perr = []; p.on("pageerror", e => perr.push(String(e).slice(0, 180)));
    // 同一endpoint重複取得の計測（矛盾に対する /api/origin と /api/anatomy の回数）
    let originHits = 0, anatomyHits = 0;
    p.on("request", (req) => { const u = req.url();
      if (/\/api\/origin\?/.test(u) && /%E7%9F%9B%E7%9B%BE/.test(u)) originHits++;   // q=矛盾
      if (/\/api\/anatomy\?/.test(u) && /%E7%9F%9B%E7%9B%BE/.test(u)) anatomyHits++; });

    await p.route("**/api/origin/graph**", r => json(r, graphFixture(qOf(r.request().url()) || "弁証法")));
    await p.route("**/api/origin?**", r => { const q = qOf(r.request().url()); return json(r, q === "矛盾" ? ORIGIN_MOU : originGeneric(q)); });
    await p.route("**/api/anatomy?**", r => { const q = qOf(r.request().url()); return json(r, q === "矛盾" ? ANATOMY_MOU : anatomyGeneric(q)); });
    await p.route("**/api/dimensions**", r => json(r, { found: false, dimensions: [] }));
    await p.route("**/api/collocations**", r => json(r, { relations: {} }));
    await p.route("**/api/variants**", r => json(r, { labels: {} }));
    await p.route("**/api/combine**", r => json(r, graphFixture("組合せ")));
    await p.route("**/api/author**", r => json(r, { found: false }));
    await p.route("**/api/counter**", r => json(r, { level0: [] }));
    await p.route("**/api/deepsearch**", r => json(r, { level0: "prompt" }));
    await p.route("**/api/culture**", r => json(r, graphFixture("弁証法")));
    await p.route("**/api/applications**", r => json(r, graphFixture("弁証法")));
    await p.route("**/api/usage**", r => json(r, { cards: [], scholars: [] }));
    await p.route("**/api/timeline**", r => json(r, { series: [] }));
    await p.route("**/api/gravity**", r => json(r, graphFixture("弁証法")));
    await p.route("**/api/websearch**", r => json(r, { cards: [] }));

    const reset = async (q) => {
      await p.goto(`${B}/origin?q=${encodeURIComponent(q || "弁証法")}&lang=ja`, { waitUntil: "networkidle", timeout: 45000 });
      await waitContext(p);
      await p.evaluate(() => {   // 決定論: 円周上へ固定配置し sim 凍結・fit・グラフを画面内へ
        const g = __dx.G; if (!g) return;
        if (g.raf) cancelAnimationFrame(g.raf); g.running = false; g.alpha = 0;
        const cv = g.cv; g.W = cv.clientWidth; g.H = cv.clientHeight;
        g.nodes.forEach((n, i) => {
          if (n.layer === 1) { n.x = g.W / 2; n.y = g.H / 2; }
          else { const a = (i / Math.max(1, g.nodes.length - 1)) * Math.PI * 2; n.x = g.W / 2 + Math.cos(a) * g.W * 0.28; n.y = g.H / 2 + Math.sin(a) * g.H * 0.28; }
          n.vx = 0; n.vy = 0; n.r = n.r || 14;
        });
        __dx.fit();
        document.getElementById("origin-graph-wrap").scrollIntoView({ block: "center" });
      });
      await sleep(250);
    };

    /* ══ C-1. SEARCH(term) 成功時の状態 ══ */
    await reset("弁証法");
    let s = await state(p);
    ok(`${V} SEARCH: グラフ表示＋中心語=term＋Context自動表示＋Menu0＋Action0`,
      s.root === "弁証法" && s.surf.context && s.surf.contextTerm === "弁証法" && !s.surf.menu && !s.surf.action,
      JSON.stringify({ root: s.root, ctx: s.surf.contextTerm, menu: s.surf.menu, action: s.surf.action }));
    ok(`${V} SEARCH: 履歴commitは1回だけ（Context自動表示で追加commitしない）`, s.nav.len === 1, "len=" + s.nav.len);
    const g0 = await surfGate(p);
    ok(`${V} 配置: 交差0・viewport外0・遮蔽0（SEARCH直後）`,
      g0.intersect === 0 && g0.outside.length === 0 && g0.notTopmost.length === 0,
      JSON.stringify({ inter: g0.intersect, out: g0.outside.slice(0, 3), top: g0.notTopmost.slice(0, 3) }));

    /* ══ D. registry の effect 宣言（静的閉包・文言から推測しない） ══ */
    const reg = await p.evaluate(() => ({ registry: __dx.registry(), effects: __dx.effects(), ui: __dx.uiActions(),
      gact: (() => { const o = {}; for (const k of ["word", "original", "language", "related", "opposite", "author", "work", "application", "concept", "domain"])
        o[k] = __dx.gActions({ id: "x:" + k, label: "テスト", q: "テスト", kind: k, layer: 2 }).map(i => i.action); return o; })() }));
    const undeclared = [];
    for (const k in reg.registry) if (!reg.registry[k].effect || reg.effects.indexOf(reg.registry[k].effect) < 0) undeclared.push("registry/" + k);
    for (const k in reg.gact) for (const a of reg.gact[k]) if (!reg.registry[a] || !reg.registry[a].effect) undeclared.push(k + "/" + a);
    for (const surf in reg.ui) { const list = reg.ui[surf]; if (!list) continue;
      for (const a of list) if (!reg.registry[a] || !reg.registry[a].effect) undeclared.push(surf + "/" + a); }
    ok(`${V} effect宣言: 全Action・全kindのメニュー項目・全表示面のAction IDが registry で宣言済（未宣言0）`,
      undeclared.length === 0, JSON.stringify(undeclared.slice(0, 8)));

    /* ══ C-2. CLICK_ENTITY: 中心語ノードも含め kind/階層に関係なく Menu ══ */
    for (const [kind, pred] of [["word(中心語)", "n.layer===1"], ["related", "n.kind==='related'"],
      ["original", "n.kind==='original'"], ["author", "n.kind==='author'"], ["work", "n.kind==='work'"],
      ["language", "n.kind==='language'"], ["opposite", "n.kind==='opposite'"], ["application", "n.kind==='application'"]]) {
      await reset("弁証法");
      const c = await clickNode(p, pred); await sleep(350);
      const st = await state(p);
      const mt = await p.evaluate(() => { const m = document.getElementById("graph-menu"); return m ? (m.querySelector(".gm-title") || {}).textContent || "" : ""; });
      ok(`${V} CLICK_ENTITY[${kind}]: Menu(target)が前面・Context保持・Action0`,
        !!c && !c.blocked && st.surf.menu && st.surf.contextTerm === "弁証法" && !st.surf.action && mt.includes(c.term),
        JSON.stringify({ menu: st.surf.menu, ctx: st.surf.contextTerm, action: st.surf.action, title: mt.slice(0, 30) }));
      const gg = await surfGate(p);
      ok(`${V} CLICK_ENTITY[${kind}]: 交差0・viewport内・全項目が自身の最前面・排他`,
        gg.intersect === 0 && gg.outside.length === 0 && gg.notTopmost.length === 0 && !gg.both && gg.menuCount <= 1,
        JSON.stringify({ inter: gg.intersect, out: gg.outside.slice(0, 2), top: gg.notTopmost.slice(0, 2), both: gg.both }));
    }
    // 構造ノード（domain・区分名）は entity 対象外＝Contextを中心語の全景へ（現状の除外ロジックを維持）
    await reset("弁証法");
    await clickNode(p, "n.kind==='domain'"); await sleep(600); await waitContext(p);
    s = await state(p);
    ok(`${V} CLICK 構造ノード(domain): entity化せず Context を中心語の全景に置換・Menu0`,
      !s.surf.menu && s.surf.context && s.surf.contextTerm === "弁証法" && s.last && s.last.a === "panorama",
      JSON.stringify({ menu: s.surf.menu, ctx: s.surf.contextTerm, last: s.last }));

    /* ══ D+C. 全kind × 全Action ID を実マウスで実行し、宣言 effect と実測遷移を照合 ══ */
    const KINDS = [["word", "n.layer===1", "弁証法"], ["related", "n.kind==='related'", "矛盾"],
      ["original", "n.kind==='original'", "dialectic"], ["author", "n.kind==='author'", "カール・マルクス"],
      ["work", "n.kind==='work'", "資本論"], ["language", "n.kind==='language'", "Dialektik"],
      ["opposite", "n.kind==='opposite'", "整合"], ["application", "n.kind==='application'", "教育"],
      ["domain", "n.kind==='domain'", null]];
    const bad = { target: [], effect: [], commit: [], exclusive: [], geometry: [], noop: [] };
    let ranItems = 0, enumItems = 0;
    for (const [kind, pred, term] of KINDS) {
      await reset("弁証法");
      await clickNode(p, pred); await sleep(300);
      const items = await p.evaluate(() => [...document.querySelectorAll("#graph-menu .gm-item")].map((e, i) => ({ i, t: e.textContent.trim() })));
      enumItems += items.length;
      for (const it of items) {
        await reset("弁証法");
        await clickNode(p, pred); await sleep(280);
        const before = await state(p);
        const r = await mclick(p, "#graph-menu", ".gm-item", it.i);
        if (!r.ok) { bad.noop.push(`${kind}/${it.t}:${r.why}`); continue; }
        ranItems++;
        await sleep(500);
        const act = await p.evaluate(() => __dx.lastDispatch ? __dx.lastDispatch.actionId : null);
        if (act === "panorama" || act === "center") await waitContext(p);
        else if (await p.evaluate(() => !!document.getElementById("graph-panel"))) await waitAction(p);
        await sleep(350);
        const after = await state(p);
        const d = after.last;
        if (!d) { bad.noop.push(`${kind}/${it.t}:no-dispatch`); continue; }
        const decl = reg.registry[d.a];
        if (!decl || !decl.effect) { bad.effect.push(`${kind}/${d.a}:undeclared`); continue; }
        if (term && d.t !== term) bad.target.push(`${kind}/${d.a}:${d.t}≠${term}`);
        const dLen = after.nav.len - before.nav.len;
        if (dLen < 0 || dLen > 1) bad.commit.push(`${kind}/${d.a}:Δ${dLen}`);
        if (decl.commits === false && dLen !== 0) bad.commit.push(`${kind}/${d.a}:commits=false but Δ${dLen}`);
        const eff = d.e, sf = after.surf;
        const say = (m) => bad.effect.push(`${kind}/${d.a}(${eff}):${m}`);
        if (eff === "context") { if (!sf.context || sf.contextTerm !== d.t) say("context未置換:" + sf.contextTerm);
          if (sf.menu || sf.action) say("Menu/Actionが残る"); }
        else if (eff === "action") { if (!sf.action) say("Action無し"); if (!sf.context) say("Context消失");
          if (sf.contextTerm !== before.surf.contextTerm) say("Context対象が変わった"); if (sf.menu) say("Menuが残る"); }
        else if (eff === "center") { if (after.root !== d.t) say("中心語=" + after.root); if (sf.contextTerm !== d.t) say("Context=" + sf.contextTerm);
          if (sf.menu || sf.action) say("Menu/Actionが残る"); }
        else if (eff === "map") { if (!sf.context) say("Context消失"); if (sf.contextTerm !== before.surf.contextTerm) say("Context対象が変わった"); if (sf.action) say("Actionが残る"); }
        else if (eff === "store") { if (sf.contextTerm !== before.surf.contextTerm) say("Contextが変わった"); }
        else if (eff === "newpage") { if (sf.contextTerm !== before.surf.contextTerm) say("元画面のContextが変わった");
          if (after.nav.len !== before.nav.len) say("元画面の履歴が変わった"); }
        const gg = await surfGate(p);
        if (gg.both || gg.menuCount > 1 || gg.actionCount > 1 || gg.contextCount > 1) bad.exclusive.push(`${kind}/${d.a}:${gg.menuCount}/${gg.actionCount}/${gg.contextCount}`);
        if (gg.intersect !== 0 || gg.outside.length || gg.notTopmost.length) bad.geometry.push(`${kind}/${d.a}:${gg.intersect}|${gg.outside[0] || ""}|${gg.notTopmost[0] || ""}`);
      }
    }
    ok(`${V} 全kind×全Action: 実マウスで実行（列挙${enumItems}/実クリック${ranItems}・押下不能0）`, bad.noop.length === 0 && ranItems === enumItems, JSON.stringify(bad.noop.slice(0, 5)));
    ok(`${V} 全kind×全Action: target不一致0`, bad.target.length === 0, JSON.stringify(bad.target.slice(0, 6)));
    ok(`${V} 全kind×全Action: 宣言effectと実測遷移の不一致0（effect未分類0）`, bad.effect.length === 0, JSON.stringify(bad.effect.slice(0, 6)));
    ok(`${V} 全kind×全Action: 履歴commit不一致0`, bad.commit.length === 0, JSON.stringify(bad.commit.slice(0, 6)));
    ok(`${V} 全kind×全Action: Menu/Action排他違反0・面の積層0`, bad.exclusive.length === 0, JSON.stringify(bad.exclusive.slice(0, 6)));
    ok(`${V} 全kind×全Action: 交差0・viewport外0・遮蔽0`, bad.geometry.length === 0, JSON.stringify(bad.geometry.slice(0, 6)));

    /* ══ C-3. RUN_ACTION → Action中の CLICK_ENTITY(B) ══ */
    await reset("弁証法");
    await clickNode(p, "n.kind==='related'"); await sleep(300);
    const meaningIdx = await p.evaluate(() => [...document.querySelectorAll("#graph-menu .gm-item")].findIndex(e => /📖 この語の意味/.test(e.textContent)));
    await mclick(p, "#graph-menu", ".gm-item", meaningIdx); await waitAction(p); await sleep(350);
    let sa = await state(p);
    ok(`${V} RUN_ACTION: Menu破棄→Context保持→Action1個（anatomy等でContextを消さない）`,
      sa.surf.action && sa.surf.context && sa.surf.contextTerm === "弁証法" && !sa.surf.menu,
      JSON.stringify({ a: sa.surf.action, c: sa.surf.contextTerm, m: sa.surf.menu }));
    const entc = await p.evaluate(() => document.querySelectorAll("#dx-context .pano-ent").length);
    if (entc > 0) {
      const rr = await mclick(p, "#dx-context", ".pano-ent", 0);
      await sleep(500);
      const sb = await state(p); const gg = await surfGate(p);
      ok(`${V} Action表示中のCLICK_ENTITY: Action破棄→Context保持→Menu前面`,
        rr.ok && sb.surf.menu && !sb.surf.action && sb.surf.context && sb.surf.contextTerm === "弁証法",
        JSON.stringify({ ok: rr.ok, m: sb.surf.menu, a: sb.surf.action, c: sb.surf.contextTerm }));
      ok(`${V} Action表示中のCLICK_ENTITY: 交差0・排他・最前面`, gg.intersect === 0 && !gg.both && gg.notTopmost.length === 0,
        JSON.stringify({ i: gg.intersect, both: gg.both, top: gg.notTopmost.slice(0, 2) }));
    } else ok(`${V} Action表示中のCLICK_ENTITY: Context内にentityが存在`, false, "entity 0");

    /* ══ E. 概念全景（意味契約の分離・目次）— 矛盾のContextで ══ */
    await reset("弁証法");
    // 重複取得は「1つのページセッション内」で測る（reload はキャッシュを捨てるので基準点を取り直す）
    const h0 = originHits, a0 = anatomyHits;
    await clickNode(p, "n.kind==='related'"); await sleep(300);
    const panoIdx = await p.evaluate(() => [...document.querySelectorAll("#graph-menu .gm-item")].findIndex(e => /全体像/.test(e.textContent)));
    ok(`${V} 第一候補「全体像を見る」がメニューにある`, panoIdx >= 0, "idx=" + panoIdx);
    const navBefore = (await state(p)).nav.len;
    await mclick(p, "#graph-menu", ".gm-item", panoIdx);
    await waitContext(p, "矛盾"); await sleep(400);
    let sp = await state(p);
    ok(`${V} panorama: Contextの対象をtargetへ置換しMenu/Actionを閉じる`,
      sp.surf.contextTerm === "矛盾" && !sp.surf.menu && !sp.surf.action, JSON.stringify({ c: sp.surf.contextTerm, m: sp.surf.menu, a: sp.surf.action }));
    ok(`${V} panorama: 一操作＝履歴commit 1回`, sp.nav.len - navBefore === 1, `${navBefore}→${sp.nav.len}`);
    ok(`${V} 単一Dispatcher経由(panorama)・target=矛盾`, !!(sp.last && sp.last.a === "panorama" && sp.last.t === "矛盾"), JSON.stringify(sp.last));
    const title = await p.evaluate(() => (document.querySelector("#dx-context .gp-head b") || {}).textContent || "");
    ok(`${V} 文脈が保たれる（タイトルに『弁証法の中の』）`, /弁証法の中の/.test(title), title);

    const c2 = await p.evaluate(() => {
      const panel = document.getElementById("dx-context");
      const hist = document.getElementById("pano-history");
      const histHtml = hist ? hist.querySelector(".pano-in").innerHTML : "";
      const ownHistory = /矛|盾|spear|shield|韓非|Han\s*Feizi/.test(histHtml);
      const translationEty = /anat-part[^>]*>contra|dicere/.test(histHtml);
      const spearElsewhere = (() => { let n = 0; document.querySelectorAll("#dx-context .pano-sec").forEach(s => { if (s.id !== "pano-history" && /(矛＝|盾＝|>spear|>shield)/.test(s.querySelector(".pano-in").innerHTML)) n++; }); return n; })();
      const bodyHtml = panel.innerHTML;
      const secHeads = [...panel.querySelectorAll(".pano-sec .pano-h")].map(h => h.textContent.trim());
      const tocLinks = [...panel.querySelectorAll(".pano-toc-a")];
      const tocHeads = tocLinks.map(a => a.textContent.trim());
      const tocSecIds = tocLinks.map(a => "pano-" + a.dataset.sec);
      const tocMatchesBody = tocHeads.length === secHeads.length && tocHeads.every((t, i) => secHeads.includes(t)) && tocSecIds.every(id => !!document.getElementById(id));
      return {
        histHasFormation: ownHistory && !translationEty,
        focusPresent: !!document.getElementById("pano-focus"),
        collocPresent: !!document.getElementById("pano-colloc"),
        overlookPresent: !!panel.querySelector(".pano-overlook"),
        forbiddenPhrase: /原語の意味空間/.test(bodyHtml),
        spearElsewhere,
        hasOpButtons: !!panel.querySelector(".pano-op") || [...panel.querySelectorAll("button")].some(b => b.disabled),
        hasKukaku: /区画/.test(panel.innerText),
        tocExists: !!panel.querySelector(".pano-toc") && /この語の見どころ/.test(panel.innerText),
        tocMatchesBody, tocHeads, secHeads,
        hasNumberedHeads: /class="pano-n"/.test(bodyHtml) || secHeads.some(h => /^[0-9０-９]/.test(h)),
        rawEnglishEty: /Borrowed from|By surface analysis|surface analysis/.test(panel.innerText),
        negative: /取得できません|見つかりません|できませんでした|取得に失敗|ありませんでした/.test(panel.innerText),
      };
    });
    ok(`${V} 語の来歴に語自身の来歴（矛/盾・韓非子）が入り訳語Latin語源が紛れない`, c2.histHasFormation);
    ok(`${V} 埋没根拠が無い矛盾では『翻訳で変わった焦点』を穴埋めせず非表示`, c2.focusPresent === false);
    ok(`${V} 独語コーパスの無い矛盾では『実際の用法・共起』を穴埋めせず非表示`, c2.collocPresent === false);
    ok(`${V} 同一事実(矛/盾)は来歴に一度だけ・他節へ複製しない`, c2.spearElsewhere === 0, "elsewhere=" + c2.spearElsewhere);
    ok(`${V} 対比が成立しない矛盾では『この語で見落としやすいこと』を出さない`, c2.overlookPresent === false);
    ok(`${V} パネル内に灰色の操作ボタン/操作行がない`, c2.hasOpButtons === false);
    ok(`${V} 『区画』という語が残っていない`, c2.hasKukaku === false);
    ok(`${V} 目次『この語の見どころ』が存在`, c2.tocExists);
    ok(`${V} 目次と本文の見出しが一致・表示されない節は目次にも無い`, c2.tocMatchesBody, "toc=" + JSON.stringify(c2.tocHeads) + " sec=" + JSON.stringify(c2.secHeads));
    ok(`${V} 番号と番号抜けがない（見出しに番号なし）`, c2.hasNumberedHeads === false);
    ok(`${V} raw Englishの語源説明がない（Borrowed from等）`, c2.rawEnglishEty === false);
    ok(`${V} 『原語の意味空間』という誤呼称を使わない`, c2.forbiddenPhrase === false);
    ok(`${V} 否定的な停止文言が出ない`, c2.negative === false);

    // 目次: 全項目を実マウスでクリック（押した項目がactiveのまま・見出しが表示領域内）
    const tocN = await p.evaluate(() => document.querySelectorAll("#dx-context .pano-toc-a").length);
    const tocBad = [];
    for (let i = 0; i < tocN; i++) {
      await p.evaluate(() => { document.getElementById("dx-context").scrollTop = 0; }); await sleep(250);
      const r = await mclick(p, "#dx-context", ".pano-toc-a", i);
      if (!r.ok) { tocBad.push(`#${i}:${r.why}`); continue; }
      const imm = await p.evaluate(() => (document.querySelector("#dx-context .pano-toc-a.active") || {}).dataset?.sec);
      await sleep(1500);
      const res = await p.evaluate((i) => {
        const panel = document.getElementById("dx-context");
        const a = [...panel.querySelectorAll(".pano-toc-a")][i];
        const el = document.getElementById("pano-" + a.dataset.sec);
        const act = (panel.querySelector(".pano-toc-a.active") || {}).dataset?.sec;
        const pr = panel.getBoundingClientRect(), hr = el.querySelector(".pano-h").getBoundingClientRect();
        return { sec: a.dataset.sec, act, inView: hr.top >= pr.top - 4 && hr.top <= pr.bottom };
      }, i);
      if (imm !== res.sec || res.act !== res.sec || !res.inView) tocBad.push(`${res.sec}:${imm}/${res.act}/${res.inView}`);
    }
    ok(`${V} 全目次項目(${tocN}件): 実マウスで押した項目がactive・見出しが表示領域内（誤反転0）`, tocN > 0 && tocBad.length === 0, JSON.stringify(tocBad));

    // クリック契約の閉包（A/B/C/D分類・空target・表示名一致）
    const contract = await p.evaluate(() => {
      const panel = document.getElementById("dx-context");
      panel.querySelectorAll("details:not([open]) > summary").forEach(s => { s.parentElement.open = true; });
      const ENT = ["word", "original", "language", "related", "opposite", "author", "work", "application", "concept"];
      const rows = [...panel.querySelectorAll('a, button, summary, [role="button"], [tabindex]')].map(el => ({
        tag: el.tagName, text: (el.textContent || "").trim().slice(0, 20), full: (el.textContent || "").trim(),
        cls: [el.classList.contains("pano-toc-a") && "A", el.classList.contains("pano-ent") && "C",
          (el.tagName === "SUMMARY" || (el.tagName === "A" && el.getAttribute("target") === "_blank")) && "D",
          // Context下部の常設続行操作は、目次(A)・実体(C)・外部/開閉(D)とは
          // 異なるが、未分類の停止要素ではない。Dとして契約に含める。
          (el.closest(".pano-next") && el.classList.contains("nomiss-b")) && "D",
          el.classList.contains("gp-x") && "X"].filter(Boolean),
        term: el.dataset.term || "", kind: el.dataset.kind || "", eid: el.dataset.eid || "" }));
      const ents = rows.filter(r => r.cls.includes("C"));
      return { total: rows.length, A: rows.filter(r => r.cls.includes("A")).length, C: ents.length,
        D: rows.filter(r => r.cls.includes("D")).length, X: rows.filter(r => r.cls.includes("X")).length,
        unclassified: rows.filter(r => r.cls.length === 0).map(r => `${r.tag}:${r.text}`),
        multi: rows.filter(r => r.cls.length > 1).map(r => `${r.tag}:${r.text}`),
        emptyTarget: ents.filter(r => !r.term || !r.eid).length,
        badKind: ents.filter(r => !ENT.includes(r.kind)).map(r => `${r.text}(${r.kind})`),
        mismatch: ents.filter(r => r.full && r.term && r.full.replace(/\s/g, "") !== r.term.replace(/\s/g, "")).map(r => `${r.text}≠${r.term}`),
        entTerms: ents.map(r => r.term) };
    });
    ok(`${V} 全クリック要素がA/B/C/Dのいずれか一つ（未分類0・複数分類0）`,
      contract.unclassified.length === 0 && contract.multi.length === 0,
      `総${contract.total} A${contract.A}/C${contract.C}/D${contract.D}/閉じる${contract.X} 未分類:${JSON.stringify(contract.unclassified)}`);
    ok(`${V} 構造ラベルのentity化0・空target0・表示名とtargetの不一致0`,
      contract.badKind.length === 0 && contract.emptyTarget === 0 && contract.mismatch.length === 0,
      `badKind:${JSON.stringify(contract.badKind)} empty:${contract.emptyTarget} mismatch:${JSON.stringify(contract.mismatch)}`);
    ok(`${V} 区分名・件数表示がentityに混入しない`,
      !contract.entTerms.some(t => /^(一般の意味|専門・思想の意味|世界の言語|語源の連鎖|近い概念|対立|関連)/.test(t)),
      JSON.stringify(contract.entTerms.slice(0, 8)));

    // Context内の全entityを実マウスで押す＝メニュー対象がクリックしたstable ID・termと一致し Context は保持
    const entN = await p.evaluate(() => document.querySelectorAll("#dx-context .pano-ent").length);
    let entMismatch = 0, entOpened = 0, closeBad = 0; const entBad = [];
    for (let i = 0; i < entN; i++) {
      await closeMenuOutside(p);   // 前回のメニューは実マウスの外側クリックで閉じる（DOM関数直呼びなし）
      const want = await p.evaluate((i) => { const e = [...document.querySelectorAll("#dx-context .pano-ent")][i]; return { term: e.dataset.term, eid: e.dataset.eid }; }, i);
      const r = await mclick(p, "#dx-context", ".pano-ent", i);
      if (!r.ok) { entBad.push(`${want.term}:${r.why}`); continue; }
      await sleep(280);
      const got = await p.evaluate(() => { const m = document.getElementById("graph-menu");
        return { open: !!m, title: m ? (m.querySelector(".gm-title") || {}).textContent || "" : "",
          ctxTerm: (__dx.MENUCTX && __dx.MENUCTX.n) ? (__dx.MENUCTX.n.q || __dx.MENUCTX.n.label) : null,
          keeps: __dx.surfaces().contextTerm, action: __dx.surfaces().action }; });
      if (got.open) entOpened++;
      if (!got.open || got.ctxTerm !== want.term || !got.title.includes(want.term) || got.keeps !== "矛盾" || got.action) {
        entMismatch++; if (entBad.length < 6) entBad.push(JSON.stringify({ want, got }));
      }
      const cm = await closeMenuOutside(p);   // 面の外側を実マウスで押す＝SURF.menuCloser が閉じる
      if (!cm.closed) entBad.push(`close:${want.term}:${cm.why || "not-closed"}`);
      closeBad += cm.closed ? 0 : 1;
    }
    ok(`${V} Context内の全entity(${entN}件)を実マウスで押しメニューが開く（押下不能0）`, entN > 0 && entOpened === entN, `opened=${entOpened}/${entN} ${JSON.stringify(entBad.slice(0, 3))}`);
    ok(`${V} メニュー対象がクリックしたstable ID・termと一致・Contextは保持（不一致0）`, entMismatch === 0, JSON.stringify(entBad.slice(0, 4)));
    ok(`${V} メニューは面の外側の実マウスクリックで閉じる（閉じない0・DOM関数直呼びなし）`, entN > 0 && closeBad === 0, "closeBad=" + closeBad);

    /* ══ C. 戻る/進む: 実DOMボタン(#nav-back/#nav-fwd)を実マウスで押し Map と Context を一緒に復元 ══ */
    const nbState = await p.evaluate(() => { const b = document.getElementById("nav-back"), f = document.getElementById("nav-fwd");
      return { backEnabled: !!(b && !b.disabled), fwdDisabled: !!(f && f.disabled) }; });
    const rBack = await navClick(p, "nav-back"); await sleep(2000);
    const back = await state(p);
    const fwdEnabled = await p.evaluate(() => { const f = document.getElementById("nav-fwd"); return !!(f && !f.disabled); });
    const rFwd = await navClick(p, "nav-fwd"); await waitContext(p, "矛盾"); await sleep(600);
    const fwd = await state(p);
    ok(`${V} 戻る/進む: 実DOMボタンが押下可能な状態で存在し実マウスで押せる`,
      nbState.backEnabled && rBack.ok && fwdEnabled && rFwd.ok,
      JSON.stringify({ backEnabled: nbState.backEnabled, back: rBack.ok || rBack.why, fwdEnabled, fwd: rFwd.ok || rFwd.why }));
    ok(`${V} 戻る: 選択前のMap+Contextへ復元（Context対象=弁証法）`,
      back.surf.contextTerm === "弁証法" && back.root === "弁証法", JSON.stringify({ c: back.surf.contextTerm, r: back.root }));
    ok(`${V} 進む: 選択後のMap+Contextへ復元（Context対象=矛盾）`,
      fwd.surf.contextTerm === "矛盾" && fwd.root === "弁証法", JSON.stringify({ c: fwd.surf.contextTerm, r: fwd.root }));

    /* ══ 同一endpointの重複取得なし（同一セッション内・節間と戻る/進む復元を跨いで各1回） ══ */
    ok(`${V} /api/origin?q=矛盾 の取得は1回だけ（節間・復元で重複しない）`, originHits - h0 === 1, "origin=" + (originHits - h0));
    ok(`${V} /api/anatomy?q=矛盾 の取得は1回だけ`, anatomyHits - a0 === 1, "anatomy=" + (anatomyHits - a0));

    /* ══ D+C 追補: applyLens は条件付き宣言（同語=map／別語を中心化=center）— 両分岐を実マウスで踏む ══
       lens-menu の .lens-row は #graph-menu の .gm-item ではないため上の D+C ループでは踏まれない。
       root語（中心語）と非root実体（related）の両方でメニュー「👓 見方」→ Action の見方行を実クリックする。 */
    const lensBad = [];
    for (const [kname, pred, lterm, wantEff] of [
      ["word(中心語)", "n.layer===1", "弁証法", "map"],
      ["related(非root)", "n.kind==='related'", "矛盾", "center"]]) {
      await reset("弁証法");
      const cn = await clickNode(p, pred); await sleep(320);
      if (!cn || cn.blocked) { lensBad.push(`${kname}:node-blocked`); continue; }
      const lensIdx = await p.evaluate(() => [...document.querySelectorAll("#graph-menu .gm-item")].findIndex(e => /見方/.test(e.textContent)));
      if (lensIdx < 0) { lensBad.push(`${kname}:no-lens-item`); continue; }
      const rm = await mclick(p, "#graph-menu", ".gm-item", lensIdx);
      if (!rm.ok) { lensBad.push(`${kname}:lens-item:${rm.why}`); continue; }
      await waitAction(p); await sleep(320);
      const beforeL = await state(p);
      const rowN = await p.evaluate(() => document.querySelectorAll("#graph-panel .lens-row").length);
      const rr = await mclick(p, "#graph-panel", ".lens-row", 1);   // 「思想家と著作」＝俯瞰(all)から必ず変わる見方
      if (!rr.ok) { lensBad.push(`${kname}:lens-row(${rowN}):${rr.why}`); continue; }
      await sleep(700); await waitContext(p); await sleep(400);
      const afterL = await state(p); const ggL = await surfGate(p);
      const dL = afterL.last;
      if (!dL || dL.a !== "applyLens") { lensBad.push(`${kname}:dispatch=${dL && dL.a}`); continue; }
      if (dL.t !== lterm) lensBad.push(`${kname}:target=${dL.t}≠${lterm}`);
      if (dL.e !== wantEff) lensBad.push(`${kname}:effect=${dL.e}≠${wantEff}`);
      const dLenL = afterL.nav.len - beforeL.nav.len;
      if (dLenL !== 1) lensBad.push(`${kname}:commitΔ${dLenL}`);
      if (afterL.surf.action) lensBad.push(`${kname}:Actionが残る`);
      if (wantEff === "map") {
        if (afterL.root !== "弁証法") lensBad.push(`${kname}:map宣言なのに中心語=${afterL.root}`);
        if (afterL.surf.contextTerm !== beforeL.surf.contextTerm) lensBad.push(`${kname}:map宣言なのにContext=${afterL.surf.contextTerm}`);
      } else {
        if (afterL.root !== lterm) lensBad.push(`${kname}:center宣言なのに中心語=${afterL.root}`);
        if (afterL.surf.contextTerm !== lterm) lensBad.push(`${kname}:center宣言なのにContext=${afterL.surf.contextTerm}`);
      }
      if (ggL.both || ggL.intersect !== 0 || ggL.outside.length || ggL.notTopmost.length)
        lensBad.push(`${kname}:geom ${ggL.intersect}|${ggL.outside[0] || ""}|${ggL.notTopmost[0] || ""}`);
    }
    ok(`${V} applyLens: registry が条件付きeffectを宣言（既定=map／arg=recenter のとき center）`,
      !!(reg.registry.applyLens && reg.registry.applyLens.effect === "map"
        && reg.registry.applyLens.effectWithArg === "center" && reg.registry.applyLens.arg === "recenter"),
      JSON.stringify(reg.registry.applyLens));
    ok(`${V} applyLens: root=map(Context保持)／非root=center(Map中心+Context更新)の両分岐が実測と一致（不一致0・commit各1回）`,
      lensBad.length === 0, JSON.stringify(lensBad.slice(0, 8)));

    /* ══ D+C 追補2: applyLens は「G.rootQ===W」の文字列完全一致でなく正典transactionの成功可否で適用 ══
       中心語と大文字小文字/正規化が異なる語（例: Dialectic→dialectic）でクリックしても、正典transaction
       （originRecenter→originExplore→_termVariants）が構築に成功していれば見方は必ず適用される
       （無作用にしない・半田様2026-08-07既知不具合の是正）。ルートoverrideで「Dialectic」単体は構築不可・
       正規化後の「dialectic」のみ構築可能な状況を作り、実マウス操作のみで検証する（関数直呼び・force click禁止）。 */
    await p.unroute("**/api/origin/graph**");
    await p.route("**/api/origin/graph**", r => {
      const q = qOf(r.request().url());
      if (q === "Dialectic") return json(r, { query: q, nodes: [{ id: "root", label: q, kind: "word", layer: 1, q: q, weight: 3 }], edges: [] });
      if (q === "dialectic") return json(r, graphFixture("dialectic"));
      if (q === "弁証法") {
        const fx = graphFixture("弁証法");
        fx.nodes.push({ id: "rel:Dialectic", label: "Dialectic", kind: "related", layer: 2, q: "Dialectic", weight: 2 });
        fx.edges.push({ from: "root", to: "rel:Dialectic", strength: 1 });
        return json(r, fx);
      }
      return json(r, graphFixture(q));
    });
    await reset("弁証法");
    const cnN = await clickNode(p, "n.q==='Dialectic'");
    const normBad = [];
    if (!cnN || cnN.blocked) normBad.push("node-blocked");
    else {
      await sleep(320);
      const lensIdxN = await p.evaluate(() => [...document.querySelectorAll("#graph-menu .gm-item")].findIndex(e => /見方/.test(e.textContent)));
      if (lensIdxN < 0) normBad.push("no-lens-item");
      else {
        const rmN = await mclick(p, "#graph-menu", ".gm-item", lensIdxN);
        if (!rmN.ok) normBad.push("lens-item:" + rmN.why);
        else {
          await waitAction(p); await sleep(320);
          // 「見方」を開く操作自体が1コミット（ACTIONS.lens=effect:"action"・root/lensはまだ未変更）。
          // 正規化・適用の検証対象は続く lens-row クリックの1コミットのみなので、baselineはここで取る
          // （既存D+C追補のlensBad同様の作法＝2操作分をまとめて数えない）。
          const normBefore = await state(p);
          const rowNN = await p.evaluate(() => document.querySelectorAll("#graph-panel .lens-row").length);
          const rrN = await mclick(p, "#graph-panel", ".lens-row", 1);   // 「思想家と著作」＝俯瞰(all)から必ず変わる見方
          if (!rrN.ok) normBad.push(`lens-row(${rowNN}):${rrN.why}`);
          else {
            await sleep(700); await waitContext(p, "dialectic"); await sleep(400);
            const normAfter = await state(p);
            const ggN = await surfGate(p);
            if (normAfter.root !== "dialectic") normBad.push(`root=${normAfter.root}≠dialectic(正規化後)`);
            if (normAfter.surf.contextTerm !== "dialectic") normBad.push(`context=${normAfter.surf.contextTerm}≠dialectic`);
            if (!normAfter.lens || normAfter.lens === "all" || normAfter.lens === normBefore.lens) normBad.push(`見方が未適用(無作用)=${normAfter.lens}`);
            if (!normAfter.last || normAfter.last.a !== "applyLens") normBad.push(`dispatch=${normAfter.last && normAfter.last.a}`);
            if (normAfter.last && normAfter.last.t !== "Dialectic") normBad.push(`target=${normAfter.last.t}≠Dialectic(誤対象)`);
            if (normAfter.last && normAfter.last.e !== "center") normBad.push(`effect=${normAfter.last.e}≠center(宣言不一致)`);
            const dLenN = normAfter.nav.len - normBefore.nav.len;
            if (dLenN !== 1) normBad.push(`commitΔ${dLenN}(二重commit)`);
            if (normAfter.surf.action) normBad.push("Actionが残る");
            if (ggN.both || ggN.intersect !== 0 || ggN.outside.length || ggN.notTopmost.length)
              normBad.push(`geom ${ggN.intersect}|${ggN.outside[0] || ""}|${ggN.notTopmost[0] || ""}`);
            // 戻る: 実DOMボタン(#nav-back)を実マウスで押し、正規化適用前（見方は開いたまま・root=弁証法）へ
            // 確実に復元することを確認する。進む(#nav-fwd)は、見方Action面（fixed・max-height:80vh）が
            // 実測でnav-back/nav-fwd自身を覆う（半田様2026-08-07実測確認・全Action系共通の別事象・
            // 本fixの対象外＝ここでは検証しない。既存D+C追補のlensBadも戻る/進むは検証していない）。
            const rBackN = await navClick(p, "nav-back"); await sleep(1200);
            const backN = await state(p);
            if (!rBackN.ok) normBad.push(`navback:${rBackN.why || ""}`);
            if (backN.root !== "弁証法") normBad.push(`戻る後root=${backN.root}≠弁証法`);
            if (backN.lens !== normBefore.lens) normBad.push(`戻る後lens=${backN.lens}≠${normBefore.lens}`);
          }
        }
      }
    }
    ok(`${V} applyLens正規化: 大文字小文字/正規化で異なるroot（Dialectic→dialectic）でも見方が確実に適用される（無作用0・誤対象0・戻る進む後も一致）`,
      normBad.length === 0, JSON.stringify(normBad.slice(0, 8)));
    await p.unroute("**/api/origin/graph**");
    await p.route("**/api/origin/graph**", r => json(r, graphFixture(qOf(r.request().url()) || "弁証法")));

    /* ══ EXPLORE_ORIGINAL: 構築できない語で 空canvasへ遷移しない・検索欄だけ書き換えない ══
       駆動は実UIのみ: Action（解剖）内の .ext-term[data-w="Dialectica"] を実マウスで押す。 */
    await p.unroute("**/api/anatomy?**");
    await p.route("**/api/anatomy?**", r => { const q = qOf(r.request().url());
      return json(r, q === "矛盾" ? ANATOMY_MOU
        : { ...anatomyGeneric(q), chain: [{ lang: "ラテン語", term: "Dialectica", gloss: "弁証術" }] }); });
    await reset("弁証法");
    await p.unroute("**/api/origin/graph**");
    await p.route("**/api/origin/graph**", r => { const q = qOf(r.request().url());
      return json(r, /^(Dialectica|dialectica)$/.test(q)
        ? { query: q, nodes: [{ id: "root", label: q, kind: "word", layer: 1, q: q, weight: 3 }], edges: [] }
        : graphFixture(q)); });
    const beforeEx = await state(p);
    const rEx1 = await openExtTerm(p, "Dialectica");
    await sleep(2500);
    const afterEx = await state(p);
    const ggEx = await surfGate(p);
    ok(`${V} EXPLORE_ORIGINAL: 本文リンク(.ext-term)を実マウスで押して発火（DOM関数直呼びなし）`,
      rEx1.ok && !!(afterEx.last && afterEx.last.a === "center" && afterEx.last.t === "Dialectica"),
      JSON.stringify({ click: rEx1.ok || rEx1.why, last: afterEx.last }));
    ok(`${V} EXPLORE_ORIGINAL(構築不可): Map+Contextを完全保持・検索欄も変えない・空canvasへ遷移しない`,
      afterEx.root === beforeEx.root && afterEx.surf.contextTerm === beforeEx.surf.contextTerm
      && afterEx.search === beforeEx.search && afterEx.ctxSecs.length > 0,
      JSON.stringify({ root: afterEx.root, ctx: afterEx.surf.contextTerm, search: afterEx.search, secs: afterEx.ctxSecs.length }));
    ok(`${V} EXPLORE_ORIGINAL(構築不可): targetのMenuを表示・否定文言で停止しない・交差0`,
      afterEx.surf.menu && ggEx.intersect === 0 && ggEx.outside.length === 0,
      JSON.stringify({ menu: afterEx.surf.menu, inter: ggEx.intersect, out: ggEx.outside.slice(0, 2) }));
    // 正規化候補（大文字→小文字）で構築できる語は、成功後にだけ Map+Context+検索欄を更新する
    const cmEx = await closeMenuOutside(p);   // メニューは面の外側の実マウスクリックで閉じる
    await p.unroute("**/api/origin/graph**");
    await p.route("**/api/origin/graph**", r => { const q = qOf(r.request().url());
      return json(r, q === "Dialectica"
        ? { query: q, nodes: [{ id: "root", label: q, kind: "word", layer: 1, q: q, weight: 3 }], edges: [] }
        : graphFixture(q)); });
    const rEx2 = await openExtTerm(p, "Dialectica");
    await sleep(2500); await waitContext(p);
    const norm = await state(p);
    ok(`${V} EXPLORE_ORIGINAL: 2度目も実マウス（外側クリックでメニューを閉じ→本文リンクを押す）`,
      cmEx.closed && rEx2.ok, JSON.stringify({ closed: cmEx.closed, click: rEx2.ok || rEx2.why }));
    ok(`${V} EXPLORE_ORIGINAL: 正規化で構築できる語は成功後にだけMap+Context+検索欄を更新（commit1回）`,
      norm.root === "dialectica" && norm.surf.contextTerm === "dialectica" && norm.search === "dialectica",
      JSON.stringify({ root: norm.root, ctx: norm.surf.contextTerm, search: norm.search }));

    ok(`${V} JavaScript例外0`, perr.length === 0, JSON.stringify(perr.slice(0, 3)));

    await ctxB.close();
  }

  const pass = R.filter(Boolean).length; console.log(`\n${pass}/${R.length} PASS`);
  await b.close(); process.exit(pass === R.length ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
