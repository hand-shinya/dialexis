/* 表示面（surface）契約の実ブラウザ・実API・実マウスによる BFS gate（半田様2026-08-02）。
   面は3種に固定: Context(#dx-context・右側・永続) / Menu(#graph-menu) / Action(#graph-panel)
   BFS:
     L1 = canvas全ノード／全edge／Context内の全entity／目次／開閉／出典／グラフ上部の全操作
     L2 = L1の実体を押して現れる、その kind で有効な全Action ID
     L3 = 各Action結果内の 全リンク・全ボタン・全entity・戻る・続けて探索する操作・多言語項目
   第3階層までBFS。それより深い循環のみ stable ID（kind|項目index / action|要素class）で停止する。
   クリック手順は必ず: getClientRects()から実際の文字・ボタン上の座標 → elementsFromPoint で対象または
   その子が最前面か確認 → page.mouse.click(x,y) → 描画安定後と1.5秒後の両方を確認。
   element.click() / Playwrightのforce click / DOM関数直呼びは使わない。
   viewport は 幅1128 と 幅1920 の両方を必須gate（DX_VIEWPORTS で 1280x720 等を追加できる）。
   DX_FULL=1 で stable ID による循環停止を無効化し、全DOM instanceを個別に押す。 */
const { chromium } = require("playwright-core");
const EXE = process.env.DX_CHROMIUM || "/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome";
const B = process.argv[2] || "http://127.0.0.1:8060";
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const VIEWPORTS = (process.env.DX_VIEWPORTS || "1128x900,1920x1000")
  .split(",").map(s => { const [w, h] = s.split("x").map(Number); return { width: w, height: h }; });
const SEED = process.env.DX_SEED || "弁証法";
const FULL = process.env.DX_FULL === "1";
const BUDGET_MS = Number(process.env.DX_BUDGET_MS || 0);
// 診断用: 第1階層のクリック数を上限で打ち切り、時間予算を第2・第3階層へ回す（既定0＝全件＝gate）。
const L1_MAX = Number(process.env.DX_L1_MAX || 0);
// 決定論的なL1範囲指定（分割実行用）。canonicalなL1一覧を確定した**後**に範囲を適用する。
//   DX_L1_FROM = 含む開始番号（既定0） / DX_L1_TO = 含まない終了番号（既定=canonical L1総数）
// 範囲外のL1は押さないため、その子孫のL2/L3も実行されない（l2tasksは押したL1からのみ積むため）。
// 各L1ケースは canonical index で唯一の範囲に属する＝範囲を並べれば重複も欠落も生じない。
const L1_FROM = Math.max(0, Number(process.env.DX_L1_FROM || 0));
const L1_TO_ENV = process.env.DX_L1_TO === undefined ? null : Number(process.env.DX_L1_TO);
const RANGED = L1_FROM !== 0 || L1_TO_ENV !== null;
// 外部出典の新規ページ待ちの固定上限（押す**前**に待受を開始する）。無負荷の実測は 96〜2332ms。
const EXT_POPUP_MS = Math.min(15000, Number(process.env.DX_EXT_POPUP_MS || 15000));   // 実測最大7000ms(Monier-Williams梵)に対し余裕を取る
const HB_MS = Number(process.env.DX_HEARTBEAT_MS || 60000);   // 進捗heartbeatの間隔（無停止監視用）
function mkHb(V) { let last = Date.now(); return (msg) => { const now = Date.now();
  if (now - last >= HB_MS) { last = now; console.log(`${V} …進行中 ${new Date(now).toTimeString().slice(0, 8)} ${msg}`); } }; }
// 必須対象（実測で弁証法グラフに存在する語・人物・原語・多言語ノード）。これらは循環停止の対象外＝全件押す。
const REQUIRED = ["dialectic", "パラドックス", "ディスクール", "西洋哲学", "矛盾",
  "カール・マルクス", "ウラジーミル・レーニン", "συλλογισμός", "Dialectica"];
