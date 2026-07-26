/* Dialexis frontend. No framework, no build step (GENESIS axiom 7: anyone can
   rebuild this). API keys live ONLY in this browser's localStorage (axiom 5/6). */

const LANG = window.DIALEXIS_LANG || "en";
const T = {
  ja: { retrieved: "取得", live: "ライブ", cached: "キャッシュ", error: "情報源エラー（沈黙させず表示）",
        loading: "世界中の学術情報源へ照会中…", none: "結果なし", del: "削除", open: "開く",
        newHits: "新着", checked: "照会完了", aiNotice: "AIが生成した未確認情報です。出典確認まで「未確認」として扱ってください。",
        needKey: "この機能のLevel 2にはAPIキーが必要です（設定→鍵スイッチ盤）。Level 0の結果を表示しています。",
        saved: "保存しました（このブラウザ内のみ）", cleared: "削除しました",
        oppLit: "対立文献の候補（OpenAlex検索）", works: "関連論文・著作", authors: "研究者", books: "無料で読める原典（Gutenberg）",
        wikisource: "Wikisource原典", notable: "主要著作", influenced: "影響を受けた", occupation: "職業", born: "生", died: "没",
        argNone: "まだ論証はありません。前提P1..Pnと結論Cを組み立て、妥当性と健全性を別々に評価してください。",
        premise: "前提", premiseAdd: "前提を追加", hidden: "隠れた前提", therefore: "ゆえに",
        voice: "声", validity: "妥当性", soundness: "健全性", locator: "ロケータ", suggestHidden: "隠れた前提をAIに提案",
        premisePh: "前提の文", locatorPh: "ロケータ（例: Republic 514a）",
        voice_author: "著者", voice_commentator: "注釈者", voice_self: "自分",
        validity_valid: "妥当", validity_invalid: "不当", validity_unassessed: "未評価",
        soundness_sound: "健全", soundness_unsound: "不健全", soundness_unassessed: "未評価" },
  en: { retrieved: "retrieved", live: "live", cached: "cached", error: "source error (shown, not silenced)",
        loading: "Querying live scholarly sources…", none: "No results", del: "Delete", open: "Open",
        newHits: "new", checked: "checked", aiNotice: "AI-generated, unverified. Treat as unverified until sources are checked.",
        needKey: "Level 2 needs an API key (Settings → Key Switchboard). Showing Level 0.",
        saved: "Saved (this browser only)", cleared: "Cleared",
        oppLit: "Candidate opposing literature (OpenAlex)", works: "Related works & papers", authors: "Scholars", books: "Free primary texts (Gutenberg)",
        wikisource: "Wikisource texts", notable: "Notable works", influenced: "Influenced by", occupation: "Occupation", born: "Born", died: "Died",
        argNone: "No arguments yet. Build premises P1..Pn and a conclusion C, then assess validity and soundness separately.",
        premise: "Premise", premiseAdd: "Add premise", hidden: "Hidden premise", therefore: "Therefore",
        voice: "Voice", validity: "Validity", soundness: "Soundness", locator: "Locator", suggestHidden: "Suggest hidden premises (AI)",
        premisePh: "Premise text", locatorPh: "Locator (e.g. Republic 514a)",
        voice_author: "Author", voice_commentator: "Commentator", voice_self: "Researcher",
        validity_valid: "Valid", validity_invalid: "Invalid", validity_unassessed: "Unassessed",
        soundness_sound: "Sound", soundness_unsound: "Unsound", soundness_unassessed: "Unassessed" }
}[LANG] || {};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" }, ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

function llmConfig() {
  const provider = localStorage.getItem("dialexis_provider") || "";
  if (!provider) return null;
  return { provider, model: localStorage.getItem("dialexis_model") || "",
           key: localStorage.getItem("dialexis_key") || "" };
}

function freshBadge(res) {
  if (!res) return "";
  if (res.error) return `<span class="badge err" title="${esc(res.error)}">${T.error}</span>`;
  const mode = res.cached ? T.cached : T.live;
  return `<span class="badge ${res.cached ? "" : "live"}">${esc(res.source)} · ${mode} · ${T.retrieved} ${esc(res.retrieved_at)}</span>`;
}

/* ---------- explore ---------- */

let ADOPT_PID = null, ADOPT_ITEMS = [];

async function loadAdoptPicker() {
  const el = $("adopt-picker");
  if (!el) return;
  try {
    const ps = await api("/api/projects");
    if (!ps.length) {
      el.innerHTML = `<span class="srcline">${LANG === "ja"
        ? "採用先プロジェクトがありません（研究デスクで作成すると、探索結果を接地ノードとして採用できます）"
        : "No project yet — create one in the research desk to adopt findings as grounded nodes."}</span>`;
      return;
    }
    el.innerHTML = `<label class="srcline">${LANG === "ja" ? "採用先プロジェクト" : "Adopt into"}:
      <select id="adopt-pid"></select></label>`;
    $("adopt-pid").innerHTML = ps.map(p =>
      `<option value="${p.id}">${esc(p.title)}</option>`).join("");
    ADOPT_PID = Number(ps[0].id);
    $("adopt-pid").addEventListener("change", e => { ADOPT_PID = Number(e.target.value); });
  } catch (e) { /* offline / no projects: adopt buttons simply stay hidden */ }
}

// One-click bridge from a live search result to a grounded node (source +
// provenance + retrieved_at). This closes the search↔desk quality gap: the
// automated quality of explore flows into the research graph with zero manual
// re-entry. Buttons render only when an adopt-target project is chosen.
function adoptBtn(title, url, source, retrieved) {
  if (!ADOPT_PID || !title) return "";
  const i = ADOPT_ITEMS.push({ title, url: url || "", source: source || "", retrieved: retrieved || "" }) - 1;
  return ` <button type="button" class="small adopt-btn" data-i="${i}">${LANG === "ja" ? "＋採用" : "+ adopt"}</button>`;
}

async function adoptItem(i, btn) {
  const it = ADOPT_ITEMS[i];
  if (!it || !ADOPT_PID) return;
  btn.disabled = true;
  try {
    await api(`/api/projects/${ADOPT_PID}/nodes`, { method: "POST", body: {
      type: "source", title: it.title, body: "",
      confidence: "unverified", origin: "external",
      provenance: [{ source_name: it.source, source_url: it.url, retrieved_at: it.retrieved, quote: "" }] } });
    btn.textContent = LANG === "ja" ? "採用済 ✓" : "adopted ✓";
    btn.classList.add("done");
  } catch (e) { btn.disabled = false; btn.textContent = "✗"; }
}

function exploreInit(q) {
  loadAdoptPicker();
  const res = $("explore-results");
  if (res) res.addEventListener("click", e => {
    const b = e.target.closest(".adopt-btn");
    if (b) adoptItem(Number(b.dataset.i), b);
  });
  if (q && q.trim()) exploreRun(q.trim());
}

async function exploreRun(q) {
  $("explore-status").innerHTML = `<p class="muted">${T.loading}</p>`;
  $("explore-results").innerHTML = "";
  ADOPT_ITEMS = [];
  try {
    const d = await api(`/api/explore?q=${encodeURIComponent(q)}&lang=${LANG}`);
    $("explore-status").innerHTML = "";
    let html = "";

    if (d.entity && !d.entity.error) {
      const e = d.entity.data;
      const wiki = d.wikipedia && !d.wikipedia.error ? d.wikipedia.data : null;
      html += `<div class="card"><h2>${esc(e.label)} <span class="muted">${esc(e.description)}</span></h2>
        ${freshBadge(d.entity)} ${wiki ? freshBadge(d.wikipedia) : ""}
        ${wiki && wiki.thumbnail ? `<img src="${esc(wiki.thumbnail)}" style="float:right;max-width:120px;border-radius:4px;margin-left:1rem">` : ""}
        ${wiki ? `<p>${esc(wiki.extract)}</p><p class="srcline"><a href="${esc(wiki.url)}" target="_blank">Wikipedia (${esc(wiki.lang)})</a></p>` : ""}
        <table class="plain">
          ${e.claims.born?.length ? `<tr><th>${T.born}</th><td>${esc(e.claims.born.join(", "))}</td></tr>` : ""}
          ${e.claims.died?.length ? `<tr><th>${T.died}</th><td>${esc(e.claims.died.join(", "))}</td></tr>` : ""}
          ${e.claims.occupation?.length ? `<tr><th>${T.occupation}</th><td>${esc(e.claims.occupation.slice(0, 8).join(", "))}</td></tr>` : ""}
          ${e.claims.notable_work?.length ? `<tr><th>${T.notable}</th><td>${esc(e.claims.notable_work.join(" / "))}</td></tr>` : ""}
          ${e.claims.influenced_by?.length ? `<tr><th>${T.influenced}</th><td>${esc(e.claims.influenced_by.join(", "))}</td></tr>` : ""}
        </table>
        ${Object.keys(e.wikisource_urls || {}).length ? `<p class="srcline">${T.wikisource}:
          ${Object.entries(e.wikisource_urls).map(([lg, u]) => `<a href="${esc(u)}" target="_blank">${esc(lg)}</a>`).join(" · ")}</p>` : ""}
        <p class="srcline"><a href="${esc(e.url)}" target="_blank">Wikidata ${esc(e.qid)}</a></p>
      </div>`;
    }

    if (d.resolved_term && d.resolved_term !== d.query) {
      html += `<p class="srcline">${esc(d.query)} → <b>${esc(d.resolved_term)}</b>
        ${LANG === "ja" ? "として照会" : "used to query"}</p>`;
    }

    // 原語基底: original-language-first. The base sits ABOVE the (English) SEP
    // card — for a German/Greek concept the original is the ground, the English
    // entry is itself a translation. Curated seed, sourced, honest about scope.
    const oc = d.orig_cluster;
    if (oc) {
      const jp = LANG === "ja";
      const liveTerms = Object.entries(oc.live_orig_labels || {})
        .map(([lg, v]) => `${esc(v)} <span class="srcline">(${esc(lg)})</span>`).join(" / ");
      html += `<div class="card orig-card">
        <h2>🔤 ${jp ? "原語の基底（翻訳で埋没する区別）" : "Original-language base (distinctions the translation loses)"}</h2>
        <p class="muted">${jp
          ? "日本語の一語の背後に、原語では別語がある。ここが全ての基底です。訳語で検索・思考する前に、原語の区別を先に見てください。"
          : "Behind one Japanese word stand several original-language terms. This is the base — see the original distinctions before searching or reasoning in translation."}</p>
        <p class="srcline">${jp ? "同一の日本語に埋没する語" : "collapse into"}:
          ${oc.collapsed_japanese.map(w => `「${esc(w)}」`).join(" ")}
          · <span class="badge">${esc(oc.tradition)}</span></p>
        <table class="plain orig-lemmas">
          <tr><th>${jp ? "原語" : "Original"}</th><th>${jp ? "語義" : "Gloss"}</th><th>${jp ? "埋没先" : "→ JP"}</th><th></th></tr>
          ${oc.lemmas.map(l => `<tr>
            <td><b lang="${esc(l.lang)}">${esc(l.lemma)}</b><br><span class="srcline">${esc(l.polarity || "")}</span></td>
            <td>${esc(l.gloss)}</td>
            <td class="srcline">${(l.collapses_to || []).map(w => esc(w)).join("・")}</td>
            <td class="srcline">${esc(l.source || "")}</td></tr>`).join("")}
        </table>
        <p class="srcline">${jp ? "一次源" : "Primary source"}: ${esc(oc.primary_source)}</p>
        ${liveTerms ? `<p class="srcline">${jp ? "Wikidataの原語ラベル（ライブ）" : "Wikidata original labels (live)"}: ${liveTerms}</p>` : ""}
        <p class="orig-note">${esc(oc.note)}</p>
        <p class="srcline">${jp ? "確度" : "Confidence"} — ${jp ? "原語の実在" : "terms"}: <b>${esc(oc.confidence_terms)}</b> ／ ${jp ? "日本語への埋没" : "collapse"}: <b>${esc(oc.confidence_collapse)}</b>.
          <span class="muted">${jp
            ? "編者による検証済みシード（網羅ではない・原語の実在と語義は独語Wikipedia等で確認済／埋没の整理は要一次確認）。"
            : "Curated verified seed (not exhaustive; term existence checked against German Wikipedia; the collapse mapping needs primary-source confirmation)."}</span></p>
      </div>`;
    }

    // SEP orientation — the real entry point: debate map + monograph bibliography.
    const se = d.sep_entry;
    if (se && !se.error && se.data) {
      const s = se.data;
      const jp = LANG === "ja";
      html += `<div class="card sep-card">
        <h2>📘 ${jp ? "オリエンテーション（SEP）" : "Orientation (SEP)"}
          ${freshBadge(se)}</h2>
        <p><a href="${esc(s.url)}" target="_blank"><b>${esc(s.title)}</b></a>
           <span class="srcline">${esc(s.pubinfo)}</span></p>
        <p class="muted">${jp
          ? "哲学研究はここから始まります。下は論争の地図（各節が主要な立場・論点）と、そのまま使える文献リスト（書籍中心＝一般の論文検索が取りこぼす層）です。"
          : "Where philosophers actually start. Below is the map of the debate (each section is a position/move) and a ready-to-mine bibliography (monograph-heavy — what article search misses)."}</p>
        <h3>${jp ? "論争の地図" : "Map of the debate"}</h3>
        <ol class="debatemap">${s.sections.map(x =>
          `<li>${esc(x.replace(/^\d+(\.\d+)*\.?\s*/, ""))}</li>`).join("")}</ol>
        <h3>${jp ? "文献（SEP書誌・検証済み）" : "Bibliography (SEP, curated)"}
          <span class="srcline">${s.bibliography.length}</span></h3>
        <ul class="biblist">${s.bibliography.slice(0, 12).map(b =>
          `<li>${esc(b.text)}${b.url ? ` <a href="${esc(b.url)}" target="_blank">↗</a>` : ""}${adoptBtn(b.text, b.url, "SEP", se.retrieved_at)}</li>`).join("")}</ul>
        ${s.related.length ? `<p class="srcline">${jp ? "関連項目" : "Related"}:
          ${s.related.slice(0, 10).map(r =>
            `<a href="/explore?q=${encodeURIComponent(r.title)}&lang=${LANG}">${esc(r.title)}</a>`).join(" · ")}</p>` : ""}
      </div>`;
    } else if (d.sep_search && !d.sep_search.error && !(d.sep_search.data || []).length) {
      html += `<p class="muted">${LANG === "ja"
        ? "この語のSEP項目は見つかりませんでした（下は補助的な情報源です）。"
        : "No SEP entry for this term (sources below are supplementary)."}</p>`;
    }

    const jp = LANG === "ja";

    // Japanese-tradition orientation (NDL + CiNii). For a Japanese subject the
    // real first-hint bibliography is the National Diet Library (books by/about)
    // and CiNii (scholarship) — the SEP is Anglophone and would return nothing
    // useful. Stand on these specialist indexes, then expand secondarily.
    const nd = d.japanese_scholarship, cn = d.cinii;
    const ndHits = nd && !nd.error ? (nd.data || []) : [];
    const cnHits = cn && !cn.error ? (cn.data || []) : [];
    if (ndHits.length || cnHits.length || (nd && nd.error) || (cn && cn.error)) {
      html += `<div class="card"><h2>📚 ${jp ? "日本語圏の学術（NDL・CiNii）" : "Japanese scholarship (NDL · CiNii)"}
        ${nd ? freshBadge(nd) : ""} ${cn ? freshBadge(cn) : ""}</h2>
        <p class="muted">${jp
          ? "日本思想の一次ヒントは国立国会図書館サーチ（本人の著作・研究書）とCiNii（論文・書籍）。既存の専門索引を起点に、ここから2次・3次へ広げます。"
          : "For a Japanese subject the first-hint bibliography is NDL Search (works by/about) and CiNii (scholarship). Start from these specialist indexes and expand outward."}</p>`;
      if (ndHits.length) {
        html += `<h3>${jp ? "著作・研究書（NDLサーチ）" : "Books by/about (NDL)"}</h3>
          <ul class="biblist">${ndHits.map(b => `<li>
            ${b.url ? `<a href="${esc(b.url)}" target="_blank">${esc(b.title)}</a>` : esc(b.title)}
            — ${esc((b.creators || []).join(" / "))}${b.publisher ? ` · ${esc(b.publisher)}` : ""}${b.year ? ` · ${esc(b.year)}` : ""}${adoptBtn(b.title, b.url, "NDL", nd.retrieved_at)}</li>`).join("")}</ul>`;
      }
      if (cnHits.length) {
        html += `<h3>${jp ? "論文・書籍（CiNii Research）" : "Articles & books (CiNii)"}</h3>
          <ul class="biblist">${cnHits.map(w => `<li>
            ${w.type ? `<span class="badge">${esc(w.type)}</span> ` : ""}
            ${w.url ? `<a href="${esc(w.url)}" target="_blank">${esc(w.title)}</a>` : esc(w.title)}
            — ${esc((w.creators || []).join(" / "))}${w.year ? ` · ${esc(w.year)}` : ""}${adoptBtn(w.title, w.url, "CiNii", cn.retrieved_at)}</li>`).join("")}</ul>`;
      }
      html += "</div>";
    }

    // Primary texts & editions — public-domain texts the reader can open now,
    // plus a pointer to standard-locator citation. This is core to real work.
    const wsUrls = (d.entity && !d.entity.error) ? (d.entity.data.wikisource_urls || {}) : {};
    const pt = d.primary_texts;
    const hasGutenberg = pt && !pt.error && !pt.skipped && (pt.data || []).length;
    const hasWikisource = Object.keys(wsUrls).length;
    if (hasGutenberg || hasWikisource) {
      html += `<div class="card"><h2>📜 ${jp ? "一次資料・原典" : "Primary texts"}</h2>`;
      if (hasWikisource) {
        html += `<p class="srcline">Wikisource: ${Object.entries(wsUrls).map(([lg, u]) =>
          `<a href="${esc(u)}" target="_blank">${esc(lg)}</a>`).join(" · ")}</p>`;
      }
      if (hasGutenberg) {
        html += pt.data.map(b => `<div class="result-item">
          <a href="${esc(b.read_url)}" target="_blank"><b>${esc(b.title)}</b></a>
          <div class="srcline">${esc(b.authors.join(", "))} · ${esc(b.languages.join(","))} · Project Gutenberg${adoptBtn(b.title, b.read_url, "Project Gutenberg", pt.retrieved_at)}</div></div>`).join("");
      }
      html += `<p class="srcline">${jp
        ? "引用は標準ロケータで（Plato=Stephanus 514a / Aristotle=Bekker 1094a1 / Kant=A/B）。該当箇所への解決は今後の版で統合します。"
        : "Cite by standard locator (Plato=Stephanus 514a / Aristotle=Bekker / Kant=A/B)."}</p></div>`;
    }

    // Japanese translations (邦訳) — for a JP user the primary text is the
    // translated book, and WHICH translator matters (translation method).
    const jt = d.japanese_translations;
    if (jt && !jt.error && !jt.skipped && (jt.data || []).length) {
      html += `<div class="card"><h2>📖 ${jp ? "邦訳（日本語訳）" : "Japanese translations"}
        ${freshBadge(jt)}</h2>
        <p class="srcline">${jp
          ? "国立国会図書館サーチより。哲学研究では「どの訳者の訳か」が決定的です（訳語の選択が解釈を左右する）。著作ごとに訳者・出版社・年を示します。"
          : "From NDL Search, grouped by work. In philosophy the choice of translator is decisive; translator/publisher/year shown."}</p>`;
      html += jt.data.map(g => `<div class="jt-work">
        <h3>${esc(g.work)}</h3>
        <ul class="biblist">${g.editions.map(b => `<li>
          ${b.url ? `<a href="${esc(b.url)}" target="_blank">${esc(b.title)}</a>` : esc(b.title)}
          — ${esc(b.creators.join(" / "))}${b.publisher ? ` · ${esc(b.publisher)}` : ""}${b.year ? ` · ${esc(b.year)}` : ""}</li>`).join("")}</ul>
      </div>`).join("");
      html += "</div>";
    }

    // Recent scholarship — clearly secondary and honest: strictly filtered so it
    // shows real hits or nothing (never trout-fishing papers). The literature
    // that matters is the SEP bibliography above.
    const rs = d.recent_scholarship;
    if (rs && !rs.error && (rs.data || []).length) {
      html += `<div class="card"><h2>🔬 ${jp ? "最近の論文（補助）" : "Recent articles (supplementary)"}
        ${freshBadge(rs)}</h2>
        <p class="srcline">${jp
          ? "OpenAlex由来。哲学の主要文献は上のSEP書誌です。ここは近年の論文の補助的手がかりに限ります。"
          : "From OpenAlex; the core literature is the SEP bibliography above."}</p>`;
      html += rs.data.slice(0, 8).map(w => `<div class="result-item">
        <a href="${esc(w.url)}" target="_blank"><b>${esc(w.title)}</b></a>
        <span class="muted">(${esc(w.year ?? "?")})</span>
        ${w.open_access ? '<span class="badge live">OA</span>' : ""}
        <div class="srcline">${esc(w.authors.join(", "))}${w.cited_by_count ? ` · cited ${w.cited_by_count}` : ""}${adoptBtn(w.title, w.url, "OpenAlex", rs.retrieved_at)}</div></div>`).join("");
      html += "</div>";
    }

    $("explore-results").innerHTML = html;
  } catch (e) {
    $("explore-status").innerHTML = `<p class="badge err">${esc(e.message)}</p>`;
  }
}

