// 画面の観測（ブラウザ内で実行する関数）。sim.js と selftest.js が同じものを使う。
// 人の目に見える物だけを返す。生 DOM は返さない（§8.4）。
"use strict";
const pageObserve = () => {
    // 可視判定。offsetHeight と bounding box だけでは足りない: 閉じた <details> の中身は
    // Chromium では content-visibility で描かれないが寸法は持つ（2026-10-13 に実測。
    // /origin の「文章・引用を…入口」の入力欄8つを、人に見えないのに Actor へ渡していた）。
    // checkVisibility は content-visibility・visibility・opacity をまとめて見る。
    const vis = (el) => { if (!el || el.offsetHeight <= 0 || el.offsetWidth <= 0) return false;
      if (el.checkVisibility && !el.checkVisibility({ contentVisibilityAuto: true, opacityProperty: true, visibilityProperty: true })) return false;
      const cs = getComputedStyle(el); if (cs.visibility === "hidden" || cs.display === "none" || +cs.opacity === 0) return false;
      const r = el.getBoundingClientRect(); if (!(r.width > 0 && r.height > 0)) return false;
      // 祖先の overflow:hidden/clip で切り取られている物は見えない（scroll/auto は送れば見えるので残す）
      for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
        const ac = getComputedStyle(a);
        if (/hidden|clip/.test(ac.overflowX + ac.overflowY)) { const q = a.getBoundingClientRect();
          if (r.right <= q.left || r.left >= q.right || r.bottom <= q.top || r.top >= q.bottom) return false; }
      }
      return !occluded(el, r); };
    // 被さり判定（2026-10-13・本走A2で実測）。浮動パネル（position:fixed）の背後にある物は人に見えない。
    // 画面内の物は中心点の elementFromPoint で、画面外の物は「送って中央に来たとき」に
    // 固定配置の覆いの下に入るかで判定する。
    function occluded(el, r) {
      const cx = r.left + r.width / 2;
      const inView = r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth;
      if (inView) { const top = document.elementFromPoint(cx, r.top + r.height / 2);
        return !!top && !el.contains(top) && !top.contains(el); }
      const cy = innerHeight / 2;
      return fixedCovers.some(f => !f.el.contains(el) && cx >= f.r.left && cx <= f.r.right && cy >= f.r.top && cy <= f.r.bottom);
    }
    const fixedCovers = [...document.querySelectorAll("body *")].filter(e => { const cs = getComputedStyle(e);
      if (cs.position !== "fixed" || cs.display === "none" || cs.visibility === "hidden" || e.offsetHeight <= 0) return false;
      const q = e.getBoundingClientRect(); return q.width * q.height > 0.1 * innerWidth * innerHeight; }).map(e => ({ el: e, r: e.getBoundingClientRect() }));
    const sel = "a[href], button, input:not([type=hidden]), textarea, select, summary, [role=button], [role=menuitem], [role=tab], [onclick]";
    const els = [...document.querySelectorAll(sel)].filter(vis);
    window.__simEls = els;
    const items = els.map((el, i) => {
      const r = el.getBoundingClientRect(); const tag = el.tagName.toLowerCase();
      let label = (el.innerText || el.value || el.getAttribute("aria-label") || el.getAttribute("title") || "").replace(/\s+/g, " ").trim();
      const isInput = tag === "input" || tag === "textarea";
      if (isInput) label = el.getAttribute("placeholder") || el.getAttribute("aria-label") || "";
      const href = tag === "a" ? el.href : null;
      return { i, tag, input: isInput && !["submit", "button", "checkbox", "radio"].includes(el.type),
        label: label.slice(0, 70), ext: (() => { try { return !!(href && new URL(href, location.href).host !== location.host); } catch (e) { return false; } })(),
        newtab: el.target === "_blank", y: Math.round(r.top + window.scrollY), below: r.top > innerHeight };
    });
    // canvas の重力グラフ: 人の目に見えるのは描かれたラベル。ラベルと画面座標だけを渡す
    let nodes = [];
    try { const G = window.__dx && window.__dx.G; const cv = document.getElementById("origin-graph");
      if (G && G.nodes && cv && vis(cv)) { const cr = cv.getBoundingClientRect();
        nodes = G.nodes.map(n => window.__dx.nodeClientXY(n.id)).filter(p => p && p.x >= cr.left && p.x <= cr.right && p.y >= cr.top && p.y <= cr.bottom)
          .slice(0, 30).map(p => ({ label: (p.label.length > 22 ? p.label.slice(0, 21) + "…" : p.label), x: p.x, y: p.y })); } } catch (e) {}
    // 文も可視判定を通す（2026-10-13・回帰調査の指摘 D）。body.innerText はパネルの下に隠れた文まで含み、
    // 「画面に見えている文」という見出しと中身が食い違っていた。直に文字を持つ要素ごとに同じ判定を掛ける。
    const seenText = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let lastEl = null, lastOk = false;
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const t = n.nodeValue.replace(/\s+/g, " ").trim(); if (!t) continue;
      const el = n.parentElement; if (!el || /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(el.tagName)) continue;
      if (el !== lastEl) { lastEl = el; lastOk = vis(el); }
      if (lastOk) seenText.push(t);
    }
    const text = seenText.join("\n");
    return { url: location.href, path: location.pathname + location.search, title: document.title, items, nodes, text,
      scrollY: Math.round(scrollY), docH: document.documentElement.scrollHeight, viewH: innerHeight };
  };
module.exports = { pageObserve };