const OPS_SEL = 'a, button, summary, [role="button"], [tabindex]';

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
  if (!r.ok) { await sleep(250); r = await pointOf(p, container, sel, index); }
  if (!r.ok) return r;
  await p.mouse.click(r.x, r.y);
  return r;
}
/* ── 面の幾何・排他・遮蔽の実測 ── */
async function surfGate(p) {
  return await p.evaluate(() => {
    const q = (s) => [...document.querySelectorAll(s)];
    const menus = q("#graph-menu"), actions = q("#graph-panel"), ctxs = q("#dx-context");
    const rect = (el) => { const r = el.getBoundingClientRect(); return { left: r.left, top: r.top, right: r.right, bottom: r.bottom }; };
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
// 実データのAction結果にはサイト内リンク（/origin?q=… 等）が含まれ、押すと**現在ページが遷移**する。
// 遷移中に評価すると実行コンテキストが壊れるため、__dx が載るまで待って読む（クラッシュさせない）。
async function state(p) {
  let err = null;
  for (let k = 0; k < 15; k++) {
    try {
      if (await p.evaluate(() => !!window.__dx)) {
        return await p.evaluate(() => ({
          surf: __dx.surfaces(), nav: { idx: __dx.nav.idx, len: __dx.nav.len, txn: !!__dx.nav.txn }, root: __dx.G && __dx.G.rootQ,
          last: __dx.lastDispatch ? { a: __dx.lastDispatch.actionId, t: __dx.lastDispatch.target.term, e: __dx.lastDispatch.effect, o: __dx.lastDispatch.outcome, seq: __dx.lastDispatch.seq } : null,
          menuTitle: ((document.querySelector("#graph-menu .gm-title") || {}).textContent || "").trim(),
          search: (document.querySelector('.searchbox input[name=q]') || {}).value || "",
          nodes: __dx.G ? __dx.G.nodes.length : 0,
          ctxSecs: [...document.querySelectorAll("#dx-context .pano-sec")].map(s => s.id),
        }));
      }
    } catch (e) { err = e; await p.waitForLoadState("domcontentloaded").catch(() => {}); }
    await sleep(400);
  }
  throw new Error("state: page never became ready " + (err ? String(err).slice(0, 80) : ""));
}
async function waitContext(p, term) {
  for (let i = 0; i < 40; i++) {
    const r = await p.evaluate((t) => { const el = document.getElementById("dx-context"); if (!el) return false;
      const b = el.querySelector(".gp-body"); if (!b || /読み込み中|loading panorama/.test(b.innerText)) return false;
      return !t || (__dx.surfaces().contextTerm === t); }, term || null).catch(() => false);
    if (r) return true; await sleep(350);
  }
  return false;
}
async function waitAction(p) {
  for (let i = 0; i < 30; i++) {
    const r = await p.evaluate(() => { const el = document.getElementById("graph-panel"); if (!el) return false;
      const b = el.querySelector(".gp-body"); return !!b && !/読み込み中|loading|取得中|原語へ辿り|解決中|世界中の学術/.test(b.innerText); }).catch(() => false);
    if (r) return true; await sleep(350);
  }
  return await p.evaluate(() => !!document.getElementById("graph-panel"));
}
/* ── 種の読み込み（SEARCH）とベースラインへの復帰 ── */
async function loadSeed(p, q) {
  await p.goto(`${B}/origin?q=${encodeURIComponent(q)}&lang=ja`, { waitUntil: "networkidle", timeout: 60000 });
  await waitContext(p);
  await p.evaluate(() => { const g = __dx.G; if (g && g.raf) cancelAnimationFrame(g.raf); if (g) { g.running = false; g.alpha = 0; }
    const w = document.getElementById("origin-graph-wrap"); if (w) w.scrollIntoView({ block: "center" });
    // 折り畳み（他N言語を展開）は開いた状態を基準にする＝列挙indexと座標が読込のたびにズレない。
    // 開閉そのものは L1 の details 項目で実マウスクリックして別途検証する。
    const c = document.getElementById("dx-context");
    if (c) c.querySelectorAll("details:not([open]) > summary").forEach(s => { s.parentElement.open = true; }); });
  await sleep(300);
}
// 面だけが開いている場合は「実マウスで閉じる」（Menu=地図見出しの余白を押す／Action=×を押す）。
// それでも Map/Context/履歴/検索欄が基準から外れていれば再読込で確実に戻す。
async function restoreBaseline(p, base) {
  const same = (s) => s.root === base.root && s.surf.contextTerm === base.surf.contextTerm
    && !s.surf.menu && !s.surf.action && s.nav.len === base.nav.len && s.search === base.search;
  let s = await state(p);
  if (s.surf.action) { await mclick(p, "#graph-panel", ".gp-x", 0); await sleep(200); s = await state(p); }
  if (s.surf.menu) { await mclick(p, null, ".graph-title", 0); await sleep(150); s = await state(p); }
  if (same(s)) {
    await p.evaluate(() => { const w = document.getElementById("origin-graph-wrap"); if (w) w.scrollIntoView({ block: "center" });
      const c = document.getElementById("dx-context");
      if (c) { c.scrollTop = 0; c.querySelectorAll("details:not([open]) > summary").forEach(x => { x.parentElement.open = true; }); } });
    return;
  }
  await loadSeed(p, base.root || SEED);
}
/* ── L1 の対象を実マウスで押す（canvasノードとエッジは利用可能領域の中心へパンしてから） ── */
async function clickL1(p, item, popupLog) {
  if (item.t === "node" || item.t === "edge") {
    const c = await p.evaluate(({ t, i }) => {
      const g = __dx.G; if (!g) return null;
      let gx, gy;
      if (t === "node") { const n = g.nodes[i]; if (!n) return null; gx = n.x; gy = n.y; }
      else { const e = g.edges[i]; if (!e) return null; const a = g.nodes[e.a], b2 = g.nodes[e.b]; gx = (a.x + b2.x) / 2; gy = (a.y + b2.y) / 2; }
      if (g.raf) cancelAnimationFrame(g.raf); g.running = false; g.alpha = 0;
      const av = __dx.surfaces().avail;
      const cv = document.getElementById("origin-graph"); const cr = cv.getBoundingClientRect();
      g.view.x = ((av.left + av.right) / 2 - cr.left) - gx * g.view.k;
      g.view.y = (cv.clientHeight / 2) - gy * g.view.k;
      gDraw();
      const r2 = cv.getBoundingClientRect();
      return { x: Math.round(r2.left + gx * g.view.k + g.view.x), y: Math.round(r2.top + gy * g.view.k + g.view.y) };
    }, { t: item.t, i: item.i });
    if (!c) return { ok: false, why: "no-node" };
    const topmost = await p.evaluate(({ x, y }) => { const e = document.elementsFromPoint(x, y)[0]; return !!(e && e.id === "origin-graph"); }, c);
    if (!topmost) return { ok: false, why: "occluded" };
    await p.mouse.click(c.x, c.y);
    await sleep(200);
    return { ok: true, x: c.x, y: c.y };
  }
  if (item.t === "ctxent") return await mclick(p, "#dx-context", ".pano-ent", item.i);
  if (item.t === "toc") return await mclick(p, "#dx-context", ".pano-toc-a", item.i);
  if (item.t === "details") return await mclick(p, "#dx-context", "summary", item.i);
  if (item.t === "extlink") return await clickOp(p, popupLog || [], "#dx-context", 'a[target="_blank"]', item.i, "ext");
  if (item.t === "topop") return await mclick(p, null, item.sel, item.i);
  return { ok: false, why: "unknown-type" };
}
/* ── L3: 結果の面（Action または Context）の内部操作を列挙 ── */
// 各操作を種別に分ける（クリック方法を分岐するため。列挙数には全て含める）:
//   ext = a[target="_blank"] 外部出典＝新規ページを開く（現在ページを壊さない・捕捉して閉じる）
//   nav = href がサイト内URLで同一タブ遷移するリンク（押すと現在ページが遷移する）
//   ui  = それ以外（ボタン・開閉・entity・目次 等＝面の中で完結する操作）
async function enumerateOps(p, root) {
  return await p.evaluate(({ root, sel }) => {
    const el = document.querySelector(root); if (!el) return [];
    el.querySelectorAll("details:not([open]) > summary").forEach(s => { s.parentElement.open = true; });
    // 安定識別子: index は面の作り直しでずれるため、押す直前に sig＋ord で再解決できるようにする。
    // 目次の active はスクロール/直前のクリックで変わる一時表示状態であり、対象そのものの同一性ではない。
    // これを含めると「各言語での表記」が存在するのに一致なしになる（実測: shelf/newtab の再現経路）。
    const stableClass = (e) => String(e.className || "").split(/\s+/).filter(Boolean)
      .filter(c => c !== "active").join(" ");
    const SIG = (e) => [e.tagName, stableClass(e), e.getAttribute("href") || "",
      e.getAttribute("target") || "", (e.dataset && e.dataset.term) || "",
      (e.textContent || "").trim().slice(0, 24)].join("\u0001");
    const seen = {};
    return [...el.querySelectorAll(sel)].map((e, i) => {
      const href = e.getAttribute && e.getAttribute("href");
      const blank = e.tagName === "A" && e.getAttribute("target") === "_blank";
      const navs = e.tagName === "A" && !blank && !!href && href !== "#" && !href.startsWith("javascript:");
      const sig = SIG(e); const ord = (seen[sig] = (seen[sig] || 0) + 1) - 1;
      return { i, tag: e.tagName, cls: stableClass(e), href: href || "",
        target: (e.getAttribute && e.getAttribute("target")) || "",
        kind: blank ? "ext" : (navs ? "nav" : "ui"),
        text: (e.textContent || "").trim().slice(0, 24), term: (e.dataset && e.dataset.term) || "",
        sig, ord };
    });
  }, { root, sel: OPS_SEL });
}
// 経路再現後の面で、列挙時の op を安定識別子(sig)＋同一sig内の序数(ord)で一意に再解決する。
// index をそのまま使うと、面が作り直された/遷移が終わっていない場合に**別要素を押してしまう**
// （実測: 遷移未完了の古いContextでは要素数162・index 8 が別語のWiktionaryリンクだった）。
// 解決できない場合は失敗として残す（読み飛ばさない）。
async function resolveOp(p, root, op) {
  return await p.evaluate(({ root, sel, op }) => {
    const el = document.querySelector(root); if (!el) return { ok: false, why: "面が無い", count: 0 };
    // enumerateOps と同じく、active は一時的な表示状態なので識別子から除外する。
    const stableClass = (e) => String(e.className || "").split(/\s+/).filter(Boolean)
      .filter(c => c !== "active").join(" ");
    const SIG = (e) => [e.tagName, stableClass(e), e.getAttribute("href") || "",
      e.getAttribute("target") || "", (e.dataset && e.dataset.term) || "",
      (e.textContent || "").trim().slice(0, 24)].join("\u0001");
    const els = [...el.querySelectorAll(sel)];
    const hits = []; let n = 0;
    els.forEach((e, i) => { if (SIG(e) === op.sig) { if (n === op.ord) hits.push(i); n++; } });
    if (hits.length === 1) return { ok: true, i: hits[0], count: els.length, sameSig: n };
    return { ok: false, why: hits.length === 0 ? `一致なし(同sig ${n}件)` : `一意でない(${hits.length}件)`, count: els.length };
  }, { root, sel: OPS_SEL, op });
}
// 実マウスのままクリックし、外部リンクは新規ページの発生を捕捉して閉じ、サイト内リンクの遷移は待つ。
// （element.click() / force click は使わない＝クリック方法は page.mouse.click のまま。）
async function clickOp(p, popupLog, container, sel, i, kind) {
  const urlBefore = p.url();
  const popsBefore = popupLog.length;
  // 外部出典は**クリックより前**に page イベントの待受を開始する。押してから待ち始めると
  // (a) 発生の速い新規ページを取りこぼし (b) 固定3秒では負荷時に足りない（実測 最大2332ms）。
  // 待受は固定上限（既定10秒・上限15秒）で必ず終わる。時間切れ＝失敗であり、成功扱いにはしない。
  const popWait = kind === "ext"
    ? p.context().waitForEvent("page", { timeout: EXT_POPUP_MS })
        .then(pg => ({ pg }), e => ({ why: String(e).split("\n")[0].slice(0, 80) }))
    : null;
  const t0 = Date.now();
  const r = await mclick(p, container, sel, i);
  if (!r.ok) { if (popWait) await popWait; return r; }
  if (kind === "ext") {
    const w = await popWait;
    const ms = Date.now() - t0;
    return { ok: true, popup: !!w.pg, popMs: w.pg ? ms : -1, popWhy: w.why || "",
      popUrl: w.pg ? w.pg.url() : (popupLog[popupLog.length - 1] || ""), navigated: p.url() !== urlBefore };
  }
  if (kind === "nav") {
    await p.waitForLoadState("domcontentloaded").catch(() => {});
    await sleep(300);
    return { ok: true, navigated: p.url() !== urlBefore };
  }
  return { ok: true, navigated: p.url() !== urlBefore };
}

/* ══ 異常件数（すべて0が合格）と網羅カウンタ ══ */
function newC() {
  return { l1Enum: 0, l1Click: 0, l2Enum: 0, l2Click: 0, l3Enum: 0, l3Click: 0,
    targetMismatch: 0, outOfViewport: 0, occluded: 0, unclickable: 0,
    menuMultiple: 0, actionMultiple: 0, menuAndAction: 0, contextLost: 0, contextTargetMismatch: 0,
    staleSurface: 0, emptyGraph: 0, searchBoxChanged: 0, commitMismatch: 0, effectUnclassified: 0,
    fallbackContract: 0, centerFallback: 0,
    unstable: 0, extMs: [], budgetCut: false, notes: [] };
}
const ANOMALY_KEYS = ["targetMismatch", "outOfViewport", "occluded", "unclickable", "menuMultiple",
  "actionMultiple", "menuAndAction", "contextLost", "contextTargetMismatch", "staleSurface",
  "emptyGraph", "searchBoxChanged", "commitMismatch", "effectUnclassified", "unstable"];
ANOMALY_KEYS.push("fallbackContract");
function note(C, s) { if (C.notes.length < 40) C.notes.push(s); }

// 面の幾何・排他・遮蔽を実測し、異常を数値で積む
async function gateGeometry(p, C, where) {
  const g = await surfGate(p);
  if (g.menuCount > 1) { C.menuMultiple++; note(C, where + ":menu×" + g.menuCount); }
  if (g.actionCount > 1) { C.actionMultiple++; note(C, where + ":action×" + g.actionCount); }
  if (g.contextCount > 1) { C.staleSurface++; note(C, where + ":context×" + g.contextCount); }
  if (g.both) { C.menuAndAction++; note(C, where + ":menu+action"); }
  if (g.intersect !== 0) { C.occluded++; note(C, where + ":intersect=" + Math.round(g.intersect)); }
  if (g.outside.length) { C.outOfViewport++; note(C, where + ":" + g.outside[0]); }
  if (g.notTopmost.length) { C.occluded++; note(C, where + ":notTopmost " + g.notTopmost[0]); }
  return g;
}
// 描画安定後と1.5秒後の両方を確認（遅れて来る応答が面を壊さないこと）。
// ①まず遷移が落ち着くまで待つ（連続2サンプルが同一＝描画安定）②その状態を記録
// ③1.5秒後にもう一度読み、変化していれば unstable として計上する。
const SKEY = (s) => JSON.stringify([s.surf.context, s.surf.menu, s.surf.action, s.surf.contextTerm, s.root, s.search, s.nav.len, s.menuTitle]);
// 作用の同一性＝Action ID・target・effect・seq（同一操作の反復も seq で区別する）。表示(SKEY)とは別に見る。
const AKEY = (s) => JSON.stringify(s.last ? [s.last.a, s.last.t, s.last.e, s.last.o, s.last.seq] : null);
// アプリ自身の「処理中」表示（#graph-busy／面の読み込み中文言）が残っている間は「描画安定」と見なさない。
// これを見ずに一定時間だけ待つと、取得が飛んでいる最中の**途中状態**を読んでしまう。
async function appBusy(p) {
  try {
    return await p.evaluate(() => {
      // ① dispatchAction の実行区間（__dx.nav.txn）。クリック直後〜最初のDOM変化までの静止区間を
      //    「安定」と誤認しないための正典条件（app.js 側は読み取り専用getterの追加のみ）。
      if (window.__dx && __dx.nav && __dx.nav.txn) return true;
      const b = document.getElementById("graph-busy");
      if (b && getComputedStyle(b).display !== "none") return true;
      const cb = document.querySelector("#dx-context .gp-body");
      if (cb && /読み込み中|loading panorama/.test(cb.innerText)) return true;
      const ab = document.querySelector("#graph-panel .gp-body");
      if (ab && /読み込み中|loading|取得中|原語へ辿り|解決中|世界中の学術|組み合わせ探索中/.test(ab.innerText)) return true;
      return false;
    });
  } catch (e) { return true; }   // 遷移中（実行コンテキスト破壊）＝まだ落ち着いていない
}
async function settledState(p, C, where) {
  let prev = await state(p), cur = prev, stable = 0, settled = false;
  for (let i = 0; i < 160; i++) {         // 最大 ~40秒
    await sleep(250);
    // ①操作が実行中(__dx.nav.txn) ②loading表示が残る の間は安定と見なさない（固定sleepで代用しない）
    if (await appBusy(p)) { stable = 0; prev = await state(p); continue; }
    cur = await state(p);
    const same = SKEY(cur) === SKEY(prev)          // 面・対象・root・検索欄・履歴len
      && AKEY(cur) === AKEY(prev)                  // ③Action ID・target・effect が2回連続で一致
      && cur.nav.len === prev.nav.len              // ④履歴commitが確定して動かない
      && cur.nav.txn === false;                    // ①の再確認（採取時点でも実行中でない）
    if (same) { if (++stable >= 2) { settled = true; break; } } else { stable = 0; }
    prev = cur;
  }
  if (!settled) { C.unstable++; note(C, where + ":安定しない(txn/loading/作用が確定しない) " + SKEY(cur) + AKEY(cur)); return cur; }
  const a = cur;
  await sleep(1500);                      // 安定確定の**後**に、遅れて来る応答が面を壊さないことを追加で確認する
  const b2 = await state(p);
  if (SKEY(a) !== SKEY(b2) || AKEY(a) !== AKEY(b2)) { C.unstable++; note(C, where + ":unstable " + SKEY(a) + AKEY(a) + "→" + SKEY(b2) + AKEY(b2)); }
  return b2;
}
// 正典transaction（app.js の _termVariants → originResolveGraph）と**同一の同一性関係**。
// 正典は「要求語そのもの → NFKC → 小文字 → 先頭大文字」の順に実際に構築できた変種を root に採る。
// ゆえに center 後の root/Context が要求語と表記だけ違う（例: Dialectica → dialectica）のは
// 仕様どおりの解決であって不一致ではない。ここを文字列完全一致で判定すると、
// applyLensFor が抱えていたのと同じ「厳密一致による誤判定」をテスト側が再生産する
// （実測: [1128] targetMismatch=636 / contextTargetMismatch=648 の主因）。
// 別語（矛盾 vs 弁証法 等）は従来どおり不一致として検出する＝assertionは弱めない。
function termVariants(q) {
  const out = [], add = (s) => { s = String(s == null ? "" : s).trim(); if (s && out.indexOf(s) < 0) out.push(s); };
  add(q);
  try { add(String(q).normalize("NFKC")); } catch (e) {}
  add(String(q).toLowerCase());
  add(String(q).charAt(0).toUpperCase() + String(q).slice(1));
  return out;
}
function sameTerm(a, b) {
  if (a == null || b == null) return a === b;
  if (String(a) === String(b)) return true;
  const va = termVariants(a), vb = termVariants(b);
  return va.some(x => vb.indexOf(x) >= 0);
}
// グラフを構築できない語の中心化は、正典transactionが false を返し、現在のMap＋Contextを
// 保持したまま対象語の標準Menuを出す。これは無作用ではなく、捏造しないための明示的なfallback。
// fallback自身の契約を検査し、成功時のcenter契約と混同しない（assertionは弱めない）。
function checkFallback(C, before, after, where) {
  const d = after.last;
  C.centerFallback++;
  const bad = [];
  if (!d || d.a !== "center" || d.e !== "center") bad.push("center以外");
  if (!after.surf.menu || after.surf.action) bad.push("対象Menuのみでない");
  if (!after.menuTitle.includes(d && d.t || "")) bad.push(`Menu対象=${after.menuTitle}`);
  if (after.root !== before.root) bad.push(`root ${after.root}≠${before.root}`);
  if (!after.surf.context || after.surf.contextTerm !== before.surf.contextTerm)
    bad.push(`Context ${after.surf.contextTerm}≠${before.surf.contextTerm}`);
  if (after.search !== before.search) bad.push(`検索欄 ${after.search}≠${before.search}`);
  if (after.nav.len !== before.nav.len) bad.push(`履歴 ${after.nav.len}≠${before.nav.len}`);
  if (bad.length) { C.fallbackContract++; note(C, `${where}:fallback契約違反 ${bad.join(" / ")}`); }
}
// 宣言 effect と実測遷移の照合（registry と照合し、文言から推測しない）
function checkEffect(C, reg, before, after, where, expectTarget) {
  const d = after.last;
  if (!d) { C.effectUnclassified++; note(C, where + ":no-dispatch"); return; }
  if (d.o === "fallback") { checkFallback(C, before, after, where); return; }
  if (d.o && d.o !== "success") { C.effectUnclassified++; note(C, `${where}:dispatch outcome=${d.o}`); return; }
  const decl = reg[d.a];
  if (!decl || !decl.effect) { C.effectUnclassified++; note(C, where + ":undeclared " + d.a); return; }
  if (expectTarget && d.t !== expectTarget) { C.targetMismatch++; note(C, `${where}:${d.a} target ${d.t}≠${expectTarget}`); }
  const dLen = after.nav.len - before.nav.len;
  if (dLen < 0 || dLen > 1 || (decl.commits === false && dLen !== 0)) { C.commitMismatch++; note(C, `${where}:${d.a} Δcommit=${dLen}`); }
  const sf = after.surf, eff = d.e;
  const stale = (m) => { C.staleSurface++; note(C, `${where}:${d.a}(${eff}) ${m}`); };
  if (eff === "context") {
    if (!sf.context) { C.contextLost++; note(C, where + ":context lost"); }
    else if (sf.contextTerm !== d.t) { C.contextTargetMismatch++; note(C, `${where}:ctx ${sf.contextTerm}≠${d.t}`); }
    if (sf.menu || sf.action) stale("Menu/Actionが残る");
  } else if (eff === "action") {
    if (!sf.action) stale("Action無し");
    if (!sf.context) { C.contextLost++; note(C, where + ":context lost"); }
    else if (sf.contextTerm !== before.surf.contextTerm) { C.contextTargetMismatch++; note(C, `${where}:ctx変化 ${before.surf.contextTerm}→${sf.contextTerm}`); }
    if (sf.menu) stale("Menuが残る");
  } else if (eff === "center") {
    // 正典の変種解決（Dialectica→dialectica 等）は一致とみなす。別語なら従来どおり不一致。
    if (!sameTerm(after.root, d.t)) { C.targetMismatch++; note(C, `${where}:root ${after.root}≠${d.t}`); }
    if (!sf.context) { C.contextLost++; note(C, where + ":context lost"); }
    else if (!sameTerm(sf.contextTerm, d.t)) { C.contextTargetMismatch++; note(C, `${where}:ctx ${sf.contextTerm}≠${d.t}`); }
    if (sf.menu || sf.action) stale("Menu/Actionが残る");
  } else if (eff === "map") {
    if (!sf.context) { C.contextLost++; note(C, where + ":context lost"); }
    else if (sf.contextTerm !== before.surf.contextTerm) { C.contextTargetMismatch++; note(C, `${where}:ctx変化`); }
    if (sf.action) stale("Actionが残る");
  } else if (eff === "store" || eff === "newpage") {
    if (sf.contextTerm !== before.surf.contextTerm) { C.contextTargetMismatch++; note(C, `${where}:${eff} でContextが変わった`); }
    if (eff === "newpage" && after.nav.len !== before.nav.len) { C.commitMismatch++; note(C, where + ":newpage が履歴を変えた"); }
  }
}

/* ══ L1 列挙（canvas全ノード／全edge／Context内の全entity／目次／開閉／出典／グラフ上部の全操作） ══ */
async function enumerateL1(p) {
  const out = [];
  const nodes = await p.evaluate(() => (__dx.G ? __dx.G.nodes : []).map((n, i) =>
    ({ i, id: n.id, label: n.label, kind: n.kind, layer: n.layer, term: n.q || n.label, structure: n.kind === "domain" || !(n.q || n.label) })));
  nodes.forEach(n => out.push({ t: "node", ...n }));
  const edges = await p.evaluate(() => (__dx.G ? __dx.G.edges : []).map((e, i) => ({ i })));
  edges.forEach(e => out.push({ t: "edge", i: e.i }));
  const ents = await p.evaluate(() => {
    const el = document.getElementById("dx-context"); if (!el) return [];
    el.querySelectorAll("details:not([open]) > summary").forEach(s => { s.parentElement.open = true; });
    return [...el.querySelectorAll(".pano-ent")].map((e, i) => ({ i, term: e.dataset.term, kind: e.dataset.kind, eid: e.dataset.eid }));
  });
  ents.forEach(e => out.push({ t: "ctxent", ...e }));
  const tocs = await p.evaluate(() => [...document.querySelectorAll("#dx-context .pano-toc-a")].map((a, i) => ({ i, sec: a.dataset.sec })));
  tocs.forEach(x => out.push({ t: "toc", ...x }));
  const dets = await p.evaluate(() => [...document.querySelectorAll("#dx-context summary")].map((s, i) => ({ i })));
  dets.forEach(x => out.push({ t: "details", ...x }));
  const exts = await p.evaluate(() => [...document.querySelectorAll('#dx-context a[target="_blank"]')].map((a, i) => ({ i, href: a.getAttribute("href") || "" })));
  exts.forEach(x => out.push({ t: "extlink", ...x }));
  const tops = await p.evaluate(() => {
    const o = [];
    [...document.querySelectorAll("#graph-lens .tm-chip")].forEach((e, i) => o.push({ sel: "#graph-lens .tm-chip", i, name: e.textContent.trim() }));
    if (document.getElementById("tm-view")) o.push({ sel: "#tm-view", i: 0, name: "見方バッジ" });
    ["#graph-play", "#graph-shelf", "#graph-fit", "#nav-back", "#nav-fwd"].forEach(s => { if (document.querySelector(s)) o.push({ sel: s, i: 0, name: s }); });
    return o;
  });
  tops.forEach(x => out.push({ t: "topop", ...x }));
  return out;
}

/* ══ メイン ══ */
if (require.main === module) (async () => {
  const R = []; const ok = (n, c, d) => { R.push(c); console.log(`${c ? "PASS" : "FAIL"}  ${n}${d ? "  — " + d : ""}`); };
  let cutFails = 0;   // 打ち切り（予算/timeout/途中終了）に由来する失敗の件数＝PARTIAL の根拠

  for (const vp of VIEWPORTS) {
    const V = `[${vp.width}]`;
    const hb = mkHb(V);
    // viewport ごとに新しい browser を起動する。1つのブラウザを viewport 間で使い回すと、
    // 1128幅のBFS（L1 260/L2 418/L3 227・約1時間）で資源が蓄積し、次の 1920幅の最初のクリックで
    // "Target page, context or browser has been closed" が再現した（2026-08-08 実測・2回とも同一地点）。
    // 新規 browser なら同じ地点を通過する（1920単独 probe 22/22 PASS・2026-08-09 実測）。
    const b = await chromium.launch({ executablePath: EXE, headless: true });
    const bctx = await b.newContext({ viewport: vp });
    try {
      const p = await bctx.newPage();
      // 新規ページ（外部出典 a[target=_blank] ／ 新タブAction）は捕捉してURLを記録し、直ちに閉じる。
      // 元画面は壊さない（newpage effect の契約＝Context・履歴を変えない、を実測で確かめる）。
      const popupLog = [];
      bctx.on("page", async (pg) => {
        const j = popupLog.push(pg.url()) - 1;
        try { await pg.waitForLoadState("domcontentloaded", { timeout: 3000 }); popupLog[j] = pg.url(); } catch (e) {}
        try { await pg.close(); } catch (e) {}
      });
      const perr = []; p.on("pageerror", e => perr.push(String(e).slice(0, 160)));
      const C = newC();
      const t0 = Date.now();
      const overBudget = () => BUDGET_MS > 0 && (Date.now() - t0) > BUDGET_MS;

      const reg = await (async () => { await loadSeed(p, SEED); return await p.evaluate(() => __dx.registry()); })();
      let base = await state(p);

      /* ── C-1. SEARCH(term) 成功時 ── */
      ok(`${V} SEARCH: グラフ＋中心語=term＋Context自動表示＋Menu0＋Action0`,
        base.root === SEED && base.surf.context && base.surf.contextTerm === SEED && !base.surf.menu && !base.surf.action,
        JSON.stringify({ root: base.root, ctx: base.surf.contextTerm, m: base.surf.menu, a: base.surf.action }));
      ok(`${V} SEARCH: 履歴commitは1回だけ`, base.nav.len === 1, "len=" + base.nav.len);
      ok(`${V} SEARCH: 中心語を再クリックしなくても全景（Context）が出ている`, base.ctxSecs.length > 0, JSON.stringify(base.ctxSecs));
      await gateGeometry(p, C, "search");

      const l1 = await enumerateL1(p);          // canonical な L1 一覧（範囲適用はこの後）
      C.l1Enum = l1.length;
      const l1To = L1_TO_ENV === null ? l1.length : Math.max(0, Math.min(L1_TO_ENV, l1.length));
      const l1From = Math.min(L1_FROM, l1To);
      let slice = l1.slice(l1From, l1To);
      if (L1_MAX) slice = slice.slice(0, L1_MAX);   // 既存の診断上限は範囲の**中**で効く
      const expectedL1 = slice.length;
      const RANGE = `[${l1From},${l1From + expectedL1})`;
      const clickedTerms = new Set();
      console.log(`${V} RANGE=${RANGE} 期待L1=${expectedL1} / canonical総数=${l1.length}`);
      const l2seen = new Set(), l3seen = new Set(), l2tasks = [];

      /* ══ 第1階層: canvas全ノード／全edge／Context内の全entity／目次／開閉／出典／グラフ上部の全操作 ══ */
      for (const item of slice) {
        hb(`L1 ${C.l1Click}/${expectedL1}`);
        if (overBudget()) { C.budgetCut = true; break; }
        if (L1_MAX && C.l1Click >= L1_MAX) break;
        await restoreBaseline(p, base);
        const before1 = await state(p);
        const r = await clickL1(p, item, popupLog);
        if (!r || !r.ok) { C.unclickable++; note(C, `L1 ${item.t}/${item.term || item.i}:${(r && r.why) || "fail"}`); continue; }
        C.l1Click++;
        if (item.term) clickedTerms.add(item.term);
        const after = await settledState(p, C, `L1 ${item.t}/${item.term || item.i}`);
        await gateGeometry(p, C, `L1 ${item.t}/${item.term || item.i}`);
        const dispatched = !!(after.last && after.last.seq !== (before1.last && before1.last.seq));   // seqで反復操作も区別
        // ── L1 種別ごとの契約
        if (item.t === "node" || item.t === "ctxent" || item.t === "edge") {
          if (item.t !== "edge" && !item.structure) {
            if (!after.surf.menu) { C.unclickable++; note(C, `L1 ${item.term}:Menuが開かない`); }
            if (!after.surf.context) { C.contextLost++; note(C, `L1 ${item.term}:Context消失`); }
            else if (after.surf.contextTerm !== base.surf.contextTerm) { C.contextTargetMismatch++; note(C, `L1 ${item.term}:Context対象が変わった`); }
            if (after.surf.action) { C.staleSurface++; note(C, `L1 ${item.term}:旧Actionが残る`); }
            const mt = await p.evaluate(() => { const m = document.getElementById("graph-menu"); return m ? (m.querySelector(".gm-title") || {}).textContent || "" : ""; });
            const want = item.term;
            if (want && !mt.includes(want)) { C.targetMismatch++; note(C, `L1 ${want}:menu title=${mt.slice(0, 30)}`); }
          } else if (item.t === "node" && item.structure) {
            if (dispatched) checkEffect(C, reg, before1, after, `L1 domain/${item.label}`, null);
            else { C.effectUnclassified++; note(C, `L1 domain/${item.label}:no-dispatch`); }
          }
        } else if (item.t === "toc") {
          const tr = await p.evaluate((sec) => {
            const panel = document.getElementById("dx-context"); if (!panel) return null;
            const el = document.getElementById("pano-" + sec); if (!el) return null;
            const act = (panel.querySelector(".pano-toc-a.active") || {}).dataset?.sec;
            const pr = panel.getBoundingClientRect(), hr = el.querySelector(".pano-h").getBoundingClientRect();
            return { act, inView: hr.top >= pr.top - 4 && hr.top <= pr.bottom };
          }, item.sec);
          if (!tr || tr.act !== item.sec || !tr.inView) { C.targetMismatch++; note(C, `L1 toc/${item.sec}:${JSON.stringify(tr)}`); }
          if (after.surf.menu || after.surf.action) { C.staleSurface++; note(C, `L1 toc/${item.sec}:面が増えた`); }
        } else if (item.t === "extlink") {
          // 出典＝新規ページを開き、元画面のContext・履歴は変えない（newpage契約）
          if (!r.popup) { C.unclickable++; note(C, `L1 extlink:新規ページが開かない(${EXT_POPUP_MS}ms以内・${r.popWhy || "timeout"}) ${item.href}`); }
          else C.extMs.push(r.popMs);
          if (r.navigated) { C.staleSurface++; note(C, "L1 extlink:元画面が遷移した"); }
          if (after.surf.contextTerm !== before1.surf.contextTerm) { C.contextTargetMismatch++; note(C, "L1 extlink:Contextが変わった"); }
          if (after.nav.len !== before1.nav.len) { C.commitMismatch++; note(C, "L1 extlink:履歴が変わった"); }
        } else if (item.t === "details") {
          if (after.surf.menu || after.surf.action) { C.staleSurface++; note(C, "L1 details:面が増えた"); }
          if (after.surf.contextTerm !== before1.surf.contextTerm) { C.contextTargetMismatch++; note(C, "L1 details:Contextが変わった"); }
        } else if (item.t === "topop") {
          if (dispatched) checkEffect(C, reg, before1, after, `L1 top/${item.name}`, null);
        }
        if (after.search !== before1.search && !(dispatched && after.last.e === "center")) { C.searchBoxChanged++; note(C, `L1 ${item.t}:検索欄=${after.search}`); }
        if (after.nodes <= 1) { C.emptyGraph++; note(C, `L1 ${item.t}/${item.term || item.i}:空グラフ`); }

        // L2 の対象（実体）はここでは実行せず、第2階層のパスとして貯める（BFS＝階層ごとに横断する）
        if ((item.t === "node" && !item.structure) || item.t === "ctxent") {
          const items = await p.evaluate(() => [...document.querySelectorAll("#graph-menu .gm-item")].map((e, i) => ({ i, t: e.textContent.trim() })));
          C.l2Enum += items.length;
          l2tasks.push({ item, items });
        }
      }

      /* ══ 第2階層: L1の実体を押して現れる、その kind で有効な全 Action ID ══ */
      const l3tasks = [];
      const l2ItemsTotal = l2tasks.reduce((a, t) => a + t.items.length, 0);   // 実列挙の総数（根拠）
      let l2ItemsSeen = 0;
      for (const task of l2tasks) {
        if (overBudget()) { C.budgetCut = true; break; }
        const item = task.item, must = REQUIRED.includes(item.term);
        for (const mi of task.items) {
          hb(`L2 ${C.l2Click}/${C.l2Enum}`);
          if (overBudget()) { C.budgetCut = true; break; }
          l2ItemsSeen++;
          const key = `${item.kind}|${mi.i}`;
          if (!FULL && !must && l2seen.has(key)) continue;
          l2seen.add(key);
          await restoreBaseline(p, base);
          const rr = await clickL1(p, item, popupLog);
          if (!rr || !rr.ok) { C.unclickable++; note(C, `L2 reopen ${item.term}:${rr && rr.why}`); continue; }
          const before2 = await state(p);
          const mc = await mclick(p, "#graph-menu", ".gm-item", mi.i);
          if (!mc.ok) { C.unclickable++; note(C, `L2 ${item.term}/${mi.t}:${mc.why}`); continue; }
          C.l2Click++;
          await sleep(400);
          const a2 = await p.evaluate(() => __dx.lastDispatch ? __dx.lastDispatch.actionId : null);
          if (a2 === "panorama" || a2 === "center") await waitContext(p);
          else if (await p.evaluate(() => !!document.getElementById("graph-panel"))) await waitAction(p);
          const after2 = await settledState(p, C, `L2 ${item.term}/${mi.t}`);
          await gateGeometry(p, C, `L2 ${item.term}/${mi.t}`);
          checkEffect(C, reg, before2, after2, `L2 ${item.term}`, item.term);
          if (after2.nodes <= 1) { C.emptyGraph++; note(C, `L2 ${item.term}/${mi.t}:空グラフ`); }
          // 第3階層のパスとして貯める（結果の面の中の全操作）
          const root3 = after2.surf.action ? "#graph-panel" : "#dx-context";
          const ops = await enumerateOps(p, root3);
          C.l3Enum += ops.length;
          l3tasks.push({ item, mi, a2, root3, ops, must });
        }
      }

      /* ══ 第3階層: 各Action結果内の 全リンク・全ボタン・全entity・戻る・続けて探索する操作・多言語項目 ══ */
      const l3OpsTotal = l3tasks.reduce((a, t) => a + t.ops.length, 0);      // 実列挙の総数（根拠）
      let l3OpsSeen = 0;
      for (const t3 of l3tasks) {
        if (overBudget()) { C.budgetCut = true; break; }
        for (const op of t3.ops) {
          hb(`L3 ${C.l3Click}/${C.l3Enum}`);
          if (overBudget()) { C.budgetCut = true; break; }
          l3OpsSeen++;
          const k3 = `${t3.a2}|${op.cls}|${op.tag}`;
          if (!FULL && !t3.must && l3seen.has(k3)) continue;   // 第3階層より深い循環のみ stable ID で停止
          l3seen.add(k3);
          await restoreBaseline(p, base);                      // 経路を再現（baseline → L1 → L2）してから L3 を押す
          const r1b = await clickL1(p, t3.item, popupLog); if (!r1b || !r1b.ok) { C.unclickable++; note(C, `L3 replay ${t3.item.term}`); break; }
          const m2 = await mclick(p, "#graph-menu", ".gm-item", t3.mi.i); if (!m2.ok) { C.unclickable++; note(C, `L3 replay menu ${t3.mi.t}`); break; }
          await sleep(400);
          const a2b = await p.evaluate(() => __dx.lastDispatch ? __dx.lastDispatch.actionId : null);
          if (a2b === "panorama" || a2b === "center") await waitContext(p);
          else if (await p.evaluate(() => !!document.getElementById("graph-panel"))) await waitAction(p);
          // 列挙(enumerateOps)は折り畳みを開いた状態で index を採る。経路を再現しただけでは面が作り直されて
          // 折り畳みが閉じており、同じ index の要素が畳まれた中に残る（実測: dioscúrsa は rects=1 のまま
          // top=1011 で viewport 外＝outside-viewport／開けば同じ index が押せてメニュー「選択：dioscúrsa」が出る）。
          // ここで列挙時と同じ前提へ戻す。クリックは実マウスのまま＝force click ではない。
          // 開閉そのものは L1 の details 項目を実マウスで押して別途検証している。
          await p.evaluate((root) => { const el = document.querySelector(root); if (!el) return;
            el.querySelectorAll("details:not([open]) > summary").forEach(s => { s.parentElement.open = true; }); }, t3.root3);
          await sleep(150);
          const where3 = `L3 ${t3.a2}/${op.kind}/${op.text}`;
          // L2 と同じく、経路再現の作用が確定するまで待ってから対象を決める。ここを待たずに読むと
          // 遷移前の古い面を対象にしてしまい、別要素を押した結果が Context/履歴の不一致として現れる
          // （実測: [28,29) の 出典：Wiktionary（dialectica で 新規ページ0・Context変化・履歴変化が同時発生）。
          await settledState(p, C, `${where3}:再現`);
          const before3 = await state(p);
          const rr = await resolveOp(p, t3.root3, op);
          if (!rr.ok) { C.unclickable++; note(C, `${where3}:対象を安定識別子で再解決できない(${rr.why})`); continue; }
          const rc = await clickOp(p, popupLog, t3.root3, OPS_SEL, rr.i, op.kind);
          if (!rc.ok) { C.unclickable++; note(C, `${where3}:${rc.why}`); continue; }
          C.l3Click++;
          if (op.kind === "ext") {
            // 外部出典＝新規ページを開き、**元画面**のContext・履歴を変えない（newpage契約）
            if (!rc.popup) { C.unclickable++; note(C, `${where3}:新規ページが開かない(${EXT_POPUP_MS}ms以内・${rc.popWhy || "timeout"}) ${op.href}`); }
            else C.extMs.push(rc.popMs);
            if (rc.navigated) { C.staleSurface++; note(C, `${where3}:元画面が遷移した`); }
            const a3 = await settledState(p, C, where3);
            await gateGeometry(p, C, where3);
            if (a3.surf.contextTerm !== before3.surf.contextTerm) { C.contextTargetMismatch++; note(C, `${where3}:元画面のContextが変わった`); }
            if (a3.nav.len !== before3.nav.len) { C.commitMismatch++; note(C, `${where3}:元画面の履歴が変わった`); }
            if (a3.nodes <= 1) { C.emptyGraph++; note(C, `${where3}:空グラフ`); }
            continue;
          }
          if (op.kind === "nav" && rc.navigated) {
            // サイト内リンク＝ページ遷移。着地はSEARCHと同じ確定状態（Context自動表示・Menu0・Action0・commit1）
            await waitContext(p);
            const a3 = await settledState(p, C, where3);
            await gateGeometry(p, C, where3);
            if (!a3.surf.context) { C.contextLost++; note(C, `${where3}:着地でContextが出ない`); }
            if (a3.surf.menu || a3.surf.action) { C.staleSurface++; note(C, `${where3}:着地に旧面が残る`); }
            if (a3.nav.len !== 1) { C.commitMismatch++; note(C, `${where3}:着地の履歴=${a3.nav.len}`); }
            if (a3.nodes <= 1 && a3.ctxSecs.length === 0) { C.emptyGraph++; note(C, `${where3}:空グラフへ遷移`); }
            continue;
          }
          const after3 = await settledState(p, C, where3);
          await gateGeometry(p, C, where3);
          if (after3.last && after3.last.seq !== (before3.last && before3.last.seq))
            checkEffect(C, reg, before3, after3, where3, null);
          if (after3.nodes <= 1) { C.emptyGraph++; note(C, `${where3}:空グラフ`); }
        }
      }
      await restoreBaseline(p, base);

      /* ── 必須対象が実際に押されたか（stable ID で確認） ── */
      // 必須9語は canonical L1 の index で唯一の範囲に属する。本範囲に属する語は必ず実クリックされ、
      // 他範囲の語はここでは対象外（＝重複実行しない）。どの範囲にも現れない語は欠落として失敗にする。
      const reqIdx = {};
      REQUIRED.forEach(t => { reqIdx[t] = l1.map((x, i) => (x.term === t ? i : -1)).filter(i => i >= 0); });
      const inSlice = (i) => i >= l1From && i < l1From + expectedL1;
      const reqHere = REQUIRED.filter(t => reqIdx[t].some(inSlice));
      const reqOther = REQUIRED.filter(t => reqIdx[t].length > 0 && !reqIdx[t].some(inSlice));
      const reqUnlisted = REQUIRED.filter(t => reqIdx[t].length === 0);
      const reqMissed = reqHere.filter(t => !clickedTerms.has(t));
      ok(`${V} 必須対象のうち本範囲に属する語が実際にクリックされた（重複・欠落なし）`,
        reqMissed.length === 0 && reqUnlisted.length === 0,
        `RANGE=${RANGE} 本範囲=${JSON.stringify(reqHere)} 他範囲=${JSON.stringify(reqOther)} 未クリック=${JSON.stringify(reqMissed)} canonicalに無い=${JSON.stringify(reqUnlisted)}`);
      const langN = l1.filter(x => x.t === "node" && x.kind === "language").length;
      ok(`${V} 実行時に列挙された全多言語ノードが第1階層に含まれる`, langN > 0, "language nodes=" + langN);

      console.log(`\n${V} 網羅: L1 列挙${C.l1Enum}/実クリック${C.l1Click} ・ L2 列挙${C.l2Enum}/実クリック${C.l2Click} ・ L3 列挙${C.l3Enum}/実クリック${C.l3Click}` + (FULL ? " (FULL)" : " (kind×Action 閉包＋必須対象は全件)"));
      const notRun = expectedL1 - C.l1Click;
      console.log(`${V} RESULT RANGE=${RANGE} 期待L1=${expectedL1} 実行L1=${C.l1Click} 未実行=${notRun} L2処理=${l2ItemsSeen}/${l2ItemsTotal} L3処理=${l3OpsSeen}/${l3OpsTotal} L2クリック=${C.l2Click} L3クリック=${C.l3Click} budgetCut=${C.budgetCut} canonical総数=${C.l1Enum}`);
      console.log(`${V} フォールバック: center=${C.centerFallback} fallbackContract違反=${C.fallbackContract}`);
      console.log(`${V} 異常件数: ` + ANOMALY_KEYS.map(k => `${k}=${C[k]}`).join(" "));
      if (C.extMs.length) console.log(`${V} 外部出典: 新規ページ ${C.extMs.length}件成功 実測 最小${Math.min(...C.extMs)}ms 最大${Math.max(...C.extMs)}ms（上限${EXT_POPUP_MS}ms）`);
      if (C.notes.length) console.log(`${V} 詳細: ` + JSON.stringify(C.notes.slice(0, 12)));
      for (const k of ANOMALY_KEYS) ok(`${V} ${k} = 0`, C[k] === 0, String(C[k]));
      ok(`${V} JavaScript例外0`, perr.length === 0, JSON.stringify(perr.slice(0, 3)));
      // 期待件数は範囲に合わせて厳密に計算する（予算切れ・中断で未実行が出れば失敗として残す）。
      ok(`${V} 範囲のL1が全件クリックされた（期待=実行）`, C.l1Click === expectedL1,
        `RANGE=${RANGE} 期待L1=${expectedL1} 実行L1=${C.l1Click} 未実行=${notRun} canonical総数=${C.l1Enum}`);
      // 部分成功の禁止: L1が完了していても L2/L3 が未処理なら PASS にしない。
      // 期待件数は推測せず、その範囲で実際に列挙された l2tasks/l3tasks の総数を根拠にする。
      const cutStart = R.length;
      ok(`${V} L2の対象を全件処理した（打ち切りなし）`, l2ItemsSeen === l2ItemsTotal, `${l2ItemsSeen}/${l2ItemsTotal}`);
      ok(`${V} L3の対象を全件処理した（打ち切りなし）`, l3OpsSeen === l3OpsTotal, `${l3OpsSeen}/${l3OpsTotal}`);
      ok(`${V} 予算・timeoutによる打ち切りが無い`, C.budgetCut === false, `budgetCut=${C.budgetCut} (DX_BUDGET_MS=${BUDGET_MS})`);
      cutFails += R.slice(cutStart).filter(x => !x).length;

    } finally {
      // 例外で抜けても必ず閉じる（孤児プロセスを残さない）。閉じる側の失敗は握り潰さず記録する。
      try { await bctx.close(); } catch (e) { console.log(`${V} 後始末: context close 失敗 — ${String(e).slice(0, 120)}`); }
      try { await b.close(); } catch (e) { console.log(`${V} 後始末: browser close 失敗 — ${String(e).slice(0, 120)}`); }
    }
  }

  const pass = R.filter(Boolean).length;
  const otherFail = (R.length - pass) - cutFails;
  // PASS は「L1/L2/L3の対象をすべて完了し、異常件数0」のときだけ。打ち切りがあれば PARTIAL（EXIT!=0）。
  const verdict = otherFail > 0 ? "FAIL" : (cutFails > 0 ? "PARTIAL" : "PASS");
  console.log(`\n${pass}/${R.length} ${verdict}` + (RANGED ? `  RANGE: DX_L1_FROM=${L1_FROM} DX_L1_TO=${L1_TO_ENV}（この範囲の結果であり全L1の判定ではない）` : ""));
  process.exit(verdict === "PASS" ? 0 : 1);
})().catch(e => { console.error("ERR", e); process.exit(2); });
// 対象を絞った短時間検証が**同じ判定実装**を呼べるようにする（ロジックを複製しないため）。
module.exports = { pointOf, mclick, state, appBusy, settledState, waitContext, waitAction, loadSeed, enumerateL1,
  restoreBaseline, clickL1, clickOp, enumerateOps, resolveOp, gateGeometry, newC, note, SKEY, AKEY, ANOMALY_KEYS, EXT_POPUP_MS, mkHb };