/* ---------- desk ---------- */

async function deskInit() {
  const list = await api("/api/projects");
  $("project-list").innerHTML = list.length
    ? `<div class="card"><table class="plain">` + list.map(p => `<tr>
        <td><a href="/project/${p.id}?lang=${LANG}"><b>${esc(p.title)}</b></a>
            <div class="srcline">${esc(p.question || "")}</div></td>
        <td>${p.node_count} nodes</td>
        <td class="srcline">${esc(p.updated_at)}</td>
        <td><button class="small secondary" onclick="deskDelete(${p.id})">${T.del}</button></td>
      </tr>`).join("") + "</table></div>"
    : `<p class="muted">${T.none}</p>`;
}

async function deskCreate() {
  const title = $("np-title").value.trim();
  if (!title) return;
  const r = await api("/api/projects", { method: "POST",
    body: { title, question: $("np-question").value.trim() } });
  location.href = `/project/${r.id}?lang=${LANG}`;
}

async function deskDelete(id) {
  if (!confirm("Delete?")) return;
  await api(`/api/projects/${id}`, { method: "DELETE" });
  deskInit();
}

async function counterRun() {
  const claim = $("counter-claim").value.trim();
  if (!claim) return;
  $("counter-results").innerHTML = `<p class="muted">${T.loading}</p>`;
  const d = await api("/api/counter", { method: "POST",
    body: { claim, lang: LANG, llm: llmConfig() } });
  let html = "";
  if (d.level2) {
    html += d.level2.error
      ? `<p class="badge err">${esc(d.level2.error)}</p>`
      : `<div class="notice-ai"><span class="badge ai">AI · ${esc(d.level2.provider)}</span>
         ${T.aiNotice}</div><pre class="llm">${esc(d.level2.text)}</pre>`;
  } else {
    html += `<p class="muted">${T.needKey}</p>`;
  }
  html += d.level0.map(p => `<details class="result-item"><summary><b>${esc(p.perspective)}</b></summary>
    <ul>${p.questions.map(q => `<li>${esc(q)}</li>`).join("")}</ul></details>`).join("");
  if (d.opposing_literature_search && !d.opposing_literature_search.error) {
    html += `<h3>${T.oppLit}</h3>` + freshBadge(d.opposing_literature_search) +
      d.opposing_literature_search.data.map(w => `<div class="result-item srcline">
        <a href="${esc(w.url)}" target="_blank">${esc(w.title)}</a> (${esc(w.year ?? "?")})</div>`).join("");
  }
  $("counter-results").innerHTML = html;
}

/* ---------- project graph ---------- */

let PROJ = null, PROJ_G = null, PROJ_PROV = {};
// Type accent color for the structure view's left border: meaning-bearing type
// coding in a readable list, NOT a decorative dot cloud (the removed cose graph).
const NODE_COLORS = { question: "#2e5c7a", claim: "#7a5c2e", evidence: "#2f7d4f",
  counterclaim: "#b91c1c", uncertainty: "#b45309", interpretation: "#6d28d9",
  decision: "#1d2430", note: "#6b7280", source: "#0e7490" };

async function projectInit(pid) {
  PROJ = pid;
  await projRefresh();
  forkRender();
}

async function projRefresh() {
  const g = await api(`/api/projects/${PROJ}/graph`);
  const provByNode = {};
  g.provenance.forEach(p => (provByNode[p.node_id] ||= []).push(p));
  PROJ_G = g; PROJ_PROV = provByNode;

  for (const selId of ["e-src", "e-dst"]) {
    $(selId).innerHTML = g.nodes.map(n =>
      `<option value="${n.id}">[${n.type}] ${esc(n.title.slice(0, 40))}</option>`).join("");
  }
  const nodeOpts = g.nodes.map(n =>
    `<option value="${n.id}">[${n.type}] ${esc(n.title.slice(0, 40))}</option>`).join("");
  if ($("arg-cnode")) $("arg-cnode").innerHTML = `<option value="">— ${T.arg_conclusion || "conclusion node"} —</option>` + nodeOpts;
  argRender(g.arguments || []);

  renderStructure(g, provByNode);
}

// Structure-bearing view of the research process — replaces the decorative
// force-graph (a "hairball that carries no priority/status/freshness", per the
// tool-UX research and 半田様's critique). Nodes are grouped by type in a reading
// order; each shows confidence, provenance count and outgoing relations. Decisions
// (reading-stance choices) and counterclaims (objections) are first-class rows,
// not dots. Click/Enter opens the node detail.
const STRUCT_ORDER = ["question", "decision", "claim", "counterclaim", "evidence",
  "interpretation", "uncertainty", "source", "note"];

function renderStructure(g, provByNode) {
  const box = $("structure");
  if (!box) return;
  const jp = LANG === "ja";
  if (!g.nodes.length) {
    box.innerHTML = `<div class="card"><h2>${jp ? "研究過程の構造" : "Research structure"}</h2>
      <p class="muted">${jp
        ? "まだノードがありません。探索（/explore）で見つけた出典を「採用」するか、下の「読解の構え」を選ぶと、ここに研究過程が構造として現れます。"
        : "No nodes yet. Adopt sources from /explore, or choose a reading stance below — the research process appears here as structure."}</p></div>`;
    return;
  }
  const titles = {};
  g.nodes.forEach(n => { titles[n.id] = n.title; });
  const edgeBySrc = {};
  g.edges.forEach(e => (edgeBySrc[e.src] ||= []).push(e));
  let html = `<div class="card"><h2>${jp ? "研究過程の構造" : "Research structure"}</h2>`;
  for (const t of STRUCT_ORDER) {
    const group = g.nodes.filter(n => n.type === t);
    if (!group.length) continue;
    const col = NODE_COLORS[t] || "#888";
    html += `<h3 class="struct-h" style="border-left-color:${col}">${esc(T["type_" + t] || t)}
      <span class="muted">${group.length}</span></h3>`;
    for (const n of group) {
      const provs = provByNode[n.id] || [];
      const rels = (edgeBySrc[n.id] || []).map(e =>
        `→ <i>${esc(e.rel)}</i> → ${esc(titles[e.dst] || e.dst)}`).join(" · ");
      html += `<div class="struct-node" style="border-left-color:${col}"
          tabindex="0" role="button" onclick="projShowNodeById(${n.id})"
          onkeydown="if(event.key==='Enter')projShowNodeById(${n.id})">
        <span class="badge conf-${n.confidence}">${esc(n.confidence)}</span>
        <b>${esc(n.title)}</b>
        ${n.origin === "ai" ? `<span class="badge ai">ai</span>` : ""}
        ${provs.length ? `<span class="srcline">· ${provs.length} ${jp ? "出典" : "src"}</span>` : ""}
        ${rels ? `<div class="srcline struct-rel">${rels}</div>` : ""}
      </div>`;
    }
  }
  html += `</div>`;
  box.innerHTML = html;
}

function projShowNodeById(id) {
  const n = ((PROJ_G && PROJ_G.nodes) || []).find(x => x.id === id);
  if (n) projShowNode(n, PROJ_PROV || {});
}

function projShowNode(n, provByNode) {
  const provs = (provByNode[n.id] || []).map(p => `<li class="srcline">
    ${esc(p.source_name)} <a href="${esc(p.source_url)}" target="_blank">${esc(p.source_url)}</a>
    · ${T.retrieved} ${esc(p.retrieved_at)}${p.quote ? ` — “${esc(p.quote)}”` : ""}</li>`).join("");
  $("node-detail").style.display = "block";
  $("node-detail").innerHTML = `
    <h2>${esc(n.title)}</h2>
    <p><span class="badge">${n.type}</span>
       <span class="badge conf-${n.confidence}">${n.confidence}</span>
       <span class="badge ${n.origin === "ai" ? "ai" : ""}">${n.origin}</span>
       <span class="badge">${n.status}</span></p>
    ${n.body ? `<p>${esc(n.body)}</p>` : ""}
    <ul>${provs}</ul>
    <div class="formrow">
      <select id="nd-status">
        ${["open", "adopted", "held", "rejected"].map(s =>
          `<option value="${s}" ${s === n.status ? "selected" : ""}>${s}</option>`).join("")}
      </select>
      <button class="small" onclick="projSetStatus(${n.id})">OK</button>
      <button class="small secondary" onclick="projDelNode(${n.id})">${T.del}</button>
    </div>`;
}

async function projSetStatus(nid) {
  await api(`/api/nodes/${nid}`, { method: "PATCH", body: { status: $("nd-status").value } });
  projRefresh();
}

async function projDelNode(nid) {
  if (!confirm("Delete node?")) return;
  await api(`/api/nodes/${nid}`, { method: "DELETE" });
  $("node-detail").style.display = "none";
  projRefresh();
}

