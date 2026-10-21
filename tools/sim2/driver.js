// sim2 操作器: 実際の画面操作（マウスの移動・hover・クリック・円形メニューの項目）で動かし、一手ごとに観測を記録する。
// 内部関数（dispatchAction）を直接呼ばない。利用者と同じ経路だけを通る。
"use strict";
const fs = require("fs"), path = require("path");
const { observe } = require("./observe");
class Driver {
  constructor(page, outdir, id) { this.p = page; this.out = outdir; this.id = id; this.steps = []; this.n = 0; fs.mkdirSync(outdir, { recursive: true }); }
  async rec(kind, detail, t0, extra) {
    const obs = await observe(this.p).catch(e => ({ error: String(e) }));
    const shot = path.join(this.out, `${this.id}_${String(++this.n).padStart(2, "0")}.jpg`);
    await this.p.screenshot({ path: shot, type: "jpeg", quality: 55 }).catch(() => {});
    const s = { step: this.n, kind, detail, ms: Date.now() - t0, obs, shot: path.basename(shot), ...(extra || {}) };
    this.steps.push(s); return s;
  }
  async open(base, q, lang, preview, waitMs) {
    const t0 = Date.now();
    await this.p.goto(`${base}/origin?q=${encodeURIComponent(q)}&lang=${lang}&preview=${preview ? 1 : 0}`, { waitUntil: "domcontentloaded" });
    // 読み込み中の仮カード（origin-loading-card）は「最初の文」に数えない
    const first = await this.p.waitForSelector(".word-card:not(.origin-loading-card), .nomiss, .bridge-cands", { timeout: waitMs }).then(() => Date.now() - t0).catch(() => null);
    const mapMs = await this.p.waitForFunction(() => window.__dx && window.__dx.G && window.__dx.G.nodes.length > 1, null, { timeout: waitMs }).then(() => Date.now() - t0).catch(() => null);
    await this.p.waitForTimeout(1500);
    return this.rec("open", { q, lang, preview }, t0, { firstMs: first, mapMs });
  }
  async nodePos(pred) {
    return this.p.evaluate((src) => { const G = window.__dx && window.__dx.G; if (!G) return null; const f = eval(src);
      const n = G.nodes.find(f); if (!n) return null; const r = G.cv.getBoundingClientRect();
      const x = r.left + n.x * G.view.k + G.view.x, y = r.top + n.y * G.view.k + G.view.y;
      return { label: n.label, kind: n.kind, q: n.q || n.label, x, y, onScreen: x > 0 && y > 0 && x < innerWidth && y < innerHeight }; }, pred.toString());
  }
  async labels() { return this.p.evaluate(() => { const G = window.__dx && window.__dx.G; return G ? G.nodes.map(n => ({ label: n.label, kind: n.kind, layer: Number(n.layer) })) : []; }); }
  // 語を開く: マウスで語へ移動し（hover）、押して円形メニュー（通常表示なら縦の一覧）を出す
  async openNodeMenu(label, touch) {
    let pos = await this.nodePos(`n => n.label === ${JSON.stringify(label)}`);
    if (!pos) return null;
    if (!pos.onScreen) { await this.p.evaluate(() => { const w = document.getElementById("origin-graph-wrap"); if (w) w.scrollIntoView({ block: "center" }); }); await this.p.waitForTimeout(400); pos = await this.nodePos(`n => n.label === ${JSON.stringify(label)}`); }
    if (!touch) { await this.p.mouse.move(pos.x - 30, pos.y - 30); await this.p.mouse.move(pos.x, pos.y, { steps: 4 }); }
    for (let k = 0; k < 2; k++) {   // 1回目のクリックが別の面（右のパネル）を閉じるだけのことがある
      await this.p.mouse.click(pos.x, pos.y);
      const ok = await this.p.waitForSelector("#radial-menu .rad-item, .gm-item", { timeout: 3000 }).then(() => true).catch(() => false);
      if (ok) break;
      pos = await this.nodePos(`n => n.label === ${JSON.stringify(label)}`) || pos;
    }
    return pos;
  }
  async menuItems() {
    return this.p.evaluate(() => [...document.querySelectorAll("#radial-menu .rad-item[data-action], .gm-item")].map(b => ({
      action: b.dataset.action || b.getAttribute("data-a") || "", label: (b.querySelector(".rad-label") || b).innerText.trim().replace(/\s+/g, " "),
      empty: b.classList.contains("rad-empty"), count: (b.querySelector(".rad-count") || {}).textContent || null, outer: b.classList.contains("rad-out") })));
  }
  // 円形メニュー（またはその他の輪）から項目を選び、結果のパネルが落ち着くまで待つ
  async choose(action, waitMs) {
    const t0 = Date.now();
    const inOuter = await this.p.$(`#radial-menu .rad-out[data-action="${action}"]`);
    if (inOuter) { const more = await this.p.$("#radial-menu .rad-more"); if (more) { await more.click(); await this.p.waitForTimeout(250); } }
    const b = await this.p.$(`#radial-menu .rad-item[data-action="${action}"]`);
    if (!b) return null;
    await b.click();
    // 結果が落ち着く: lastDispatch が終わり、パネル本文が1秒変わらない
    await this.p.waitForFunction(() => !window.__dx.lastDispatch || window.__dx.lastDispatch.outcome !== "running", null, { timeout: waitMs }).catch(() => {});
    let prev = "", stable = 0;
    for (let i = 0; i < Math.ceil(waitMs / 500) && stable < 2; i++) {
      const cur = await this.p.evaluate(() => [...document.querySelectorAll(".gp-body")].map(x => x.innerText).join("|").length + ":" + (window.__dx.G ? window.__dx.G.rootQ + window.__dx.G.nodes.length : ""));
      stable = cur === prev ? stable + 1 : 0; prev = cur; await this.p.waitForTimeout(500);
    }
    return this.rec("choose", { action }, t0);
  }
  async closePanels() { await this.p.evaluate(() => document.querySelectorAll(".gp-x").forEach(x => x.click())); await this.p.keyboard.press("Escape").catch(() => {}); await this.p.waitForTimeout(200); }
  save() { fs.writeFileSync(path.join(this.out, `${this.id}.json`), JSON.stringify(this.steps, null, 1)); }
}
module.exports = { Driver };
