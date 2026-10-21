// sim2 オラクル（判定器）。観測（observe.js）と、外部の一次資料（Wikipedia・Wiktionary）の取得結果だけから決める。
// LLM の印象では判定しない（Claim 2/3: 迎合・自己選好）。各オラクルは変異で FAIL を出せることを selftest で確かめる。
"use strict";
const norm = (s) => String(s || "").replace(/\s+/g, " ").trim();
function sentences(t) { return norm(t).split(/(?<=[。．！？.!?])\s*|⏎|\n/).map(x => x.trim()).filter(x => x.length >= 8); }
function shingles(t, k = 6) { const s = norm(t).replace(/\s/g, ""); const out = new Set(); for (let i = 0; i + k <= s.length; i++) out.add(s.slice(i, i + k)); return out; }
function jaccard(a, b) { const A = shingles(a), B = shingles(b); if (!A.size || !B.size) return 0; let i = 0; for (const x of A) if (B.has(x)) i++; return i / (A.size + B.size - i); }

// O-dup: 別の見方のパネルと中身がほぼ同じ（写し）。同じ語に対する異なる操作の結果どうしで比べる
function duplicate(panelText, others, th = 0.6) {
  let best = { sim: 0, with: null };
  for (const o of others) { const s = jaccard(panelText, o.text); if (s > best.sim) best = { sim: s, with: o.label }; }
  return { fail: best.sim >= th, ...best };
}
// O-tmpl: 定型文率。異なる3語以上の結果に同じ文が現れたら、その文は語に固有でない（テンプレート）
class TemplateIndex {
  constructor() { this.seen = new Map(); }
  add(term, text) { for (const s of new Set(sentences(text))) { if (!this.seen.has(s)) this.seen.set(s, new Set()); this.seen.get(s).add(term); } }
  ratio(text, minTerms = 3) { const ss = sentences(text); if (!ss.length) return 0;
    const chars = ss.reduce((n, s) => n + s.length, 0); const t = ss.filter(s => (this.seen.get(s) || new Set()).size >= minTerms).reduce((n, s) => n + s.length, 0);
    return t / chars; }
}
// O-spec: 関係のパネルが、2つの語の両方を同じ文の中で述べているか（なぜつながるかの根拠）
function specificity(text, a, b) {
  const forms = (x) => { const n = String(x || "").replace(/[（(][^）)]*[）)]\s*$/, "").trim(); const f = [n]; const last = n.split(/[・\s]/).pop(); if (last && last.length >= 2) f.push(last); return f; };
  const fa = forms(a), fb = forms(b);
  return sentences(text).filter(s => fa.some(x => s.includes(x)) && fb.some(x => s.includes(x))).length;
}
// O-id: 対象の同一性。入力語と、実際に使われた記事（転送・検索の差し替え）を一次資料で照合する
function identity(word, wp) {
  // wp: { title, redirectedFrom, missing, p31 } … ja.wikipedia の実取得
  if (!wp) return { status: "unknown" };
  if (wp.missing) return { status: "no-article" };
  if (wp.title !== word) return { status: "redirected", to: wp.title };
  return { status: "exact" };
}
// O-dead: 行き止まり。移った先の地図の語（分岐・言語ノードを除く）が5未満で、戻り道の提示も無い
function deadEnd(obs) {
  if (!obs.map) return { fail: false };
  const k = obs.map.kinds || {}; const n = obs.map.n - (k.domain || 0) - (k.language || 0);
  return { fail: n < 5 && !obs.smallMap && !(obs.decomp || []).length, n };
}
// O-new: 新規性。パネルに出た固有の語（カタカナ・漢字・ラテン文字の語）のうち、地図と前のパネルに無かったもの
function novelty(text, known) {
  const toks = (norm(text).match(/[ァ-ヶー・]{3,}|[一-鿿]{2,}|[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'-]{3,}/g) || []);
  const fresh = [...new Set(toks)].filter(t => !known.has(t));
  return { n: fresh.length, sample: fresh.slice(0, 8) };
}
// 語そのものを伏せ字にした文（語だけが違う定型文を同じ文として数えるため）
function normTerms(text, terms) {
  let t = String(text || "");
  const forms = [];
  for (const x of terms || []) { if (!x) continue; const n = String(x).replace(/[（(][^）)]*[）)]\s*$/, "").trim(); forms.push(n); const last = n.split(/[・\s]/).pop(); if (last && last.length >= 2) forms.push(last); }
  forms.sort((a, b) => b.length - a.length).forEach(f => { t = t.split(f).join("〈語〉"); });
  return t;
}
module.exports = { normTerms, duplicate, TemplateIndex, specificity, identity, deadEnd, novelty, jaccard, sentences };