async function projAddNode() {
  const title = $("n-title").value.trim();
  if (!title) return;
  const prov = [];
  if ($("n-src-name").value.trim() || $("n-src-url").value.trim()) {
    prov.push({ source_name: $("n-src-name").value.trim(),
                source_url: $("n-src-url").value.trim() });
  }
  await api(`/api/projects/${PROJ}/nodes`, { method: "POST", body: {
    type: $("n-type").value, title, body: $("n-body").value,
    confidence: $("n-conf").value, origin: $("n-origin").value, provenance: prov } });
  $("n-title").value = ""; $("n-body").value = "";
  $("n-src-name").value = ""; $("n-src-url").value = "";
  projRefresh();
}

async function projAddEdge() {
  await api(`/api/projects/${PROJ}/edges`, { method: "POST", body: {
    src: $("e-src").value, dst: $("e-dst").value, rel: $("e-rel").value } });
  projRefresh();
}

/* ---------- fork 4: reading-stance decision surface (PoC-1) ----------
   The pivotal juncture: choosing the reading stance = choosing the
   problématique = fixing the reach → the reachable conclusions. So it is a
   decision-surface (options with reach/bias/blind-spot/outcome), not a picker,
   and the analytic/historical GATE swaps the option SET (an analytic user must
   not be shown a flat continental menu). The choice is recorded as a grounded
   `decision` node — no schema change (decision ∈ NODE_TYPES). */
const STANCES = {
  historical: [
    { k: "系譜学", by: "Foucault", reach: "権力/知の生成・主体の構成・実践の偶然性", bias: "制度・実践を前景化", blind: "著者の意図・論証の妥当性は射程外", out: "批判的・系譜学的貢献", rec: true },
    { k: "概念史", by: "Koselleck", reach: "概念の意味変容・鞍の時代・対抗概念", bias: "意味構造の長期変動", blind: "個別論証の妥当性は中心化しない", out: "歴史的・統合的貢献" },
    { k: "文脈主義", by: "Cambridge / Skinner", reach: "著者が『何をしていたか』・言語行為・論争文脈", bias: "同時代の意図を前景化", blind: "長期の意味変動・非意図的構造", out: "解釈的貢献（アナクロニズム回避）" },
  ],
  analytic: [
    { k: "論証分析", by: "argument reconstruction", reach: "前提/結論の分離・推論の妥当性・隠れた前提", bias: "論理構造を前景化", blind: "歴史的生成・社会的文脈は射程外", out: "批判的・解釈的貢献", rec: true },
    { k: "概念分析", by: "conceptual analysis", reach: "必要十分条件・直観・反例", bias: "非歴史的な本質", blind: "概念の歴史的変容", out: "解釈的貢献" },
    { k: "思考実験", by: "thought experiment", reach: "直観の喚起・可能性空間・反例構成", bias: "論理的可能性を前景化", blind: "経験的妥当性・歴史的現実", out: "批判的・創造的貢献" },
  ],
};
let FORK_BRANCH = "historical";

function forkRender() {
  const box = $("fork-stance");
  if (!box) return;
  const jp = LANG === "ja";
  const gate = (b, label) =>
    `<button type="button" class="gatebtn${FORK_BRANCH === b ? " on" : ""}" onclick="forkGate('${b}')">${label}</button>`;
  const cards = STANCES[FORK_BRANCH].map((s, i) => `
    <div class="fcard${s.rec ? " rec" : ""}">
      <h4>${esc(s.k)} <span class="muted">${esc(s.by)}</span>${s.rec ? ` <span class="recbadge">${jp ? "推奨・上書き可" : "suggested"}</span>` : ""}</h4>
      <div class="facet"><span class="fk">${jp ? "射程" : "reach"}</span>${esc(s.reach)}</div>
      <div class="facet"><span class="fk">${jp ? "偏重" : "bias"}</span>${esc(s.bias)}</div>
      <div class="facet blind"><span class="fk">${jp ? "死角" : "blind"}</span>${esc(s.blind)}</div>
      <div class="facet out"><span class="fk">${jp ? "結末" : "outcome"}</span>${esc(s.out)}</div>
      <button type="button" class="small" onclick="forkPick('${FORK_BRANCH}',${i})">${jp ? "この構えを選ぶ" : "choose this stance"}</button>
    </div>`).join("");
  box.innerHTML = `
    <h2>${jp ? "岐路：読解の構え" : "Fork: reading stance"}</h2>
    <div class="osf">${jp
      ? "これらが「読み方」の道。選ぶのは<b>貴方</b>。道具は地図を描き、答えない。構えの選択は射程・方向・結論を規定する重要な場面です。"
      : "These are the paths of reading. <b>You</b> choose; the tool maps, it does not answer. The stance governs reach, direction and conclusion."}</div>
    <div class="gate-row"><span class="srcline">${jp ? "まず一つ：概念をどう見るか" : "First: how do you see concepts"}</span>
      ${gate("analytic", jp ? "非歴史的な実体として" : "ahistorical entities")}
      ${gate("historical", jp ? "歴史的な産物として" : "historically produced")}</div>
    <div class="fcards">${cards}</div>
    <div class="llm-meta">${jp
      ? "🤖 <b>LLMのメタ認知</b>：このメニューは私の学習データの偏り（大陸系・英語圏寄り）を帯び、貴方を分析的伝統や非西洋の読解から逸らしうる。私が挙げていない構えを疑ってください。"
      : "🤖 <b>LLM metacognition</b>: this menu carries my training bias; I may steer you away from analytic or non-Western readings. Doubt the stances I did not list."}</div>
    <p class="srcline">${jp
      ? "選ぶと「判断（decision）」ノードとして根拠つきで研究グラフに残ります。選択自体を論考したい場合は "
      : "Your choice is recorded as a grounded decision node. To deliberate the choice itself, use "}<a href="/deepsearch">/deepsearch</a></p>`;
}

function forkGate(b) { FORK_BRANCH = b; forkRender(); }

async function forkPick(branch, i) {
  const s = STANCES[branch][i];
  const gateLabel = branch === "historical" ? "歴史的な産物として" : "非歴史的な実体として";
  const body = `ゲート：${gateLabel}\n射程：${s.reach}\n偏重：${s.bias}\n死角：${s.blind}\n結末：${s.out}`;
  await api(`/api/projects/${PROJ}/nodes`, { method: "POST", body: {
    type: "decision", title: `読解の構え：${s.k}（${s.by}）`, body,
    confidence: "unverified", origin: "human", status: "adopted" } });
  projRefresh();
}

/* ---------- argument reconstruction (E1-E5) ---------- */

const VOICES = ["author", "commentator", "self"];
const VALIDITY = ["valid", "invalid", "unassessed"];
const SOUNDNESS = ["sound", "unsound", "unassessed"];
let ARG_CACHE = {};  // aid -> ordered premise ids, for up/down reordering

function optList(kinds, prefix, selected) {
  return kinds.map(k =>
    `<option value="${k}"${k === selected ? " selected" : ""}>${esc(T[prefix + "_" + k] || k)}</option>`).join("");
}

async function argAdd() {
  const title = $("arg-title").value.trim();
  if (!title) return;
  await api(`/api/projects/${PROJ}/arguments`, { method: "POST", body: {
    title, conclusion: $("arg-conclusion").value.trim(),
    conclusion_node_id: $("arg-cnode").value ? Number($("arg-cnode").value) : null } });
  $("arg-title").value = ""; $("arg-conclusion").value = "";
  projRefresh();
}

function argRender(args) {
  ARG_CACHE = {};
  if (!args.length) { $("arg-list").innerHTML = `<p class="muted">${T.argNone}</p>`; return; }
  $("arg-list").innerHTML = args.map(a => {
    ARG_CACHE[a.id] = a.premises.map(p => p.id);
    const prems = a.premises.map((p, i) => `<div class="result-item">
      <b>P${i + 1}.</b> ${esc(p.text)}
      ${p.hidden ? `<span class="badge">${T.hidden}</span>` : ""}
      <span class="srcline">(${T.voice}: ${esc(T["voice_" + p.voice] || p.voice)})${p.locator ? ` — ${esc(p.locator)}` : ""}
        ${p.source_url ? ` <a href="${esc(p.source_url)}" target="_blank">↗</a>` : ""}</span>
      <button class="small secondary" onclick="argMove(${a.id},${p.id},-1)">↑</button>
      <button class="small secondary" onclick="argMove(${a.id},${p.id},1)">↓</button>
      <button class="small secondary" onclick="argDelPremise(${p.id})">×</button>
    </div>`).join("");
    return `<div class="card" style="border-left:3px solid #7a5c2e">
      <h3>${esc(a.title)}</h3>
      ${prems}
      <div class="formrow" style="align-items:center;gap:.5rem;flex-wrap:wrap">
        <input id="ap-text-${a.id}" placeholder="${T.premisePh}" style="flex:1;min-width:180px">
        <label class="srcline"><input type="checkbox" id="ap-hidden-${a.id}"> ${T.hidden}</label>
        <select id="ap-voice-${a.id}">${optList(VOICES, "voice", "author")}</select>
        <input id="ap-loc-${a.id}" placeholder="${T.locatorPh}" style="width:180px">
        <button class="small" onclick="argAddPremise(${a.id})">${T.premiseAdd}</button>
      </div>
      <p style="margin:.4rem 0"><b>${T.therefore} ∴ C.</b> ${esc(a.conclusion)}</p>
      <div class="formrow" style="gap:1rem;flex-wrap:wrap">
        <label class="srcline">${T.validity}:
          <select onchange="argSetValidity(${a.id},this.value)">${optList(VALIDITY, "validity", a.validity)}</select></label>
        <label class="srcline">${T.soundness}:
          <select onchange="argSetSoundness(${a.id},this.value)">${optList(SOUNDNESS, "soundness", a.soundness)}</select></label>
        <button class="small secondary" onclick="argSuggestHidden(${a.id})">${T.suggestHidden}</button>
        <button class="small secondary" onclick="argDel(${a.id})">${T.del}</button>
      </div>
      <div id="arg-ai-${a.id}"></div>
    </div>`;
  }).join("");
}

async function argAddPremise(aid) {
  const text = $(`ap-text-${aid}`).value.trim();
  if (!text) return;
  await api(`/api/arguments/${aid}/premises`, { method: "POST", body: {
    text, hidden: $(`ap-hidden-${aid}`).checked ? 1 : 0,
    voice: $(`ap-voice-${aid}`).value, locator: $(`ap-loc-${aid}`).value.trim() } });
  projRefresh();
}

async function argDelPremise(prid) {
  await api(`/api/premises/${prid}`, { method: "DELETE" });
  projRefresh();
}

async function argMove(aid, prid, dir) {
  const order = (ARG_CACHE[aid] || []).slice();
  const i = order.indexOf(prid);
  const j = i + dir;
  if (i < 0 || j < 0 || j >= order.length) return;
  [order[i], order[j]] = [order[j], order[i]];
  await api(`/api/arguments/${aid}/premises/reorder`, { method: "POST", body: { order } });
  projRefresh();
}

async function argSetValidity(aid, validity) {
  await api(`/api/arguments/${aid}`, { method: "PATCH", body: { validity } });
}

async function argSetSoundness(aid, soundness) {
  await api(`/api/arguments/${aid}`, { method: "PATCH", body: { soundness } });
}

async function argDel(aid) {
  if (!confirm("Delete argument?")) return;
  await api(`/api/arguments/${aid}`, { method: "DELETE" });
  projRefresh();
}

async function argSuggestHidden(aid) {
  const out = $(`arg-ai-${aid}`);
  const cfg = llmConfig();
  if (!cfg) { out.innerHTML = `<p class="muted">${T.needKey}</p>`; return; }
  out.innerHTML = `<p class="muted">${T.loading}</p>`;
  try {
    const d = await api(`/api/arguments/${aid}/suggest_hidden`, { method: "POST",
      body: { lang: LANG, llm: cfg } });
    if (d.level2 && d.level2.error) { out.innerHTML = `<p class="badge err">${esc(d.level2.error)}</p>`; return; }
    out.innerHTML = `<div class="notice-ai"><span class="badge ai">AI · ${esc(d.level2.provider)}</span>
      ${T.aiNotice}</div><pre class="llm">${esc(d.level2.text)}</pre>`;
  } catch (e) {
    out.innerHTML = `<p class="badge err">${esc(e.message)}</p>`;
  }
}

/* ---------- watches ---------- */

async function watchesInit() {
  const ws = await api("/api/watches");
  $("watch-list").innerHTML = ws.length ? ws.map(w => `<div class="card">
    <h2>${esc(w.label)} <span class="badge">${w.kind}</span>
        ${w.unseen ? `<span class="badge live">${w.unseen} ${T.newHits}</span>` : ""}</h2>
    <p class="srcline">last checked: ${esc(w.last_checked || "—")}
       ${w.openalex_id ? ` · <a href="${esc(w.openalex_id)}" target="_blank">OpenAlex</a>` : ""}</p>
    <button class="small" onclick="watchRun(${w.id})">▶ ${T.checked.replace("完了", "")}</button>
    <button class="small" onclick="watchHits(${w.id})">${T.open}</button>
    <button class="small secondary" onclick="watchDel(${w.id})">${T.del}</button>
    <div id="watch-hits-${w.id}"></div>
  </div>`).join("") : `<p class="muted">${T.none}</p>`;
}

async function watchAdd() {
  const label = $("w-label").value.trim();
  if (!label) return;
  await api("/api/watches", { method: "POST",
    body: { label, kind: $("w-kind").value } });
  $("w-label").value = "";
  watchesInit();
}

async function watchRun(id) {
  const el = $(`watch-hits-${id}`);
  el.innerHTML = `<p class="muted">${T.loading}</p>`;
  const r = await api(`/api/watches/${id}/run`, { method: "POST" });
  el.innerHTML = `<p class="srcline">${T.checked}: +${r.new_count} ${T.newHits}
    ${r.errors.length ? `<span class="badge err">${esc(r.errors.join("; "))}</span>` : ""}</p>`;
  watchesInit();
}

async function watchHits(id) {
  const hits = await api(`/api/watches/${id}/hits`);
  $(`watch-hits-${id}`).innerHTML = hits.length ? `<table class="plain">` +
    hits.map(h => `<tr><td><a href="${esc(h.url)}" target="_blank">${esc(h.title)}</a></td>
      <td>${esc(h.year)}</td><td><span class="badge">${esc(h.source)}</span></td>
      <td class="srcline">${esc(h.found_at)}</td></tr>`).join("") + "</table>"
    : `<p class="muted">${T.none}</p>`;
}

async function watchDel(id) {
  if (!confirm("Delete watch?")) return;
  await api(`/api/watches/${id}`, { method: "DELETE" });
  watchesInit();
}

/* ---------- reading levels ---------- */

function levelsInit() {
  $("lv-concept").addEventListener("change", () => {
    $("lv-custom").style.display =
      $("lv-concept").value === "__custom__" ? "block" : "none";
  });
}

