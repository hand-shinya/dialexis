// sim2 観測（2026-10-21）: 一手ごとの画面の状態を、機械で測れる形で記録する。判定（オラクル）は oracles.js。
// 過去の sim（tools/sim）は「見える文字と押せる物」だけを Actor に渡し、結果の中身と配置を記録しなかった。
"use strict";
async function observe(p) {
  return p.evaluate(() => {
    const vw = innerWidth, vh = innerHeight;
    const vis = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
      return r.width > 2 && r.height > 2 && s.visibility !== "hidden" && s.display !== "none" && r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw; };
    const rectOf = (el) => { const r = el.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; };
    const G = window.__dx && window.__dx.G;
    const wrap = document.getElementById("origin-graph-wrap");
    const wr = wrap ? wrap.getBoundingClientRect() : null;
    const panels = [...document.querySelectorAll(".gp-body")].map(b => {
      const box = b.parentElement; const head = box && box.querySelector(".gp-head b");
      return { title: head ? head.textContent.trim() : "", text: b.innerText.trim(), rect: rectOf(box), visible: vis(box) };
    }).filter(x => x.visible);
    const ctxPanel = [...document.querySelectorAll("[class*=context], #ctx-panel, .pano")].find(vis);
    let overlap = 0;
    for (let i = 0; i < panels.length; i++) for (let j = i + 1; j < panels.length; j++) {
      const a = panels[i].rect, b = panels[j].rect;
      const ox = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)), oy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
      overlap += ox * oy;
    }
    const btns = [...document.querySelectorAll("button, a.tm-chip, .gp-cont-b, .nomiss-b")].filter(b => vis(b) && !b.closest("#radial-menu") && (b.innerText || "").trim().length > 1);
    const radial = document.querySelector("#radial-menu");
    let radialClip = null;
    if (radial) { const items = [...radial.querySelectorAll(".rad-item")].filter(x => getComputedStyle(x).display !== "none" && !x.closest("[hidden]"));
      radialClip = items.filter(x => { const r = x.getBoundingClientRect(); return r.left < 0 || r.top < 0 || r.right > vw || r.bottom > vh; }).length; }
    const bodyText = document.body.innerText || "";
    const jp = (bodyText.match(/[぀-ヿ一-鿿]/g) || []).length;
    return {
      url: location.pathname + location.search, vw, vh, scrollY: Math.round(scrollY),
      map: G ? { root: G.rootQ, n: G.nodes.length, kinds: G.nodes.reduce((m, x) => (m[x.kind] = (m[x.kind] || 0) + 1, m), {}),
                 labels: G.nodes.map(x => x.label) } : null,
      mapTopAbs: wr ? Math.round(wr.top + scrollY) : null,
      mapInFirstScreen: wr ? (wr.top + scrollY) < vh * 0.6 : false,
      mapVisibleNow: wrap ? vis(wrap) : false,
      mapVisibleFrac: (() => { const c = document.getElementById("origin-graph"); if (!c || !vis(c)) return 0; const r = c.getBoundingClientRect();
        const h = Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0)), w = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0));
        return Math.round(100 * (h * w) / Math.max(1, r.width * r.height)) / 100; })(),
      panels, panelOverlapPx: overlap, ctxText: ctxPanel ? ctxPanel.innerText.slice(0, 4000) : "",
      textButtonsVisible: btns.length,
      radialItems: radial ? radial.querySelectorAll(".rad-item").length : 0, radialClipped: radialClip,
      trail: [...document.querySelectorAll("#dx-trail .tr-step")].map(x => x.innerText.trim()),
      smallMap: !!document.getElementById("dx-small-map"), decomp: [...document.querySelectorAll("#decomp-strip .ds-part b")].map(x => x.textContent),
      redirectNote: [...document.querySelectorAll(".redirect-note")].map(x => x.innerText).slice(0, 2),
      jpRatio: bodyText.length ? jp / bodyText.length : 0,
      leak: (bodyText.match(/mw-parser-output[^\n]{0,60}|\.[a-z-]+\s*\{[^}\n]{0,60}\}|rgba?\([^)\n]{0,30}\)/) || [null])[0],
      lastDispatch: window.__dx && window.__dx.lastDispatch ? { a: window.__dx.lastDispatch.actionId, outcome: window.__dx.lastDispatch.outcome } : null,
    };
  });
}
module.exports = { observe };
