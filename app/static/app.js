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
        <h2>🔤 ${jp ? "原語の基底（翻訳で潰れる区別）" : "Original-language base (distinctions the translation loses)"}</h2>
        <p class="muted">${jp
          ? "日本語の一語の背後に、原語では別語がある。ここが全ての基底です。訳語で検索・思考する前に、原語の区別を先に見てください。"
          : "Behind one Japanese word stand several original-language terms. This is the base — see the original distinctions before searching or reasoning in translation."}</p>
        <p class="srcline">${jp ? "同一の日本語に潰れる語" : "collapse into"}:
          ${oc.collapsed_japanese.map(w => `「${esc(w)}」`).join(" ")}
          · <span class="badge">${esc(oc.tradition)}</span></p>
        <table class="plain orig-lemmas">
          <tr><th>${jp ? "原語" : "Original"}</th><th>${jp ? "語義" : "Gloss"}</th><th>${jp ? "潰れ先" : "→ JP"}</th><th></th></tr>
          ${oc.lemmas.map(l => `<tr>
            <td><b lang="${esc(l.lang)}">${esc(l.lemma)}</b><br><span class="srcline">${esc(l.polarity || "")}</span></td>
            <td>${esc(l.gloss)}</td>
            <td class="srcline">${(l.collapses_to || []).map(w => esc(w)).join("・")}</td>
            <td class="srcline">${esc(l.source || "")}</td></tr>`).join("")}
        </table>
        <p class="srcline">${jp ? "一次源" : "Primary source"}: ${esc(oc.primary_source)}</p>
        ${liveTerms ? `<p class="srcline">${jp ? "Wikidataの原語ラベル（ライブ）" : "Wikidata original labels (live)"}: ${liveTerms}</p>` : ""}
        <p class="orig-note">${esc(oc.note)}</p>
        <p class="srcline">${jp ? "確度" : "Confidence"} — ${jp ? "原語の実在" : "terms"}: <b>${esc(oc.confidence_terms)}</b> ／ ${jp ? "日本語への潰れ" : "collapse"}: <b>${esc(oc.confidence_collapse)}</b>.
          <span class="muted">${jp
            ? "編者による検証済みシード（網羅ではない・原語の実在と語義は独語Wikipedia等で確認済／潰れの整理は要一次確認）。"
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
  if (q) originRun(q);
}

// Attribute string for an internal word link — a new tab (keeping the current
// result) or in-place, per the user's choice (#6: don't silently overwrite).
function originLinkAttr() {
  return (localStorage.getItem("origin_newtab") === "1")
    ? ' target="_blank" rel="noopener"' : "";
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
async function originRun(q) {
  const jp = LANG === "ja";
  $("origin-status").innerHTML = `<p class="muted">${jp ? "原点へ辿っています…" : "Tracing to the origin…"}</p>`;
  $("origin-results").innerHTML = "";
  $("origin-results").dataset.q = q;
  const linkAttr = originLinkAttr();
  let d;
  try { d = await api(`/api/origin?q=${encodeURIComponent(q)}&lang=${LANG}`); }
  catch (e) { $("origin-status").innerHTML = `<p class="badge err">${esc(String(e.message || e))}</p>`; return; }
  $("origin-status").innerHTML = "";
  const olink = (t) => `<a href="/origin?q=${encodeURIComponent(t)}&lang=${LANG}"${linkAttr}>${esc(t)}</a>`;
  let html = "";

  // ── 言葉（主役） ──
  html += `<div class="card word-card">
    <p class="srcline">${jp ? "この探求は、まず言葉そのものから始まります" : "This inquiry begins with the word itself"}</p>
    <h2 class="theword">「${esc((d.word || {}).query || q)}」</h2></div>`;

  if (!d.found) {
    html += `<div class="card"><p>${jp ? "この語のWiktionaryエントリが見つかりませんでした（語幹・別表記・ローマ字で再試行してみてください）。" : "No Wiktionary entry for this form (try a lemma / alternative spelling / romanization)."}</p></div>`;
    $("origin-results").innerHTML = html; return;
  }

  // ── 広く共有されている意味（入力言語） ──
  if (d.general_meaning && d.general_meaning.length) {
    html += `<div class="card"><h3>${jp ? "広く共有されている意味" : "The broadly shared meaning"}</h3>
      <ol class="gm-senses">${d.general_meaning.map(s => `<li>${esc(s)}</li>`).join("")}</ol></div>`;
  }

  // ── 原点：概念-翻訳-原点（密度）＋ 語源原点（語史）を分けて示す ──
  const co = d.concept_origin || [], o = d.word_origin;
  html += `<div class="card orig-card"><h3>${jp ? "この言葉の原点" : "This word's origin"}</h3>`;
  // 概念-翻訳-原点：訳語がどの言語の何から来たか（疎外→独 Entfremdung）
  if (co.length) {
    html += `<p>${jp ? "概念の原点（この訳語が写した原語）" : "Concept origin (the original this translation renders)"}:
      ${co.map(o2 => `<b class="origin-lang">${esc(o2.name)}</b> <span lang="${esc(o2.code||'')}">${esc(o2.term)}</span>`).join("　／　")}</p>
      <p class="srcline">${jp ? "密度の高い言説（記事・著者・論議）から辿った手がかり。権威源での裏取りは今後。" : "A lead traced from dense discourse; authoritative confirmation to follow."}</p>`;
  }
  // 語源原点：語そのものの言語史
  if (o) {
    html += `<p>${jp ? "語源の原点（語そのものの言語史・推定）" : "Etymological origin (the word's own history, estimated)"}:
      <b class="origin-lang">${esc(o.name)}</b>
      ${o.native ? `<span class="badge">${jp ? "この言語生まれ" : "native"}</span>` : ""}
      ${o.multi ? `<span class="badge warn2">${jp ? "複数の語源" : "multiple"}</span>` : ""}</p>`;
  }
  if (!co.length && !o) {
    html += `<p class="muted">${jp ? "原点を特定できませんでした（記事・語源とも手がかりが乏しい語です）。" : "Could not identify an origin (sparse article/etymology data)."}</p>`;
  }
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
    html += `<div class="card"><h3>${jp ? "この概念を担う、世界の言語とその語" : "The world's languages that carry this concept, and their word"} <span class="srcline">${d.breadth_count}</span></h3>
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
}