async function levelsShow() {
  const sel = $("lv-concept").value;
  const level = $("lv-level").value;
  const out = $("levels-result");
  out.innerHTML = `<p class="muted">${T.loading}</p>`;
  try {
    if (sel === "__custom__") {
      const concept = $("lv-custom").value.trim();
      if (!concept) return;
      const cfg = llmConfig();
      if (!cfg) { out.innerHTML = `<p class="muted">${T.needKey}</p>`; return; }
      const d = await api("/api/levels/llm", { method: "POST",
        body: { concept, level, lang: LANG, llm: cfg } });
      out.innerHTML = `<div class="notice-ai"><span class="badge ai">AI · ${esc(d.provider)}</span>
        ${T.aiNotice}</div><pre class="llm">${esc(d.text)}</pre>`;
    } else {
      const d = await api(`/api/levels?concept=${encodeURIComponent(sel)}`);
      out.innerHTML = `<p><span class="badge">${esc(d.origin)}</span>
        <b>${esc(sel)}</b> <span class="muted">(${esc(d.en_label)})</span></p>
        <pre class="llm">${esc(d.levels[level] || "—")}</pre>`;
    }
  } catch (e) {
    out.innerHTML = `<p class="badge err">${esc(e.message)}</p>`;
  }
}

/* ---------- deep-search prompt generator ---------- */

let DS_SERVICES = [];
function deepsearchInit(services) {
  DS_SERVICES = services || [];
  const sel = $("ds-service");
  const upd = () => {
    const s = DS_SERVICES.find(x => x.id === sel.value);
    $("ds-note").textContent = s ? ((LANG === "ja" ? s.note_ja : s.note_en)
      + (s.free_ja && LANG === "ja" ? " ／ 無料: " + s.free_ja : "")) : "";
  };
  sel.addEventListener("change", upd);
  upd();
  // prefill the topic from ?q= so the graph's "深掘り探索プロンプト" action lands
  // with the word already filled in (fixes the empty deep-search page).
  const q = new URLSearchParams(location.search).get("q");
  if (q && $("ds-topic")) $("ds-topic").value = q;
}

async function deepsearchRun() {
  const topic = $("ds-topic").value.trim();
  if (!topic) return;
  const out = $("ds-result");
  out.innerHTML = `<p class="muted">${T.loading}</p>`;
  const d = await api("/api/deepsearch", { method: "POST", body: {
    topic, goal: $("ds-goal").value.trim(), service: $("ds-service").value,
    lang: LANG, llm: llmConfig() } });

  let dsN = 0;
  const block = (label, text, aiBadge) => {
    const id = "ds-pre-" + (++dsN);
    return `<div class="card">
      <h2>${label} ${aiBadge || ""}
        <button class="small" onclick="dsCopy('${id}', this)">${LANG === "ja" ? "コピー" : "Copy"}</button></h2>
      <pre class="llm" id="${id}">${esc(text)}</pre></div>`;
  };
  let html = "";
  if (d.level2 && !d.level2.error) {
    html += block(LANG === "ja" ? "生成プロンプト（AI精緻化）" : "Prompt (AI-refined)",
      d.level2.text, `<span class="badge ai">AI · ${esc(d.level2.provider)}</span>`);
  } else if (d.level2 && d.level2.error) {
    html += `<p class="badge err">${esc(d.level2.error)}</p>`;
  }
  html += block(LANG === "ja" ? "生成プロンプト（そのまま使用可）" : "Prompt (ready to use)", d.level0);
  html += `<p class="muted">${LANG === "ja"
    ? "上をコピーし、選んだサービス（" + esc(($("ds-service").selectedOptions[0] || {}).text || "")
      + "）に貼り付けてください。設定でAPIキーを入れると、サービス別に精緻化した版も生成されます。"
    : "Copy the above and paste into your chosen service. Add an API key in Settings for a service-tuned refinement."}</p>`;
  out.innerHTML = html;
}

function copyText(text) {
  // navigator.clipboard needs a secure context (HTTPS/localhost); this site is
  // served over plain HTTP, where it is undefined. Fall back to the legacy
  // textarea + execCommand path, which works on HTTP.
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  }
  return new Promise((resolve, reject) => {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.top = "-1000px";
    ta.setAttribute("readonly", "");
    document.body.appendChild(ta);
    ta.select();
    ta.setSelectionRange(0, text.length);
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    document.body.removeChild(ta);
    ok ? resolve() : reject(new Error("copy failed"));
  });
}

function dsCopy(id, btn) {
  const el = document.getElementById(id);
  if (!el) return;
  const done = (msg) => {
    const o = btn.textContent;
    btn.textContent = msg;
    setTimeout(() => (btn.textContent = o), 1500);
  };
  copyText(el.textContent)
    .then(() => done(LANG === "ja" ? "コピー済" : "Copied"))
    .catch(() => {
      // Last resort: select the text so the user can copy manually (Ctrl+C).
      const r = document.createRange();
      r.selectNodeContents(el);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(r);
      done(LANG === "ja" ? "選択しました→Ctrl+C" : "Selected → Ctrl+C");
    });
}

/* ---------- settings ---------- */

async function settingsInit() {
  $("s-provider").value = localStorage.getItem("dialexis_provider") || "";
  $("s-model").value = localStorage.getItem("dialexis_model") || "";
  $("s-key").value = localStorage.getItem("dialexis_key") || "";
  const ledger = await api("/api/ledger");
  $("ledger").innerHTML = ledger.length ? `<table class="plain">
    <tr><th>time</th><th>provider</th><th>task</th></tr>` +
    ledger.map(l => `<tr><td class="srcline">${esc(l.ts)}</td>
      <td>${esc(l.provider)} ${esc(l.model || "")}</td><td>${esc(l.task)}</td></tr>`).join("")
    + "</table>" : `<p class="muted">${T.none}</p>`;
}

function settingsSave() {
  localStorage.setItem("dialexis_provider", $("s-provider").value);
  localStorage.setItem("dialexis_model", $("s-model").value);
  localStorage.setItem("dialexis_key", $("s-key").value);
  $("settings-msg").textContent = T.saved;
}

function settingsClear() {
  ["dialexis_provider", "dialexis_model", "dialexis_key"]
    .forEach(k => localStorage.removeItem(k));
  settingsInit();
  $("settings-msg").textContent = T.cleared;
}

/* ---------- 原語による探求 (origin) — 言葉が先にありきの階層 ---------- */
function originInit(q) {
  const cb = $("origin-newtab");
  if (cb) {
    cb.checked = localStorage.getItem("origin_newtab") === "1";
    cb.addEventListener("change", () => {
      localStorage.setItem("origin_newtab", cb.checked ? "1" : "0");
      const box = $("origin-results");   // re-render so existing links pick up the choice
      if (box && box.dataset.q) originRun(box.dataset.q);
    });
  }
  const fit = $("graph-fit");
  if (fit) fit.addEventListener("click", () => graphFit());
  const res = $("origin-results");
  if (res && !res._dimBound) {
    res._dimBound = 1;
    res.addEventListener("click", (e) => {
      const b = e.target.closest(".dim");
      if (b && DIMS) { gDimAct(DIMS[Number(b.dataset.i)]); return; }
      const th = e.target.closest(".origin-thinker");   // 概念を立てた思想家→経歴・著作・情報源
      if (th) { e.preventDefault(); gAuthorInvestigate(th.dataset.name, th.dataset.name); return; }
      const di = e.target.closest(".origin-discourse");  // この概念の言説を広く調べる（外部・多言語）
      if (di) { e.preventDefault(); gExtPanel(di.dataset.q); return; }
    });
  }
  if (q) { const t = originClaim(q); originGraph(q, t); originRun(q, t); }
}

// UNIVERSAL rule: selecting a word (a node / an in-page link) makes THAT word the
// new subject — the whole exploration (search box, cards, graph) is rebuilt FRESH
// from it. No data from a previously-entered word is reused. Optionally, after the
// fresh cards render, scroll to a specific card of THIS word (opts.scrollTo).
async function originRecenter(q, opts) {
  const tok = originClaim(q);            // this selection becomes THE subject (single source of truth)
  const inp = document.querySelector('.searchbox input[name=q]');
  if (inp) inp.value = q;
  // graph と cards を同じトークンで並行再構築。両方 settle して初めて再中心「完了」。
  await Promise.all([originGraph(q, tok), originRun(q, tok)]);
  if (originStale(tok)) return;          // 別の語に上書きされた＝この古い語のためにスクロール/確定しない
  const id = opts && opts.scrollTo;
  const el = id && $(id);
  if (el) { el.scrollIntoView({ behavior: "smooth", block: "center" }); return; }
  if (id) {                 // the requested aspect doesn't exist for THIS word — honest
    const wc = document.querySelector(".word-card");
    if (wc) wc.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// Attribute string for an internal word link — a new tab (keeping the current
// result) or in-place, per the user's choice (#6: don't silently overwrite).
function originLinkAttr() {
  return (localStorage.getItem("origin_newtab") === "1")
    ? ' target="_blank" rel="noopener"' : "";
}

/* ---------- 言語空間の重力グラフ（canvas force-directed・階層/展開/俯瞰） ---------- */
const GKIND = { word: "#1d2430", domain: "#2e5c7a", original: "#7a5c2e",
  author: "#b45309", work: "#9a7b52", language: "#4a7fa5",
  related: "#3a7d44", opposite: "#a03b3b", appdomain: "#5b4b8a", application: "#8a6d3b" };
let G_lenscache = {};   // 遅延レンズ（応用/使用例/時代変遷）の 語+レンズ ごとの取得キャッシュ
let G = null, DIMS = null, G_raw = null, G_lens = "all";

// ── レンズ（複数の地図）: 同じ言葉・同じ取得データを、いくつもの見方で見せる（半田様提案
// 2026-07-26）。追加取得ゼロ——グラフの型付きノード(word/original/author/work/language/
// domain)を型で絞り、その語を中心に再投影するだけ。「専門/一般の1分岐」を最初に見せる代わりに、
// ユーザーが見方を選べる＝知的好奇心の間口を広げる（老若男女・並ぶことの喜び・セレンディピティ）。
const LENSES = [
  { key: "all", label: "俯瞰（すべて）", en: "Overview", kinds: null,
    cap: "この言葉をめぐる全体像。意味の領域・原語・世界の言語・思想家までを一度に。" },
  { key: "thinkers", label: "思想家と著作", en: "Thinkers & works", kinds: ["author", "work"],
    cap: "この概念を立て、論じた人と著作。名前をクリックで経歴・著作・情報源へ。" },
  { key: "original", label: "原語と語源", en: "Original terms", kinds: ["original"],
    cap: "訳語の背後にある原語・埋没した複数の語。クリックでその原語空間へ。" },
  { key: "languages", label: "世界の言語", en: "World languages", kinds: ["language"],
    cap: "この概念を担う世界の言語と、その語。既知の数言語に縮めない。" },
  { key: "relations", label: "類語・対義（星座）", en: "Related & opposite", kinds: ["related", "opposite"],
    cap: "近い/類する概念（緑）と、対立・区別される概念（赤）の星座。クリックでその概念へ。思考を横に広げる。" },
  { key: "domains", label: "意味の領域", en: "Fields of meaning", kinds: ["domain"],
    cap: "一般の意味／専門・思想／世界の言語という、意味の大きな分かれ。" },
  { key: "spheres", label: "文化圏", en: "Cultural spheres", mode: "region",
    cap: "欧／漢字圏／日本など、どの文化圏の言語がこの概念を担うかで束ねる。重力場が変わる。" },
  { key: "applications", label: "応用・波及", en: "Applications", mode: "lazy-graph", endpoint: "/api/applications",
    cap: "この概念を主題とする作品を分野別に（文学・芸術・映画・歴史）。応用と波及。クリックでその作品語へ。" },
  { key: "usage", label: "使用例・引用", en: "Usage", mode: "cards", endpoint: "/api/usage",
    cap: "この語が実テキスト（学術）で実際にどう使われたか。出典つきの引用カード（賛否は判定しない）。" },
  { key: "era", label: "時代・変遷", en: "Over time", mode: "timeline", endpoint: "/api/timeline",
    cap: "原語がいつ現れ・広まり・衰退し・再評価されたか（Google Books Ngram・書物コーパス）。" },
];

// 文化圏（言語コード→圏）。欧/漢字圏/日本/その他。同じ概念でもどの圏を基準にするかで見え方が変わる。
const REGION_EU = ["de", "fr", "en", "es", "it", "la", "grc", "el", "ru", "nl", "pt", "pl",
  "sv", "da", "no", "nb", "fi", "uk", "cs", "ro", "hu", "tr", "he", "ar", "fa", "ca", "eo"];
function regionOf(code) {
  if (code === "ja") return "日本";
  if (["zh", "ko", "vi", "yue", "wuu", "za"].includes(code)) return "漢字圏";
  if (REGION_EU.includes(code)) return "欧";
  return "その他";
}
// 言語ノードを文化圏で束ねる再投影（語→圏→言語）。追加取得なし（G_rawの言語ノードから）。
function applyRegion(d) {
  const root = d.nodes.find(n => n.kind === "word");
  const langs = d.nodes.filter(n => n.kind === "language");
  const nodes = root ? [{ ...root, layer: 1 }] : [];
  const edges = [], regs = {};
  langs.forEach(n => {
    const reg = regionOf((n.id.split(":")[1] || ""));
    const rid = `reg:${reg}`;
    if (!regs[reg]) { regs[reg] = 1; nodes.push({ id: rid, label: reg, kind: "appdomain", layer: 2, weight: 2.2 }); if (root) edges.push({ from: root.id, to: rid, strength: 1.2 }); }
    nodes.push({ ...n, layer: 3 }); edges.push({ from: rid, to: n.id, strength: 0.5 });
  });
  return { query: d.query, note: "文化圏で束ねる: どの言語圏がこの概念を担うか。欧／漢字圏／日本／その他。", nodes, edges };
}

// 選んだレンズで生データを再投影（俯瞰=そのまま／それ以外=語を中心にその型だけの星型）
function applyLens(d, key) {
  const L = LENSES.find(x => x.key === key) || LENSES[0];
  if (!L.kinds) return d;
  const root = d.nodes.find(n => n.kind === "word");
  const leaves = d.nodes.filter(n => L.kinds.includes(n.kind));
  const nodes = [];
  if (root) nodes.push({ ...root, layer: 1 });
  leaves.forEach(n => nodes.push({ ...n, layer: 2 }));
  const edges = root ? leaves.map(n => ({ from: root.id, to: n.id, strength: 0.9 })) : [];
  return { query: d.query, note: L.cap, nodes, edges };
}

function lensLeafCount(d, L) {
  return L.kinds ? d.nodes.filter(n => L.kinds.includes(n.kind)).length : d.nodes.length;
}

function renderLensChips(d) {
  const el = $("graph-lens"); if (!el) return;
  const jp = LANG === "ja";
  el.innerHTML = LENSES.map(L => {
    const n = lensLeafCount(d, L), empty = L.kinds && n === 0;
    return `<button type="button" class="lens-chip${L.key === G_lens ? " on" : ""}${empty ? " empty" : ""}" data-k="${L.key}"${empty ? " disabled" : ""}>${esc(jp ? L.label : L.en)}${L.kinds ? ` <span class="lens-n">${n}</span>` : ""}</button>`;
  }).join("");
  el.querySelectorAll(".lens-chip:not(.empty)").forEach(c =>
    c.addEventListener("click", () => applyLensBuild(c.dataset.k)));
}

function setActiveChip(key) {
  const el = $("graph-lens");
  if (el) el.querySelectorAll(".lens-chip").forEach(c => c.classList.toggle("on", c.dataset.k === key));
}
// グラフ描画（canvas）と専用描画（#graph-alt: カード/チャート）の切替。altに入る時は描画ループを止める。
function showCanvas() { const c = $("origin-graph"), a = $("graph-alt"); if (c) c.style.display = "block"; if (a) { a.style.display = "none"; a.innerHTML = ""; } }
function showAlt() { const c = $("origin-graph"), a = $("graph-alt"); if (G && G.raf) { cancelAnimationFrame(G.raf); G.running = false; } if (c) c.style.display = "none"; if (a) a.style.display = "block"; }

async function applyLensBuild(key) {
  if (!G_raw) return;
  G_lens = key; setActiveChip(key);
  const L = LENSES.find(x => x.key === key) || LENSES[0];
  const jp = LANG === "ja", note = $("graph-note");
  const setNote = t => { if (note) note.textContent = t; };
  const mode = L.mode || "filter";
  if (mode === "filter") { showCanvas(); const pd = applyLens(G_raw, key); setNote(pd.note || G_raw.note || ""); gBuild(pd); return; }
  if (mode === "region") { showCanvas(); const pd = applyRegion(G_raw); setNote(pd.note); gBuild(pd); return; }
  // 遅延レンズ（応用/使用例/時代変遷）: エンドポイントを取得（語ごとキャッシュ）して描画
  const ck = `${L.key}:${G_raw.query}`;
  let data = G_lenscache[ck];
  if (!data) {
    setNote((jp ? "読み込み中… " : "loading… ") + L.cap);
    if (mode === "cards" || mode === "timeline") { showAlt(); $("graph-alt").innerHTML = `<p class="lens-empty">${jp ? "読み込み中…" : "loading…"}</p>`; }
    try { data = await api(`${L.endpoint}?q=${encodeURIComponent(G_raw.query)}&lang=${LANG}`); G_lenscache[ck] = data; }
    catch (e) { if (G_lens === key) { setNote((jp ? "取得に失敗: " : "failed: ") + esc(String(e.message || e))); if (mode !== "lazy-graph") { showAlt(); $("graph-alt").innerHTML = `<p class="lens-empty">${jp ? "取得に失敗しました。" : "failed."}</p>`; } } return; }
    if (G_lens !== key) return;   // 読み込み中に別レンズへ切替＝古い結果を捨てる（状態一貫性）
  }
  setNote(data.note || L.cap);
  if (mode === "lazy-graph") {
    if (!data.nodes || data.nodes.length <= 1) { showAlt(); $("graph-alt").innerHTML = `<p class="lens-empty">${esc(data.note || (jp ? "この語ではこのレンズのデータがありません。" : "no data."))}</p>`; return; }
    showCanvas(); gBuild(data);
  } else if (mode === "cards") { showAlt(); renderUsageCards(data); }
  else if (mode === "timeline") { showAlt(); renderTimeline(data); }
}

// 使用例・引用: 出典つきの引用カード群（賛否は判定しない・中立）
function renderUsageCards(data) {
  const a = $("graph-alt"); if (!a) return; const jp = LANG === "ja";
  const cards = data.cards || [];
  if (!cards.length) { a.innerHTML = `<p class="lens-empty">${esc(data.note || (jp ? "用例が見つかりませんでした。" : "no usage."))}</p>`; return; }
  a.innerHTML = `<div class="usage-cards">` + cards.map(c => {
    const meta = [(c.authors || []).join(", "), c.year, c.venue].filter(Boolean).map(esc).join(" · ");
    const link = c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${jp ? "出典を開く" : "open"}</a>` : "";
    return `<div class="ucard"><div class="ut">${esc(c.title)}</div><div class="um">${meta}${meta && link ? " · " : ""}${link}<br><span class="srcline">${jp ? "用いた語" : "term"}: ${esc(c.term)}</span></div></div>`;
  }).join("") + `</div>`;
}

// 時代・変遷: 原語の通時頻度を"川/時間軸"で（Google Books Ngram）
function renderTimeline(data) {
  const a = $("graph-alt"); if (!a) return; const jp = LANG === "ja";
  const series = data.series || [];
  if (!series.length) { a.innerHTML = `<p class="lens-empty">${esc(data.note || (jp ? "通時頻度が取得できませんでした。" : "no series."))}</p>`; return; }
  const cols = ["#b45309", "#2e5c7a", "#3a7d44", "#a03b3b"];
  a.innerHTML = `<div class="tl-wrap"><div class="tl-legend">${series.map((s, i) =>
    `<span><i class="tl-sw" style="background:${cols[i % cols.length]}"></i>${esc(s.lang)}：${esc(s.term)}（${jp ? "最盛" : "peak"} ${s.peak_year}）</span>`).join("")}</div><canvas id="tl-canvas"></canvas></div>`;
  drawTimeline($("tl-canvas"), series, cols);
}
function drawTimeline(cv, series, cols) {
  if (!cv) return;
  const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  cv.width = W * dpr; cv.height = H * dpr; const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  const padL = 40, padR = 14, padT = 14, padB = 26, y0 = 1800, y1 = 2019;
  let maxv = 0; series.forEach(s => s.values.forEach(v => { if (v > maxv) maxv = v; })); if (maxv <= 0) maxv = 1;
  const X = yr => padL + (yr - y0) / (y1 - y0) * (W - padL - padR);
  const Y = v => H - padB - (v / maxv) * (H - padT - padB);
  ctx.strokeStyle = "rgba(0,0,0,0.12)"; ctx.lineWidth = 1; ctx.fillStyle = "#888"; ctx.font = "11px system-ui,sans-serif"; ctx.textAlign = "center";
  for (let yr = 1800; yr <= 2000; yr += 50) { ctx.beginPath(); ctx.moveTo(X(yr), padT); ctx.lineTo(X(yr), H - padB); ctx.stroke(); ctx.fillText(String(yr), X(yr), H - padB + 16); }
  series.forEach((s, i) => {
    const col = cols[i % cols.length], n = s.values.length;
    const path = () => { s.values.forEach((v, k) => { const x = X(y0 + (y1 - y0) * k / (n - 1)), y = Y(v); k ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); };
    ctx.beginPath(); path(); ctx.lineTo(X(y1), H - padB); ctx.lineTo(X(y0), H - padB); ctx.closePath();
    ctx.globalAlpha = 0.13; ctx.fillStyle = col; ctx.fill(); ctx.globalAlpha = 1;
    ctx.beginPath(); path(); ctx.strokeStyle = col; ctx.lineWidth = 1.6; ctx.stroke();
    const pi = Math.round((s.peak_year - y0) / (y1 - y0) * (n - 1));
    ctx.fillStyle = col; ctx.beginPath(); ctx.arc(X(s.peak_year), Y(s.values[pi] || 0), 3, 0, 7); ctx.fill();
  });
}

// ── 探索の単一真実源（root-A: 状態一貫性・要求ID・古い応答の破棄・再中心完了条件） ──
// 半田様の「他の語のデータが流用される／動いたり動かなかったり」の機構は意味ドリフトでなく
// 非同期の状態管理だった。現在の主語(q)と単調増加トークンを唯一の真実源とし、主語を変える
// 操作は originClaim(q) でトークンを取得、各非同期処理は await の後 originStale(tok) を確認
// してから DOM/グラフ(G)/パネルを書く。これにより、遅れて届いた古い語の応答が新しい語の画面を
// 上書きする競合（stale-response）を構造的に排除する。同じ語＋同じメニュー＝どこでも同じ作用（P11）。
const OZ = { q: null, qid: null, token: 0 };
function originClaim(q) { OZ.q = q; OZ.qid = null; return ++OZ.token; }
function originStale(tok) { return tok !== OZ.token; }
function originCurrent(q) { return OZ.q === q; }

// dispatch a dimension-of-inquiry entry to its data path (or 整備中 note).
function gDimAct(dm) {
  if (!dm) return;
  const jp = LANG === "ja", act = dm.act || "";
  if (dm.status === "soon") {
    gPanel(dm.label, `<p class="muted">${jp ? "この次元は整備中です。路（構造）は用意されており、データ源が接続され次第ここに現れます。内容はベンチマークと違ってよく、広さ・深さ・次元の多様性の路を保証します。" : "This dimension is being built; the path exists and fills in as its source connects."}</p>`);
    return;
  }
  if (act.startsWith("scroll:")) {
    const el = $(act.slice(7));
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    else gPanel(dm.label, `<p class="muted">${jp ? "この探索ではこの次元の内容が見つかりませんでした。" : "Not available for this word."}</p>`);
  } else if (act.startsWith("colloc:")) gColloc(act.slice(7), "de");
  else if (act.startsWith("counter:")) gCounter(act.slice(8));
  else if (act === "graph") { const w = $("origin-graph-wrap"); if (w) w.scrollIntoView({ behavior: "smooth", block: "start" }); }
  else gPanel(dm.label, `<p class="muted">${jp ? "準備中" : "coming"}</p>`);
}

// 批判・異論の次元 — reuse the existing counterargument engine (steelman
// perspectives + real opposing literature). Benchmark's『批判・異論』dimension.
async function gCounter(claim) {
  const jp = LANG === "ja";
  const p = gPanel((jp ? "批判・異論：" : "Critique: ") + claim, `<p class="muted">${jp ? "読み込み中…" : "loading…"}</p>`);
  let d;
  try { d = await api("/api/counter", { method: "POST", body: { claim, lang: LANG } }); }
  catch (e) { p.querySelector(".gp-body").innerHTML = `<p class="badge err">${esc(String(e.message || e))}</p>`; return; }
  let html = `<p class="muted">${jp ? "この語・主張を、複数の視点から検証する問い（steelman）。加えて、この主張に関連する実在の文献を示します（賛成か反対かは判定していません）。" : "Counter-questions from multiple perspectives, plus related real literature (stance NOT judged)."}</p>`;
  (d.level0 || []).forEach(pv => { html += `<h4 class="gp-h">${esc(pv.perspective)}</h4><ul class="gp-ul">${(pv.questions || []).map(q => `<li>${esc(q)}</li>`).join("")}</ul>`; });
  const lit = d.opposing_literature_search;
  if (lit && !lit.error && lit.data && lit.data.length) {
    html += `<h4 class="gp-h">${jp ? "関連文献（OpenAlex・実データ／賛否は未判定）" : "Related literature (OpenAlex; stance not judged)"}</h4><ul class="gp-ul">`
      + lit.data.slice(0, 6).map(w => `<li>${esc(w.title)} <span class="srcline">${esc((w.authors || []).slice(0, 2).join(", "))}</span></li>`).join("") + "</ul>";
  }
  p.querySelector(".gp-body").innerHTML = html;
}

async function originGraph(q, tok) {
  if (tok == null) tok = originClaim(q);   // standalone caller (e.g. 全体に戻す) claims its own token
  const wrap = $("origin-graph-wrap"), cv = $("origin-graph");
  if (!wrap || !cv) return;
  let d;
  try { d = await api(`/api/origin/graph?q=${encodeURIComponent(q)}&lang=${LANG}`); }
  catch (e) { if (!originStale(tok)) wrap.style.display = "none"; return; }
  if (originStale(tok)) return;            // 古い語の応答＝現在の語のグラフを壊さない（stale破棄）
  if (d.qid) OZ.qid = d.qid;               // 既存qidをノードから単一真実源へ伝播（後段のP11強化用）
  if (!d.nodes || d.nodes.length <= 1) { wrap.style.display = "none"; return; }
  wrap.style.display = "block";
  G_raw = d;
  // 選んでいたレンズをこの語でも保つ（見方の連続性）。ただし新しい語でそのフィルタが空なら俯瞰へ。
  const cur = LENSES.find(x => x.key === G_lens) || LENSES[0];
  if (cur.kinds && lensLeafCount(d, cur) === 0) G_lens = "all";
  renderLensChips(d);
  const cur2 = LENSES.find(x => x.key === G_lens) || LENSES[0];
  if ((cur2.mode || "filter") === "filter") {
    showCanvas();
    const pd = applyLens(d, G_lens);
    const note = $("graph-note"); if (note) note.textContent = pd.note || d.note || "";
    gBuild(pd);
  } else {
    applyLensBuild(G_lens);   // region/応用/使用例/時代変遷は新しい語で再描画（遅延取得は語ごとキャッシュ）
  }
}

function gBuild(d) {
  const cv = $("origin-graph");
  const W = cv.clientWidth, H = cv.clientHeight, dpr = window.devicePixelRatio || 1;
  cv.width = W * dpr; cv.height = H * dpr;
  const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const cx = W / 2, cy = H / 2, idx = {};
  const nodes = d.nodes.map((n, i) => { idx[n.id] = i; return { ...n }; });
  const maxLayer = Math.max(...nodes.map(n => n.layer));
  nodes.forEach(n => {
    const R = (n.layer - 1) * Math.min(W, H) / (maxLayer + 1);
    const peers = nodes.filter(m => m.layer === n.layer);
    const k = peers.indexOf(n);
    const ang = (k / Math.max(1, peers.length)) * Math.PI * 2 + n.layer * 0.7;
    n.x = cx + R * Math.cos(ang) + (Math.random() - .5) * 24;
    n.y = cy + R * Math.sin(ang) + (Math.random() - .5) * 24;
    n.vx = 0; n.vy = 0; n.r = 5 + n.weight * 4.5;
  });
  const edges = d.edges.map(e => ({ a: idx[e.from], b: idx[e.to], s: e.strength || 1 }))
    .filter(e => e.a != null && e.b != null);
  // parent/children by layer, so hovering a line lights the whole path root→leaves
  const children = {}, parent = {};
  edges.forEach(e => {
    const lo = nodes[e.a].layer <= nodes[e.b].layer ? e.a : e.b;
    const hi = lo === e.a ? e.b : e.a;
    (children[lo] = children[lo] || []).push(hi);
    parent[hi] = lo;
  });
  G = { nodes, edges, children, parent, ctx, cv, W, H, cx, cy, rootQ: d.query, note: d.note,
        view: { x: 0, y: 0, k: 1 }, drag: null, hover: null, hl: null, alpha: 1, raf: 0, needFit: true };
  gFitInstant();
  gBind();
  gLoop(200);
}

function gStep() {
  const N = G.nodes, E = G.edges;
  for (let i = 0; i < N.length; i++) {
    const a = N[i];
    for (let j = i + 1; j < N.length; j++) {
      const b = N[j];
      let dx = a.x - b.x, dy = a.y - b.y, ds = dx * dx + dy * dy || 1;
      const dist = Math.sqrt(ds), f = 2900 / ds;   // modest repulsion (auto-fit keeps all on-screen)
      const fx = f * dx / dist, fy = f * dy / dist;
      a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
    }
  }
  E.forEach(e => {
    const a = N[e.a], b = N[e.b];
    const dx = b.x - a.x, dy = b.y - a.y, dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const target = 74 + Math.abs(a.layer - b.layer) * 38;   // slightly longer springs
    const f = 0.025 * (dist - target);
    const fx = f * dx / dist, fy = f * dy / dist;
    a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
  });
  N.forEach(n => {
    n.vx += (G.cx - n.x) * 0.006; n.vy += (G.cy - n.y) * 0.006;
    if (n === G.drag) { n.vx = 0; n.vy = 0; return; }
    n.vx *= 0.86; n.vy *= 0.86; n.x += n.vx * G.alpha; n.y += n.vy * G.alpha;
  });
}

function gDraw() {
  const { ctx, W, H, view, nodes, edges, hl } = G;
  ctx.clearRect(0, 0, W, H);
  ctx.save(); ctx.translate(view.x, view.y); ctx.scale(view.k, view.k);
  edges.forEach((e, ei) => {
    const a = nodes[e.a], b = nodes[e.b];
    const on = !hl || hl.eset.has(ei);
    ctx.strokeStyle = on ? "rgba(122,92,46," + (0.28 + 0.4 * e.s) + ")" : "rgba(122,92,46,0.06)";
    ctx.lineWidth = (on ? (0.8 + e.s * 1.2) : 0.5) / view.k;
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  });
  nodes.forEach((n, i) => {
    const on = !hl || hl.nset.has(i);
    ctx.globalAlpha = on ? 1 : 0.14;
    ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, 7); ctx.fillStyle = GKIND[n.kind] || "#888"; ctx.fill();
    if (n === G.hover) { ctx.lineWidth = 2 / view.k; ctx.strokeStyle = "#111"; ctx.stroke(); }
    ctx.fillStyle = "#1d2430";
    ctx.font = (n.layer === 1 ? "bold 15px" : Math.round(10 + n.weight * 1.4) + "px") + " system-ui, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "bottom";
    const lab = n.label.length > 22 ? n.label.slice(0, 21) + "…" : n.label;
    ctx.fillText(lab, n.x, n.y - n.r - 2);
  });
  ctx.globalAlpha = 1;
  ctx.restore();
}

// path highlight: descendants (down to leaves) ∪ ancestors (up to root) of a node
function gHl(nodeIdx) {
  const nset = new Set(), eset = new Set(), stack = [nodeIdx];
  while (stack.length) { const i = stack.pop(); nset.add(i); (G.children[i] || []).forEach(c => { if (!nset.has(c)) stack.push(c); }); }
  let p = G.parent[nodeIdx];
  while (p != null) { nset.add(p); p = G.parent[p]; }
  G.edges.forEach((e, ei) => { if (nset.has(e.a) && nset.has(e.b)) eset.add(ei); });
  return { nset, eset };
}
function gSegDist(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1, L = dx * dx + dy * dy || 1;
  let t = ((px - x1) * dx + (py - y1) * dy) / L; t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}
function gEdgeAt(mx, my) {
  // screen-space: convert both endpoints to px, then a fixed 7px tolerance —
  // consistent regardless of zoom (fixes the unstable line selection).
  let best = -1, bestd = 8;
  for (let ei = 0; ei < G.edges.length; ei++) {
    const e = G.edges[ei], a = gToScreen(G.nodes[e.a]), b = gToScreen(G.nodes[e.b]);
    const d = gSegDist(mx, my, a.x, a.y, b.x, b.y);
    if (d < bestd) { bestd = d; best = ei; }
  }
  return best;
}

// center a node & expand its branch to the limit, without leaving the graph:
// re-lay-out only that node's subtree with the node as the new layer-1 centre.
function gFocusSubtree(nodeIdx) {
  const keep = new Set([nodeIdx]), st = [nodeIdx];
  while (st.length) { const i = st.pop(); (G.children[i] || []).forEach(c => { if (!keep.has(c)) { keep.add(c); st.push(c); } }); }
  const base = G.nodes[nodeIdx].layer;
  const nodes = [...keep].map(i => { const n = G.nodes[i]; return { ...n, layer: n.layer - base + 1 }; });
  const edges = G.edges.filter(e => keep.has(e.a) && keep.has(e.b))
    .map(e => ({ from: G.nodes[e.a].id, to: G.nodes[e.b].id, strength: e.s }));
  gBuild({ query: G.rootQ, nodes, edges, note: G.note });
}

// 著者を調べる — REAL in-portal retrieval (bio, dates, occupation, works, source)
// via /api/author. This is the detection/extraction the user asked for; it never
// touches the word-origin engine. Empty results show WHERE it failed, not a blank.
async function gAuthorInvestigate(searchName, label) {
  const jp = LANG === "ja";
  const p = gPanel((jp ? "著者を調べる：" : "Author: ") + (label || searchName),
    `<p class="muted">${jp ? "取得中…" : "loading…"}</p>`);
  let d;
  try { d = await api(`/api/author?name=${encodeURIComponent(searchName)}&lang=${LANG}`); }
  catch (e) { p.querySelector(".gp-body").innerHTML = `<p class="badge err">${esc(String(e.message || e))}</p>`; return; }
  if (!d.found) {
    p.querySelector(".gp-body").innerHTML = `<p class="muted">${esc(d.note || d.error || (jp ? "取得できませんでした。" : "Not found."))}</p>
      <p class="srcline">${jp ? "代替：" : "alt:"} <a href="https://ja.wikipedia.org/wiki/Special:Search?search=${encodeURIComponent(searchName)}" target="_blank">Wikipedia検索</a></p>`;
    return;
  }
  const row = (k, v) => v && v.length ? `<tr><th>${esc(k)}</th><td>${esc(Array.isArray(v) ? v.join("、") : v)}</td></tr>` : "";
  let html = `<p>${esc(d.extract || "")}</p>
    <table class="plain">
      ${row(jp ? "生" : "born", (d.born || [])[0])}
      ${row(jp ? "没" : "died", (d.died || [])[0])}
      ${row(jp ? "職業" : "occupation", d.occupation)}
      ${row(jp ? "主要著作" : "works", (d.works || []).map(w => `${w}`))}
    </table>
    <p class="srcline"><a href="${esc(d.wikipedia_url)}" target="_blank">Wikipedia (${LANG})</a>${d.wikidata_url ? ` · <a href="${esc(d.wikidata_url)}" target="_blank">Wikidata</a>` : ""} · ${esc((d.sources && d.sources[0] && d.sources[0].retrieved_at) || "")}</p>
    <h4 class="gp-h">${jp ? "より深く・広く調べる（外部の専門情報源・多言語・新しいタブで開く）" : "Investigate deeper & wider (external expert sources, new tab)"}</h4>
    ${extResourcesHtml(d.title || searchName)}`;
  p.querySelector(".gp-body").innerHTML = html;
}

// ── 普遍原理: どの項目からも、公開・合法な専門情報源へ多言語で最大限リンクし、
//    ユーザーが選んで【新しいタブ】で開ける。当ポータルは選択肢を示すだけ（客観・
//    無編集・出所明示）。偏った編集をせず、思考の広がりと刺激を与える。──
function extResources(term) {
  const t = encodeURIComponent(term);
  return {
    "検索": [
      ["Google", `https://www.google.com/search?q=${t}`],
      ["Google Scholar", `https://scholar.google.com/scholar?q=${t}`],
      ["Bing", `https://www.bing.com/search?q=${t}`],
      ["DuckDuckGo", `https://duckduckgo.com/?q=${t}`],
    ],
    "百科事典": [
      ["Wikipedia 日", `https://ja.wikipedia.org/wiki/Special:Search?search=${t}`],
      ["Wikipedia 英", `https://en.wikipedia.org/w/index.php?search=${t}`],
      ["Wikipedia 独", `https://de.wikipedia.org/w/index.php?search=${t}`],
      ["Wikipedia 仏", `https://fr.wikipedia.org/w/index.php?search=${t}`],
      ["Stanford哲学百科 SEP", `https://plato.stanford.edu/search/searcher.py?query=${t}`],
      ["Internet哲学百科 IEP", `https://iep.utm.edu/?s=${t}`],
      ["Britannica", `https://www.britannica.com/search?query=${t}`],
      ["コトバンク", `https://kotobank.jp/word/${t}`],
    ],
    "辞書・辞典": [
      ["Wiktionary 日", `https://ja.wiktionary.org/wiki/Special:Search?search=${t}`],
      ["Wiktionary 英", `https://en.wiktionary.org/wiki/Special:Search?search=${t}`],
      ["DWDS 独", `https://www.dwds.de/wb/${t}`],
      ["Perseus 希/羅", `https://www.perseus.tufts.edu/hopper/searchresults?q=${t}`],
      ["Logeion 希/羅", `https://logeion.uchicago.edu/${t}`],
      ["Monier-Williams 梵", `https://www.sanskrit-lexicon.uni-koeln.de/scans/MWScan/2020/web/webtc/indexcaller.php`],
    ],
    "学術・論文": [
      ["PhilPapers", `https://philpapers.org/s/${t}`],
      ["CiNii", `https://cir.nii.ac.jp/all?q=${t}`],
      ["J-STAGE", `https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey=${t}`],
      ["JSTOR", `https://www.jstor.org/action/doBasicSearch?Query=${t}`],
      ["OpenAlex", `https://openalex.org/works?search=${t}`],
      ["国立国会図書館サーチ", `https://ndlsearch.ndl.go.jp/search?cs=bib&keyword=${t}`],
    ],
    "原典・全集": [
      ["Wikisource 日", `https://ja.wikisource.org/wiki/Special:Search?search=${t}`],
      ["Wikisource 独", `https://de.wikisource.org/wiki/Spezial:Suche?search=${t}`],
      ["Project Gutenberg", `https://www.gutenberg.org/ebooks/search/?query=${t}`],
      ["archive.org", `https://archive.org/search?query=${t}`],
    ],
  };
}
// render the external-resource fan as HTML (all links open in a NEW TAB)
function extResourcesHtml(term) {
  const jp = LANG === "ja", R = extResources(term);
  let h = `<p class="muted">${jp ? "公開・合法な専門情報源へのリンクです。各リンクは新しいタブで開きます。当ポータルは選択肢を示すだけで、中身は各サイトの提供です（客観・出所明示）。" : "Links to public expert sources; each opens in a new tab. This portal only offers the choices."}</p>`;
  for (const cat of Object.keys(R)) {
    h += `<div class="ext-cat"><span class="ext-cat-h">${esc(cat)}</span> `
      + R[cat].map(([lbl, url]) => `<a class="ext-link" href="${esc(url)}" target="_blank" rel="noopener">${esc(lbl)}</a>`).join(" ") + `</div>`;
  }
  return h;
}
function gExtPanel(term) {
  const jp = LANG === "ja";
  gPanel((jp ? "外部の専門情報で深く・広く調べる：" : "External resources: ") + term, extResourcesHtml(term));
}

// author info panel — from the lineage node's own data (work/year/term). Never
// routes a person's name through the word-origin engine.
function gAuthorPanel(n) {
  const jp = LANG === "ja";
  const wp = `https://ja.wikipedia.org/wiki/Special:Search?search=${encodeURIComponent(n.label)}`;
  const rows = [];
  if (n.work) rows.push([jp ? "主要著作" : "work", esc(n.work) + (n.year ? `（${n.year}）` : "")]);
  if (n.term_de) rows.push([jp ? "この語での原語" : "term", `<b lang="de">${esc(n.term_de)}</b>`]);
  const body = `<p class="muted">${jp ? "思想家の系譜（検証済シード）から。著者は語とは別の次元なので、語源エンジンでなく著者情報として示します。" : "From the curated lineage; authors are a different dimension than words."}</p>
    ${rows.length ? `<table class="plain">${rows.map(r => `<tr><th>${esc(r[0])}</th><td>${r[1]}</td></tr>`).join("")}</table>` : ""}
    <p class="srcline"><a href="${wp}" target="_blank">${jp ? "Wikipediaで開く" : "Wikipedia"}</a> · <a href="/deepsearch?q=${encodeURIComponent(n.label)}&lang=${LANG}">${jp ? "深掘り探索プロンプト" : "deep-search"}</a></p>
    <p class="srcline muted">${jp ? "著者固有の用法（その著作でこの語がどう使われたか）・時代性・年表は整備中です。" : "Author-specific usage / timeline are being built."}</p>`;
  gPanel((jp ? "著者：" : "Author: ") + n.label, body);
}

// contextual action menu — the dimension of a WORD (origin/meaning/translations)
// differs from that of an AUTHOR/WORK (usage/texts/era), so the menu ADAPTS to
// what was clicked. ≥7 actions; the ones not yet built are shown as 次段 (honest).
function gActions(n) {
  const jp = LANG === "ja", q = n.q, L = n.label;
  const nt = () => window.open(`/origin?q=${encodeURIComponent(q || L)}&lang=${LANG}`, "_blank");
  const ds = (term) => { location.href = `/deepsearch?q=${encodeURIComponent(term || q || L)}&lang=${LANG}`; };
  // AUTHOR/WORK is a different DIMENSION than a word — do NOT route the person's
  // name through the word-origin engine (that gave 'no Wiktionary entry' / an
  // empty graph). Show author-appropriate content (works, era, their term) and
  // real external links; the word engine is never called on a person.
  if (n.kind === "author" || n.kind === "work") {
    const who = n.kind === "author" ? "この著者" : "この著作";
    const sq = n.search || L;
    const wp = () => window.open(`https://ja.wikipedia.org/wiki/Special:Search?search=${encodeURIComponent(sq)}`, "_blank");
    return [
      { t: `🔍 ${who}を調べる（経歴・著作・出典を取得）`, fn: () => gAuthorInvestigate(sq, L) },
      { t: `🎯 ${who}を中心に（${jp ? "この語の文脈を保ち著作へ" : "keep context, focus works"}）`, fn: () => gFocusSubtree(G.nodes.indexOf(n)) },
      { t: `📖 ${who}の系譜メモ（この語での原語）`, fn: () => gAuthorPanel(n) },
      { t: `🌐 外部の専門情報で調べる（多言語・新タブ）`, fn: () => gExtPanel(sq) },
      { t: `✍ 深掘り探索プロンプトを作る（${who}）`, fn: () => ds(sq) },
      { t: "📖 この著者のこの語での用法（著者固有の共起）", soon: 1 },
      { t: "🕰 時代性・年表上の位置", soon: 1 },
    ];
  }
  if (n.kind === "domain") {
    return [
      { t: "🎯 この分岐を中心に（下層を最大表示）", fn: () => gFocusSubtree(G.nodes.indexOf(n)) },
      { t: "↩ 全体の重力分布に戻す", fn: () => originGraph(G.rootQ) },
      { t: "🔦 この分岐の経路を強調（ホバーでも可）", fn: () => { G.hl = gHl(G.nodes.indexOf(n)); gDraw(); } },
      { t: "📖 この意味領域の説明", soon: 1 },
      { t: "🔎 この領域の主要な語をたどる", soon: 1 },
      { t: "🌍 この領域を多言語で見る", soon: 1 },
      { t: "✍ 深掘り探索プロンプトを作る", fn: ds },
    ];
  }
  // word / original / language — UNIVERSAL: every action operates on THIS node's
  // word W, starting fresh from it (recenter the whole page on W, then focus the
  // requested aspect of W). No reuse of the previously-entered word's data.
  const W = q || L;
  return [
    { t: "🎯 この語を中心に展開（新たな第1階層に）", fn: () => originRecenter(W) },
    { t: "🔍 この語を深く調べる（意味・原点・変容）", fn: () => originRecenter(W, { scrollTo: "card-origin" }) },
    { t: "⚠ 埋没した原語を見る", fn: () => originRecenter(W, { scrollTo: "card-collapse" }) },
    { t: "🌍 多言語での言い方を見る", fn: () => originRecenter(W, { scrollTo: "card-breadth" }) },
    { t: "✍ 深掘り探索プロンプトを作る", fn: () => ds(W) },
    { t: "🕮 原語空間の共起（共に使われる語）", fn: () => gColloc(W) },
    { t: "🌐 外部の専門情報で調べる（多言語・新タブ）", fn: () => gExtPanel(W) },
    { t: "🔗 新しいタブでこの語を開く", fn: nt },
  ];
}

function gMenu(cx, cy, n) {
  const items = gActions(n);
  gShowMenu(cx, cy, (LANG === "ja" ? "選択：" : "Selected: ") + n.label, items);
}
function gMenuEdge(cx, cy, ei) {
  const e = G.edges[ei];
  const child = G.nodes[e.a].layer >= G.nodes[e.b].layer ? e.a : e.b;
  const a = G.nodes[e.a].label, b = G.nodes[e.b].label;
  gShowMenu(cx, cy, `${a} — ${b}`, [
    { t: "🔦 この関係の経路を根まで強調", fn: () => { G.hl = gHl(child); gDraw(); } },
    { t: "🎯 子側を中心に展開", fn: () => gFocusSubtree(child) },
    { t: "⚖ 両端の語を比較する", soon: 1 },
    { t: "📖 この関係（なぜ結ばれるか）の説明", soon: 1 },
    { t: "🔍 子側の語を深く調べる", fn: () => { const q = G.nodes[child].q || G.nodes[child].label; originRecenter(q); } },
    { t: "🌿 この枝だけを残して整理", fn: () => gFocusSubtree(child) },
    { t: "↩ 全体に戻す", fn: () => originGraph(G.rootQ) },
  ]);
}
function gShowMenu(cx, cy, title, items) {
  gMenuClose();
  const m = document.createElement("div");
  m.id = "graph-menu";
  m.innerHTML = `<div class="gm-title">${esc(title)}</div>` + items.map((it, i) =>
    `<div class="gm-item${it.soon ? " gm-soon" : ""}" data-i="${i}">${esc(it.t)}${it.soon ? "（次段）" : ""}</div>`).join("");
  document.body.appendChild(m);
  const w = m.offsetWidth || 300, x = Math.min(cx, window.innerWidth - w - 10),
        y = Math.min(cy + window.scrollY, window.scrollY + window.innerHeight - m.offsetHeight - 10);
  m.style.left = Math.max(6, x) + "px"; m.style.top = Math.max(6, y) + "px";
  // BUGFIX: keep the item's pointerdown from reaching the document-level closer,
  // which previously removed the menu on the SAME pointerdown so the click that
  // runs the action never landed (→ every item looked dead).
  m.addEventListener("pointerdown", (ev) => ev.stopPropagation());
  m.addEventListener("click", (ev) => {
    const el = ev.target.closest(".gm-item"); if (!el) return;
    const it = items[Number(el.dataset.i)];
    gMenuClose();
    if (it && it.fn) it.fn();
  });
  G.menuCloser = (ev) => { if (!ev.target.closest("#graph-menu")) gMenuClose(); };
  setTimeout(() => document.addEventListener("pointerdown", G.menuCloser), 0);
}
function gMenuClose() {
  const m = $("graph-menu"); if (m) m.remove();
  if (G && G.menuCloser) { document.removeEventListener("pointerdown", G.menuCloser); G.menuCloser = null; }
}
// dismissible overlay panel (for menu actions that show their own content)
function gPanel(title, bodyHtml) {
  const old = $("graph-panel"); if (old) old.remove();
  const p = document.createElement("div");
  p.id = "graph-panel";
  p.innerHTML = `<div class="gp-head"><b>${esc(title)}</b><button type="button" class="gp-x">×</button></div>
    <div class="gp-body">${bodyHtml}</div>`;
  document.body.appendChild(p);
  p.querySelector(".gp-x").addEventListener("click", () => p.remove());
  return p;
}
// 原語空間の共起（DWDS）— the benchmark's『関連概念群』dimension, made real.
// BUGFIX (Codex): a non-Latin node label (Japanese 疎外) can't be sent to DWDS
// directly — resolve it to its German concept-origin (Entfremdung) first, else
// say so. Only German has a collocation source for now (honest).
async function gColloc(term) {
  const jp = LANG === "ja";
  const p = gPanel((jp ? "原語空間の共起：" : "Collocations: ") + term,
    `<p class="muted">${jp ? "読み込み中…" : "loading…"}</p>`);
  let deTerm = term;
  if (!/[A-Za-zÀ-ɏ]/.test(term)) {
    try {
      const od = await api(`/api/origin?q=${encodeURIComponent(term)}&lang=${LANG}`);
      const g = (od.concept_origin || []).find(o => o.name === "ドイツ語");
      if (!g) { p.querySelector(".gp-body").innerHTML = `<p class="muted">${jp ? "この語の原語（独語）が特定できず、共起（現状は独語コーパスのみ）を引けません。" : "No German origin resolved; collocations (German corpus only) unavailable."}</p>`; return; }
      deTerm = g.term;
    } catch (e) { p.querySelector(".gp-body").innerHTML = `<p class="badge err">${esc(String(e.message || e))}</p>`; return; }
  }
  let d;
  try { d = await api(`/api/collocations?term=${encodeURIComponent(deTerm)}&lang=de`); }
  catch (e) { p.querySelector(".gp-body").innerHTML = `<p class="badge err">${esc(String(e.message || e))}</p>`; return; }
  const rels = d.relations || {}, keys = Object.keys(rels);
  let html = "";
  if (!keys.length) {
    html = `<p class="muted">${esc(d.note || (jp ? "共起データがありません。" : "No collocation data."))}</p>`;
  } else {
    html = `<p class="muted">${jp ? "この原語が、原語コーパスで共に使われる語（文法関係別・頻度つき）。クリックでその語へ。" : "Words this term lives with in its own corpus."}</p>
      <table class="plain orig-collo">` + keys.map(rel =>
      `<tr><td class="srcline">${esc(jp ? (REL_JP[rel] || rel) : rel)}</td><td>${rels[rel].map(w =>
        `<a href="/origin?q=${encodeURIComponent(w.word)}&lang=${LANG}"${originLinkAttr()} lang="de">${esc(w.word)}</a> <span class="srcline">${w.freq}</span>`).join("　")}</td></tr>`).join("") + `</table>`;
  }
  if (d.note && keys.length) html += `<p class="srcline muted">${esc(d.note)}</p>`;
  p.querySelector(".gp-body").innerHTML = html;
}

// scroll to a result card; if it isn't present for the current word, recenter
// on the clicked word (which renders that word's cards) and then scroll.
function gScrollCard(id, q) {
  const el = $(id);
  if (el && (!G || q === G.rootQ)) { el.scrollIntoView({ behavior: "smooth", block: "center" }); return; }
  originRecenter(q);
  setTimeout(() => { const e2 = $(id); if (e2) e2.scrollIntoView({ behavior: "smooth", block: "center" }); }, 900);
}

// The physics loop runs only while ACTIVE (settling, or a node being dragged);
// when it stops it clears G.raf and flips G.running=false, so hover/zoom/pan can
// redraw on demand. The previous version left a stale G.raf, so `if(!G.raf)`
// never fired and hover-highlight flickered / appeared only sometimes.
function gLoop(iters) {
  cancelAnimationFrame(G.raf); G.running = true; let i = 0;
  const tick = () => {
    const active = (i++ < iters) || G.drag;
    if (active) gStep();
    gDraw();
    if (active) { G.raf = requestAnimationFrame(tick); }
    else {
      G.running = false; G.raf = 0;
      if (G.needFit) { G.needFit = false; graphFit(); }  // fit once after settle → all nodes on-screen
      else gDraw();
    }
  };
  tick();
}

function gScreenToGraph(mx, my) {
  return { x: (mx - G.view.x) / G.view.k, y: (my - G.view.y) / G.view.k };
}
// Hit-testing in SCREEN space (px), so it is stable across zoom levels — the old
// graph-space thresholds shrank/grew with zoom and made selection unpredictable.
function gToScreen(n) { return { x: n.x * G.view.k + G.view.x, y: n.y * G.view.k + G.view.y }; }
function gNodeAt(mx, my) {
  for (let i = G.nodes.length - 1; i >= 0; i--) {
    const n = G.nodes[i], s = gToScreen(n), rr = n.r * G.view.k + 8;
    if ((s.x - mx) ** 2 + (s.y - my) ** 2 <= rr * rr) return n;
  }
  return null;
}

function gBind() {
  const cv = G.cv;
  cv.onpointerdown = (e) => {
    gMenuClose();
    cv.setPointerCapture(e.pointerId);
    const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    const n = gNodeAt(mx, my);
    // Do NOT start dragging on pointerdown. A human click has a few px of jitter;
    // dragging immediately turned that jitter into a drag, so the menu never
    // opened (→ "sometimes works"). Dragging begins only past a real threshold.
    G.press = { mx, my, n, ei: n ? -1 : gEdgeAt(mx, my), moved: false, panx: G.view.x, pany: G.view.y };
  };
  cv.onpointermove = (e) => {
    const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    if (!G.press) {
      const n = gNodeAt(mx, my);
      if (n) { G.hover = n; G.hl = gHl(G.nodes.indexOf(n)); cv.style.cursor = "pointer"; }
      else {
        const ei = gEdgeAt(mx, my);
        if (ei >= 0) { G.hover = null; const e2 = G.edges[ei]; const child = G.nodes[e2.a].layer >= G.nodes[e2.b].layer ? e2.a : e2.b; G.hl = gHl(child); cv.style.cursor = "pointer"; }
        else { G.hover = null; G.hl = null; cv.style.cursor = "grab"; }
      }
      if (!G.running) gDraw();   // when settled, reflect the hover immediately
      return;
    }
    const ddx = mx - G.press.mx, ddy = my - G.press.my;
    if (!G.press.moved && Math.hypot(ddx, ddy) > 10) {  // 10px euclidean = real drag, tolerant of click jitter
      G.press.moved = true;
      if (G.press.n) G.drag = G.press.n;   // begin dragging the node only now
    }
    if (!G.press.moved) return;            // below threshold → it is a click, do nothing
    if (G.drag) { const p = gScreenToGraph(mx, my); G.drag.x = p.x; G.drag.y = p.y; gLoopKick(); }
    else { G.view.x = G.press.panx + ddx; G.view.y = G.press.pany + ddy; gDraw(); }
  };
  cv.onpointerup = (e) => {
    const p = G.press; G.drag = null; G.press = null;
    if (p && !p.moved) {
      if (p.n) gMenu(e.clientX, e.clientY, p.n);
      else if (p.ei >= 0) gMenuEdge(e.clientX, e.clientY, p.ei);
    } else gLoopKick();
  };
  cv.onwheel = (e) => {
    e.preventDefault();
    const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    const f = e.deltaY < 0 ? 1.12 : 0.89, nk = Math.max(0.2, Math.min(4, G.view.k * f));
    G.view.x = mx - (mx - G.view.x) * (nk / G.view.k);
    G.view.y = my - (my - G.view.y) * (nk / G.view.k);
    G.view.k = nk; gDraw();
  };
}
function gLoopKick() { if (!G.running) gLoop(40); else gDraw(); }

function gFitInstant() { G.view = { x: 0, y: 0, k: 1 }; }
function graphFit() {
  if (!G) return;
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  G.nodes.forEach(n => { x0 = Math.min(x0, n.x - n.r - 40); y0 = Math.min(y0, n.y - n.r - 20);
    x1 = Math.max(x1, n.x + n.r + 40); y1 = Math.max(y1, n.y + n.r + 20); });
  const k = Math.min(G.W / (x1 - x0), G.H / (y1 - y0), 2);
  G.view.k = k;
  G.view.x = (G.W - (x0 + x1) * k) / 2;
  G.view.y = (G.H - (y0 + y1) * k) / 2;
  gDraw();
}

const REL_JP = {
  "hat Adjektivattribut": "形容詞で修飾される",
  "ist Adjektivattribut von": "〜を形容する",
  "ist in Koordination mit": "並んで語られる（並列）",
  "ist Akkusativ-Objekt von": "〜される（目的語）",
  "ist Dativ-/Genitiv-Objekt von": "〜の対象になる",
  "ist Subjekt von": "〜する（主語）",
  "ist Genitivattribut von": "〜の（属格で係る）",
  "hat Genitivattribut": "〜を伴う（属格）",
};

function cleanWikt(s) {
  return String(s || "").replace(/:?\[(\d+)\]/g, "$1.").replace(/\{\{[^}]*\}\}/g, "")
    .replace(/\s+/g, " ").trim();
}
async function originRun(q, tok) {
  if (tok == null) tok = originClaim(q);   // standalone caller (newtab re-render) claims its own token
  const jp = LANG === "ja";
  $("origin-status").innerHTML = `<p class="muted">${jp ? "原点へ辿っています…" : "Tracing to the origin…"}</p>`;
  $("origin-results").innerHTML = "";
  $("origin-results").dataset.q = q;
  const linkAttr = originLinkAttr();
  let d;
  try { d = await api(`/api/origin?q=${encodeURIComponent(q)}&lang=${LANG}`); }
  catch (e) { if (!originStale(tok)) $("origin-status").innerHTML = `<p class="badge err">${esc(String(e.message || e))}</p>`; return; }
  if (originStale(tok)) return;            // 古い語の応答＝現在の語のカードを上書きしない（stale破棄）
  if (d.qid) OZ.qid = d.qid;               // 既存qidを単一真実源へ伝播
  $("origin-status").innerHTML = "";
  const olink = (t) => `<a href="/origin?q=${encodeURIComponent(t)}&lang=${LANG}"${linkAttr}>${esc(t)}</a>`;
  let html = "";

  // ── 言葉（主役） ──
  // 入力語と異なる記事へ辿った場合は正直に明示（間主観 →（間主観性 として辿りました））
  const rf = d.resolved_from, rt = d.resolved_to;
  const resolvedNote = (rf && rt && rf !== rt)
    ? `<p class="srcline">${jp ? `「${esc(rf)}」の記事は無いため、通常検索が見つける` : `no exact article for “${esc(rf)}”; followed `}<b>${olink(rt)}</b>${jp ? "（同じ概念）として辿りました" : " (same concept)"}</p>`
    : "";
  html += `<div class="card word-card">
    <p class="srcline">${jp ? "この探求は、まず言葉そのものから始まります" : "This inquiry begins with the word itself"}</p>
    <h2 class="theword">「${esc((d.word || {}).query || q)}」</h2>${resolvedNote}</div>`;

  if (!d.found) {
    // 行き止まりにしない: 候補（通常検索が見つける記事）をクリックで辿れる形で示す（第二次戦略）
    const sg = d.suggestions || [];
    if (sg.length) {
      html += `<div class="card"><p>${jp ? `「${esc(q)}」そのものの項目は見つかりませんでした。通常の検索が見つける、近い項目はこちらです（クリックで辿れます）：` : `No exact entry for “${esc(q)}”. Closest entries normal search finds:`}</p>
        <div class="dim-disc-list">${sg.map(s => `<a class="dim-disc-l" href="/origin?q=${encodeURIComponent(s)}&lang=${LANG}"${linkAttr}>${esc(s)}</a>`).join("")}</div></div>`;
    } else {
      html += `<div class="card"><p>${jp ? "この語の項目が見つかりませんでした（語幹・別表記・ローマ字で再試行してみてください）。" : "No entry for this form (try a lemma / alternative spelling / romanization)."}</p></div>`;
    }
    $("origin-results").innerHTML = html; return;
  }

  // ── 探究の次元（ベンチマークの広さ・深さへ辿れる路の一覧・構造の保証） ──
  if (d.dimensions && d.dimensions.length) {
    const badge = (s) => s === "ok" ? `<span class="dim-b dim-ok">${jp ? "辿れる" : "ready"}</span>`
      : s === "partial" ? `<span class="dim-b dim-part">${jp ? "一部" : "partial"}</span>`
      : `<span class="dim-b dim-soon">${jp ? "整備中" : "coming"}</span>`;
    DIMS = d.dimensions;
    html += `<div class="card dim-card"><h3>${jp ? "探究の次元（この言葉をどこから見ていくか）" : "Dimensions of inquiry"}</h3>
      <p class="muted">${jp ? "一つの言葉を、いくつかの次元から見ていく入口です。「辿れる」＝実データに到達する次元／「一部」＝既存機構につながる次元／「整備中」＝まだ路だけで内容は未接続、を正直に区別します。上は暫定の【共通次元】。その下に、この概念自身の記事構造から【概念ごとに異なる固有の切り口】を発見して示します（固定分類でない）。" : "Entry points into several dimensions of a word. ready = reaches real data; partial = wired to an existing engine; coming = path only. Above are COMMON dimensions; below are facets DISCOVERED from this concept's own article — different per concept."}</p>
      <div class="dims">${d.dimensions.map((dm, i) =>
        `<button type="button" class="dim${dm.status === "soon" ? " dim-x" : ""}" data-i="${i}">${esc(dm.label)} ${badge(dm.status)}</button>`).join("")}</div>
      <div id="dim-discovered" class="dim-disc"><p class="srcline muted">${jp ? "この概念に固有の切り口を、記事の構造から取得中…" : "discovering concept-specific facets…"}</p></div></div>`;
  }

  // ── 広く共有されている意味（入力言語） ──
  if (d.general_meaning && d.general_meaning.length) {
    html += `<div class="card"><h3>${jp ? "広く共有されている意味" : "The broadly shared meaning"}</h3>
      <ol class="gm-senses">${d.general_meaning.map(s => `<li>${esc(s)}</li>`).join("")}</ol></div>`;
  }

  // ── ⚠ 埋没の明示警告（最重要）：日本語A ← 原語B・C・D ──
  const cw = d.collapse_warning;
  if (cw && cw.lemmas && cw.lemmas.length) {
    const olink2 = (t) => `<a href="/origin?q=${encodeURIComponent(t)}&lang=${LANG}"${linkAttr} lang="de">${esc(t)}</a>`;
    html += `<div class="card warn-card" id="card-collapse">
      <h3>⚠ ${jp ? "この言葉は、扱いに注意が要ります" : "This word needs careful handling"}</h3>
      <p>${jp
        ? `日本語の${(cw.collapsed_japanese||[]).map(w=>`「${esc(w)}」`).join("・")}という一語には、原語では<b>別々の複数の語</b>があり、翻訳の際に一語へ抽象化され、その区別が<b>埋没</b>しています。日本語だけを見ていると、この区別は見えません——どれを指すかで、あなたの問いの意味は変わります。`
        : `Behind this single Japanese word stand <b>several distinct original terms</b>, collapsed into one. The distinction vanishes in Japanese — and which one you mean changes what your question means.`}</p>
      <table class="plain collapse-tbl">
        ${cw.lemmas.map(l => `<tr>
          <td><b>${olink2(l.lemma)}</b>${(l.collapses_to&&l.collapses_to.length)?`<br><span class="srcline">→「${l.collapses_to.map(esc).join("・")}」</span>`:""}</td>
          <td>${esc(l.gloss||"")}</td></tr>`).join("")}
      </table>
      ${cw.note?`<p class="muted">${esc(cw.note)}</p>`:""}
      ${cw.primary_source?`<p class="srcline">${jp?"一次源":"primary source"}: ${esc(cw.primary_source)}</p>`:""}
      <p class="srcline">${jp?"各語をクリックすると、その原語の空間に入れます":"Click a term to enter its original-language space"} · ${jp?"確度":"confidence"}: ${esc(cw.confidence||"")}</p>
    </div>`;
  }

  // ── 原点：単一の断定を禁じ、複数の軸を分けて正直に示す（P1無中心・P6捏造しない）。
  // (1)概念を立てた思想家(P61/P112・決定論・本命) (2)語形の由来=語源(概念の原点でない)
  // (3)語源チェーン を明確に分離。「語源だけを唯一の原点」と示す誤誘導を構造的に禁止する。──
  const co = d.concept_origin || [], o = d.word_origin;
  const orig = d.originators || [], na = d.named_after || [], assoc = d.associated || [];
  html += `<div class="card orig-card" id="card-origin"><h3>${jp ? "この言葉の原点" : "This word's origin"}</h3>`;
  // (1) 立てた/著した人 — 決定論（P50著者/P61考案者）。資本論→マルクス、リゾーム→ドゥルーズ・ガタリ
  if (orig.length) {
    html += `<p>${jp ? "この概念を立てた／著した人（Wikidata: 著者・考案者）" : "Who framed/authored this (Wikidata: author/inventor)"}:
      ${orig.map(p => `<a href="#" class="origin-thinker" data-name="${esc(p.label)}"><b>${esc(p.label)}</b></a>`).join("　／　")}</p>
      <p class="srcline">${jp ? "名前をクリックすると、その人の経歴・著作・多言語の専門情報源（新タブ）へ入れます。" : "Click a name for their bio, works and multilingual sources (new tab)."}</p>`;
  }
  // (1b) 関連する思想家（記事言及・重要度順）— P50/P61が無い概念でも0にしない（資本主義→スミス/マルクス…）
  if (assoc.length) {
    html += `<p>${jp ? "関連する思想家（この概念の記事が言及・重要度順）" : "Associated thinkers (named in the article, by prominence)"}:
      ${assoc.map(p => `<a href="#" class="origin-thinker" data-name="${esc(p.label)}">${esc(p.label)}</a>`).join("　／　")}</p>
      <p class="srcline">${jp ? "『立てた人』が特定できない概念でも、通常検索が結びつける主要人物へ届くための層。記事の言及に接地（賛否は判定しない）。" : "A recall layer reaching the figures normal search associates; grounded in the article's mentions."}</p>`;
  }
  // (2) 語形の由来（語源）＋翻訳原点の候補 — 思想家がいる場合は"語源"として明確に降格し警告
  if (co.length || na.length) {
    const label = orig.length
      ? (jp ? "語形の由来（語源・この訳語の《形》が写した語）" : "Word-form etymology")
      : (jp ? "概念-翻訳-原点の候補（この訳語が写した可能性のある原語）" : "Candidate translation-origin (not asserted as the single origin)");
    const items = co.map(o2 => `<b class="origin-lang">${esc(o2.name)}</b> <span lang="${esc(o2.code||'')}">${esc(o2.term)}</span>`)
      .concat(na.map(p => `<span class="origin-lang">${esc(p.label)}</span>`));
    html += `<p>${label}: ${items.join("　／　")}</p>`;
    html += orig.length
      ? `<p class="srcline" style="color:var(--warn)">⚠ ${jp ? "これは語の《形》の由来（語源）であって、この概念そのものの原点ではありません。概念の原点は上の思想家です。語源だけを『原点』として断定すると、強い誤った誘導になります。" : "This is the word-FORM's etymology, NOT the concept's origin (the thinkers above are). Asserting the etymology as 'the origin' would mislead."}</p>`
      : `<p class="srcline">${jp ? "密度の高い言説から辿った手がかり（候補）。単一に断定しません。権威源での裏取りは今後。" : "A lead from dense discourse (a candidate; not asserted as the single origin)."}</p>`;
  }
  // (3) 語源の原点：語そのものの言語史（Wiktionary推定）
  if (o) {
    html += `<p>${jp ? "語源の原点（語そのものの言語史・推定）" : "Etymological origin (the word's own history, estimated)"}:
      <b class="origin-lang">${esc(o.name)}</b>
      ${o.native ? `<span class="badge">${jp ? "この言語生まれ" : "native"}</span>` : ""}
      ${o.multi ? `<span class="badge warn2">${jp ? "複数の語源" : "multiple"}</span>` : ""}</p>`;
  }
  if (!orig.length && !co.length && !na.length && !o) {
    html += `<p class="muted">${jp ? "この概念の原点を単一に断定できる決定論的手がかりがありませんでした（貧弱な記事や、一人に帰さない概念）。断定は避けます——下の外部の専門情報源や『思想家の系譜』から、実際の言説（誰が・どの著作で・どう使ったか）へ辿ってください。" : "No deterministic single origin found; we do not assert one. Reach the actual discourse via the external sources / thinkers below."}</p>`;
  }
  // 常に：単一断定の禁止を明示し、言説へ広く辿る入口（普通の検索が届く所へ確実に届く・P4/P1）
  html += `<p class="srcline"><a href="#" class="origin-discourse" data-q="${esc((d.word || {}).query || q)}">${jp ? "▶ この概念の言説を広く調べる（多言語の専門情報源・新タブ）" : "▶ Explore this concept's discourse (multilingual sources, new tab)"}</a> · ${jp ? "原点は一つに断定しません（無中心・P1）" : "we never assert a single center (P1)"}</p>`;
  if (d.polysemy) {
    html += `<p class="muted">⚠ ${jp ? "この語は多義です：概念経路と語源経路が異なる意味・原点を指しています（両方を示しています）。" : "This word is polysemous: the concept path and the etymology path point to different senses/origins (both shown)."}</p>`;
  }
  // 変容の連鎖：現在語 ← … ← 原点（言語＋実語形）
  if (d.chain && d.chain.length) {
    const steps = [`<span class="chain-now">「${esc(q)}」</span>`].concat(
      d.chain.map(c => `<span class="chain-step"><span class="chain-lang">${esc(c.name)}</span>${c.form ? `<span class="chain-form">${esc(c.form)}</span>` : ""}</span>`));
    html += `<p class="chain-label">${jp ? "変容の連鎖（訳語をさかのぼる）" : "The chain of transformation (back through translation)"}</p>
      <div class="chain">${steps.join(`<span class="chain-arrow">←</span>`)}</div>`;
  }
  if (d.senses && d.senses.length) {
    html += `<p class="muted">${jp ? "原語での語義" : "senses in the original"}: ${esc(cleanWikt(d.senses.slice(0,3).join(" / ")))}</p>`;
  }
  if (d.wiktionary_url) html += `<p class="srcline"><a href="${esc(d.wiktionary_url)}" target="_blank">Wiktionary</a></p>`;
  html += `</div>`;

  // ── breadth：この概念を担う言語と、その各言語での語（データの和集合） ──
  if (d.breadth && d.breadth.length) {
    html += `<div class="card" id="card-breadth"><h3>${jp ? "この概念を担う、世界の言語とその語" : "The world's languages that carry this concept, and their word"} <span class="srcline">${d.breadth_count}</span></h3>
      <p class="muted">${jp ? "どの言語を出すかは、私（AI）でなくデータが決めています。既知の数言語に縮めない——見知らぬ言語こそ現れるべきだからです。" : "Which languages appear is decided by the data, not by me (the AI) — the unfamiliar ones are exactly what should surface."}</p>
      <div class="breadth">${d.breadth.map(b => `<span class="blang" title="${esc(b.via)}">${esc(b.name)}${b.term ? `：<span lang="">${esc(b.term)}</span>` : ""}</span>`).join("")}</div></div>`;
  }

  // ── 出所・確度・限界 ──
  const badges = (d.sources || []).map(s => s.error
    ? `<span class="badge err" title="${esc(s.error)}">${esc(s.source)}</span>`
    : `<span class="badge">${esc(s.source)} · ${esc(s.retrieved_at)}</span>`).join(" ");
  const cf = d.confidence || {};
  html += `<p class="srcline">${badges}<br>${jp ? "確度" : "confidence"} — ${jp ? "概念原点" : "concept"}: ${esc(cf.concept_origin||"")} ／ ${jp ? "語源" : "etymology"}: ${esc(cf.word_origin||"")} ／ breadth: ${esc(cf.breadth||"")}</p>`;
  if (d.note) html += `<p class="srcline muted">${esc(d.note)}</p>`;

  $("origin-results").innerHTML = html;
  gDiscoverDims(q, tok);   // #1: concept-specific dimensions from the article's own structure
}

// 概念固有の次元を発見する層（#1）: その概念自身の記事の節見出し＝固定でなく概念ごとに
// 変わる切り口。共通次元とは分離して示す。各切り口は記事の該当節を新タブで開く（P4）。
async function gDiscoverDims(q, tok) {
  const el = $("dim-discovered"); if (!el) return;
  const jp = LANG === "ja";
  let d;
  try { d = await api(`/api/dimensions?q=${encodeURIComponent(q)}&lang=${LANG}`); }
  catch (e) { if (tok == null || !originStale(tok)) el.innerHTML = ""; return; }
  if (tok != null && originStale(tok)) return;   // 古い語の固有次元を現在の語に混ぜない（stale破棄）
  if (!d.found || !d.dimensions || !d.dimensions.length) {
    el.innerHTML = `<p class="srcline muted">${esc(d.note || (jp ? "この概念に固有の切り口は取得できませんでした。" : "No concept-specific facets found."))}</p>`;
    return;
  }
  const link = (x) => `<a class="dim-disc-l" href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.heading)}</a>`;
  el.innerHTML = `<p class="dim-disc-h">${jp ? "この概念に固有の切り口（記事の構造から・出所つき・概念ごとに異なる）" : "Facets specific to this concept (from its own article structure)"}</p>
    ${d.disambiguation ? `<p class="srcline" style="color:var(--warn)">⚠ ${esc(d.note)}</p>` : ""}
    <div class="dim-disc-list">${d.dimensions.map(link).join("")}</div>
    <p class="srcline muted">${jp ? "出所" : "source"}: <a href="${esc(d.article_url)}" target="_blank">Wikipedia (${LANG})「${esc(d.title)}」</a>。固定の共通次元と違い、語ごとに違う切り口が出ます。</p>`;
}
