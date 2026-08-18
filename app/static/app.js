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
        loading: "Querying live scholarly sources…", none: "None yet", del: "Delete", open: "Open",
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

// 外部情報源の応答が返らない時も、画面を「読み込み中」のまま固定しない。
// 個別の呼び出し側で timeout を書かず、全てのAPI操作に同じ安全弁を掛ける。
const API_TIMEOUT_MS = 20000;
async function api(path, opts = {}) {
  const { timeout = API_TIMEOUT_MS, signal: callerSignal, body, ...fetchOpts } = opts;
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  let timer = null;
  let abortFromCaller = null;
  if (controller && callerSignal) {
    abortFromCaller = () => controller.abort();
    if (callerSignal.aborted) controller.abort();
    else callerSignal.addEventListener("abort", abortFromCaller, { once: true });
  }
  if (controller && Number.isFinite(timeout) && timeout > 0) {
    timer = setTimeout(() => controller.abort(), timeout);
  }
  try {
    const r = await fetch(path, {
      ...fetchOpts,
      headers: { "Content-Type": "application/json", ...(fetchOpts.headers || {}) },
      signal: controller ? controller.signal : callerSignal,
      body: body == null ? undefined : (typeof body === "string" ? body : JSON.stringify(body)),
    });
    if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
    return r.json();
  } catch (e) {
    if (controller && controller.signal.aborted && !(callerSignal && callerSignal.aborted)) {
      const err = new Error(`API timeout: ${path}`);
      err.name = "TimeoutError";
      throw err;
    }
    throw e;
  } finally {
    if (timer) clearTimeout(timer);
    if (callerSignal && abortFromCaller) callerSignal.removeEventListener("abort", abortFromCaller);
  }
}

function llmConfig() {
  const provider = localStorage.getItem("dialexis_provider") || "";
  if (!provider) return null;
  return { provider, model: localStorage.getItem("dialexis_model") || "",
           key: localStorage.getItem("dialexis_key") || "" };
}

function freshBadge(res) {
  if (!res) return "";
  if (res.error) { try { console.error(res.error); } catch (e) {} return `<span class="badge err" title="${esc((LANG === "ja" ? "取得を見送りました" : "skipped"))}">${T.error}</span>`; }
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
        ? "下の情報源からもこの語を辿れます。"
        : "Reach this term via the sources below as well."}</p>`;
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
    console.error(e); $("explore-status").innerHTML = `<p class="badge err">${esc((LANG==="ja"?"取得を見送りました":"skipped"))}</p>`;
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
      ? `<p class="badge err">${esc((LANG==="ja"?"Level 2 は今回見送りました（Level 0 を表示）":"Level 2 skipped; showing Level 0"))}</p>`
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
    if (d.level2 && d.level2.error) { out.innerHTML = `<p class="badge err">${esc((LANG==="ja"?"Level 2 は今回見送りました（Level 0 を表示）":"Level 2 skipped; showing Level 0"))}</p>`; return; }
    out.innerHTML = `<div class="notice-ai"><span class="badge ai">AI · ${esc(d.level2.provider)}</span>
      ${T.aiNotice}</div><pre class="llm">${esc(d.level2.text)}</pre>`;
  } catch (e) {
    console.error(e); out.innerHTML = `<p class="badge err">${esc((LANG==="ja"?"取得を見送りました":"skipped"))}</p>`;
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
    ${r.errors.length ? `<span class="badge err">${esc((LANG==="ja"?"一部の情報源は今回見送りました":"some sources skipped"))}</span>` : ""}</p>`;
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
    console.error(e); out.innerHTML = `<p class="badge err">${esc((LANG==="ja"?"取得を見送りました":"skipped"))}</p>`;
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
    html += `<p class="badge err">${esc((LANG==="ja"?"Level 2 は今回見送りました（Level 0 を表示）":"Level 2 skipped; showing Level 0"))}</p>`;
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
    ok ? resolve() : reject(new Error("clipboard error"));   /* neg-ok: 内部Error・非表示 */
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
  const nb = $("nav-back"), nf = $("nav-fwd");
  if (nb) nb.addEventListener("click", () => navGo(-1));
  if (nf) nf.addEventListener("click", () => navGo(1));
  const pl = $("graph-play");
  if (pl) pl.addEventListener("click", () => gPlayPanel());
  const sh = $("graph-shelf");
  if (sh) sh.addEventListener("click", () => gShelfPanel());
  // 普遍原則: 画面に出した語(.ext-term)はどこでもクリックでサイト内探索へ（行き止まりにしない・
  // copy&pasteを強いない）。パネル/カードのどの語からも第2・第3階層へ自由に広がる。
  bindNoMiss();   // 否定表示を建設的代替へ差し替える委譲ハンドラ（逆側logic・一度だけ）
  if (!document._extTermBound) {
    document._extTermBound = 1;
    document.addEventListener("click", (e) => {
      const t = e.target.closest(".ext-term");
      if (!t) return;
      e.preventDefault();
      const w = t.dataset.w; if (!w) return;
      const r = t.getBoundingClientRect();
      // 「原語による探求」＝正典 term exploration transaction（検索・中心変更と同じ1本）
      dispatchAction("center", { term: w, kind: t.getAttribute("lang") ? "original" : "word", lang: t.getAttribute("lang") },
        currentViewState(), { surface: "text-link", anchor: { x: Math.round(r.left + r.width / 2), y: Math.round(r.bottom + 6) } });
    });
  }
  if (!window._dxResizeBound) {   // viewportが変わっても Context占有領域と Menu/Action の配置を保つ
    window._dxResizeBound = 1;
    window.addEventListener("resize", () => surfSyncLayout());
  }
  if (q) { NAV.stack = [{ q, lens: "all", focus: null, context: null, panel: null, combine: null }]; NAV.idx = 0; navUpdate(); }   // 初期ViewState
  const res = $("origin-results");
  if (res && !res._dimBound) {
    res._dimBound = 1;
    res.addEventListener("click", (e) => {
      const cw = () => (G && G.rootQ) || ((res.dataset && res.dataset.q) || "");
      const b = e.target.closest(".dim");
      if (b && DIMS) { dispatchAction("dimension", { term: cw() }, currentViewState(), { surface: "dimension-card", dm: DIMS[Number(b.dataset.i)] }); return; }
      const th = e.target.closest(".origin-thinker");   // 概念を立てた思想家→経歴・著作・情報源
      if (th) { e.preventDefault(); dispatchAction("author", { term: th.dataset.name, label: th.dataset.name, kind: "author" }, currentViewState(), { surface: "origin-card", search: th.dataset.name }); return; }
      const di = e.target.closest(".origin-discourse");  // この概念の言説を広く調べる（外部・多言語）
      if (di) { e.preventDefault(); dispatchAction("external", { term: di.dataset.q }, currentViewState(), { surface: "origin-card" }); return; }
    });
  }
  if (q) {
    originShellShow(q);   // 初期から操作shell（ナビ＋共通メニュー）を出す（graph成否に依存しない）
    // SEARCH(term) ＝ 正典 term exploration transaction。成功時: グラフ＋中心語=term＋Contextを自動表示、
    // Menu=0・Action=0、履歴commitは1回だけ（Context自動表示で追加commitしない）。
    const t = originClaim(q);
    NAV.txn = true;   // 初期構築中の中間pushを抑止（settle後に初期ViewStateを1件だけ確定させる）
    (async () => {
      try { await originExplore(q, { tok: t, initial: true }); }
      catch (e) { console.error("initial explore", e); }
      finally {
        NAV.txn = false; gBusy(false);
        NAV.stack = [currentViewState()]; NAV.idx = 0; navUpdate();   // 履歴commitは1回だけ
      }
    })();
  }
}

// 探索の履歴（戻る/進む）＝正規 ViewState {q,lens,focus,panel,combine} の履歴。
// 1ユーザー操作＝1 commit（dispatchAction が settle 後に navCommit）。stale/途中失敗/hover は積まない。
const NAV = { stack: [], idx: -1, restoring: false, txn: false };
function navSame(a, b) {
  if (!a || !b) return false;
  return a.q === b.q && a.lens === b.lens && a.focus === b.focus
    && JSON.stringify(a.context || null) === JSON.stringify(b.context || null)
    && JSON.stringify(a.panel || null) === JSON.stringify(b.panel || null)
    && JSON.stringify(a.combine || null) === JSON.stringify(b.combine || null);
}
function navCommit(s) {   // 確定した ViewState を履歴に積む（復元中・トランザクション中は積まない）
  if (typeof s === "string") s = { q: s, lens: "all", focus: null, context: null, panel: null, combine: null };
  if (NAV.restoring || NAV.txn) return;
  if (!s || !s.q) return;
  if (navSame(NAV.stack[NAV.idx], s)) return;
  NAV.stack = NAV.stack.slice(0, NAV.idx + 1); NAV.stack.push(s); NAV.idx = NAV.stack.length - 1;
  navUpdate();
}
function navUpdate() {
  const b = $("nav-back"), f = $("nav-fwd");
  if (b) b.disabled = NAV.idx <= 0;
  if (f) f.disabled = NAV.idx >= NAV.stack.length - 1;
}
async function navGo(d) {
  const i = NAV.idx + d;
  if (i < 0 || i >= NAV.stack.length) return;
  const prevIdx = NAV.idx;                       // 復元失敗時に巻き戻すため元indexを保持（A2）
  NAV.idx = i; navUpdate();
  const s = NAV.stack[i];
  NAV.restoring = true; NAV.txn = true;
  try {
    surfDestroy("menu"); surfDestroy("action"); PANEL_CTX = null;            // 一旦Menu/Actionを閉じる
    surfDestroy("context");                                                 // Contextも一旦閉じる（stateが言えば開き直す）
    if (!G || G.rootQ !== s.q) { await originExplore(s.q, { nav: true, noContext: true }); }   // 中心語を復元
    if (s.combine) { COMBINE_CTX = null; await gCombineRun(s.combine.a, s.combine.b, s.combine.op); }  // 組合せ結果を復元
    else { COMBINE_CTX = null; await applyLensBuild(s.lens || "all"); }      // 見方を復元（focusも一旦解除）
    if (s.focus) {                                                          // 分岐focusを復元（stable ID基準・表示labelでない）
      const idx = (G.nodes || []).findIndex(n => n.kind === "domain" && (n.id === s.focus || n.label === s.focus));
      if (idx >= 0) gFocusSubtree(idx, { nav: true });
    }
    if (s.context) await gPanorama({ term: s.context.term });               // Contextを復元（Mapと一緒に戻る/進む）
    if (s.panel && ACTIONS[s.panel.action]) {                               // Actionを復元（開き直す）
      PANEL_CTX = { action: s.panel.action, term: s.panel.term };
      await ACTIONS[s.panel.action].run(normTarget(s.panel.term), {});
    }
  } catch (e) {                                  // 復元中の失敗＝indexをprevへ巻き戻す（履歴カーソルの真偽を保つ・A2）
    console.error("navGo restore rolled back", e);
    NAV.idx = prevIdx; navUpdate();
  } finally { NAV.restoring = false; NAV.txn = false; }
}
// 処理中インジケータ（選んだ付近に出す・止まって見えないように）
function gBusy(on, text, x, y) {
  const el = $("graph-busy"); if (!el) return;
  if (!on) { el.style.display = "none"; return; }
  el.querySelector(".bt").textContent = text || "探索中…";
  const stage = el.parentElement, r = stage.getBoundingClientRect();
  let cx = (x != null) ? (x - r.left) : stage.clientWidth / 2;
  let cy = (y != null) ? (y - r.top) : stage.clientHeight / 2;
  cx = Math.max(70, Math.min(cx, stage.clientWidth - 70));
  cy = Math.max(26, Math.min(cy, stage.clientHeight - 26));
  el.style.left = cx + "px"; el.style.top = cy + "px";
  el.style.display = "flex";
}

/* ═══════════ 正典 term exploration transaction（半田様2026-08-02）═══════════
   SEARCH（初回ロード）・center（中心に据える）・本文の語リンク（原語による探求）は、すべて
   この1本の transaction を通る。順序を固定する:
     ① target のデータを取得（大小文字などの正規化候補も含めて「構築可能か」を判定する）
     ② 中心ノードと Context を構築可能か確認する
     ③ 成功後にだけ 検索欄・Map・Context・履歴 をまとめて更新（commitは1回）
   構築できない場合:
     空canvasへ遷移しない／検索欄だけ書き換えない／現在の Map + Context を完全保持する／
     取得済みの実データで target の Context または Menu を表示する／捏造しない／否定文言で停止しない。 */
function _termVariants(q) {
  const out = [], add = (s) => { s = String(s || "").trim(); if (s && out.indexOf(s) < 0) out.push(s); };
  add(q);
  try { add(String(q).normalize("NFKC")); } catch (e) {}
  add(String(q).toLowerCase());
  add(String(q).charAt(0).toUpperCase() + String(q).slice(1));
  return out;
}
// ① 取得＋② 構築可能性の確認。構築できた変種のデータを返す（できなければ null）。
async function originResolveGraph(q, tok) {
  for (const v of _termVariants(q)) {
    let d = null;
    try { d = await api(`/api/origin/graph?q=${encodeURIComponent(v)}&lang=${LANG}`); } catch (e) { d = null; }
    if (tok != null && originStale(tok)) return null;
    // rootだけの薄いMapも「構築可能な結果」として採用する。語源形・著者名・
    // 外部sourceが薄い語を、旧Mapを残したままの見かけ上の停止にしない。
    // nodes=[] や layer 1 の無い壊れた応答は、従来どおり復旧面へ送る。
    if (d && Array.isArray(d.nodes) && d.nodes.length >= 1 && d.nodes.some(n => n.layer === 1)) {
      if (d.qid) OZ.qid = d.qid;
      return { data: d, term: d.query || v, asked: q };
    }
  }
  return null;
}
async function originExplore(q, opts) {
  opts = opts || {};
  const tok = (opts.tok != null) ? opts.tok : originClaim(q);
  const jp = LANG === "ja";
  gBusy(true, "「" + q + "」を探索中…", G && G.lastX, G && G.lastY);   // 選んだ付近に処理中を表示
  const res = await originResolveGraph(q, tok);                        // ①②
  if (originStale(tok)) { gBusy(false); return false; }
  if (!res) {
    gBusy(false);
    if (opts.initial) {
      // 初回ロード＝保持すべき Map/Context がまだ無い。空canvasへは遷移させず、操作帯は残し、
      // 取得できた実データで Context を出す（行き止まりにしない・否定文言で停止しない）。
      originShellShow(q);
      graphThin(jp ? `「${q}」は、上の入口からこの語のまま探索を続けられます。`
                   : `Continue exploring “${q}” from the entry points above.`, q);
      // 結果カードの取得を待たず、Contextの読み込み面と常設の次アクションを先に出す。
      // 重い外部源が遅くても、ユーザーの操作面を空白にしない。
      const contextPromise = !opts.noContext
        ? surfaceContextFor(q, null).catch(e => { console.error("context while exploring", e); })
        : null;
      await originRun(q, tok);
      if (contextPromise && !originStale(tok)) await contextPromise;
      return false;
    }
    // 既存の Map + Context を完全保持し、target の標準操作メニューを出す（検索欄も書き換えない）
    const a = opts.anchor || SURF.anchor.menu || surfAnchorDefault();
    gMenu(a.x, a.y, { id: "word:" + q, label: q, q: q, kind: "word", layer: 2 });
    return false;
  }
  // ③ ここから先だけが「成功後の更新」
  const term = res.term;
  const thinResult = res.data.nodes.length === 1;
  const inp = document.querySelector('.searchbox input[name=q]');
  if (inp) inp.value = term;
  originShellShow(term);
  graphThin(null);
  gApplyGraph(res.data);
  if (thinResult) {
    // root-onlyでも主語・カード・履歴は新語へ進める。ただし、情報量の少ない
    // Mapを豊富な地図のように見せず、薄い表示と常設の次入口を残す。
    graphThin(jp ? `「${term}」の地図は薄い状態ですが、この語から探索を続けられます。`
                 : `The map for “${term}” is thin, but exploration can continue from this term.`, term);
  }
  // Mapが構築できた時点でContextの読み込み面を出し、カード取得と並行して次の入口を見せる。
  const contextPromise = !opts.noContext
    ? surfaceContextFor(term).catch(e => { console.error("context while loading", e); })
    : null;
  await originRun(term, tok);
  if (originStale(tok)) { gBusy(false); return false; }
  if (contextPromise) await contextPromise;                  // 検索成功＝Contextを自動表示
  // 中心語の変更はAction/組合せを閉じる文脈。dispatch経由は txn で抑止され、dispatcher が確定commit。
  if (!opts.nav && !opts.initial) { PANEL_CTX = null; COMBINE_CTX = null; navCommit(currentViewState()); }
  gBusy(false);                          // 完了＝インジケータを消す
  const id = opts && opts.scrollTo;
  const el = id && $(id);
  if (el) { el.scrollIntoView({ behavior: "smooth", block: "center" }); return true; }
  if (id) {                 // the requested aspect doesn't exist for THIS word — honest
    const wc = document.querySelector(".word-card");
    if (wc) wc.scrollIntoView({ behavior: "smooth", block: "start" });
    return true;
  }
  if (!opts.initial) window.scrollTo({ top: 0, behavior: "smooth" });
  return true;
}
// UNIVERSAL rule: selecting a word (a node / an in-page link) makes THAT word the
// new subject — the whole exploration (search box, cards, graph) is rebuilt FRESH
// from it. 実体は上の正典 transaction 1本（作用を再実装しない）。
async function originRecenter(q, opts) { return originExplore(q, opts || {}); }

// Attribute string for an internal word link — a new tab (keeping the current
// result) or in-place, per the user's choice (#6: don't silently overwrite).
function originLinkAttr() {
  return (localStorage.getItem("origin_newtab") === "1")
    ? ' target="_blank" rel="noopener"' : "";
}

// ── 逆側logic（半田様2026-07-29）: 「〜できません/見つかりません」の否定表示を絶対に出さない ──
// 予防で塞ぐのは抜け道が残る。そこで、否定を出す条件(＝コードが既に検出している点)をtriggerに、
// 否定文の"代わりに"建設的な代替（この語で今できる探索）を差し込む。全場面・全menuで単一ハンドラに集約。
// これは捏造でない（P6）: 機能の成功を偽らず、実在する別経路へ誘導するだけ。否定語は一切使わない。
function noMiss(term, opts) {
  opts = opts || {};
  const jp = LANG === "ja";
  const lead = opts.lead ? esc(opts.lead) : (jp
    ? `「${esc(term)}」は、次の入り口から探索を続けられます。`
    : `Continue exploring “${esc(term)}” from these entry points.`);
  const acts = [
    ["center", "🎯 " + (jp ? "中心に据えて地図を見る" : "map it")],
    ["lang", "🌍 " + (jp ? "多言語での言い方を見る" : "languages")],
    ["ext", "🌐 " + (jp ? "外部の専門情報で調べる" : "external")],
    ["combine", "🔗 " + (jp ? "別の語と組み合わせる" : "combine")],
    ["lens", "👓 " + (jp ? "別の見方で見る" : "other views")],
    ["history", "🧭 " + (jp ? "翻訳・受容史を追跡する" : "translation / reception history")],
  ];
  return `<div class="nomiss"><p class="nomiss-lead">${lead}</p><div class="nomiss-acts">`
    + acts.map(([a, l]) => `<button type="button" class="nomiss-b" data-a="${a}" data-w="${esc(term)}">${esc(l)}</button>`).join("")
    + `</div></div>`;
}
// パネル内・カード内を問わず、文章だけで終わらせない。softLineも同じ実行可能な入口を返す。
function softLine(term, opts) {
  opts = opts || {};
  const jp = LANG === "ja";
  return noMiss(term, { lead: opts.lead || (jp
    ? `「${term}」は、下の入り口から別の見方で探索を続けられます。`
    : `Continue with “${term}” via the options below.`) });
}
// nomiss ボタンの委譲ハンドラ（一度だけbind）。どのパネル/グラフ領域に現れても同じ作用（普遍）。
function bindNoMiss() {
  if (document._noMissBound) return;
  document._noMissBound = 1;
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest(".nomiss-b"); if (!btn) return;
    e.preventDefault();
    const a = UI_ACTION_MAP.nomiss[btn.dataset.a], w = btn.dataset.w; if (!w || !a) return;
    if (btn.disabled || btn.dataset.running === "1") return;
    const group = btn.closest(".nomiss-acts");
    if (group) group.querySelectorAll(".nomiss-b").forEach(x => { x.disabled = true; x.dataset.running = "1"; });
    const r = btn.getBoundingClientRect();
    try {
      await dispatchAction(a, { term: w }, currentViewState(), { surface: "nomiss", anchor: { x: Math.round(r.left + r.width / 2), y: Math.round(r.bottom + 6) } });   // 単一Dispatcher経由（作用を再実装しない）
    } catch (err) {
      console.error("nomiss action", err);
    } finally {
      if (group && group.isConnected) group.querySelectorAll(".nomiss-b").forEach(x => { x.disabled = false; delete x.dataset.running; });
    }
  });
}

/* ═══════════ A3 自動代替（否定条件→同一操作内で別源を実走行）═══════════
   API系Actionが空/エラー（否定Outcome）になったとき、同じユーザー操作の中で、その作用に適した
   代替源を「実際に取得」して出所+取得時刻つきで示す。softLine（入口リンク表示）だけでは代替の
   「実行」にならない（半田様A3）。履歴は増やさない（dispatchActionが操作末で1回commitするだけ）。 */
let FALLBACK_LOG = [];   // 自動代替の発火ログ（E2E/最終報告が実発火を確認できる外部証跡）
function logFallback(word, kind, altSource, outcome) {
  const rec = { word, kind, alt: altSource, outcome, at: new Date().toISOString() };
  FALLBACK_LOG.push(rec); if (FALLBACK_LOG.length > 80) FALLBACK_LOG.shift();
  try { console.log("FALLBACK " + JSON.stringify(rec)); } catch (e) {}
}
function _nowStamp() { try { return new Date().toISOString(); } catch (e) { return ""; } }
// /api/origin の実データから代替表示（Wikidata記事＋多言語breadth・意味）。捏造しない・空なら空を返す。
function altFromOrigin(o, word) {
  const jp = LANG === "ja"; let h = ""; if (!o) return "";
  const gm = (o.general_meaning || []).slice(0, 5);
  if (gm.length) h += `<ul class="gp-ul">${gm.map(s => `<li>${esc(s.length > 200 ? s.slice(0, 200) + "…" : s)}</li>`).join("")}</ul>`;
  h += segmentLayersHtml(o.segment_layers, { includeCharacter: true });
  const br = (o.breadth || []).slice(0, 24);
  if (br.length) h += `<div class="breadth-chips">` + br.map(b => `<span class="breadth-chip">${esc(b.name)}${b.term ? "：<a href=\"#\" class=\"ext-term\" data-w=\"" + esc(b.term) + "\">" + esc(b.term) + "</a>" : ""}</span>`).join("") + `</div>`;
  const co = (o.concept_origin || []).slice(0, 6);
  if (co.length) h += `<p class="srcline">${jp ? "原語の候補：" : "originals: "}${co.map(x => `<a href="#" class="ext-term" data-w="${esc(x.term)}">${esc(x.term)}</a>${x.name ? "（" + esc(x.name) + "）" : ""}`).join("　")}</p>`;
  return h;
}
// /api/anatomy の実データから代替表示（Wiktionaryの構成要素・変容連鎖）。
function altFromAnatomy(a, word) {
  const jp = LANG === "ja"; let h = ""; if (!a || !a.term) return "";
  h += segmentLayersHtml(a.segment_layers, { includeCharacter: false });
  if ((a.components || []).length) h += `<div class="anat-comp">` + a.components.map(c => `<span class="anat-part"><a href="#" class="ext-term" data-w="${esc(c.part)}" lang="grc">${esc(c.part)}</a>＝${esc(c.meaning)}</span>`).join(`<span class="anat-plus">＋</span>`) + `</div>`;
  if ((a.chain || []).length) h += `<div class="chain">` + a.chain.map(c => `<span class="chain-step"><span class="chain-lang">${esc(c.lang)}</span><a href="#" class="ext-term chain-form" data-w="${esc(c.term)}">${esc(c.term)}</a>${c.gloss ? `<span class="anat-gloss">「${esc(c.gloss)}」</span>` : ""}</span>`).join("<span class=\"chain-arrow\">←</span>") + `</div>`;
  if (a.summary) h += `<p class="anat-summary">${esc(a.summary.length > 300 ? a.summary.slice(0, 300) + "…" : a.summary)}</p>`;
  return h;
}
// kind ごとの代替経路＝「その操作で既に試したendpointは使わない」（虚偽の切替を出さないための鍵・半田様2026-07-30）。
//   meaning/breadth/collapse は gWordAspect が最初に /api/origin を使う → 代替は未試行の /api/anatomy。
//   anatomy は最初に /api/anatomy → 代替は未試行の /api/origin（維持）。
//   colloc は /api/origin(独語解決)＋/api/collocations を試す → 代替は未試行の /api/anatomy。
//   contrast は /api/origin＋/api/anatomy を両方試済 → 未試行の第三経路が無い＝null（再利用しない）。
const _ALT_FOR = { meaning: "anatomy", breadth: "anatomy", collapse: "anatomy", anatomy: "origin", colloc: "anatomy", contrast: null };
// 表示する出所は内部endpoint名でも推測既定値でもなく、応答が実際に接地している提供元だけにする（P6・捏造禁止）。
// 応答の sources[] の公開提供元名と、応答が明示するURLフィールド（wiktionary_url/wikidata_url/article_url=Wikipedia）
// から確定できる提供元のみを採る。内部集約id（concept-node 等）は公開提供元名でないので採らない。確定できなければ空。
function _providerLabel(ep, data) {
  const names = [];
  const add = (n) => { if (n && !names.includes(n)) names.push(n); };
  for (const s of ((data && data.sources) || [])) {
    if (!s || s.error) continue;
    const id = String(s.source || "");
    if (/wiktionary/i.test(id)) add("Wiktionary");
    else if (/wikipedia/i.test(id)) add("Wikipedia");
    else if (/wikidata/i.test(id)) add("Wikidata");
    // concept-node 等の内部idは推測で提供元名にしない
  }
  if (data) {
    if (data.wiktionary_url) add("Wiktionary");
    if (data.wikidata_url) add("Wikidata");
    if (data.article_url) add("Wikipedia");   // /api/origin の article_url は Wikipedia 記事
  }
  return names.join("・");   // 確定できなければ空文字（提供元名を捏造しない）
}
// 否定Outcome時に実走行する自動代替。body（パネル本体）へ実データ＋実提供元+取得時刻を書き、続行フッターも残す。
// 未試行の第三経路が無い kind（contrast）は、虚偽の切替文言を出さず、既存の続行操作を直ちに表示する（P6）。
async function autoFallback(word, kind, body) {
  const jp = LANG === "ja";
  const ep = _ALT_FOR.hasOwnProperty(kind) ? _ALT_FOR[kind] : "origin";
  let html = "", outcome = ep ? "empty" : "no-alt", provider = "", retrieved = "";
  if (ep) {
    try {
      if (ep === "anatomy") {
        const a = await api(`/api/anatomy?q=${encodeURIComponent(word)}&lang=${LANG}`);
        html = altFromAnatomy(a, word); provider = _providerLabel("anatomy", a); retrieved = (a && a.queried_at) || "";
      } else {
        const o = await api(`/api/origin?q=${encodeURIComponent(word)}&lang=${LANG}`);
        html = altFromOrigin(o, word); provider = _providerLabel("origin", o); retrieved = (o && o.queried_at) || "";
      }
      outcome = html ? "success" : "empty";
    } catch (e) { outcome = "error"; console.error("autoFallback", e); }
  }
  logFallback(word, kind, ep ? ("/api/" + ep) : "(none)", outcome);
  if (html && body) {   // 実データが取れた時だけ「切替えた」と言う（切替文言は実取得に接地する）
    // 出所・取得時刻は応答から確定できたものだけを出す（推測・既定値は出さない＝捏造禁止・P6・半田様2026-07-30）
    const parts = [];
    if (provider) parts.push((jp ? "出所：" : "source: ") + esc(provider));
    if (retrieved) parts.push((jp ? "取得時刻：" : "retrieved: ") + esc(retrieved));
    const srcline = parts.length
      ? `<p class="srcline">${jp ? "自動代替（" : "auto-fallback ("}${parts.join(jp ? "／" : ", ")}${jp ? "）" : ")"}</p>`
      : `<p class="srcline">${jp ? "自動代替" : "auto-fallback"}</p>`;
    body.innerHTML = `<div class="fallback"><p class="fb-note">${jp ? "主要な源では十分な結果が得られなかったため、別の情報源に自動で切り替えて取得しました。" : "Auto-switched to an alternative source."}</p>${html}${srcline}</div>`
      + softLine(word);
  } else if (body) {
    body.innerHTML = `<p class="fb-note">${jp ? "主要な情報源と代替経路から表示できるデータが返らなかったため、結果を作らず次の入口を残します。" : "No grounded data was returned from the primary or alternative source; the next entry points remain available."}</p>`
      + softLine(word);   // 第三経路なし/空/失敗＝虚偽の切替文言を出さず、続行操作を直ちに表示（捏造で埋めない・P6）
  }
  return outcome;
}

/* ═══════════ 共通操作基盤（半田様2026-07-29: 操作/状態遷移/失敗継続の単一基盤）═══════════
   全ての選択可能項目を ExplorationTarget へ正規化し、全ての普遍操作を ACTIONS registry に集約し、
   全ての表示面（上部帯・ノードpopup・パネルフッター・noMiss・本文語リンク）を dispatchAction の
   単一経路に通す。表示面ごとに作用を再実装しない。状態変更関数の直接呼び出しは ACTIONS.run に閉じる。 */

// すべての選択可能項目を1つの正規化対象へ（語/原語/関連語/言語/人物名を同じ基盤へ渡せる形）
function normTarget(t) {
  if (t == null) t = {};
  if (typeof t === "string") t = { term: t };
  const term = String(t.term || t.q || t.label || "").trim();
  return {
    term, label: t.label || term, kind: t.kind || "word", lang: t.lang || null,
    id: t.id || ((t.kind ? t.kind : "t") + ":" + term),
    surface: t.surface || null, layer: (t.layer != null ? t.layer : null),
  };
}

// 現在開いているパネル/組合せ（ViewStateに含める確定状態＝戻る/進むで復元）
let PANEL_CTX = null;    // { action, term } ＝ Action面
let CONTEXT_CTX = null;  // { term }         ＝ Context面（右側の概念全景・永続）
let COMBINE_CTX = null;  // { a, b, op }
let _lastDispatch = null; // 最後に dispatch した {actionId, target, surface, effect, seq, outcome}（操作同値性テスト用）
let _dispatchSeq = 0;     // dispatch の単調増加連番（同じ操作の反復も外部から区別できる）

/* ═══════════ 表示面の中央管理（Surface Manager・半田様2026-08-02）═══════════
   面は3種に固定する:
     Context (#dx-context)  右側の概念全景。×で閉じるか別全景へ置換するまで残る（永続）。
     Menu    (#graph-menu)  選択語の標準操作メニュー。
     Action  (#graph-panel) 意味・解剖・比較・多言語等の操作結果。
   create / replace / destroy / place をここへ集約する（各関数が個別に document.body.appendChild /
   remove しない）。不変条件:
     ・Menu と Action は排他で合計1個まで／同種を積層しない
     ・後から開いた面が古い面の背後に出ない（DOM順とz-indexの両方をmanagerが保証）
     ・Menu / Action は Context の占有領域と矩形交差0・全体がviewport内・超過分は面内部スクロール
   個別の語・個別Actionごとの座標指定は禁止（配置は surfPlace だけが行う）。 */
const SURFACE_ID = { context: "dx-context", menu: "graph-menu", action: "graph-panel" };
const SURF_MARGIN = 8;
const SURF = { z: 200, anchor: { menu: null, action: null }, menuCloser: null };

function surfEl(kind) { return document.getElementById(SURFACE_ID[kind]); }
function surfRect(kind) {
  const el = surfEl(kind); if (!el) return null;
  const r = el.getBoundingClientRect();
  return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height };
}
// Context が占有していない利用可能領域（viewport座標）。Menu/Action はこの中だけに置く。
function surfAvail() {
  const box = { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight };
  const r = surfRect("context");
  if (r && r.width > 0 && r.height > 0) {
    if (r.right >= window.innerWidth - 2) box.right = Math.max(0, r.left);        // 右ドック
    else if (r.left <= 2) box.left = Math.min(box.right, r.right);                // 左ドック（将来）
  }
  return box;
}
function surfAnchorDefault() {
  const av = surfAvail();
  return { x: (av.left + av.right) / 2, y: av.top + Math.min(120, Math.max(40, (av.bottom - av.top) / 4)) };
}
// 面の配置。Context は右ドック（CSS）。Menu/Action は利用可能領域内へ収める。
function surfPlace(kind) {
  const el = surfEl(kind); if (!el || kind === "context") return;
  const av = surfAvail();
  const availW = Math.max(200, av.right - av.left - SURF_MARGIN * 2);
  const availH = Math.max(160, av.bottom - av.top - SURF_MARGIN * 2);
  el.style.position = "fixed";
  el.style.transform = "none";
  el.style.right = "auto"; el.style.bottom = "auto";
  el.style.boxSizing = "border-box";
  el.style.maxWidth = availW + "px";
  el.style.maxHeight = availH + "px";      // 高さがviewportを超えるときは面内部をスクロール可能に
  el.style.overflowY = "auto";
  el.style.overflowX = "hidden";
  const w = Math.min(el.offsetWidth || 300, availW);
  el.style.width = w + "px";
  const a = SURF.anchor[kind] || surfAnchorDefault();
  let x = a.x + 20;
  if (x + w > av.right - SURF_MARGIN) x = a.x - w - 20;
  x = Math.max(av.left + SURF_MARGIN, Math.min(x, av.right - w - SURF_MARGIN));
  let y;
  if (kind === "action") {
    y = av.top + SURF_MARGIN;              // Actionは内容が後から伸びる＝上端固定＋maxHeightで必ず収まる
  } else {
    const h = Math.min(el.offsetHeight || 200, availH);
    y = Math.max(av.top + SURF_MARGIN, Math.min(a.y - 12, av.bottom - h - SURF_MARGIN));
  }
  el.style.left = Math.round(x) + "px";
  el.style.top = Math.round(y) + "px";
}
// Context の占有幅をページ本体へ反映（地図がドロワーの下に隠れない＝実クリック座標が常に有効になる）
function surfSyncLayout() {
  const r = surfRect("context");
  const w = r ? Math.round(r.width) : 0;
  document.body.style.paddingRight = w ? w + "px" : "";
  if (typeof gResize === "function") gResize();
  surfPlace("menu"); surfPlace("action");
}
function surfDestroy(kind) {
  const el = surfEl(kind); if (!el) return false;
  if (kind === "menu") {
    if (SURF.menuCloser) { document.removeEventListener("pointerdown", SURF.menuCloser); SURF.menuCloser = null; }
    if (G) G.menuNode = null;
  }
  el.remove();
  if (kind === "context") { CONTEXT_CTX = null; surfSyncLayout(); }
  return true;
}
// Action を閉じる＝「Action無し」も1つの確定状態（A2）。PANEL_CTXを消して1回だけcommitする。
function surfCloseAction(commit) {
  const had = surfDestroy("action");
  if (had && PANEL_CTX) { PANEL_CTX = null; if (commit && !NAV.txn && !NAV.restoring) navCommit(currentViewState()); }
  return had;
}
function surfCreate(kind, el, anchor) {
  if (kind === "menu") { surfCloseAction(true); surfDestroy("menu"); }              // Menu/Action は排他
  else if (kind === "action") { surfDestroy("menu"); surfDestroy("action"); }       // 同種は積層しない
  else if (kind === "context") { surfDestroy("menu"); surfCloseAction(true); surfDestroy("context"); }
  el.id = SURFACE_ID[kind];
  el.classList.add("dx-surface");
  document.body.appendChild(el);          // DOM順で常に最後＝後から開いた面が古い面の背後に出ない
  el.style.zIndex = String(++SURF.z);     // z-indexでも最前面
  if (kind === "context") surfSyncLayout();
  else { SURF.anchor[kind] = anchor || SURF.anchor[kind] || surfAnchorDefault(); surfPlace(kind); }
  return el;
}

// ── Action registry ────────────────────────────────────────────────────────────
// 各Actionは effect（面への作用）を**宣言**する。テストは文言から推測せず registry と照合する。
//   context = Contextを置換（Menu/Actionを閉じる）
//   center  = Map中心を移し Context を同じ語へ更新
//   map     = 地図を描き替える（Contextは保持）
//   action  = Contextを保持し Action を置換
//   store   = 宣言された保存状態のみ（面を変えない）
//   newpage = 新規ページを開く（元画面のContext・履歴を変えない）
const EFFECTS = ["context", "center", "map", "action", "store", "newpage"];
// Action ID → 正規作用。run は状態変更関数（originRecenter/gWordAspect/…）を呼ぶ唯一の場所。
const ACTIONS = {
  center:       { label: "中心に据える", effect: "center", changesCenter: true, run: (t, ctx) => originRecenter(t.term, { anchor: ctx && ctx.anchor }) },
  meaning:      { label: "意味", effect: "action", run: (t) => gWordAspect(t.term, "meaning") },
  multilingual: { label: "多言語", effect: "action", run: (t) => gWordAspect(t.term, "breadth") },   // 中心を変えない（Aの是正・全入口統一）
  collapse:     { label: "埋没原語", effect: "action", run: (t) => gWordAspect(t.term, "collapse") },
  translationHistory: { label: "翻訳・受容史", effect: "action", run: (t) => gTranslationHistoryPanel(t.term) },
  anatomy:      { label: "解剖", effect: "action", run: (t) => gAnatomyPanel(t.term) },
  contrast:     { label: "並置", effect: "action", run: (t) => gContrastPanel(t.term) },
  colloc:       { label: "共起", effect: "action", run: (t) => gColloc(t.term) },
  lens:         { label: "見方", effect: "action", run: (t) => gLensMenu(t.term) },   // 見方の一覧＝Action、適用は applyLens
  // 見方の適用は条件付き作用（宣言を実装に一致させる・A3）: 対象語が既に中心なら地図の描き替えだけ（map・
  // Contextは保持）、中心でない語なら applyLensFor が先に再中心するので中心語とContextが変わる（center）。
  applyLens:    { label: "見方を適用", effect: "map", effectWithArg: "center", arg: "recenter",
                  run: (t, ctx) => applyLensFor(t.term, ctx.lensKey) },
  // 語入力フォーム＝Action／第2語(b)を伴う実行＝地図の置換（effectWithArg で宣言）
  combine:      { label: "組み合わせ", effect: "action", effectWithArg: "map", arg: "b",
                  run: (t, ctx) => (ctx && ctx.b)
                    ? gCombineRun(t.term, ctx.b, ctx.op || "and")
                    : gCombinePanel(t.term, (ctx && ctx.retryB) || "", (ctx && ctx.retryOp) || "and") },
  external:     { label: "外部で調べる", effect: "action", newPage: true, transient: true, commits: false, run: (t) => gExtPanel(t.term) },
  shelf:        { label: "棚に追加", effect: "store", commits: false, run: (t) => shelfAdd(t.term) },
  deepsearch:   { label: "深掘り", effect: "action", run: (t) => gPerspectivePanel(t.term) },
  newtab:       { label: "新タブ", effect: "newpage", transient: true, commits: false, run: (t) => {
    const w = window.open(`/origin?q=${encodeURIComponent(t.term)}&lang=${LANG}`, "_blank");
    return !!w;   // popup blocker等で開けない時はdispatcherがMenuを再提示する
  } },
  author:       { label: "著者を調べる", effect: "action", run: (t, ctx) => gAuthorInvestigate((ctx && ctx.search) || t.term, t.label) },
  authorNote:   { label: "系譜メモ", effect: "action", run: (t, ctx) => gAuthorPanel((ctx && ctx.node) || { label: t.label }) },
  dimension:    { label: "探究の次元", effect: "action", run: (t, ctx) => gDimAct(ctx.dm) },   // 探究の次元カード（.dim）
  panorama:     { label: "概念全景", effect: "context", run: (t, ctx) => gPanorama({ term: t.term, node: ctx && ctx.node, secHint: ctx && ctx.secHint }) },
  focus:        { label: "この分岐を中心に", effect: "map", run: (t, ctx) => gFocusSubtree(ctx.nodeIdx) },
  hl:           { label: "経路を強調", effect: "map", run: (t, ctx) => { G.hl = gHl(ctx.nodeIdx); gDraw(); } },
  resetFocus:   { label: "全体に戻す", effect: "map", run: () => { if (G) return originGraph(G.rootQ); } },
};
// 各表示面が使う Action ID の宣言（テストが registry と照合し「未宣言のユーザー操作」を0にする）。
// 実装側の各面はこの定義を参照する（文言から推測しない・面ごとに作用を再実装しない）。
const UI_ACTION_MAP = {
  panelFooter: { center: "center", lens: "lens", lang: "multilingual", ext: "external", combine: "combine", history: "translationHistory", new: "newtab" },
  nomiss:      { center: "center", lang: "multilingual", ext: "external", combine: "combine", lens: "lens", history: "translationHistory" },
};
const UI_ACTION_IDS = {
  topbar:      null,   // gActions（中心語）— 実行時に列挙
  popup:       null,   // gActions（選択ノード）— 実行時に列挙
  edge:        ["hl", "focus", "combine", "deepsearch", "center", "resetFocus"],
  node:        ["panorama"],
  panelFooter: Object.values(UI_ACTION_MAP.panelFooter),
  nomiss:      Object.values(UI_ACTION_MAP.nomiss),
  lensMenu:    ["applyLens"],
  textLink:    ["center"],
  card:        ["dimension", "author", "external"],
  play:        ["center", "combine"],
  shelfPanel:  ["shelf", "center", "combine"],
  scrollCard:  ["center"],
  contextEnt:  ["panorama"],   // Context内の実体クリック＝標準メニューを開く（対象はそのentity）
};

function _activeTerm(fallback) {
  const input = document.querySelector('.searchbox input[name="q"]');
  return String(fallback || (G && G.rootQ) || (input && input.value) || "").trim();
}

// 非同期Actionが予期せず失敗しても、空の面だけを残さない。失敗理由はコンソールに記録し、
// ユーザーには同じ語から再開できる実行可能な入口を必ず残す。
function _dispatchRecovery(t, eff, ctx, actionId) {
  const term = _activeTerm(t && t.term);
  if (!term) return;
  const jp = LANG === "ja";
  const actionLabel = (ACTIONS[actionId] && ACTIONS[actionId].label) || (actionId || "選択した操作");
  const lead = jp
    ? `「${term}」から、次の操作を選んで探索を続けられます。`
    : `Continue exploring “${term}” from the next actions.`;
  const bodyHtml = `<p class="muted">${esc(jp
    ? `操作結果：${actionLabel}。外部情報の取得・入力条件・画面構築のいずれかに追加確認が必要です。元のMapとContextは保持しました。`
    : `Result: ${actionLabel}. The external source, input condition, or view construction needs another check. The current map and context were kept.`)}</p>${noMiss(term, { lead })}`;

  if (eff === "action") {
    const p = surfEl("action");
    if (p && p.querySelector(".gp-body")) {
      p.querySelector(".gp-body").innerHTML = bodyHtml;
      surfPlace("action");
    } else {
      PANEL_CTX = null;
      try { gPanel(jp ? "探索を続ける" : "Continue exploring", bodyHtml, term); } catch (e) { console.error("action recovery panel", e); }
    }
    PANEL_CTX = null;   // recovery面は一時面。途中状態を履歴の確定状態として残さない。
    gToast(jp
      ? `「${actionLabel}」の確認項目と、同じ語から続ける操作を表示しました。`
      : `The check items and next actions for “${actionLabel}” are shown.`);
    return;
  }

  if (eff === "context") {
    const p = surfEl("context");
    if (p && p.querySelector(".gp-body")) {
      p.querySelector(".gp-body").innerHTML = bodyHtml;
      CONTEXT_CTX = { term };
      gToast(jp
        ? `「${actionLabel}」の確認項目と、同じ語から続ける操作を表示しました。`
        : `The check items and next actions for “${actionLabel}” are shown.`);
      return;
    }
    try {
      const cp = _panoShell(term, term);
      cp.querySelector(".gp-body").innerHTML = bodyHtml;
      CONTEXT_CTX = { term };
      gToast(jp
        ? `「${actionLabel}」の確認項目と、同じ語から続ける操作を表示しました。`
        : `The check items and next actions for “${actionLabel}” are shown.`);
      return;
    } catch (e) { console.error("context recovery panel", e); }
  }

  // center/map/newpage の失敗は、現在の地図やContextを消さず、対象語の標準Menuを再提示する。
  const a = (ctx && ctx.anchor) || SURF.anchor.menu || surfAnchorDefault();
  gToast(jp
    ? `「${actionLabel}」を確定できなかったため、元の画面を保持してMenuを再表示しました。`
    : `“${actionLabel}” could not be completed; the current screen was kept and the Menu was restored.`);
  if (!surfEl("menu")) {
    gMenu(a.x, a.y, { id: t.id || ("word:" + term), label: t.label || term, q: term,
      kind: t.kind || "word", lang: t.lang || null, layer: t.layer == null ? 2 : t.layer });
  }
  gToast(jp
    ? `「${actionLabel}」の結果面を確定するため、確認項目と次の操作を表示しました。`
    : `The check items and next actions for “${actionLabel}” are shown.`);
}

// 単一Dispatcher: どの表示面も (actionId, target) だけを渡す。中間push抑止→settle後に一度だけcommit。
async function dispatchAction(actionId, target, currentState, surfaceContext) {
  const a = ACTIONS[actionId];
  if (!a) {
    console.error("unknown action", actionId);
    const t0 = normTarget(target);
    _dispatchRecovery(t0, "map", surfaceContext || {}, actionId);
    return { ok: false, outcome: "unknown", actionId, target: t0 };
  }
  if (!a.effect || EFFECTS.indexOf(a.effect) < 0) {
    console.error("undeclared effect", actionId);
    const t0 = normTarget(target);
    _dispatchRecovery(t0, "map", surfaceContext || {}, actionId);
    return { ok: false, outcome: "undeclared", actionId, target: t0 };
  }
  const t = normTarget(target); t.surface = (surfaceContext && surfaceContext.surface) || t.surface;
  const ctx = surfaceContext || {};
  const eff = (a.effectWithArg && a.arg && ctx[a.arg]) ? a.effectWithArg : a.effect;
  _lastDispatch = { actionId, target: t, surface: t.surface, effect: eff, seq: ++_dispatchSeq, outcome: "running" };   // seq＝同一操作の反復も区別できる単調増加
  const prevPanel = PANEL_CTX, prevCombine = COMBINE_CTX, prevContext = CONTEXT_CTX;   // 失敗時に元へ戻す（A2）
  if (eff === "action") { PANEL_CTX = a.transient ? null : { action: actionId, term: t.term }; }   // run が surfCreate で置換する
  else if (eff === "store" || eff === "newpage") { /* 現在の画面の面も履歴も変えない */ }
  else { PANEL_CTX = null; surfDestroy("action"); }   // context / center / map は Action を確実に閉じる（面と状態を一致させる）
  NAV.txn = true;
  let ok = true, runResult;
  try { runResult = await a.run(t, ctx); }
  catch (e) { ok = false; console.error("action error", actionId, e); }
  finally {
    NAV.txn = false;
    _lastDispatch.outcome = !ok ? "error" : (runResult === false ? "fallback" : "success");
  }
  if (!ok) {                                       // 予期せぬ失敗＝存在しない確定状態をcommitしない（A2）
    PANEL_CTX = eff === "action" ? prevPanel : null;
    COMBINE_CTX = prevCombine; CONTEXT_CTX = prevContext;
    _dispatchRecovery(t, eff, ctx, actionId);
    return { ok: false, outcome: "error", actionId, target: t };
  }
  if (runResult === false) {                       // 構築不能時も入口を残し、履歴へはcommitしない
    // run 自身が理由つきの結果面を構築した場合、それを Menu の汎用復旧面で
    // 上書きしない。失敗後の説明と同じ条件での再実行入口を保持する。
    if (!surfEl("menu") && !surfEl("action") && !surfEl("context")) _dispatchRecovery(t, eff, ctx, actionId);
    gToast(LANG === "ja"
      ? `「${a.label}」の結果説明と、同じ語から続ける操作を表示しました。`
      : `The result explanation and next actions for “${a.label}” are shown.`);
    return { ok: true, outcome: "fallback", actionId, target: t };
  }
  if (a.commits === false) {
    gToast(LANG === "ja" ? `「${a.label}」を実行しました。` : `“${a.label}” executed.`);
    return { ok: true, outcome: "success", actionId, target: t };  // 棚・新タブ・外部リンク集は状態遷移でない
  }
  navCommit(currentViewState());                   // 1ユーザー操作＝1回のcommit（確定状態）
  gToast(LANG === "ja" ? `「${a.label}」を実行しました。次の操作を選べます。` : `“${a.label}” executed. Choose the next action.`);
  return { ok: true, outcome: "success", actionId, target: t };
}

// 正規 ViewState（復元に必要な確定状態のみ。hover/loading等の一時状態は含めない）
function currentViewState() {
  return {
    q: (G && G.rootQ) || null,
    lens: G_lens || "all",
    focus: (G && (G.focusId || G.focusLabel)) || null,   // stable ID優先（表示labelはfallback・A2）
    context: CONTEXT_CTX ? { term: CONTEXT_CTX.term } : null,
    panel: PANEL_CTX ? { action: PANEL_CTX.action, term: PANEL_CTX.term } : null,
    combine: COMBINE_CTX ? { a: COMBINE_CTX.a, b: COMBINE_CTX.b, op: COMBINE_CTX.op } : null,
  };
}
// SEARCH / center 成功時の Context 自動表示（履歴は呼び元が1回だけ commit する）
async function surfaceContextFor(term, node) {
  if (!term) return;
  await gPanorama({ term, node: node || (G && (G.nodes || []).find(n => n.layer === 1)) || null });
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
  { key: "spheres", label: "文化圏", en: "Cultural spheres", mode: "lazy-graph", endpoint: "/api/culture",
    cap: "欧／漢字圏／日本／その他で束ねる。日本圏は国立国会図書館の国内文献も（受容史）。重力場が変わる。" },
  { key: "applications", label: "応用・波及", en: "Applications", mode: "lazy-graph", endpoint: "/api/applications",
    cap: "応用（主題とする作品＝文学・芸術・映画）と、波及（結びつく思想・体制・運動＝資本論→共産主義/マルクス経済学…）。クリックでその語へ。" },
  { key: "usage", label: "使用例・引用", en: "Usage", mode: "cards", endpoint: "/api/usage",
    cap: "この語が実テキスト（学術）で実際にどう使われたか。出典つきの引用カード（賛否は判定しない）。" },
  { key: "era", label: "時代・変遷", en: "Over time", mode: "timeline", endpoint: "/api/timeline",
    cap: "原語がいつ現れ・広まり・衰退し・再評価されたか（Google Books Ngram・書物コーパス）。" },
  { key: "gravity", label: "重力探索", en: "Gravity (web)", mode: "lazy-graph", endpoint: "/api/gravity",
    cap: "一般ウェブの頻度×意味（Wikidataの思想家・関連概念）のハイブリッド重力。重い領域（例 リゾーム→哲学/植物）をAND検索で次階層へ展開。意味一致は大きく・先に。件数だけでない。" },
  { key: "websearch", label: "一般ウェブ", en: "Web search", mode: "cards", endpoint: "/api/websearch",
    cap: "一般ウェブ検索（SearXNG＝Google等を束ねる自前メタ検索・鍵不要）。Wikipedia系の背骨に対し一般の広さ。順位はエンジン由来・新タブ。" },
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
  const keep = new Set(), nodes = [];
  if (root) { keep.add(root.id); nodes.push({ ...root }); }
  d.nodes.filter(n => L.kinds.includes(n.kind)).forEach(n => { keep.add(n.id); nodes.push({ ...n }); });
  // 元の枝を保つ＝思想家→著作の階層／思想家どうしの関係線（P737）を残す（星型に潰さない）
  const edges = d.edges.filter(e => keep.has(e.from) && keep.has(e.to)).map(e => ({ ...e }));
  // 入ってくる枝の無いノードだけ語に結ぶ（浮かせない・関係のある者は関係線で繋がったまま）
  if (root) nodes.forEach(n => {
    if (n.id !== root.id && !edges.some(e => e.to === n.id)) edges.push({ from: root.id, to: n.id, strength: 0.6 });
  });
  return { query: d.query, note: L.cap, nodes, edges };
}

function lensLeafCount(d, L) {
  return L.kinds ? d.nodes.filter(n => L.kinds.includes(n.kind)).length : d.nodes.length;
}

// 上部の帯 ＝ 中心語の「共通メニュー パッケージ」を常時表示（案C・普遍性）。中心語も他ノードと
// 全く同じ gActions を使う＝どの語でも同じUI。0だらけのレンズ帯は廃止（レンズは👓見方の中）。
function renderTopMenu(d) {
  const el = $("graph-lens"); if (!el) return;
  const jp = LANG === "ja";
  const rootNode = { kind: "word", label: d.query, q: d.query };
  const items = gActions(rootNode);
  el._items = items; el._word = d.query;
  el.innerHTML = `<span class="tm-label" title="${jp ? "この中心語のメニュー。どのノードをクリックしても同じ操作が出ます（普遍）。" : "menu of the centre word; every node offers the same"}">◉ ${esc(d.query)}</span>`
    + `<button type="button" class="tm-view" id="tm-view" title="${jp ? "今この地図を描いている見方（menu）。クリックで別の見方に切り替え。" : "the view this map is drawn from; click to switch"}"></button>`
    + items.map((it, i) => `<button type="button" class="tm-chip" data-i="${i}" title="${esc(it.t)}">${esc(it.s || it.t)}</button>`).join("");
  el.querySelectorAll(".tm-chip").forEach(b => b.addEventListener("click", () => {
    const it = el._items[+b.dataset.i]; if (!it) return;
    dispatchAction(it.action, it.target, currentViewState(), { surface: "topbar", ...(it.ctx || {}) });
  }));
  const vb = $("tm-view"); if (vb) vb.addEventListener("click", () => dispatchAction("lens", { term: el._word }, currentViewState(), { surface: "topbar" }));
  updateViewBadge(G_lens);   // 現在の見方を表示（初期は俯瞰）
}

// 「今この地図が何の見方（menu）で描かれているか」を常時表示（半田様指摘: 生成元が画面に無い）。
function updateViewBadge(key) {
  const Lz = LENSES.find(x => x.key === key) || LENSES[0];
  const vb = $("tm-view"); if (!vb) return;
  vb.textContent = (LANG === "ja" ? "◉ 今の見方：" : "◉ view: ") + (LANG === "ja" ? Lz.label : Lz.en) + " ▾";
}

function setActiveChip(key) {   // 現在の見方（レンズ）を上部バッジ＋graph-note に反映（旧レンズ帯は廃止）
  updateViewBadge(key);
  const Lz = LENSES.find(x => x.key === key), note = $("graph-note");
  if (Lz && note) note.textContent = (LANG === "ja" ? "見方：" : "view: ") + (LANG === "ja" ? Lz.label : Lz.en) + " — " + (Lz.cap || "");
}
// グラフ描画（canvas）と専用描画（#graph-alt: カード/チャート）の切替。altに入る時は描画ループを止める。
function showCanvas() { const c = $("origin-graph"), a = $("graph-alt"); if (c) c.style.display = "block"; if (a) { a.style.display = "none"; a.innerHTML = ""; } }
function showAlt() { const c = $("origin-graph"), a = $("graph-alt"); if (G && G.raf) { cancelAnimationFrame(G.raf); G.running = false; } if (c) c.style.display = "none"; if (a) a.style.display = "block"; }

async function applyLensBuild(key) {
  if (!G_raw) return;
  G_lens = key; setActiveChip(key);
  const L = LENSES.find(x => x.key === key) || LENSES[0];
  const jp = LANG === "ja", note = $("graph-note");
  const vlabel = (jp ? "見方：" : "view: ") + (jp ? L.label : L.en);   // アクティブな見方を常に明示（旧レンズchipのon表示の代替）
  const setNote = t => { if (note) note.textContent = vlabel + (t ? " — " + t : ""); };
  const mode = L.mode || "filter";
  // filter/region も lazy-graph と同じ「空になったら行き止まりにしない」規律を適用する（半田様2026-08-08）。
  // その語に該当kindのノードが無い見方（例: 著者ノードの無い語で「思想家と著作」）を選ぶと、
  // applyLens/applyRegion は root 1個だけを返し、そのまま gBuild すると**空canvas＝行き止まり**になる。
  // 従来この防御は lazy-graph mode にしか無く、filter/region に無いのが非対称＝欠落だった
  // （実測: panorama_live [1128] emptyGraph=43 の "L3 lens/ui/思想家と著作…:空グラフ"）。
  // 空のときは既存の地図を壊さず（gBuild しない＝G を保持）、noMiss の建設的な入口を出す（否定文言は使わない）。
  const lensThin = (pd) => !pd || !pd.nodes || pd.nodes.length <= 1;
  if (mode === "filter") {
    const pd = applyLens(G_raw, key);
    if (lensThin(pd)) { setNote(vlabel); showAlt(); $("graph-alt").innerHTML = noMiss(G_raw.query); return; }
    showCanvas(); setNote(pd.note || G_raw.note || ""); gBuild(pd); return;
  }
  if (mode === "region") {
    const pd = applyRegion(G_raw);
    if (lensThin(pd)) { setNote(vlabel); showAlt(); $("graph-alt").innerHTML = noMiss(G_raw.query); return; }
    showCanvas(); setNote(pd.note); gBuild(pd); return;
  }
  // 遅延レンズ（応用/使用例/時代変遷）: エンドポイントを取得（語ごとキャッシュ）して描画
  const ck = `${L.key}:${G_raw.query}`;
  let data = G_lenscache[ck];
  if (!data) {
    setNote((jp ? "読み込み中… " : "loading… ") + L.cap);
    if (mode === "cards" || mode === "timeline") { showAlt(); $("graph-alt").innerHTML = `<p class="lens-empty">${jp ? "読み込み中…" : "loading…"}</p>`; }
    try { data = await api(`${L.endpoint}?q=${encodeURIComponent(G_raw.query)}&lang=${LANG}`); G_lenscache[ck] = data; }
    catch (e) { if (G_lens === key) { setNote(vlabel); showAlt(); $("graph-alt").innerHTML = noMiss(G_raw.query); } return; }   // どの遅延レンズでも空canvasで止めず続行入口を残す
    if (G_lens !== key) return;   // 読み込み中に別レンズへ切替＝古い結果を捨てる（状態一貫性）
  }
  setNote(data.note || L.cap);
  if (mode === "lazy-graph") {
    if (!data.nodes || data.nodes.length <= 1) { showAlt(); $("graph-alt").innerHTML = noMiss(G_raw.query); return; }   // 否定表示を出さず建設的代替へ
    showCanvas(); gBuild(data);
  } else if (mode === "cards") { showAlt(); renderUsageCards(data); }
  else if (mode === "timeline") { showAlt(); renderTimeline(data); }
}

// 使用例・引用: 出典つきの引用カード群（賛否は判定しない・中立）
function renderUsageCards(data) {
  const a = $("graph-alt"); if (!a) return; const jp = LANG === "ja";
  const cards = data.cards || [], scholars = data.scholars || [];
  if (!cards.length && !scholars.length) { a.innerHTML = noMiss((data && data.query) || (G_raw && G_raw.query) || ""); return; }   // 否定表示を出さず建設的代替へ
  // 現代の研究者（OpenAlex著者集計・被研究度順）＝いま最もこの概念を論じている人（歴史的正典と区別）
  const schHtml = scholars.length ? `<p class="dim-disc-h">${jp ? "この概念を今、最も論じている研究者（OpenAlex・被研究度順／歴史的思想家は「思想家」レンズ）" : "Most-publishing scholars now (OpenAlex)"}</p>
    <div class="dim-disc-list">${scholars.map(s => `<a class="dim-disc-l" href="/origin?q=${encodeURIComponent(s.name)}&lang=${LANG}"${originLinkAttr()}>${esc(s.name)} <span class="lens-n">${s.count}</span></a>`).join("")}</div>` : "";
  a.innerHTML = schHtml + `<div class="usage-cards">` + cards.map(c => {
    const meta = [(c.authors || []).join(", "), c.year, c.venue].filter(Boolean).map(esc).join(" · ");
    const link = c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${jp ? "出典を開く" : "open"}</a>` : "";
    return `<div class="ucard"><div class="ut">${esc(c.title)}</div><div class="um">${meta}${meta && link ? " · " : ""}${link}<br><span class="srcline">${jp ? "用いた語" : "term"}: ${esc(c.term)}</span></div></div>`;
  }).join("") + `</div>`;
}

// 時代・変遷: 原語の通時頻度を"川/時間軸"で（Google Books Ngram）
function renderTimeline(data) {
  const a = $("graph-alt"); if (!a) return; const jp = LANG === "ja";
  const series = data.series || [];
  if (!series.length) { a.innerHTML = noMiss((data && data.query) || (G_raw && G_raw.query) || ""); return; }   // 否定表示を出さず建設的代替へ
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
function originStale(tok) {
  // 実行時の回帰試験や診断からガードの観測点を差し替えられるようにする。
  // 通常運用では自分自身がwindow.originStaleなので、必ず単調token判定へ戻る。
  const hook = typeof window !== "undefined" && window.originStale;
  if (typeof hook === "function" && hook !== originStale) {
    try { return !!hook(tok); } catch (e) { console.error("origin stale hook", e); }
  }
  return tok !== OZ.token;
}
function originCurrent(q) { return OZ.q === q; }

// dispatch a dimension-of-inquiry entry to its data path (or 整備中 note).
// 非同期の実データ経路は必ず return して呼び元 dispatchAction に await させる（settle後に1回だけcommit＝
// 一操作一commitを守る。returnしないと取得完了前に先行commitし、gCombineRun等の完了時に再commitして履歴が
// 2件になる回帰＝Codex対審E2・半田様2026-07-30の保持指示に違反する）。
function gDimAct(dm) {
  if (!dm) return false;
  const act = dm.act || "";
  const w = (G && G.rootQ) || (($("origin-results") || {}).dataset || {}).q || "";   // この探索の中心語
  // soon次元＝説明だけで止めない。現在語と次元名を既存の組合せ探索(実データ)へ渡し、同一操作内で実行する
  // （新機構を作らず既存Action/APIを再利用・取得できなければ組合せ側が続行操作を出す・半田様2026-07-30）。
  if (dm.status === "soon") { return gCombineRun(w, dm.label, "and"); }
  if (act.startsWith("scroll:")) {
    const el = $(act.slice(7));
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      return gPanel(dm.label, `<p class="muted">「${esc(dm.label)}」の該当箇所へ移動しました。</p>${softLine(w)}`, w);
    }
    else return gPanel(dm.label, softLine(w), w);   // 否定表示を出さず続行フッターへ（逆側logic）
  } else if (act.startsWith("colloc:")) return gColloc(act.slice(7), "de");
  else if (act.startsWith("counter:")) return gCounter(act.slice(8));
  else if (act === "graph") {
    const gw = $("origin-graph-wrap"); if (gw) gw.scrollIntoView({ behavior: "smooth", block: "start" });
    return gPanel(dm.label, `<p class="muted">地図の該当箇所へ移動しました。</p>${softLine(w)}`, w);
  }
  else return gCombineRun(w, dm.label, "and");   // 未知のact＝「準備中」で止めず、既存の組合せ実データ経路へ（P6/P11）
}

// 批判・異論の次元 — reuse the existing counterargument engine (steelman
// perspectives + real opposing literature). Benchmark's『批判・異論』dimension.
async function gCounter(claim) {
  const jp = LANG === "ja";
  const p = gPanel((jp ? "批判・異論：" : "Critique: ") + claim, `<p class="muted">${jp ? "読み込み中…" : "loading…"}</p>`, claim);
  let d;
  try { d = await api("/api/counter", { method: "POST", body: { claim, lang: LANG } }); }
  catch (e) { console.error(e); p.querySelector(".gp-body").innerHTML = softLine(claim, { lead: jp ? `「${claim}」の検証データ取得を見送りました。下の入口から別の経路で続けられます。` : `The verification data for “${claim}” was deferred. Continue below.` }); return; }   // 生エラーを出さず続行フッターへ
  let html = `<p class="muted">${jp ? "この語・主張を、複数の視点から検証する問い（steelman）。加えて、この主張に関連する実在の文献を示します（賛成か反対かは判定していません）。" : "Counter-questions from multiple perspectives, plus related real literature (stance NOT judged)."}</p>`;
  (d.level0 || []).forEach(pv => { html += `<h4 class="gp-h">${esc(pv.perspective)}</h4><ul class="gp-ul">${(pv.questions || []).map(q => `<li>${esc(q)}</li>`).join("")}</ul>`; });
  const lit = d.opposing_literature_search;
  if (lit && !lit.error && lit.data && lit.data.length) {
    html += `<h4 class="gp-h">${jp ? "関連文献（OpenAlex・実データ／賛否は未判定）" : "Related literature (OpenAlex; stance not judged)"}</h4><ul class="gp-ul">`
      + lit.data.slice(0, 6).map(w => `<li>${esc(w.title)} <span class="srcline">${esc((w.authors || []).slice(0, 2).join(", "))}</span></li>`).join("") + "</ul>";
  }
  p.querySelector(".gp-body").innerHTML = html;
}

// 操作shell（ナビ＋共通メニュー）は語がある限り常設。graph の成否に依存しない（普遍性・Codex E2是正）。
// gActions は語だけで作れる（graphデータ不要）ので、取得前・失敗時でもメニューが出せる。
function originShellShow(q) {
  const sh = $("origin-shell"); if (sh) sh.style.display = "block";
  renderTopMenu({ query: q });
}
// グラフ本体と「薄い/失敗」代替表示の切替。msg=null でグラフ表示、msg文字列で代替表示（メニューは常設のまま）。
function graphThin(msg, term) {
  const wrap = $("origin-graph-wrap"), thin = $("graph-thin");
  if (msg) {
    if (wrap) wrap.style.display = "none";
    if (thin) {
      thin.style.display = "block";
      thin.innerHTML = `<p class="lens-empty">${esc(msg)}</p>` + (term ? noMiss(term) : "");
    }
  } else {
    if (wrap) wrap.style.display = "block";
    if (thin) { thin.style.display = "none"; thin.innerHTML = ""; }
  }
}

// 取得済みグラフデータを Map へ適用する唯一の場所（取得と適用を分離＝正典transactionの③で使う）
function gApplyGraph(d) {
  G_raw = d;
  // 選んでいたレンズをこの語でも保つ（見方の連続性）。ただし新しい語でそのフィルタが空なら俯瞰へ。
  const cur = LENSES.find(x => x.key === G_lens) || LENSES[0];
  if (cur.kinds && lensLeafCount(d, cur) === 0) G_lens = "all";
  renderTopMenu(d);
  const cur2 = LENSES.find(x => x.key === G_lens) || LENSES[0];
  if ((cur2.mode || "filter") === "filter") {
    showCanvas();
    const pd = applyLens(d, G_lens);
    const note = $("graph-note"); if (note) note.textContent = pd.note || d.note || "";
    gBuild(pd);
    return null;
  }
  return applyLensBuild(G_lens);   // region/応用/使用例/時代変遷は新しい語で再描画（遅延取得は語ごとキャッシュ）
}

async function originGraph(q, tok) {
  if (tok == null) tok = originClaim(q);   // standalone caller (e.g. 全体に戻す) claims its own token
  const wrap = $("origin-graph-wrap"), cv = $("origin-graph");
  if (!wrap || !cv) return false;
  const jp = LANG === "ja";
  originShellShow(q);   // 取得の成否に関わらず、まず操作帯（ナビ＋共通メニュー）を出す
  const res = await originResolveGraph(q, tok);
  if (originStale(tok)) return false;      // 古い語の応答＝現在の語のグラフを壊さない（stale破棄）
  if (!res) { graphThin(jp ? `「${q}」は、上の入口からこの語のまま探索を続けられます。` : `Continue exploring “${q}” from the entry points above.`, q); return false; }
  graphThin(null);   // グラフ本体を表示（薄い/失敗表示を隠す）
  await gApplyGraph(res.data);
  return true;
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
  G = { nodes, edges, children, parent, ctx, cv, W, H, cx, cy, rootQ: d.query, note: d.note, focusLabel: null,
        view: { x: 0, y: 0, k: 1 }, drag: null, hover: null, hl: null, alpha: 1, raf: 0, needFit: true };
  gFitInstant();
  gBind();
  gLoop(200);
}

function gStep() {
  const N = G.nodes, E = G.edges;
  // 反発は節点数でスケール（大きいグラフが線状に潰れるのを防ぐ）＋近接時に強く押す（下限床）
  const REP = 3400 + N.length * 140;
  for (let i = 0; i < N.length; i++) {
    const a = N[i];
    for (let j = i + 1; j < N.length; j++) {
      const b = N[j];
      let dx = a.x - b.x, dy = a.y - b.y, ds = dx * dx + dy * dy || 1;
      const dist = Math.sqrt(ds), f = REP / Math.max(ds, 90);
      const fx = f * dx / dist, fy = f * dy / dist;
      a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
    }
  }
  E.forEach(e => {
    const a = N[e.a], b = N[e.b];
    const dx = b.x - a.x, dy = b.y - a.y, dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const target = 88 + Math.abs(a.layer - b.layer) * 42;   // やや長いバネ（潰れ防止）
    const f = 0.02 * (dist - target);
    const fx = f * dx / dist, fy = f * dy / dist;
    a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy;
  });
  N.forEach(n => {
    n.vx += (G.cx - n.x) * 0.004; n.vy += (G.cy - n.y) * 0.004;   // 中心引力は弱め（広がりを保つ）
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
    const isRoot = n.layer === 1;          // 入力語（現在地）＝はっきり目立たせる
    const isHover = n === G.hover;          // ホバー中＝何を選んでいるか明瞭に
    ctx.globalAlpha = on ? 1 : 0.12;
    const r = n.r * (isHover ? 1.4 : (isRoot ? 1.25 : 1));
    if (isRoot || isHover) {                // ハロー（外側の輪）で強調
      ctx.beginPath(); ctx.arc(n.x, n.y, r + (isRoot ? 9 : 6), 0, 7);
      ctx.fillStyle = isRoot ? "rgba(194,65,12,0.20)" : "rgba(17,17,17,0.12)"; ctx.fill();
    }
    ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 7);
    ctx.fillStyle = isRoot ? "#c2410c" : (GKIND[n.kind] || "#888"); ctx.fill();
    if (isRoot) { ctx.lineWidth = 3 / view.k; ctx.strokeStyle = "#7c2d12"; ctx.stroke(); }
    else if (isHover) { ctx.lineWidth = 3 / view.k; ctx.strokeStyle = "#111"; ctx.stroke(); }
    const bold = isRoot || isHover;
    ctx.font = (bold ? "bold " : "") + (isRoot ? 18 : Math.round(10 + n.weight * 1.4)) + "px system-ui, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "bottom";
    const lab = n.label.length > 22 ? n.label.slice(0, 21) + "…" : n.label;
    if (bold) {                             // 強調ノードは下地つき・文字を下地の中央に（欠けない）
      const fs = isRoot ? 18 : 13, th = fs + 8, tw = ctx.measureText(lab).width + 14;
      const screenY = n.y * view.k + view.y;
      const above = screenY > 60;           // 画面上端に近ければ下に描いてクリップ回避
      const cyP = above ? (n.y - r - 7 - th / 2) : (n.y + r + 7 + th / 2);
      ctx.globalAlpha = on ? 0.96 : 0.12;
      ctx.fillStyle = isRoot ? "#7c2d12" : "#111";
      ctx.fillRect(n.x - tw / 2, cyP - th / 2, tw, th);
      ctx.globalAlpha = on ? 1 : 0.12;
      ctx.fillStyle = "#fff"; ctx.textBaseline = "middle"; ctx.fillText(lab, n.x, cyP + 1);
      ctx.textBaseline = "bottom";
    } else {
      ctx.fillStyle = "#1d2430"; ctx.fillText(lab, n.x, n.y - r - 5);
    }
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
function gFocusSubtree(nodeIdx, opts) {
  opts = opts || {};
  const label = G.nodes[nodeIdx].label, rootQ = G.rootQ, note = G.note, nid = G.nodes[nodeIdx].id;
  const keep = new Set([nodeIdx]), st = [nodeIdx];
  while (st.length) { const i = st.pop(); (G.children[i] || []).forEach(c => { if (!keep.has(c)) { keep.add(c); st.push(c); } }); }
  const base = G.nodes[nodeIdx].layer;
  const nodes = [...keep].map(i => { const n = G.nodes[i]; return { ...n, layer: n.layer - base + 1 }; });
  const edges = G.edges.filter(e => keep.has(e.a) && keep.has(e.b))
    .map(e => ({ from: G.nodes[e.a].id, to: G.nodes[e.b].id, strength: e.s }));
  const fid = nid || label;       // 表示labelでなく stable ID で focus を保存・復元する
  gBuild({ query: rootQ, nodes, edges, note: note });
  if (G) { G.focusId = fid; G.focusLabel = label; }   // focus対象（idが真の鍵・labelは表示用）
  if (!opts.nav) navCommit(currentViewState());  // 「この分岐を中心に」の確定commit（txn中はdispatcherが一括）
}

// 著者を調べる — REAL in-portal retrieval (bio, dates, occupation, works, source)
// via /api/author. This is the detection/extraction the user asked for; it never
// touches the word-origin engine. Empty results show WHERE it failed, not a blank.
async function gAuthorInvestigate(searchName, label) {
  const jp = LANG === "ja";
  const p = gPanel((jp ? "著者を調べる：" : "Author: ") + (label || searchName),
    `<p class="muted">${jp ? "取得中…" : "loading…"}</p>`, searchName);
  let d;
  try { d = await api(`/api/author?name=${encodeURIComponent(searchName)}&lang=${LANG}`); }
  catch (e) { console.error(e); p.querySelector(".gp-body").innerHTML = softLine(searchName, { lead: jp ? `「${searchName}」の著者情報取得を見送りました。下の入口から別の経路で続けられます。` : `Author data for “${searchName}” was deferred. Continue below.` }); return; }   // 生エラーを出さず続行フッターへ
  if (!d.found) {
    p.querySelector(".gp-body").innerHTML = softLine(searchName) + `<p class="srcline">${jp ? "入り口：" : "entry:"} <a href="https://ja.wikipedia.org/wiki/Special:Search?search=${encodeURIComponent(searchName)}" target="_blank">Wikipedia検索</a></p>`;   // 否定表示を出さず続行フッター＋入口へ
    return;
  }
  const row = (k, v) => v && v.length ? `<tr><th>${esc(k)}</th><td>${esc(Array.isArray(v) ? v.join("、") : v)}</td></tr>` : "";
  const V = await resolveVariants(d.title || searchName);   // 外部リンクを各サイトの言語形で
  let html = `<p>${esc(d.extract || "")}</p>
    <table class="plain">
      ${row(jp ? "生" : "born", (d.born || [])[0])}
      ${row(jp ? "没" : "died", (d.died || [])[0])}
      ${row(jp ? "職業" : "occupation", d.occupation)}
      ${row(jp ? "主要著作" : "works", (d.works || []).map(w => `${w}`))}
    </table>
    <p class="srcline"><a href="${esc(d.wikipedia_url)}" target="_blank">Wikipedia (${LANG})</a>${d.wikidata_url ? ` · <a href="${esc(d.wikidata_url)}" target="_blank">Wikidata</a>` : ""} · ${esc((d.sources && d.sources[0] && d.sources[0].retrieved_at) || "")}</p>
    <h4 class="gp-h">${jp ? "より深く・広く調べる（外部の専門情報源・多言語・新しいタブで開く）" : "Investigate deeper & wider (external expert sources, new tab)"}</h4>
    ${extResourcesHtml(d.title || searchName, V)}`;
  p.querySelector(".gp-body").innerHTML = html;
}

// ── 普遍原理: どの項目からも、公開・合法な専門情報源へ多言語で最大限リンクし、
//    ユーザーが選んで【新しいタブ】で開ける。当ポータルは選択肢を示すだけ（客観・
//    無編集・出所明示）。偏った編集をせず、思考の広がりと刺激を与える。──
// 語の多言語variants（各外部サイトが受け付ける言語形へ）。カタカナのニーチェ→英名 等。cache付。
const _varCache = {};
async function resolveVariants(term) {
  if (_varCache[term]) return _varCache[term];
  try { const d = await api(`/api/variants?q=${encodeURIComponent(term)}&lang=${LANG}`); const V = d.labels || {}; _varCache[term] = V; return V; }
  catch (e) { _varCache[term] = {}; return {}; }
}
// 外部リンク一覧。各サイトが受け付ける言語形を選ぶ（普遍原則: 全サイト・全場面に適用）。
// 英語系サイトにカタカナを渡さない＝V.en(ローマ字/英名)を使い、無ければ原語→ja の順で退避。
function extResources(term, V) {
  V = V || {};
  const enc = s => encodeURIComponent(s || term);
  const ja = enc(V.ja || term), en = enc(V.en || term), de = enc(V.de || V.en || term),
        fr = enc(V.fr || V.en || term), grla = enc(V.grc || V.la || V.en || term);
  return {
    "検索": [
      ["Google", `https://www.google.com/search?q=${ja}`],
      ["Google Scholar", `https://scholar.google.com/scholar?q=${en}`],
      ["Bing", `https://www.bing.com/search?q=${ja}`],
      ["DuckDuckGo", `https://duckduckgo.com/?q=${ja}`],
    ],
    "百科事典": [
      ["Wikipedia 日", `https://ja.wikipedia.org/wiki/Special:Search?search=${ja}`],
      ["Wikipedia 英", `https://en.wikipedia.org/w/index.php?search=${en}`],
      ["Wikipedia 独", `https://de.wikipedia.org/w/index.php?search=${de}`],
      ["Wikipedia 仏", `https://fr.wikipedia.org/w/index.php?search=${fr}`],
      ["Stanford哲学百科 SEP", `https://plato.stanford.edu/search/searcher.py?query=${en}`],
      ["Internet哲学百科 IEP", `https://iep.utm.edu/?s=${en}`],
      ["Britannica", `https://www.britannica.com/search?query=${en}`],
      ["コトバンク", `https://kotobank.jp/word/${ja}`],
    ],
    "辞書・辞典": [
      ["Wiktionary 日", `https://ja.wiktionary.org/wiki/Special:Search?search=${ja}`],
      ["Wiktionary 英", `https://en.wiktionary.org/wiki/Special:Search?search=${en}`],
      ["DWDS 独", `https://www.dwds.de/wb/${de}`],
      ["Perseus 希/羅", `https://www.perseus.tufts.edu/hopper/searchresults?q=${grla}`],
      ["Logeion 希/羅", `https://logeion.uchicago.edu/${grla}`],
      ["Monier-Williams 梵", `https://www.sanskrit-lexicon.uni-koeln.de/scans/MWScan/2020/web/webtc/indexcaller.php`],
    ],
    "学術・論文": [
      ["PhilPapers", `https://philpapers.org/s/${en}`],
      ["CiNii", `https://cir.nii.ac.jp/all?q=${ja}`],
      ["J-STAGE", `https://www.jstage.jst.go.jp/result/global/-char/ja?globalSearchKey=${ja}`],
      ["JSTOR", `https://www.jstor.org/action/doBasicSearch?Query=${en}`],
      ["OpenAlex", `https://openalex.org/works?search=${en}`],
      ["国立国会図書館サーチ", `https://ndlsearch.ndl.go.jp/search?cs=bib&keyword=${ja}`],
    ],
    "原典・全集": [
      ["Wikisource 日", `https://ja.wikisource.org/wiki/Special:Search?search=${ja}`],
      ["Wikisource 独", `https://de.wikisource.org/wiki/Spezial:Suche?search=${de}`],
      ["Project Gutenberg", `https://www.gutenberg.org/ebooks/search/?query=${en}`],
      ["archive.org", `https://archive.org/search?query=${en}`],
    ],
  };
}
// render the external-resource fan as HTML (all links open in a NEW TAB)
function extResourcesHtml(term, V) {
  const jp = LANG === "ja", R = extResources(term, V);
  let h = `<p class="muted">${jp ? "公開・合法な専門情報源へのリンクです。各サイトが受け付ける言語（英語系は英名・独語系は独語…）で開きます。各リンクは新しいタブ。当ポータルは選択肢を示すだけで、中身は各サイトの提供です（客観・出所明示）。" : "Links to public expert sources, each in the language that site accepts; open in a new tab."}</p>`;
  for (const cat of Object.keys(R)) {
    h += `<div class="ext-cat"><span class="ext-cat-h">${esc(cat)}</span> `
      + R[cat].map(([lbl, url]) => `<a class="ext-link" href="${esc(url)}" target="_blank" rel="noopener">${esc(lbl)}</a>`).join(" ") + `</div>`;
  }
  return h;
}
// 語の側面（意味／多言語／埋没原語）を、地図の中心を変えずにパネルで個別に見せる（半田様指摘2026-07-29:
// 第2階層のノードのmenuで無断に再中心すると、元の中心語の意識と乖離する。中心変更は「中心に据え直す」に限る）。
async function gWordAspect(word, aspect) {
  const jp = LANG === "ja";
  const title = { meaning: jp ? "この語の意味：" : "Meaning: ", breadth: jp ? "多言語での言い方：" : "Languages: ",
                  collapse: jp ? "埋没した原語：" : "Buried originals: " }[aspect] || "";
  const p = gPanel(title + word, `<p class="muted">${jp ? "取得中…" : "loading…"}</p>`, word);
  let d; try { d = await api(`/api/origin?q=${encodeURIComponent(word)}&lang=${LANG}`); }
  catch (e) { console.error(e); await autoFallback(word, aspect, p.querySelector(".gp-body")); return; }   // A3: 別源を実走行
  const body = p.querySelector(".gp-body"); let h = "";
  if (aspect === "meaning") {
    const gm = d.general_meaning || [];
    if (gm.length) h += `<ul class="gp-ul">${gm.map(s => `<li>${esc(s)}</li>`).join("")}</ul>`;
    h += segmentLayersHtml(d.segment_layers, { includeCharacter: true });
    const wo = d.word_origin, co = d.concept_origin || [];
    if (wo && wo.name) h += `<p class="srcline">${jp ? "語源の原点（推定）：" : "origin: "}${esc(wo.name)}</p>`;
    if (co.length) h += `<p class="srcline">${jp ? "原語の候補：" : "original: "}${co.map(o => `<a href="#" class="ext-term" data-w="${esc(o.term)}">${esc(o.term)}</a>${o.name ? "（" + esc(o.name) + "）" : ""}`).join("　")}</p>`;
  } else if (aspect === "breadth") {
    const br = d.breadth || [];
    if (br.length) h += `<p class="muted">${jp ? "この概念を担う世界の言語とその語（クリックでその語へ）。既知の数言語に縮めない。" : "World languages carrying this concept."}</p><div class="breadth-chips">`
      + br.map(b => `<span class="breadth-chip">${esc(b.name)}${b.term ? "：<a href=\"#\" class=\"ext-term\" data-w=\"" + esc(b.term) + "\">" + esc(b.term) + "</a>" : ""}</span>`).join("") + `</div>`;
  } else if (aspect === "collapse") {
    const cw = d.collapse_warning;
    if (cw && cw.lemmas && cw.lemmas.length) h += `<p class="muted">${jp ? "この一語に埋没した複数の原語（区別の消失・クリックでその原語へ）：" : "Multiple originals collapsed into this one word:"}</p><div class="anat-comp">`
      + cw.lemmas.map(l => `<span class="anat-part"><a href="#" class="ext-term" data-w="${esc(l.lemma)}">${esc(l.lemma)}</a>${l.gloss ? "＝" + esc(l.gloss) : ""}</span>`).join(`<span class="anat-plus">・</span>`) + `</div>`;
  }
  if (h) body.innerHTML = h; else await autoFallback(word, aspect, body);   // A3: 空なら別源を実走行（softLine単独でない）
}

// ── 翻訳・受容史（通常の語源/外部検索とは別の証拠台帳モード） ────────────────
// 地図を再中心せず、原典・版・訳者・受容者・変形・反証を一枚の研究面に束ねる。
// curated seed がある語は確定台帳を返し、未登録語は既存の辞書・概念・書誌コネクタから
// 自動予備台帳を作る。全自動抽出を原典の証明と混同せず、証拠レベルを画面に残す。
const TH_DOMAIN_OPTIONS = [
  ["philosophy", "哲学・思想"], ["literature", "文学"], ["science", "科学・化学"], ["art", "芸術・美術"]
];
function _thLevel(level, levels) {
  const rec = (levels || []).find(x => x && x.id === level);
  const label = rec && rec.label ? rec.label : (level || "未分類");
  const cls = String(level || "unknown").replace(/[^a-z0-9_-]/gi, "-");
  return `<span class="th-badge th-${cls}">${esc(label)}</span>`;
}
function _thSources(ids, sources) {
  const by = Object.fromEntries((sources || []).filter(Boolean).map(s => [s.id, s]));
  return (ids || []).map(id => by[id]).filter(Boolean).map(s => {
    const label = esc(s.label || s.id || "source");
    const link = s.url
      ? `<a class="ext-link th-source-link" href="${esc(s.url)}" target="_blank" rel="noopener">${label}</a>`
      : `<span class="th-source-name">${label}</span>`;
    const local = (s.local_refs || []).length ? `<small class="th-local-ref">ローカル資料：${esc(s.local_refs.join(" ／ "))}</small>` : "";
    return `<span class="th-source-ref">${link}${local}</span>`;
  }).join(" ");
}
function _thField(label, value) {
  if (value == null || value === "") return "";
  return `<dt>${esc(label)}</dt><dd>${esc(String(value))}</dd>`;
}
function _thSourceLine(ids, sources) {
  const links = _thSources(ids, sources);
  return links ? `<p class="th-source-line"><span>出所：</span>${links}</p>` : "";
}
function _thNextActions(actions, sources) {
  if (!(actions || []).length) return "";
  return `<ul class="th-next-list">` + actions.map(a =>
    `<li><span>${esc(a.label || "次の調査")}</span>${_thSources(a.source_ids, sources)}</li>`).join("") + `</ul>`;
}
function _thPlan(plan) {
  if (!(plan || []).length) return "";
  return `<div class="th-plan">` + plan.map(x =>
    `<div class="th-plan-row"><b>${esc(x.label || "")}</b><span>${esc(x.purpose || "")}</span><em>${esc(x.status || "")}</em></div>`).join("") + `</div>`;
}
function _thCandidateCards(sources, levels) {
  if (!(sources || []).length) return "";
  return `<div class="th-source-list">` + sources.map(s =>
    `<article class="th-source-card"><div class="th-card-top"><b>${s.url ? `<a class="ext-link" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label || s.id || "source")}</a>` : esc(s.label || s.id || "source")}</b>${_thLevel(s.evidence || "candidate", levels)}</div><p>${esc(s.purpose || "")}</p><p class="muted">${esc(s.status || "")}</p></article>`).join("") + `</div>`;
}
function _thResponseHtml(d) {
  const jp = LANG === "ja";
  if (!d || (d.status !== "ready" && d.status !== "discovery") || !d.dossier) {
    const sources = (d && d.source_candidates) || [];
    const brief = (d && d.research_brief) || {};
    const next = _thNextActions((d && d.next_actions) || [], sources);
    return `<div class="th-result th-unseeded">
      <div class="th-status-line"><b>この語の調査台帳をここから開始できます</b><span class="th-badge th-unverified">初回調査</span></div>
      <p>${esc((d && d.note) || (jp ? "この分野の証拠台帳はまだ登録されていません。" : "This evidence dossier is not seeded yet."))}</p>
      <div class="th-question"><b>${esc(brief.title || `「${d && d.query || ""}」の新規調査`)}</b><p>${esc(brief.center_question || "原語・原典・翻訳・受容を同じ台帳へ登録するための開始点です。")}</p></div>
      <p class="muted">既存の哲学資料を別分野の答えとして流用しません。この語の原語・版・出典を登録すれば、同じ画面で台帳を継続できます。</p>
      ${brief.first_pass && brief.first_pass.length ? `<h4 class="th-subhead">最初に揃える証拠</h4><ol class="th-first-pass">${brief.first_pass.map(x => `<li>${esc(x)}</li>`).join("")}</ol>` : ""}
      ${next ? `<h4 class="th-subhead">次にできること</h4>${next}` : ""}
      ${sources.length ? `<h4 class="th-subhead">この語の調査入口</h4>${_thCandidateCards(sources, (d && d.evidence_levels) || [])}` : ""}
      <h4 class="th-subhead">情報源の選定計画</h4>${_thPlan((d && d.source_plan) || [])}
      <p class="srcline">${esc((d && d.verified_at) ? `台帳確認日：${d.verified_at}` : "確認日：未記録")}</p>
    </div>`;
  }
  const ds = d.dossier, sources = ds.sources || [], levels = d.evidence_levels || [];
  const isDiscovery = d.status === "discovery";
  let h = `<div class="th-result ${isDiscovery ? "th-discovery" : "th-ready"}">
    <div class="th-status-line"><b>${isDiscovery ? "自動予備台帳を表示しています：" : "台帳を表示しています："}${esc(ds.title || d.query)}</b>${_thLevel(isDiscovery ? "candidate" : "strong", levels)}</div>
    <p class="th-honesty">${esc(d.note || "")}</p>
    ${isDiscovery ? `<div class="th-discovery-banner"><b>これは最初の自動整理です</b><p>辞書・概念データ・書誌検索から取得できた情報を先に配置しました。原典の該当頁、版ごとの訳語、実際の引用・影響関係は未確認のまま保持しています。</p></div>` : ""}
    <div class="th-question"><b>中心問い</b><p>${esc(ds.center_question || "")}</p></div>
    <p class="th-scope">${esc(ds.scope_note || "")}</p>
    <details class="th-evidence-guide"><summary>証拠階層と読み方</summary><p>${esc(d.honesty || "")}</p><ul>`
      + levels.map(x => `<li>${_thLevel(x.id, levels)} ${esc(x.description || "")}</li>`).join("")
      + `</ul></details>`;

  h += `<section class="th-section"><h3>原語・翻訳語の対応</h3><p class="muted">一つの日本語にまとめず、原語・翻訳・保存／欠損／追加を別々に表示します。</p><div class="th-term-grid">`
    + (ds.term_map || []).map(t => `<article class="th-term-card">
      <div class="th-card-top"><code>${esc(t.source_term || "")}</code><span>${esc(t.language || "")}</span>${_thLevel(t.evidence, levels)}</div>
      <p class="th-kind">${esc(t.kind || "")}</p>
      <p><b>日本語候補：</b>${esc((t.japanese_candidates || []).join(" ／ "))}</p>
      <p class="th-distinction">${esc(t.distinction || "")}</p>
      <dl class="th-dl">${_thField("保存", t.preserved)}${_thField("欠損・変形", t.lost_or_shifted)}${_thField("付加", t.added)}</dl>
      ${_thSourceLine(t.source_ids, sources)}
    </article>`).join("") + `</div></section>`;

  h += `<section class="th-section"><h3>時系列 5W1H</h3><div class="th-timeline">`
    + (ds.timeline || []).map(t => `<article class="th-timeline-card">
      <div class="th-card-top"><b>${esc(t.when || "")}</b><span>${esc(t.who || "")}</span>${_thLevel(t.evidence, levels)}</div>
      <dl class="th-dl th-fivew">${_thField("Where", t.where)}${_thField("What", t.what)}${_thField("Why", t.why)}${_thField("How", t.how)}</dl>
      ${t.evidence_note ? `<p class="th-evidence-note">${esc(t.evidence_note)}</p>` : ""}${_thSourceLine(t.source_ids, sources)}
    </article>`).join("") + `</div></section>`;

  h += `<section class="th-section"><h3>翻訳・受容による変形</h3><div class="th-transform-grid">`
    + (ds.transformations || []).map(t => `<article class="th-transform-card">
      <div class="th-card-top"><b>${esc(t.stage || "")}</b>${_thLevel(t.evidence, levels)}</div>
      <dl class="th-dl">${_thField("保存", t.preserved)}${_thField("失われた／移動した焦点", t.lost)}${_thField("加わった焦点", t.added)}${_thField("検証方法", t.test)}</dl>
      ${_thSourceLine(t.source_ids, sources)}
    </article>`).join("") + `</div></section>`;

  h += `<section class="th-section"><h3>受容史の人物台帳</h3><div class="th-ledger">`
    + (ds.reception_ledger || []).map(t => `<article class="th-ledger-card">
      <div class="th-card-top"><b>${esc(t.who || "")}</b><span>${esc(t.when || "")}</span>${_thLevel(t.evidence, levels)}</div>
      <dl class="th-dl th-fivew">${_thField("Where", t.where)}${_thField("What", t.what)}${_thField("Why", t.why)}${_thField("How", t.how)}${_thField("関係", t.relation)}</dl>
      ${_thSourceLine(t.source_ids, sources)}
    </article>`).join("") + `</div></section>`;

  h += `<section class="th-section"><h3>最強の反証・注意点</h3><div class="th-counter-grid">`
    + (ds.counterchecks || []).map(t => `<article class="th-counter-card"><p><b>主張：</b>${esc(t.claim || "")}</p><p><b>反証候補：</b>${esc(t.counterargument || "")}</p><p><b>検査：</b>${esc(t.test || "")}</p></article>`).join("")
    + `</div></section>`;

  h += `<section class="th-section"><h3>情報源の選定計画</h3><p class="muted">自動予備台帳で拾えた候補を、次の確認順に並べます。候補の存在と本文の証明を混同しません。</p>${_thPlan(d.source_plan || [])}</section>`;

  h += `<section class="th-section"><h3>参照先</h3><div class="th-source-list">` + sources.map(s =>
    `<article class="th-source-card"><div class="th-card-top"><b>${s.url ? `<a class="ext-link" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.label || s.id || "source")}</a>` : esc(s.label || s.id || "source")}</b>${_thLevel(s.evidence, levels)}</div><p>${esc(s.status || "")}</p>${(s.local_refs || []).length ? `<small class="th-local-ref">${esc(s.local_refs.join(" ／ "))}</small>` : ""}</article>`).join("") + `</div></section>`;
  h += `<section class="th-section th-next"><h3>次の調査</h3>${_thNextActions(d.next_actions || ds.next_actions || [], sources)}</section>`;
  return h + `</div>`;
}
async function gTranslationHistoryPanel(word) {
  const jp = LANG === "ja";
  const controls = `<div class="th-controls"><label for="th-domain">分野</label><select id="th-domain">${TH_DOMAIN_OPTIONS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select><button type="button" class="th-run">この条件で調査を開始</button></div>
    <p class="th-intro">通常の意味検索や単純な語源検索とは別に、「誰が・いつ・どの版で・どの言語へ移し、何が保存／欠損／追加されたか」を証拠階層つきで追跡します。登録済み台帳がある語は詳細台帳を表示し、未登録語でも既存情報源から自動予備台帳を作って調査を始めます。</p>
    <div class="th-results"><p class="muted">${jp ? "台帳を読み込んでいます…" : "Loading the evidence dossier…"}</p></div>`;
  const p = gPanel((jp ? "🧭 翻訳・受容史を追跡：" : "Translation / reception history: ") + word, controls, word);
  if (!p) return false;
  const results = p.querySelector(".th-results"), select = p.querySelector("#th-domain"), runButton = p.querySelector(".th-run");
  const run = async () => {
    if (!results || !select || !runButton) return;
    const domain = select.value || "philosophy";
    runButton.disabled = true;
    results.innerHTML = `<p class="muted"><span class="spin"></span> ${esc(jp ? `「${word}」の${domain}分野の原典・翻訳・受容史を照合中…` : "Checking the source dossier…")}</p>`;
    try {
      const d = await api(`/api/translation-history?q=${encodeURIComponent(word)}&domain=${encodeURIComponent(domain)}&lang=${LANG}`, { timeout: 45000 });
      if (results.isConnected) results.innerHTML = _thResponseHtml(d);
    } catch (e) {
      console.error("translation history", e);
      if (results.isConnected) results.innerHTML = `<div class="th-result th-unseeded"><div class="th-status-line"><b>この調査面は追加確認を要します</b><span class="th-badge th-unverified">未確認</span></div><p>「${esc(word)}」の現在のMapと、ここからの次の入口は保持されています。下のフッターから外部情報源・多言語・組み合わせへ続けられます。</p><p class="srcline">${esc(String(e && e.message || e))}</p></div>`;
    } finally {
      if (runButton.isConnected) runButton.disabled = false;
    }
  };
  runButton.addEventListener("click", run);
  await run();
  return true;
}

// 普遍的な語源解剖（半田様指摘の弁証法ケース＝dia-対話性の復元）。原語へ辿り構成要素と
// 意味の連鎖をWiktionaryの実文書から。どんな語にも普遍適用（seed不要）。
async function gAnatomyPanel(word) {
  const jp = LANG === "ja";
  const p = gPanel((jp ? "語源と構成要素を解剖する：" : "Anatomy: ") + word, `<p class="muted">${jp ? "原語へ辿り、構成要素と意味を復元中…" : "…"}</p>`, word);
  let d; try { d = await api(`/api/anatomy?q=${encodeURIComponent(word)}&lang=${LANG}`); } catch (e) { console.error(e); await autoFallback(word, "anatomy", p.querySelector(".gp-body")); return; }   // A3: 別源を実走行
  const body = p.querySelector(".gp-body");
  if (!d.term) { await autoFallback(word, "anatomy", body); return; }   // A3: 空なら別源（/api/origin）を実走行
  // 外部sourceの部分応答でも画面構築を止めない。termだけ返る場合は、空の
  // 配列として扱い、語全体・次の操作・出所の面を維持する。
  const components = Array.isArray(d.components) ? d.components : [];
  const chain = Array.isArray(d.chain) ? d.chain : [];
  let h = `<p class="muted">${jp ? "日本語の字面には現れにくい、原語の構成要素と意味の連鎖です。翻訳で削ぎ落とされた原義を、原語の実文書（Wiktionary）に接地して復元します。" : ""}</p>`;
  h += segmentLayersHtml(d.segment_layers, { includeWhole: true, includeCharacter: false });
  if (components.length) {
    const hasChars = (d.segment_layers || []).some(x => x && x.level === "character");
    const comp = components.map(c => `<span class="anat-part"><a href="#" class="ext-term" data-w="${esc(c.part)}" lang="grc">${esc(c.part)}</a>＝${esc(c.meaning)}</span>`).join(`<span class="anat-plus">＋</span>`);
    h += hasChars
      ? `<details class="segment-secondary"><summary>${jp ? "文字辞書義（補助）を開く" : "Open character glosses (secondary)"}</summary><p class="segment-note">${jp ? "意味のまとまりを確認した後に、各文字の辞書義を補助情報として参照できます。" : "Refer to character dictionary glosses after reading the meaningful units."}</p><div class="anat-comp">${comp}</div></details>`
      : `<h4 class="gp-h">${jp ? "語源的な構成要素（クリックで探索）" : "Components"}</h4><div class="anat-comp">${comp}</div>`;
  }
  if (chain.length) {
    h += `<h4 class="gp-h">${jp ? "変容の連鎖（原語へさかのぼる・クリックで探索）" : "Chain"}</h4><div class="chain">`
      + `<span class="chain-now">「${esc(word)}」</span>`
      + chain.map(c => `<span class="chain-arrow">←</span><span class="chain-step"><span class="chain-lang">${esc(c.lang)}</span><a href="#" class="ext-term chain-form" data-w="${esc(c.term)}">${esc(c.term)}</a>${c.gloss ? `<span class="anat-gloss">「${esc(c.gloss)}」</span>` : ""}</span>`).join("") + `</div>`;
  }
  if (d.summary) {   // 語自身の語源の散文（矛盾＝韓非子の故事 等）。字ごとの分解に加えて語の由来を示す。
    h += `<h4 class="gp-h">${jp ? "語源（この語の由来）" : "Etymology"}</h4><p class="anat-summary">${esc(d.summary)}</p>`;
  }
  h += `<p class="srcline"><a href="${esc(d.wiktionary_url)}" target="_blank">Wiktionary（${esc(d.term)}）</a> · ${jp ? "全語に普遍適用・出所つき（意味drift差分の自動化は埋め込み層＝要RAMで将来）" : "universal"}</p>`;
  body.innerHTML = h;
}

// 並置比較カード（第三者提案・半田様承認の方向）: 訳語の意味と原語の意味を左右に並べ、機械が
// 差分を断定せず、人が自分の目で「字面が隠しているもの（対話性など）」を発見する（並ぶことの喜び）。
// 既存の /api/origin(日本語語義) と /api/anatomy(原語の構成要素・連鎖) を合成。RAM/新API不要。
async function gContrastPanel(word) {
  const jp = LANG === "ja";
  const p = gPanel((jp ? "訳語と原語の意味を並べて比べる：" : "Contrast: ") + word, `<p class="muted">${jp ? "日本語訳の意味と、原語の意味を並べて取得中…" : "…"}</p>`, word);
  let o = {}, a = {};
  try { [o, a] = await Promise.all([api(`/api/origin?q=${encodeURIComponent(word)}&lang=${LANG}`), api(`/api/anatomy?q=${encodeURIComponent(word)}&lang=${LANG}`)]); } catch (e) {}
  const anatomyLayers = Array.isArray(a.segment_layers) ? a.segment_layers : [];
  const anatomyHasContent = anatomyLayers.some(x => x && Array.isArray(x.units) && x.units.length)
    || (Array.isArray(a.components) && a.components.length)
    || (Array.isArray(a.chain) && a.chain.length);
  if (!(o.general_meaning || []).length && !anatomyHasContent) {   // A3: 両源とも空→別源を実走行
    await autoFallback(word, "contrast", p.querySelector(".gp-body")); return;
  }
  const jaMean = (o.general_meaning || []).map(s => `<li>${esc(s.length > 200 ? s.slice(0, 200) + "…" : s)}</li>`).join("") || `<li class="muted">—</li>`;
  const cw = o.collapse_warning;
  const jaCollapse = cw && cw.lemmas && cw.lemmas.length ? `<p class="srcline">${jp ? "※この一語に埋没した原語（クリックで探索）：" : "collapsed: "}${cw.lemmas.map(l => `<a href="#" class="ext-term" data-w="${esc(l.lemma)}">${esc(l.lemma)}</a>`).join("・")}</p>` : "";
  const comps = (Array.isArray(a.components) ? a.components : []).map(c => `<li><a href="#" class="ext-term" data-w="${esc(c.part)}" lang="grc">${esc(c.part)}</a>＝${esc(c.meaning)}</li>`).join("");
  const chain = (Array.isArray(a.chain) ? a.chain : []).map(c => `<li>${esc(c.lang)}：<a href="#" class="ext-term" data-w="${esc(c.term)}">${esc(c.term)}</a>${c.gloss ? `「${esc(c.gloss)}」` : ""}</li>`).join("");
  const semantic = segmentLayersHtml(a.segment_layers, { includeWhole: false, includeCharacter: false });
  const origHtml = (semantic || comps || chain)
    ? `${semantic}${comps ? `<p class="srcline">${jp ? "文字・語源の構成要素（補助）" : "components"}</p><ul class="ct-ul">${comps}</ul>` : ""}${chain ? `<p class="srcline">${jp ? "変容の連鎖（原語へ）" : "chain"}</p><ul class="ct-ul">${chain}</ul>` : ""}`
    : `<p class="muted">${jp ? "（原語の意味は下の入り口から辿れます）" : "—"}</p>`;
  p.querySelector(".gp-body").innerHTML = `
    <p class="muted">${jp ? "左の【日本語訳の意味】と右の【原語の意味】を、機械の判定でなく、あなた自身の目で並べて比べてください。字面が何を隠しているか（例：弁証法の「対話性」）が、並べることで見えてきます。" : "Compare the two meaning-spaces yourself."}</p>
    <div class="contrast">
      <div class="ct-col"><h4 class="gp-h">【日本語訳の意味空間】「${esc(word)}」</h4><ul class="ct-ul">${jaMean}</ul>${jaCollapse}</div>
      <div class="ct-col"><h4 class="gp-h">【原語の意味空間】${a.term ? `（${esc(a.term)}）` : ""}</h4>${origHtml}</div>
    </div>
    <p class="srcline">${jp ? "出所つき（ja.wiktionary / en.wiktionary）・全語に普遍適用。機械が差分を断定せず、人が発見する（並ぶことの喜び・捏造しないP6）。" : "source-grounded; universal."}</p>`;
}

async function gExtPanel(term) {
  const jp = LANG === "ja";
  const p = gPanel((jp ? "外部の専門情報で深く・広く調べる：" : "External resources: ") + term,
    `<p class="muted">${jp ? "各サイトが受け付ける言語形を解決中…" : "resolving language forms…"}</p>`, term);
  const V = await resolveVariants(term);
  const body = p.querySelector(".gp-body"); if (body) body.innerHTML = extResourcesHtml(term, V);
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
    <p class="srcline"><a href="${wp}" target="_blank">${jp ? "Wikipediaで開く" : "Wikipedia"}</a> · <a href="/deepsearch?q=${encodeURIComponent(n.label)}&lang=${LANG}"${originLinkAttr()}>${jp ? "深掘り探索プロンプト" : "deep-search"}</a></p>
    <p class="srcline muted">${jp ? "著者固有の用法（その著作でこの語がどう使われたか）・時代性・年表は整備中です。" : "Author-specific usage / timeline are being built."}</p>`;
  gPanel((jp ? "著者：" : "Author: ") + n.label, body, n.label);
}

// 分解の表示契約: 語全体を先に置き、意味のまとまりを主表示にし、文字は補助へ下げる。
// segment_layers は API から来た構造だけを描画する。ここで意味を推測・合成しない。
function segmentLayersHtml(layers, opts) {
  opts = opts || {};
  const jp = LANG === "ja";
  const ls = Array.isArray(layers) ? layers : [];
  const whole = ls.find(x => x && x.level === "whole");
  const semantic = ls.find(x => x && x.level === "semantic");
  const morphology = ls.find(x => x && x.level === "morphology");
  const character = ls.find(x => x && x.level === "character");
  let h = "";
  if (opts.includeWhole !== false && whole && whole.units && whole.units.length) {
    const u = whole.units[0];
    h += `<div class="segment-whole"><span class="segment-kicker">${jp ? "語全体" : "whole term"}</span><b>${esc(u.text || "")}</b></div>`;
  }
  const primary = semantic || morphology;
  if (primary && primary.units && primary.units.length) {
    const label = semantic ? (jp ? "意味のまとまり（優先）" : "Meaningful units (primary)")
                           : (jp ? "語源的なまとまり" : "Etymological units");
    h += `<div class="segment-block segment-primary"><p class="segment-heading">${label}</p>`
      + `<p class="segment-note">${jp ? "まずこの単位で読み、必要な時だけ下の文字・語源へ進みます。" : "Read these units first; open character or etymological detail only when useful."}</p>`
      + `<div class="segment-units">`
      + primary.units.map(u => `<span class="segment-unit"><a href="#" class="ext-term" data-w="${esc(u.text || "")}">${esc(u.text || "")}</a>${u.gloss ? `<small>${esc(u.gloss)}</small>` : ""}</span>`).join(`<span class="segment-join">＋</span>`)
      + `</div></div>`;
  }
  if (opts.includeCharacter !== false && character && character.units && character.units.length) {
    h += `<details class="segment-secondary"><summary>${jp ? "文字構成（補助）を開く" : "Open character composition (secondary)"}</summary>`
      + `<p class="segment-note">${jp ? "文字辞書の義は、語全体の意味そのものではありません。意味のまとまりを確認した後の補助情報です。" : "Character glosses are supporting evidence, not the meaning of the whole term."}</p>`
      + `<div class="segment-units segment-chars">`
      + character.units.map(u => `<span class="segment-unit"><a href="#" class="ext-term" data-w="${esc(u.text || "")}">${esc(u.text || "")}</a>${u.gloss ? `<small>${esc(u.gloss)}</small>` : ""}</span>`).join(`<span class="segment-join">＋</span>`)
      + `</div></details>`;
  }
  return h;
}

// contextual action menu — the dimension of a WORD (origin/meaning/translations)
// differs from that of an AUTHOR/WORK (usage/texts/era), so the menu ADAPTS to
// what was clicked. ≥7 actions; the ones not yet built are shown as 次段 (honest).
// 普遍原則（原理原則）: どの factor（ノード）にも "共通コア" の操作が必ず付く。ここに1つ
// 足せば全場面へ普遍適用される（個別menuへの付け忘れが構造的に起きない）。domain は語でなく
// 構造ラベルなので語操作を出さない（＝概念/人物/著作/言語など"実在の語"にのみ普遍コアを適用）。
// 全ノード共通の「メニュー パッケージ」。中心語も言語マップの語も第2/3階層のノードも、
// これ一つを接続する（普遍性・P11）。t=完全ラベル（ポップアップ用）・s=短縮ラベル（上部の帯用）。
// 上部の帯（renderTopMenu）とクリックのポップアップ（gMenu）は同じ本関数を使う＝どこでも同一UI。
// 全ノード共通メニュー。項目は「表示名」でなく Action ID を持ち、実行は dispatchAction 単一経路へ。
// 各表示面（上部帯/popup/フッター/noMiss/本文リンク）はこの item.action と target を渡すだけ（作用を再実装しない）。
function gActions(n) {
  const idx = (G && G.nodes) ? G.nodes.indexOf(n) : -1;
  const tgt = { term: n.q || n.label, label: n.label, kind: n.kind, id: n.id, lang: n.lang, layer: n.layer };
  let items;
  if (n.kind === "domain") {   // 構造の分岐＝語操作でなく分岐操作
    items = [
      { s: "🎯 この分岐を中心", t: "🎯 この分岐を中心に（下層を最大表示）", action: "focus", ctx: { nodeIdx: idx } },
      { s: "↩ 全体に戻す", t: "↩ 全体の重力分布に戻す", action: "resetFocus" },
      { s: "🔦 経路を強調", t: "🔦 この分岐の経路を強調（ホバーでも可）", action: "hl", ctx: { nodeIdx: idx } },
      { s: "✍ 深掘り", t: "✍ 深掘り探索プロンプトを作る（視点・目的・難易度）", action: "deepsearch" },
    ];
  } else {
    const CORE_HEAD = [
      // 第一候補＝この語の全体像（概念全景）。派生ノードからも全景へ進める（半田様2026-08-01）
      { s: "🖼 全体像を見る", t: "🖼 この語の全体像を見る（概念全景）", action: "panorama", ctx: { node: n } },
      { s: "🎯 中心に据える", t: "🎯 これを地図の中心に据え直す（グラフを再構成）", action: "center" },
      { s: "🔗 組み合わせ", t: "🔗 別の語と組み合わせる（AND／意味／除外／比較）", action: "combine" },
      { s: "👓 見方", t: "👓 見方を選ぶ（この地図の切り口）", action: "lens" },
      { s: "🧭 翻訳・受容史", t: "🧭 この語・人物・著作の翻訳・受容史を追跡する（原典・版・変容・欠損を証拠付きで整理）", action: "translationHistory" },
    ];
    const CORE_TAIL = [
      { s: "🌐 外部で調べる", t: "🌐 外部の専門情報で調べる（各サイトの言語で・新タブ）", action: "external" },
      { s: "⭐ 棚", t: "⭐ 棚に追加（あとで見る）", action: "shelf" },
      { s: "✍ 深掘り", t: "✍ 深掘り探索プロンプトを作る（視点・目的・難易度）", action: "deepsearch" },
      { s: "↗ 新タブ", t: "🔗 新しいタブでこの語を開く", action: "newtab" },
    ];
    let extra;
    if (n.kind === "author" || n.kind === "work") {
      const who = n.kind === "author" ? "この人物" : "この著作";
      extra = [
        { s: `🔍 ${who}を調べる`, t: `🔍 ${who}を調べる（経歴・著作・出典を取得）`, action: "author", ctx: { search: n.search || tgt.term } },
        { s: "📖 系譜メモ", t: `📖 ${who}の系譜メモ（この語での原語）`, action: "authorNote", ctx: { node: n } },
      ];
    } else {   // word / original / language / related / application
      extra = [
        { s: "📖 意味", t: "📖 この語の意味を見る（中心は変えない）", action: "meaning" },
        { s: "🔬 解剖", t: "🔬 語源と構成要素を解剖する（原義を復元）", action: "anatomy" },
        { s: "⚖ 並置", t: "⚖ 訳語と原語の意味を並べて比べる（何が隠れたか）", action: "contrast" },
        { s: "⚠ 埋没", t: "⚠ 埋没した原語を見る（中心は変えない）", action: "collapse" },
        { s: "🌍 多言語", t: "🌍 多言語での言い方を見る（中心は変えない）", action: "multilingual" },
        { s: "🕮 共起", t: "🕮 原語空間の共起（共に使われる語）", action: "colloc" },
      ];
    }
    items = [...CORE_HEAD, ...extra, ...CORE_TAIL];
  }
  return items.map(it => ({ ...it, target: tgt }));   // 全項目に正規化targetを付す
}

// 👓 見方を選ぶ ＝ この地図（重力場）の切り口。全ノードのメニューから普遍に開ける。
// レンズは中心語のグラフを絞る操作ゆえ、W が中心でなければ先に再中心してから適用（P11一貫性）。
function gLensMenu(W) {
  const jp = LANG === "ja";
  const items = LENSES.map(Lz => ({ key: Lz.key, label: jp ? Lz.label : Lz.en, cap: jp ? Lz.cap : "" }));
  const p = gPanel((jp ? "見方を選ぶ（この地図の切り口）：" : "Views: ") + W,
    `<p class="muted">${jp ? "同じ言葉を、いくつもの見方で。どれもこの地図（重力場）の切り口です。選ぶとこの語を中心にその見方で描き直します。" : "Views of this map; each re-draws around this word."}</p>`
    + `<div class="lens-list">` + items.map((it, i) =>
        `<button type="button" class="lens-row" data-i="${i}" data-k="${esc(it.key)}"><b>${esc(it.label)}</b><span class="lens-cap">${esc(it.cap)}</span></button>`).join("") + `</div>`, W);
  if (!p) return;
  p._lensItems = items;
  p.querySelectorAll(".lens-row").forEach(b => b.addEventListener("click", () => {
    const it = p._lensItems[+b.dataset.i]; if (!it) return;
    // recenter=この操作が中心語を移すか（W が現在の中心でないとき真）。registry の effectWithArg が
    // これを見て map（同語＝Context保持）か center（別語を中心化＝Map中心+Context更新）かを宣言する。
    dispatchAction("applyLens", { term: W }, currentViewState(),
      { surface: "lens-menu", lensKey: it.key, recenter: !!(G && G.rootQ !== W) });
  }));
}
// W を中心にした上でレンズを適用（他ノードの「見方」も、その語を中心に据えてから効く＝普遍）
async function applyLensFor(W, key) {
  if (G && G.rootQ === W && G_raw) {
    await applyLensBuild(key); navCommit(currentViewState());
    return !!(G && G_raw && G_lens === key);
  }
  // 同一性の判定は文字列完全一致（G.rootQ===W）でなく、正典transaction（originRecenter→originExplore）
  // 自身の成功シグナルで行う。大文字小文字・NFKC正規化・原語探索でrootの表記がWと変わっても
  // （例: Dialectic→dialectic）、transactionが構築に成功していればlensは必ず適用する（無作用にしない・
  // 半田様2026-08-07既知不具合の是正）。transactionが失敗（stale/構築不可）した場合はlensを適用しない
  // ＝別語や存在しない状態への誤適用を防ぐ。
  const ok = await originRecenter(W);
  if (!ok || !G || !G_raw) return false;
  await applyLensBuild(key); navCommit(currentViewState());   // 見方切替の確定commit（txn中はdispatcherが一括）
  return !!(G && G_raw && G_lens === key);
}

function gMenu(cx, cy, n) {
  G.menuNode = n;
  MENUCTX = { cx, cy, n };   // このノードのメニューを、パネル閲覧後に開き直すための文脈（戻る導線）
  gShowMenu(cx, cy, (LANG === "ja" ? "選択：" : "Selected: ") + n.label, gActions(n));
}
// ノードのポップアップ メニュー→パネルを見た後に「別のメニューを選ぶ」ために元メニューへ戻る文脈
let MENUCTX = null, _panelFromMenu = false;
function gReopenMenu() { if (MENUCTX) gMenu(MENUCTX.cx, MENUCTX.cy, MENUCTX.n); }
function gMenuEdge(cx, cy, ei) {
  const e = G.edges[ei];
  const child = G.nodes[e.a].layer >= G.nodes[e.b].layer ? e.a : e.b;
  const other = child === e.a ? e.b : e.a;
  const cn = G.nodes[child], a = G.nodes[e.a].label, b = G.nodes[e.b].label;
  const ct = { term: cn.q || cn.label, label: cn.label, kind: cn.kind, id: cn.id, lang: cn.lang, layer: cn.layer };
  const otherTerm = G.nodes[other].q || G.nodes[other].label;
  // エッジメニューも Action ID＋正規target で（無作用0・全項目が dispatch 経由・比較/説明も実アクション）
  gShowMenu(cx, cy, `${a} — ${b}`, [
    { t: "🔦 この関係の経路を根まで強調", action: "hl", ctx: { nodeIdx: child }, target: ct },
    { t: "🎯 子側を中心に展開", action: "focus", ctx: { nodeIdx: child }, target: ct },
    { t: "⚖ 両端の語を比較する", action: "combine", ctx: { b: otherTerm, op: "compare" }, target: ct },
    { t: "📖 この関係（なぜ結ばれるか）を深掘り", action: "deepsearch", target: ct },
    { t: "🔍 子側の語を中心に据える", action: "center", target: ct },
    { t: "🌿 この枝だけを残して整理", action: "focus", ctx: { nodeIdx: child }, target: ct },
    { t: "↩ 全体に戻す", action: "resetFocus", target: ct },
  ]);
}
// メニューの中身（タイトル＋項目）を描画。ホバー追従で差し替えるため関数化・itemsをmに保持。
function _gmFill(m, title, items) {
  m._items = items;
  m.innerHTML = `<div class="gm-title" title="ドラッグで移動できます">⠿ ${esc(title)}</div>` + items.map((it, i) =>
    `<button type="button" class="gm-item${it.soon ? " gm-soon" : ""}" data-i="${i}">${esc(it.t)}${it.soon ? "（次段）" : ""}</button>`).join("");
  const tt = m.querySelector(".gm-title");
  tt.addEventListener("pointerdown", (ev) => {
    ev.stopPropagation(); ev.preventDefault();
    const sx = ev.clientX, sy = ev.clientY, ox = parseFloat(m.style.left), oy = parseFloat(m.style.top);
    const mv = (e) => { m.style.left = (ox + e.clientX - sx) + "px"; m.style.top = (oy + e.clientY - sy) + "px"; };
    const up = () => { document.removeEventListener("pointermove", mv); document.removeEventListener("pointerup", up); };
    document.addEventListener("pointermove", mv); document.addEventListener("pointerup", up);
  });
}
// ホバー追従: メニューを出したまま別factorにホバーしたら、そのノードへ内容(タイトル+項目)を差し替える
function gMenuRetarget(n) {
  const m = surfEl("menu"); if (!m || !n || (G && G.menuNode === n)) return;
  if (G) G.menuNode = n;
  if (MENUCTX) MENUCTX.n = n;   // ホバー追従で対象が変わったら戻る文脈も更新（Codex E2是正: 元ノードへ誤帰還を防ぐ）
  _gmFill(m, (LANG === "ja" ? "選択：" : "Selected: ") + n.label, gActions(n));
  surfPlace("menu");            // 項目数が変わっても Context と交差せず viewport 内に収める
}
// Menu の生成・配置・z は surface manager が一元決定する（座標系も fixed に統一）。
function gShowMenu(cx, cy, title, items) {
  if (G) { G.lastX = cx; G.lastY = cy; }   // 処理中インジケータを選択付近に出すため記録
  const m = document.createElement("div");
  surfCreate("menu", m, { x: cx, y: cy });
  _gmFill(m, title, items);
  surfPlace("menu");
  // BUGFIX: keep the item's pointerdown from reaching the document-level closer.
  m.addEventListener("pointerdown", (ev) => ev.stopPropagation());
  m.addEventListener("click", async (ev) => {
    const el = ev.target.closest(".gm-item"); if (!el) return;
    const it = m._items[Number(el.dataset.i)];
    if (!it || m.dataset.busy === "1") return;
    m.dataset.busy = "1";
    m.setAttribute("aria-busy", "true");
    m.querySelectorAll(".gm-item").forEach(x => { x.disabled = true; });
    gMenuClose();
    _panelFromMenu = true;   // この直後に開くパネルへ「←メニューに戻る」を付ける（戻る導線）
    try {
      const result = await dispatchAction(it.action, it.target, currentViewState(), { surface: "popup", ...(it.ctx || {}) });
      // unknown action等でdispatcherが面を作れなかった場合だけ、閉じたMenuを元の位置へ戻す。
      if (result && !result.ok && !surfEl("menu") && !surfEl("action")) gShowMenu(cx, cy, title, items);
    } catch (err) {
      console.error("menu action", err);
      if (!surfEl("menu") && !surfEl("action")) gShowMenu(cx, cy, title, items);
    } finally {
      _panelFromMenu = false;
    }
  });
  SURF.menuCloser = (ev) => { if (!ev.target.closest("#graph-menu")) gMenuClose(); };
  setTimeout(() => { if (SURF.menuCloser) document.addEventListener("pointerdown", SURF.menuCloser); }, 0);
}
function gMenuClose() { surfDestroy("menu"); }
// dismissible overlay panel (for menu actions that show their own content)
// 語に関するパネルには term を渡す。すると下部に「この語で続ける」普遍フッターが必ず付き、
// 空状態・失敗（例: 解剖で原語が特定できない）でも行き止まりにならず探索を続けられる（根源的・全パネル共通）。
function gPanel(title, bodyHtml, term) {
  const jp = LANG === "ja";
  const continueTerm = _activeTerm(term);
  const back = (_panelFromMenu && MENUCTX);   // ノードのメニューから開いた＝別メニューへ戻れるようにする
  const p = document.createElement("div");
  const foot = continueTerm ? `<div class="gp-cont"><span class="gp-cont-h">🧭 ${jp ? `「${esc(continueTerm)}」で続ける` : `continue with “${esc(continueTerm)}”`}：</span>` + [
    ["center", "🎯 " + (jp ? "中心に据える" : "centre")],
    ["lens", "👓 " + (jp ? "見方" : "views")],
    ["lang", "🌍 " + (jp ? "多言語" : "languages")],
    ["ext", "🌐 " + (jp ? "外部で調べる" : "external")],
    ["combine", "🔗 " + (jp ? "組み合わせ" : "combine")],
    ["history", "🧭 " + (jp ? "翻訳・受容史" : "translation history")],
    ["new", "↗ " + (jp ? "新タブ" : "new tab")],
  ].map(([a, l]) => `<button type="button" class="gp-cont-b" data-a="${a}">${esc(l)}</button>`).join("") + `</div>` : "";
  p.innerHTML = `<div class="gp-head">${back ? `<button type="button" class="gp-back" title="${jp ? "このノードのメニューに戻って別の項目を選ぶ" : "back to menu"}">← ${jp ? "メニュー" : "menu"}</button>` : ""}<b>${esc(title)}</b><button type="button" class="gp-x">×</button></div>
    <div class="gp-body">${bodyHtml}</div>${foot}`;
  // Action面の生成・置換・配置・z は surface manager が一元決定する（Context は破壊しない）
  surfCreate("action", p, SURF.anchor.menu || ((G && G.lastX != null) ? { x: G.lastX, y: G.lastY } : null));
  const closePanel = () => surfCloseAction(true);
  p.querySelector(".gp-x").addEventListener("click", closePanel);
  const bb = p.querySelector(".gp-back");
  if (bb) bb.addEventListener("click", () => { closePanel(); gReopenMenu(); });
  const FMAP = UI_ACTION_MAP.panelFooter;   // 面ごとに作用を再実装しない（registry宣言と同一）
  p.querySelectorAll(".gp-cont-b").forEach(btn => btn.addEventListener("click", async () => {
    const a = FMAP[btn.dataset.a]; if (!a) return;
    const footEl = btn.closest(".gp-cont");
    if (btn.disabled || (footEl && footEl.dataset.busy === "1")) return;
    if (footEl) { footEl.dataset.busy = "1"; footEl.querySelectorAll(".gp-cont-b").forEach(x => { x.disabled = true; }); }
    const r = btn.getBoundingClientRect();
    try {
      await dispatchAction(a, { term: continueTerm }, currentViewState(), { surface: "panel-footer", anchor: { x: Math.round(r.left + r.width / 2), y: Math.round(r.bottom + 6) } });
    } catch (err) {
      console.error("panel footer action", err);
    } finally {
      if (footEl && footEl.isConnected) { delete footEl.dataset.busy; footEl.querySelectorAll(".gp-cont-b").forEach(x => { x.disabled = false; }); }
    }
  }));
  return p;
}

/* ═══════════ 概念全景（Concept Panorama）＝語ノード選択時の広い詳細ドロワー（半田様2026-07-30）═══════════
   個別menu選択型→概念全景型。選択語に文脈(rootQ/parentTerm/edge/lens/nodeKind/layer)を渡し、意味契約ごとに
   分けた区画を出す。【意味契約】anatomy=語形成・借用・語彙史のみ／contrast(焦点)=意味・用法・概念作用の差
   （構成要素の再掲でない）／collapse=複数原語が一訳語へ統合された根拠がある時だけ／colloc=実コーパスの共起
   だけ／multilingual=翻字羅列でなく担い方の広がり。同じ事実は一度だけ・別カテゴリで穴埋めしない・契約を
   満たす源が無い区画は出さない。既存/api/origin・/api/anatomy・現graphを共有し重複取得しない。重い区画は遅延。 */
const _PANO_CACHE = {};   // term → { origin, anatomy }（区画間で共有＝同一endpointの重複取得を避ける）
async function panoData(term) {
  if (_PANO_CACHE[term]) return _PANO_CACHE[term];
  const [o, a] = await Promise.allSettled([
    api(`/api/origin?q=${encodeURIComponent(term)}&lang=${LANG}`),
    api(`/api/anatomy?q=${encodeURIComponent(term)}&lang=${LANG}&own=1`),   // S2は「語そのものの来歴」＝訳語でなく語自身（矛盾→矛+盾/韓非子）
  ]);
  const rec = { origin: o.status === "fulfilled" ? o.value : null, anatomy: a.status === "fulfilled" ? a.value : null };
  _PANO_CACHE[term] = rec; return rec;
}
const _pw = (x) => (x && (x.term || x.label || x.q || x.word)) || (typeof x === "string" ? x : "");
function _panoSection(id, heading, inner) {   // 実在する時だけ節を返す（番号なし・<section>+<h4>・目次と同名見出し）
  if (!inner) return null;   // 契約を満たす源が無い節は目次にも本文にも出さない（静かに除外）
  return { id, heading, html: `<section class="pano-sec" id="pano-${id}"><h4 class="pano-h">${esc(heading)}</h4><div class="pano-in">${inner}</div></section>` };
}
// 日本語UIでは、接地済みの**日本語**glossだけを併記する。英語gloss（spear/shield 等＝原語でなく英語訳）は
// 出さない（原語表記・言語名・出典だけを示す）。機械翻訳層・手書き辞書は追加しない（半田様2026-07-31）。
function _jaGloss(s) {
  s = (s || "").trim(); if (!s) return "";
  return /[ぁ-んァ-ヶ一-龥]/.test(s) ? s : "";   // 日本語文字を含む時だけ採る
}
// 概要（この場所での意味を短く）＝パネル最上部・目次には入れない。空なら欄ごと出さない（否定表示をしない）
function _panoLead(d, cx) {
  const gm = ((d.origin || {}).general_meaning || []);
  if (!gm.length) return "";   // 取得できない旨をユーザーへ示さず、存在する「見どころ」から始める
  const ctxLine = (cx.parentTerm && cx.parentTerm !== cx.term)
    ? `<p class="pano-ctx">この探索（${esc(cx.rootQ || "")}）の文脈で——「${esc(cx.parentTerm)}」から辿った——「${esc(cx.term)}」。</p>` : "";
  return `<div class="pano-lead"><p class="pano-eyebrow">この場所での意味</p>${ctxLine}`
    + `<p class="pano-lead-body">${esc((gm[0] || "").slice(0, 200))}</p></div>`;
}
// 「この語で見落としやすいこと」＝取得データに**両側の焦点が明示**されている時だけ出す（半田様2026-07-31）。
// 必要条件（すべて取得データから確認）: ①日本語側＝同一の訳語へ統合されたことが collapses_to に明示され、
// ②原語側＝その訳語へ統合される2つ以上の別語がそれぞれ日本語glossで別の焦点を持つ。
// general_meaning と単一の英語gloss から対比文を生成することは禁止（推論・翻訳層は追加しない）。
function _panoOverlook(d, cx) {
  const cw = (d.origin || {}).collapse_warning;
  const lem = (cw && cw.lemmas) || [];
  if (!lem.length) return "";
  // 同一の日本語訳語へ統合される、日本語glossを持つ別語を2件以上探す（＝統合の明示根拠）
  const byJa = {};
  lem.forEach(l => {
    const g = _jaGloss(l && l.gloss); if (!l || !l.lemma || !g) return;
    (l.collapses_to || []).forEach(ja => { (byJa[ja] = byJa[ja] || []).push({ lemma: l.lemma, gloss: g }); });
  });
  const keys = Object.keys(byJa).filter(k => byJa[k].length >= 2);
  if (!keys.length) return "";   // 両側の明示根拠が無ければ枠ごと出さない（穴埋め・推論禁止）
  const ja = keys.indexOf(cx.term) >= 0 ? cx.term : keys[0];
  const pair = byJa[ja].slice(0, 3);
  const src = [cw.primary_source, cw.confidence].filter(Boolean).map(esc).join("・");
  return `<div class="pano-overlook"><p class="pano-ol-h">この語で見落としやすいこと</p>`
    + `<p class="pano-ol-sub">日本語だけでは見えにくい、原語・文脈上の焦点。</p>`
    + `<p class="pano-ol-body">日本語では <b>「${esc(ja)}」</b> の一語にまとまるが、原語では次のように別の焦点として区別される：</p>`
    + `<ul class="pano-collapse">` + pair.map(x => `<li>${_entLink(x.lemma, "original", "orig:" + x.lemma)}＝${esc(x.gloss)}</li>`).join("") + `</ul>`
    + (cw.note ? `<p class="pano-ol-note">${esc(cw.note)}</p>` : "")
    + (src ? `<p class="srcline">${src}</p>` : "") + `</div>`;
}
function _panoHistory(d) {   // 語の来歴＝日本語漢字表記の語形・構成要素・原語表記・出典（英語散文は出さない）
  const a = d.anatomy || {};
  const semantic = ((a.segment_layers || []).find(x => x && x.level === "semantic") || {}).units || [];
  const hasForm = semantic.length || (a.components || []).length || (a.chain || []).length;
  if (!hasForm) return "";   // 語形・構成が無ければ来歴は出さない（英語散文だけでは出さない）
  let h = "";
  if (semantic.length) h += `<p class="pano-lbl">意味のまとまり（優先）</p><div class="anat-comp segment-panorama">`
    + semantic.map(u => `${_entLink(u.text, "word", "segment:" + u.text)}${u.gloss ? `<span class="anat-gloss">「${esc(u.gloss)}」</span>` : ""}`).join(`<span class="anat-plus">＋</span>`) + `</div>`;
  // 原語表記は保持し、glossは接地済みの日本語がある時だけ併記（英語訳は原語の意味として主表示しない）
  if ((a.components || []).length) h += `<p class="pano-lbl">語形・構成要素</p><div class="anat-comp">`
    + a.components.map(c => { const g = _jaGloss(c.meaning);
      return `<span class="anat-part">${_entLink(c.part, "original", "orig:" + c.part)}${g ? "＝" + esc(g) : ""}</span>`; }).join(`<span class="anat-plus">＋</span>`) + `</div>`;
  if ((a.chain || []).length) h += `<p class="pano-lbl">語形変化・借用の経路</p><div class="chain">`
    + a.chain.map(c => { const g = _jaGloss(c.gloss);
      return `<span class="chain-step"><span class="chain-lang">${esc(c.lang)}</span>${_entLink(c.term, "original", "orig:" + c.term)}${g ? `<span class="anat-gloss">「${esc(g)}」</span>` : ""}</span>`; }).join("<span class=\"chain-arrow\">←</span>") + `</div>`;
  if (a.wiktionary_url) h += `<p class="srcline"><a href="${esc(a.wiktionary_url)}" target="_blank">出典：Wiktionary${a.term ? `（${esc(a.term)}）` : ""}</a></p>`;
  return h;
}
// concept_origin（記事LEADの併記表記）は原語と訳語が混在する。語自身の語源データ（word_origin の言語／
// anatomy の語形）に接地するものだけを「原語」とし、それ以外は翻訳対応語として各言語での表記側へ回す
// （矛盾の contradiction（英語）を原語欄に置かない・半田様2026-08-01）。推測で振り分けない。
// 由来関係が実源で確認できるものだけを「原語・語源」とし、確認できないものは訳語（各言語での表記）とする。
// サイト内の全レンダラ（概念全景・旧カード）が同じ規則を使う（半田様2026-08-02）。
function _groundedOrigSplit(co, wordOrigin, forms) {
  const woName = (wordOrigin && wordOrigin.name) || "";
  const F = new Set((forms || []).filter(Boolean));
  const isOrig = (x) => !!x && ((woName && x.name === woName) || F.has(x.term));
  return { origs: (co || []).filter(isOrig), trans: (co || []).filter(x => !isOrig(x)) };
}
function _panoOrigSplit(d) {
  const o = d.origin || {}, a = d.anatomy || {};
  return _groundedOrigSplit(o.concept_origin || [], o.word_origin,
    [...(a.components || []).map(c => c.part), ...(a.chain || []).map(c => c.term), a.term]);
}
// ── 全景パネル内のクリック契約（半田様2026-08-02）──
//  A=目次(.pano-toc-a) 節内スクロールのみ／B=見出し・区分名・集約・件数（**リンクにしない**）／
//  C=実在する語・人物・著作(.pano-ent) クリックで既存の標準操作メニュー(gMenu)／D=開閉(summary)・外部出典(a[target=_blank])
// Cは表示文字列や親見出しから対象を逆算せず、data-term/data-kind/data-eid（stable ID）を保持する。
const _ENT_KINDS = new Set(["word", "original", "language", "related", "opposite", "author", "work", "application", "concept"]);
// 実グラフに同じ語の実体ノードがあれば、その **stable ID** を採る（"related:"+w のような合成IDが
// グラフの id（rel:西洋哲学 等）と食い違い、ラベル一致fallbackで domain ノードへ化けるのを防ぐ）。
function _gnodeFor(term, kind) {
  const pool = (G && G.nodes) || [];
  const t = String(term || "");
  return pool.find(n => n && _ENT_KINDS.has(n.kind) && n.kind === kind && (n.q || n.label) === t)
      || pool.find(n => n && _ENT_KINDS.has(n.kind) && (n.q || n.label) === t) || null;
}
function _entLink(term, kind, id, label) {
  const t = String(term == null ? "" : term).trim(); if (!t) return "";
  const k = _ENT_KINDS.has(kind) ? kind : "word";
  const gn = _gnodeFor(t, k);
  const eid = (gn && gn.id) || id || (k + ":" + t);
  return `<a href="#" class="pano-ent" data-term="${esc(t)}" data-kind="${esc(k)}" data-eid="${esc(eid)}">${esc(label || t)}</a>`;
}
// Cのクリック＝派生グラフノードと同じ正典経路（既存gMenu）。親要素への伝播で区分名が選ばれるのを止める。
function _panoBindEntities(panel) {
  panel.addEventListener("click", (e) => {
    const a = e.target.closest(".pano-ent"); if (!a) return;
    e.preventDefault(); e.stopPropagation();
    const term = a.dataset.term, kind = a.dataset.kind || "word", eid = a.dataset.eid;
    if (!term) return;                                   // 空targetでは何もしない
    const pool = (G && G.nodes) || [];
    // 構造ノード（domain等）へは決して落とさない＝実体ノードか、data属性から作る実体だけを対象にする
    const node = pool.find(n => n.id === eid && _ENT_KINDS.has(n.kind)) || _gnodeFor(term, kind)
      || { id: eid, label: term, q: term, kind, layer: null };
    const r = a.getBoundingClientRect();
    gMenu(Math.round(r.left + r.width / 2), Math.round(r.bottom + 6), node);
  });
}
function _panoBearers(d) {   // 原語・思想家・著作（概念を担った系譜＝日本語表記の来歴とは別次元）
  const o = d.origin || {}; let h = "";
  const co = _panoOrigSplit(d).origs;   // 語自身の語源に接地した原語だけ（翻訳対応語は表記側へ）
  if (co.length) h += `<p class="pano-lbl">概念を担った原語</p><p class="pano-terms">`
    + co.map(x => `${_entLink(x.term, "original", "orig:" + x.term)}${x.name ? `（${esc(x.name)}）` : ""}`).join("　") + `</p>`;
  const persons = (o.associated || []).filter(x => x && x.is_person).slice(0, 8);
  if (persons.length) h += `<p class="pano-lbl">この概念を担った思想家</p><p class="pano-terms">`
    + persons.map(x => _entLink(_pw(x), "author", x.qid ? ("wd:" + x.qid) : ("author:" + _pw(x)))).join("　") + `</p>`;
  return h;
}
function _panoFocus(d) {   // 翻訳で変わった焦点（意味・用法・概念作用の差＝構成要素の再掲でない）
  const cw = (d.origin || {}).collapse_warning;
  if (!(cw && cw.lemmas && cw.lemmas.length)) return "";   // 複数原語が一訳語へ統合された根拠がある時だけ
  return `<p class="pano-note">この訳語には、原語では区別される複数の意味・焦点が畳み込まれています（意味・用法・概念作用の差）。</p><ul class="pano-collapse">`
    + cw.lemmas.map(l => { const g = _jaGloss(l.gloss);
      return `<li>${_entLink(l.lemma, "original", "orig:" + l.lemma)}${g ? `＝${esc(g)}` : ""}</li>`; }).join("") + `</ul>`;
}
function _panoRelations(d, cx) {   // 関係・対立・運動
  const o = d.origin || {}, rel = o.relations || {}; let h = "";
  const opp = (rel.opposite || []).map(_pw).filter(Boolean).slice(0, 10);
  const near = (rel.near || []).map(_pw).filter(Boolean).slice(0, 10);
  const concepts = (o.associated || []).filter(x => x && !x.is_person).map(_pw).filter(Boolean).slice(0, 10);
  // 「対立」「近い概念」「関連」は**区分名（B）**＝リンクにしない。語だけがエンティティ（C）。
  const row = (lbl, arr, kind) => arr.length ? `<p class="pano-lbl">${lbl}</p><p class="pano-terms">`
    + arr.map(w => _entLink(w, kind, kind + ":" + w)).join("　") + `</p>` : "";
  h += row("対立", opp, "opposite") + row("近い概念", near, "related") + row("関連", concepts, "related");
  return h || "";   // 実データが無ければ節を出さない
}
// 意味・焦点・用法の差が出典に接地している場合だけ「言語間の意味変化」と呼ぶ。表記しか無ければ
// 見出しも目次も「各言語での表記」にする（表記一覧を意味変化と偽らない・半田様2026-08-01）。
function _panoLangHasSense(d) {
  return ((d.origin || {}).breadth || []).some(b => b && (_jaGloss(b.gloss) || _jaGloss(b.sense) || _jaGloss(b.note)));
}
function _panoLangHeading(d) { return _panoLangHasSense(d) ? "言語間の意味変化" : "各言語での表記"; }
function _panoLang(d) {   // 各言語での表記（代表例＋展開・翻字の全列挙にしない）
  const br = ((d.origin || {}).breadth || []).slice();
  // 原語に接地しなかった concept_origin（翻訳対応語）はここへ統合し、原語欄との重複表示をしない
  const seen = new Set(br.map(b => (b.name || "") + " " + (b.term || "")));
  _panoOrigSplit(d).trans.forEach(t => { const k = (t.name || "") + " " + (t.term || ""); if (!seen.has(k)) { seen.add(k); br.unshift({ name: t.name, term: t.term }); } });
  if (!br.length) return "";
  const withSense = _panoLangHasSense(d);
  // 言語名（Chinese/Japanese 等）は**区分名（B）**＝リンクにしない。語形がある時だけ語をエンティティ（C）にする。
  const chip = (b) => { const g = _jaGloss(b.gloss) || _jaGloss(b.sense) || "";
    return `<span class="breadth-chip">${esc(b.name)}${b.term ? "：" + _entLink(b.term, "language", "lang:" + (b.name || "") + ":" + b.term) : ""}${g ? `<span class="anat-gloss">「${esc(g)}」</span>` : ""}</span>`; };
  const rep = br.slice(0, 12), rest = br.slice(12);
  const note = withSense
    ? "この概念が言語ごとにどう意味・焦点を変えるか（出典に接地した差のみ）。"
    : "この概念を各言語でどう表記するか（代表例）。意味の差までは確認できていないため、表記として示します。";
  let h = `<p class="pano-note">${note}</p><div class="breadth-chips">${rep.map(chip).join("")}</div>`;
  if (rest.length) h += `<details class="pano-more"><summary>他 ${rest.length} 言語を展開</summary><div class="breadth-chips">${rest.map(chip).join("")}</div></details>`;
  return h;
}
function _panoColloc(d, cx) {   // 実際の用法・共起（実コーパスのみ・描画後に自動取得）
  // 人物・著作はコーパスの見出し語でない＝対象外（節を作らない）。押せないボタンを見せないため
  // ボタン自体を置かず、描画後に自動取得し、空・取得不能なら節と目次項目を静かに除去する。
  if (cx.nodeKind === "author" || cx.nodeKind === "work") return "";
  const de = ((d.origin || {}).concept_origin || []).find(x => x.name === "ドイツ語");
  const hasCorpus = de || /[A-Za-zÀ-ÿ]/.test(cx.term);   // DWDS(独語)コーパスに載りうる時だけ節を出す
  if (!hasCorpus) return "";
  return `<div class="pano-lazy" data-term="${esc(cx.term)}"><p class="pano-note">実コーパス（DWDS・独語）から取得中…</p></div>`;
}
// 共起が空/失敗＝失敗説明を出さず、その節と対応する目次項目を静かに取り除く（他の見どころ・枝はそのまま残る）
function _panoDropSection(id) {
  const sec = $("pano-" + id); if (sec) sec.remove();
  const a = document.querySelector(`.pano-toc-a[data-sec="${id}"]`); if (a) a.remove();
  const toc = document.querySelector(".pano-toc");
  if (toc && !toc.querySelector(".pano-toc-a")) toc.remove();   // 見どころが全て消えたら目次自体も残さない
}
// 次にたどれる言葉＝**実体を持つ語・人物・著作だけ**。root/domain/language-hub/section/group/count/metadata
// のような構造ノード、自分自身、term空、言語名だけ、stable IDの無い構造ラベル、正規化termの重複は除外する
// （「一般の意味」「専門・思想の意味」「世界の言語 127」を探索対象にしない・半田様2026-08-02）。
function _panoBranches(d, cx) {
  const out = [], seen = new Set();
  const norm = (s) => String(s || "").normalize("NFKC").trim().toLowerCase();
  const add = (term, kind, id) => {
    const t = String(term == null ? "" : term).trim();
    if (!t || !id) return;                                   // term空・stable ID無しは候補にしない
    if (!_ENT_KINDS.has(kind)) return;                       // 構造ノード（domain等）は語ではない
    if (norm(t) === norm(cx.term)) return;                   // 現在表示中の語自身
    const k = norm(t); if (seen.has(k)) return; seen.add(k); // 正規化termの重複
    out.push({ term: t, kind, id });
  };
  const gnode = (n) => { if (n && n.q) add(n.q, n.kind, n.id); };   // q（実体の語）が無いノード＝構造ノード
  if (G && G.nodes) {
    const idx = cx.node ? G.nodes.indexOf(cx.node) : -1;
    if (idx >= 0) {
      ((G.children && G.children[idx]) || []).forEach(c => gnode(G.nodes[c]));
      const pi = (G.parent && G.parent[idx] != null) ? G.parent[idx] : null;
      if (pi != null) { gnode(G.nodes[pi]); ((G.children && G.children[pi]) || []).slice(0, 6).forEach(c => gnode(G.nodes[c])); }
    }
    if (!out.length) G.nodes.forEach(n => { if (n && n.layer >= 2) gnode(n); });   // 中心語の全景＝グラフの実体ノードから
  }
  _panoOrigSplit(d).origs.slice(0, 4).forEach(x => add(x.term, "original", "orig:" + x.term));
  (((d.origin || {}).breadth) || []).filter(b => b && b.term).slice(0, 4)
    .forEach(b => add(b.term, "language", "lang:" + (b.name || "") + ":" + b.term));
  const chips = out.slice(0, 12).map(e => _entLink(e.term, e.kind, e.id));
  if (!chips.length) return "";
  return `<p class="pano-note">ここからたどれる言葉（クリックすると、その語の操作メニューを開きます）。</p>`
    + `<p class="pano-branch">${chips.join("　")}</p>`;
}
// Context面（右側の概念全景）。Action(#graph-panel)とは**別のDOM id**にする＝Action系Actionが
// Contextを破壊しない（id衝突の根治・半田様2026-08-02）。生成・置換・破棄は surface manager 経由。
function _panoShell(title, term) {   // ヘッダは title＋閉じる、下部には常時使える次アクションを置く。
  const jp = LANG === "ja";
  const p = document.createElement("div"); p.className = "gp-wide";
  const next = term ? noMiss(term, { lead: jp ? `「${term}」から次にできること` : `Next actions for “${term}”` }) : "";
  p.innerHTML = `<div class="gp-head"><b>${esc(title)}</b><button type="button" class="gp-x" title="${jp ? "閉じる" : "close"}">×</button></div><div class="gp-body"></div><div class="pano-next">${next}</div>`;
  surfCreate("context", p);
  // ユーザーが×で閉じるまで（または別全景へ置換されるまで）Contextは残る
  p.querySelector(".gp-x").addEventListener("click", () => {
    surfDestroy("context");
    if (!NAV.txn && !NAV.restoring) navCommit(currentViewState());
  });
  return p;
}
function _panoBindLazy(bodyEl) {
  bodyEl.querySelectorAll(".pano-lazy").forEach(async (box) => {   // 描画後に自動取得（押せないボタンを見せない）
    const term = box.dataset.term; if (!term) return;
    try {
      let deTerm = term;
      if (!/[A-Za-zÀ-ÿ]/.test(term)) { const od = await panoData(term); const g = (((od.origin || {}).concept_origin) || []).find(x => x.name === "ドイツ語"); if (!g) { _panoDropSection("colloc"); return; } deTerm = g.term; }
      const d = await api(`/api/collocations?term=${encodeURIComponent(deTerm)}&lang=de`);
      const rels = (d && d.relations) || {}, keys = Object.keys(rels);
      if (!keys.length) { _panoDropSection("colloc"); return; }   // 空＝節と目次項目を除去（失敗説明を出さない）
      box.innerHTML = `<table class="plain orig-collo">` + keys.map(rel => `<tr><td class="srcline">${esc(rel)}</td><td>`
        + (rels[rel] || []).slice(0, 8).map(w => { const t = _pw(w); return _entLink(t, "original", "colloc:" + t); }).join("・") + `</td></tr>`).join("")
        + `</table><p class="srcline">${esc(deTerm)}・DWDS（独語コーパス）</p>`;
    } catch (e) { console.error("pano colloc", e); _panoDropSection("colloc"); }
  });
}
// 「この語の見どころ」＝パネル内目次（実在する節だけから自動生成・本文と同名・クリックでスクロール・読了節を強調）
// 目次の選択状態（半田様2026-08-01の回帰是正）:
//  旧実装は判定に offsetTop（コンテンツ座標）＋scrollTop を使い、スクロール/表示位置は rect（client座標）
//  という**異なる座標系の混在**だった。パネル下端まで来ると対象節の先頭を上端まで運べず、
//  「判定線を跨いだ最後の節」が常に選ばれて別項目（原語・思想家・著作）へ誤反転していた。
//  → 判定は client座標に一本化し、明示クリック中はロックして誤反転させない。
function _panoBindToc(panel) {
  const links = [...panel.querySelectorAll(".pano-toc-a")];
  if (!links.length) return;
  const scroll = panel.querySelector(".gp-body") || panel;
  let locked = null;   // 明示クリックで選ばれた節id（ユーザーが自分でスクロールするまで維持）
  const secs = () => [...panel.querySelectorAll(".pano-sec")];
  // 判定線＝固定ヘッダ＋固定目次の直下（client座標・スクロール量に依存しない）
  const line = () => {
    const pr = scroll.getBoundingClientRect();
    const tc = panel.querySelector(".pano-toc");
    return pr.top + (tc ? tc.getBoundingClientRect().height : 0) + 8;
  };
  const paint = (id) => links.forEach(a => a.classList.toggle("active", ("pano-" + a.dataset.sec) === id));
  // 通常スクロール時に「いま主に見えている節」を同一座標系で選ぶ
  const visibleId = () => {
    const list = secs(); if (!list.length) return null;
    const L = line(), pr = scroll.getBoundingClientRect();
    const atBottom = scroll.scrollTop + scroll.clientHeight >= scroll.scrollHeight - 2;
    if (atBottom) {   // 下端＝先頭を上端まで運べない。表示中の節のうち最後のものを選ぶ
      const vis = list.filter(s => { const r = s.getBoundingClientRect(); return r.bottom > L && r.top < pr.bottom; });
      return (vis[vis.length - 1] || list[list.length - 1]).id;
    }
    let cur = list[0].id;
    for (const s of list) { const r = s.getBoundingClientRect(); if (r.top <= L + 2) cur = s.id; else break; }
    return cur;
  };
  const spy = () => { if (locked) return; paint(visibleId()); };   // 明示クリック中は通常スクロール判定を止める
  links.forEach(a => a.addEventListener("click", (e) => {
    e.preventDefault();
    const id = "pano-" + a.dataset.sec, s = panel.querySelector("#" + id);
    locked = id; paint(id);                                        // 押した項目を即active（短いパネルでも変わる）
    if (s) s.scrollIntoView({ behavior: "smooth", block: "start" });
    // 明示クリックのactiveは**ユーザー自身が動かすまで**維持する（半田様2026-08-02）。
    // 旧実装はスクロール完了後に visibleId() で再判定していたが、smooth scroll の残りイベントや
    // 下端到達（atBottom分岐）で「表示中の最後の節」へ誤反転しうる（bearers→branches の実測回帰）。
    // ロック解除は下の wheel/touchmove/keydown（＝ユーザー操作）だけが行う。
  }));
  // ユーザー自身の操作（ホイール/タッチ/キー）でロック解除＝明示クリック中と通常スクロール中を区別する
  ["wheel", "touchmove", "keydown"].forEach(ev => panel.addEventListener(ev, () => { locked = null; }, { passive: true }));
  scroll.addEventListener("scroll", spy);
  paint(visibleId());
}
async function gPanorama(ctx) {
  ctx = ctx || {}; const jp = LANG === "ja"; const term = ctx.term || "";
  if (!term) return;
  const node = ctx.node || (G && (G.nodes || []).find(n => (n.q || n.label) === term)) || null;
  const idx = (node && G) ? G.nodes.indexOf(node) : -1;
  // 文脈（タイトルの「〜の中の」）は、実グラフの到達経路を上へ辿って求める。ただし
  //  ・同種ノード間の親（思想家→思想家の影響線。例: マルクスの親がレーニン）は文脈にしない
  //  ・domain（分類の箱）も飛ばし、その上の「語」を文脈にする
  // ＝直前に開いたPANEL_CTXや選択順序には一切依存しない（順序を入れ替えても同じタイトル・半田様2026-08-01）
  let parent = null;
  if (idx >= 0 && G && G.parent) {
    let pi = G.parent[idx];
    for (let guard = 0; pi != null && guard < 8; guard++) {
      const pn = G.nodes[pi]; if (!pn) break;
      if (pn.kind !== "domain" && (!node || pn.kind !== node.kind)) { parent = pn; break; }
      pi = G.parent[pi];
    }
  }
  const cx = { term, node, nodeId: node && node.id, nodeKind: node && node.kind, layer: node && node.layer,
    rootQ: (G && G.rootQ) || term, parentTerm: parent ? (parent.q || parent.label) : ((G && G.rootQ) || ""), lens: (typeof G_lens !== "undefined" ? G_lens : "all") };
  const title = (cx.parentTerm && cx.parentTerm !== term) ? `${term}（${cx.parentTerm}の中の）` : term;
  const p = _panoShell(title, term);
  CONTEXT_CTX = { term };   // Contextの対象＝この語（ViewStateに入り、戻る/進むでMapと一緒に復元される）
  const bodyEl = p.querySelector(".gp-body");
  bodyEl.innerHTML = `<p class="muted">${jp ? "概念全景を読み込み中…" : "loading panorama…"}</p>`;
  let d;
  try { d = await panoData(term); } catch (e) {
    console.error("panorama", e);
    if (surfEl("context") !== p) return false;
    bodyEl.innerHTML = `<div class="pano-outcome"><p class="pano-note">${jp ? "概念全景の取得を見送りました。検索条件を保ったまま、下の入口や外部の専門情報源から続けられます。" : "Panorama retrieval was deferred. Continue with the same term below or via external sources."}</p>${extResourcesHtml(term, {})}</div>`;
    return false;
  }   // /api/origin＋/api/anatomy を1回だけ取得（節間で共有）
  if (surfEl("context") !== p) return;   // 途中で閉じ/遷移したら描かない
  // 実在する節だけ（番号なし・見出し名は目次と同一）
  const built = [
    _panoSection("history", "語の来歴", _panoHistory(d)),
    _panoSection("bearers", "原語・思想家・著作", _panoBearers(d)),
    _panoSection("focus", "翻訳で変わった焦点", _panoFocus(d)),
    _panoSection("relations", "関係・対立・運動", _panoRelations(d, cx)),
    _panoSection("lang", _panoLangHeading(d), _panoLang(d)),   // 意味差データが無ければ「各言語での表記」
    _panoSection("colloc", "実際の用法・共起", _panoColloc(d, cx)),
    _panoSection("branches", "次にたどれる言葉", _panoBranches(d, cx)),
  ].filter(Boolean);
  const toc = built.length ? `<nav class="pano-toc"><span class="pano-toc-h">この語の見どころ</span>`
    + built.map(s => `<a href="#" class="pano-toc-a" data-sec="${s.id}">${esc(s.heading)}</a>`).join("") + `</nav>` : "";
  bodyEl.innerHTML = built.length
    ? _panoLead(d, cx) + _panoOverlook(d, cx) + toc + built.map(s => s.html).join("")
    : `<div class="pano-outcome"><p class="pano-note">${jp ? "この語について表示できる接地済みの全景データがまだ返っていないため、結果を作らず次の入口を残します。" : "No grounded panorama sections were returned yet; the next entry points remain available."}</p>${extResourcesHtml(term, {})}</div>`;
  _panoBindLazy(bodyEl);
  _panoBindToc(p);
  _panoBindEntities(p);   // C（実在する語・人物・著作）のクリック＝既存の標準操作メニュー
  if (ctx.secHint) { const s = $("pano-" + ctx.secHint); if (s) s.scrollIntoView({ behavior: "smooth", block: "start" }); }   // domainノード等の「関心のある箇所へ進む」
}

function _combineSearchQuery(a, b, op) {
  const qa = `"${String(a || "").trim()}"`, qb = `"${String(b || "").trim()}"`;
  if (op === "or") return `${qa} OR ${qb}`;
  if (op === "not") return `${qa} -${qb}`;
  return `${qa} ${qb}`;
}

function _combineExternalLinks(a, b, op) {
  const q = encodeURIComponent(_combineSearchQuery(a, b, op));
  const links = [
    ["Google", `https://www.google.com/search?q=${q}`],
    ["Google Scholar", `https://scholar.google.com/scholar?q=${q}`],
    ["Bing", `https://www.bing.com/search?q=${q}`],
    ["DuckDuckGo", `https://duckduckgo.com/?q=${q}`],
    ["Wikipedia", `https://ja.wikipedia.org/w/index.php?search=${q}`],
    ["OpenAlex", `https://openalex.org/works?search=${q}`],
  ];
  return `<div class="ext-cat combine-ext">${links.map(([label, url]) =>
    `<a class="ext-link" href="${esc(url)}" target="_blank" rel="noopener">${esc(label)}</a>`).join(" ")}</div>`;
}

// 組み合わせの「空/取得失敗」は、検索を実行しなかったことではない。
// 検索条件・結果状態・原因・次の実行先を同じ面に残し、元Mapを黙って表示し続けない。
function gCombineOutcomePanel(a, b, op, data, status) {
  const jp = LANG === "ja";
  const note = String((data && data.note) || "").trim();
  const sourceGap = status === "error" || /準備中|利用できない|接続|未応答|timeout|Timeout|失敗/i.test(note);
  const opLabel = { and: "AND", semand: "意味で絞る", not: "NOT", or: "OR", compare: "比較" }[op] || op;
  const query = _combineSearchQuery(a, b, op);
  const reason = status === "error"
    ? (jp ? "内部の組み合わせ検索源は時間枠内に応答情報を返さなかったため、元の地図を保持しました。" : "The internal combination source did not return within the time window; the current map was kept.")
    : sourceGap
      ? (jp ? "内部の一般ウェブ検索源から表示に使える結果が届かなかったため、元の地図を保持しました。" : "The internal web source returned no displayable result; the current map was kept.")
      : (jp ? "この条件の一致情報が返らなかったため、元の地図を保持しました。" : "No matching information was returned; the current map was kept.");
  const detail = note ? `<p class="combine-reason-detail">${esc(note)}</p>` : "";
  const headline = status === "error"
    ? (jp ? "内部検索：応答情報を待つ時間枠を終了しました" : "Internal search: the response window ended")
    : sourceGap
      ? (jp ? `${opLabel}検索を試み、確認面を表示しました` : `${opLabel} search was attempted; the check view is shown`)
      : (jp ? `${opLabel}検索を実行しました` : `${opLabel} search was executed`);
  const html = `<div class="combine-outcome" data-combine-status="${esc(status)}">
    <p class="combine-status"><b>${headline}</b></p>
    <p>${esc(reason)}</p>${detail}
    <p class="combine-query"><span class="srcline">${jp ? "検索条件" : "query"}</span><br><code>${esc(query)}</code></p>
    <h4 class="gp-h">${jp ? "同じ条件で検索を続ける" : "Continue with the same condition"}</h4>
    ${_combineExternalLinks(a, b, op)}
    <p><button type="button" id="combine-edit" class="cmb-op">${jp ? "条件を変更して再検索" : "edit and retry"}</button></p>
  </div>`;
  PANEL_CTX = { action: "combine", term: a };
  const p = gPanel((jp ? "組み合わせ検索：" : "Combination search: ") + `${a} ${opLabel} ${b}`, html, a);
  const edit = p && p.querySelector("#combine-edit");
  if (edit) edit.addEventListener("click", () => {
    dispatchAction("combine", { term: a }, currentViewState(), { surface: "combine-recovery", retryB: b, retryOp: op });
  });
  return p;
}

// A: ユーザー主導の組み合わせ探索（半田様のAND案）。語を入れて操作を選ぶ。
function gCombinePanel(a, initialB = "", initialOp = "and") {
  const jp = LANG === "ja";
  const ops = [["and", "絞り込み（AND）"], ["semand", "意味で絞る"], ["not", "除外（NOT）"],
               ["or", "合わせる（OR）"], ["compare", "比較（vs）"]];
  const html = `<p class="muted">${jp ? `「${esc(a)}」に別の語を組み合わせて探索します。語を入れて操作を選んでください。` : `Combine “${esc(a)}” with another word.`}</p>
    <input id="cmb-b" class="cmb-in" value="${esc(initialB)}" placeholder="${jp ? "組み合わせる語（例：教育／労働／音楽）" : "second word"}" autocomplete="off" />
    <div class="cmb-ops">${ops.map(([k, l]) => `<button type="button" class="cmb-op${k === initialOp ? " on" : ""}" data-op="${k}">${esc(l)}</button>`).join("")}</div>
    <p class="srcline muted">${jp ? "AND=両方に関わる／意味で絞る=意味の近縁をその観点で／NOT=除外／OR=合わせる／比較=共有と差分。ORと比較は空でも可。" : ""}</p>
    <p id="cmb-note" class="combine-form-note" role="status" aria-live="polite"></p>`;
  const p = gPanel((jp ? "別の語と組み合わせる：" : "Combine: ") + a, html, a);
  const inp = p.querySelector("#cmb-b");
  const formNote = p.querySelector("#cmb-note");
  setTimeout(() => inp && inp.focus(), 30);
  p.querySelectorAll(".cmb-op").forEach(btn => btn.addEventListener("click", () => {
    const b = (inp.value || "").trim();
    if (!b && btn.dataset.op !== "or") {
      if (formNote) formNote.textContent = jp
        ? "2つ目の語を入力してください。例：吉本隆明"
        : "Enter a second word, for example: Yoshimoto Takaaki.";
      inp.focus(); return;
    }
    if (formNote) formNote.textContent = "";
    surfCloseAction(false); dispatchAction("combine", { term: a }, currentViewState(), { surface: "combine-form", b, op: btn.dataset.op });
  }));
  if (inp) inp.addEventListener("keydown", (e) => { if (e.key === "Enter") {
    const b = inp.value.trim();
    if (b) { if (formNote) formNote.textContent = ""; surfCloseAction(false); dispatchAction("combine", { term: a }, currentViewState(), { surface: "combine-form", b, op: "and" }); }
    else if (formNote) formNote.textContent = jp ? "2つ目の語を入力してください。例：吉本隆明" : "Enter a second word.";
  } });
}
async function gCombineRun(a, b, op) {
  const jp = LANG === "ja";
  gBusy(true, jp ? "組み合わせ探索中…" : "combining…", G && G.lastX, G && G.lastY);
  let d;
  // SearXNG→Wikipediaの二段経路は通常の単一APIより時間がかかる。
  // 共通20秒制限で正常な退避結果を途中で捨てない一方、45秒で説明面へ収束する。
  try { d = await api(`/api/combine?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}&op=${op}&lang=${LANG}`, { timeout: 45000 }); }
  catch (e) {
    console.error(e); gBusy(false);
    gCombineOutcomePanel(a, b, op, { note: e && e.name === "TimeoutError"
      ? "内部検索源の応答が時間内に返りませんでした。"
      : "内部検索源への接続が完了しませんでした。" }, "error");
    return false;
  }
  gBusy(false);
  if (!d.nodes || d.nodes.length <= 1 || d.has_results === false) {
    gCombineOutcomePanel(a, b, op, d, "empty");
    return false;
  }
  showCanvas();
  G_raw = d; G_lens = "all";                    // 組み合わせ結果を今のグラフに描く
  const note = $("graph-note"); if (note) note.textContent = d.note || "";
  gBuild(d);
  COMBINE_CTX = { a, b, op }; PANEL_CTX = null;  // 組合せ結果は確定状態（戻る/進むで復元）
  const w = $("origin-graph-wrap"); if (w) w.scrollIntoView({ behavior: "smooth", block: "start" });
  navCommit(currentViewState());                 // 1操作1commit（restoring/txn中は no-op）
}

// B: 視点・目的・難易度＝同じ概念を「あなたの見方」で。選ぶと、その見方に合う入口(言語対応の
// 外部源)＋その見方で深掘りするAI用プロンプト(あなたのAIに貼る)を作る。ポータル内LLMは使わない。
const PERSPECTIVES = {
  "子ども向け": { cur: ["Wikipedia 日", "コトバンク"], frame: "やさしい言葉で、身近な例や物語を交え、なぜ面白いかを伝える。専門用語は避ける。" },
  "一般向け": { cur: ["Wikipedia 日", "Wikipedia 英", "Britannica"], frame: "一般の大人に、背景と要点をバランスよく。" },
  "専門家向け": { cur: ["Stanford哲学百科 SEP", "PhilPapers", "OpenAlex", "Perseus 希/羅"], frame: "専門家向けに、一次文献・標準的な参照箇所・論争の所在を厳密に。原語で確認する。" },
  "批判的に": { cur: ["Stanford哲学百科 SEP", "PhilPapers"], frame: "批判的視点で、主要な反論・対立仮説・弱点を steelman（最強の形）で検討する。" },
  "歴史的に": { cur: ["Wikipedia 独", "Perseus 希/羅", "Project Gutenberg"], frame: "歴史的・通時的に、概念の起源・変遷・再評価を年代順に辿る。" },
  "実用（AI・仕事）": { cur: ["OpenAlex", "Google Scholar"], frame: "実用・応用の観点で、現代の労働・消費・AI・制度への含意を具体的に。" },
};
const PURPOSES = { "知りたい": "", "レポート": "レポートに使える構成（主張・根拠・引用）で。", "議論の材料": "議論のための論点・賛否・具体例を。", "授業で使う": "授業で使える説明・問い・活動案を。", "面白がる": "意外な関係やセレンディピティ、驚きのある切り口を。" };
const LEVELS = { "やさしい": "小学生〜中学生にも分かる平易さで。", "ふつう": "高校〜一般の水準で。", "専門的": "専門・研究水準で厳密に。" };

// E: 遊び・セレンディピティ＝つなぐ・おみくじ・クイズ。思いがけない出会いと学びを、子どもから
// 大人まで。おみくじは面白い概念の種list（無料・鍵不要）、つなぐは組み合わせ(AND)、クイズは
// その語のWikidata(対義/発見者/由来)から機械生成。
const OMIKUJI = ["リゾーム", "疎外", "縁起", "間主観性", "自由", "正義", "時間", "無", "気", "道",
  "イデア", "弁証法", "実存", "現象学", "権力", "贈与", "身体", "他者", "記憶", "崇高",
  "アイロニー", "ミメーシス", "カタルシス", "エントロピー", "創発", "アフォーダンス", "脱構築",
  "パノプティコン", "シミュラークル", "ノマド", "永遠回帰", "ルサンチマン", "アンガージュマン",
  "純粋経験", "物自体", "アウラ", "散種", "差延", "リヴァイアサン", "モナド"];

function gPlayPanel() {
  const jp = LANG === "ja";
  const cur = (G_raw && G_raw.query) || ((document.querySelector('.searchbox input[name=q]') || {}).value) || "";
  const html = `<p class="muted">${jp ? "思いがけない出会い（セレンディピティ）と、ちょっとした学びの遊びです。子どもから大人まで。" : "Serendipity games."}</p>
    <h4 class="gp-h">🔮 ${jp ? "おみくじ（今日の概念）" : "Random concept"}</h4>
    <p><button type="button" id="play-omi" class="cmb-op">${jp ? "ランダムな概念を引く" : "draw"}</button></p>
    <h4 class="gp-h">🔗 ${jp ? "2語をつなぐ" : "Bridge two words"}</h4>
    <div class="psp-g"><input id="play-a" class="cmb-in" style="width:44%" placeholder="${jp ? `1つ目（既定=${esc(cur)}）` : "word A"}"/><input id="play-b" class="cmb-in" style="width:44%" placeholder="${jp ? "2つ目（例：音楽）" : "word B"}"/></div>
    <p><button type="button" id="play-bridge" class="cmb-op">${jp ? "どうつながる？" : "connect"}</button></p>
    <h4 class="gp-h">❓ ${jp ? "クイズ" : "Quiz"}</h4>
    <p><button type="button" id="play-quiz" class="cmb-op">${esc(cur || "—")} ${jp ? "で出題" : "quiz"}</button></p>
    <p id="play-note" class="combine-form-note" role="status" aria-live="polite"></p><div id="play-out"></div>`;
  const p = gPanel(jp ? "遊ぶ：つなぐ・おみくじ・クイズ" : "Play", html, cur);
  p.querySelector("#play-omi").addEventListener("click", () => {
    const pool = OMIKUJI.filter(x => !G || x !== G.rootQ);   // 現在語を除外＝必ず別概念へ移動（決定論的に移る）
    const w = pool[Math.floor(Math.random() * pool.length)] || OMIKUJI[0];
    surfCloseAction(false); dispatchAction("center", { term: w }, currentViewState(), { surface: "play" });   // 単一Dispatcher経由
  });
  p.querySelector("#play-bridge").addEventListener("click", () => {
    const a = (p.querySelector("#play-a").value || cur).trim(), b = (p.querySelector("#play-b").value || "").trim();
    const note = p.querySelector("#play-note");
    if (!a || !b) { if (note) note.textContent = jp ? "2つの語を入力してください。例：弁証法／音楽" : "Enter two words, for example: dialectic / music."; p.querySelector("#play-b").focus(); return; }
    if (note) note.textContent = "";
    surfCloseAction(false); dispatchAction("combine", { term: a }, currentViewState(), { surface: "play", b, op: "and" });
  });
  p.querySelector("#play-quiz").addEventListener("click", async () => {
    const out = p.querySelector("#play-out"); if (!cur) { out.innerHTML = `<p class="muted">${jp ? "先に語を選んでください。" : "pick a word first."}</p>`; return; }
    out.innerHTML = `<p class="muted">${jp ? "出題準備中…" : "…"}</p>`;
    let d; try { d = await api(`/api/origin?q=${encodeURIComponent(cur)}&lang=${LANG}`); } catch (e) { out.innerHTML = `<p class="srcline">${jp ? "出題データの取得を見送りました。" : "Question data was deferred."}</p>${noMiss(cur)}`; return; }   // 否定表示を出さず建設的代替へ
    const opp = ((d.relations && d.relations.opposite) || [])[0], org = (d.originators || [])[0],
          assoc = (d.associated || [])[0], na = (d.named_after || [])[0];
    let qtext, ans;
    if (org) { qtext = `「${cur}」を立てた（発見・考案した）思想家は？`; ans = org.label; }
    else if (opp) { qtext = `「${cur}」と対立・区別される概念は？`; ans = opp.label; }
    else if (assoc) { qtext = `「${cur}」に最も深く関わる思想家は？`; ans = assoc.label; }
    else if (na) { qtext = `「${cur}」の語形の由来（語源）は？`; ans = na.label; }
    else { out.innerHTML = `<p class="srcline">${jp ? "この語の出題根拠がまだ返っていないため、別の入口を残します。" : "No grounded quiz clue was returned yet; the next entry points remain."}</p>${noMiss(cur)}`; return; }   // 否定表示を出さず建設的代替へ
    out.innerHTML = `<p><b>${esc(qtext)}</b></p><p><button type="button" id="quiz-rev" class="cmb-op">${jp ? "答えを見る" : "reveal"}</button> <span id="quiz-ans"></span></p>`;
    p.querySelector("#quiz-rev").addEventListener("click", () => { p.querySelector("#quiz-ans").innerHTML = `→ <b>${esc(ans)}</b>`; });
  });
}

// D: 収集・経路保存・自分のレンズ（localStorage・鍵不要・自分で拡張し蓄積する＝並ぶことの喜び）
function _lsGet(k, def) { try { return JSON.parse(localStorage.getItem(k)) || def; } catch (e) { return def; } }
function _lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
function gToast(msg) { let t = $("dx-toast"); if (!t) { t = document.createElement("div"); t.id = "dx-toast"; document.body.appendChild(t); } t.textContent = msg; t.style.display = "block"; clearTimeout(t._h); t._h = setTimeout(() => { t.style.display = "none"; }, 1800); }
function shelfAdd(w) { const s = _lsGet("dx_shelf", []); if (w && !s.includes(w)) { s.push(w); _lsSet("dx_shelf", s); } gToast(`「${w}」を棚に追加しました`); }

function gShelfPanel() {
  const jp = LANG === "ja";
  const cur = (G_raw && G_raw.query) || ((document.querySelector('.searchbox input[name=q]') || {}).value) || "";
  const shelf = _lsGet("dx_shelf", []), paths = _lsGet("dx_paths", []), lenses = _lsGet("dx_lenses", []);
  const empty = `<span class="muted">${jp ? "（まだありません）" : "(empty)"}</span>`;
  const chip = w => `<span class="shelf-item"><a href="#" class="shelf-go" data-w="${esc(w)}">${esc(w)}</a><a href="#" class="shelf-x" data-w="${esc(w)}" title="削除">×</a></span>`;
  const html = `<p class="muted">${jp ? "気に入った概念を集め、辿った道を保存し、自分の観点（レンズ）を作れます。あなただけの知の航海図です（この端末に保存）。" : "Your own collection, paths and lenses (saved on this device)."}</p>
    <h4 class="gp-h">⭐ ${jp ? "棚（集めた概念）" : "Shelf"}</h4>
    <p><button type="button" id="shelf-add" class="cmb-op">${jp ? `今の「${esc(cur)}」を棚に追加` : "add current"}</button></p>
    <div class="shelf-list">${shelf.length ? shelf.map(chip).join("") : empty}</div>
    <h4 class="gp-h">🧭 ${jp ? "探索の道（辿った経路を保存・再生）" : "Paths"}</h4>
    <p><button type="button" id="path-save" class="cmb-op">${jp ? "今の探索の道を保存" : "save path"}</button></p>
    <div class="shelf-list">${paths.length ? paths.map((pt, i) => `<span class="shelf-item"><a href="#" class="path-go" data-i="${i}">${esc(pt[0])}→…→${esc(pt[pt.length - 1])}（${pt.length}歩）</a><a href="#" class="path-x" data-i="${i}">×</a></span>`).join("") : empty}</div>
    <h4 class="gp-h">🔬 ${jp ? "自分のレンズ（観点を作って拡張）" : "My lenses"}</h4>
    <p class="srcline muted">${jp ? "観点の名前と語（カンマ区切り）を決めると、任意の概念をその観点で絞れます。例：名前「労働から」語「労働,搾取,賃金」" : ""}</p>
    <div class="psp-g"><input id="lens-name" class="cmb-in" style="width:30%" placeholder="${jp ? "観点の名前" : "name"}"/><input id="lens-words" class="cmb-in" style="width:58%" placeholder="${jp ? "観点の語（カンマ区切り）" : "words"}"/></div>
    <p><button type="button" id="lens-save" class="cmb-op">${jp ? "レンズを保存" : "save"}</button></p>
    <div class="shelf-list">${lenses.length ? lenses.map((l, i) => `<span class="shelf-item"><a href="#" class="lens-use" data-i="${i}">${esc(l.name)}</a><a href="#" class="lens-x" data-i="${i}">×</a></span>`).join("") : empty}</div>
    <p id="shelf-note" class="combine-form-note" role="status" aria-live="polite"></p>`;
  const p = gPanel(jp ? "棚：集める・道を保存・自分のレンズ" : "Shelf", html, cur);
  const refresh = () => { gShelfPanel(); };   // gPanel→surfCreate が同種Actionを置換する（積層しない）
  p.querySelector("#shelf-add").addEventListener("click", () => {
    if (cur) { dispatchAction("shelf", { term: cur }, currentViewState(), { surface: "shelf-panel" }); refresh(); }
    else { const n = p.querySelector("#shelf-note"); if (n) n.textContent = jp ? "棚に加える語を先に選んでください。" : "Choose a term before adding it to the shelf."; }
  });
  p.querySelectorAll(".shelf-go").forEach(a => a.addEventListener("click", e => { e.preventDefault(); surfCloseAction(false); dispatchAction("center", { term: a.dataset.w }, currentViewState(), { surface: "shelf-panel" }); }));
  p.querySelectorAll(".shelf-x").forEach(a => a.addEventListener("click", e => { e.preventDefault(); _lsSet("dx_shelf", _lsGet("dx_shelf", []).filter(w => w !== a.dataset.w)); refresh(); }));
  p.querySelector("#path-save").addEventListener("click", () => { if (NAV.stack.length > 1) { const ps = _lsGet("dx_paths", []); ps.push(NAV.stack.slice()); _lsSet("dx_paths", ps); refresh(); } else { const n = p.querySelector("#shelf-note"); if (n) n.textContent = jp ? "探索の道は、もう1歩進むと保存できます。" : "Take one more step before saving a path."; } });
  p.querySelectorAll(".path-go").forEach(a => a.addEventListener("click", e => { e.preventDefault(); const pt = _lsGet("dx_paths", [])[+a.dataset.i]; if (pt) { const last = pt[pt.length - 1]; const lastQ = typeof last === "string" ? last : (last && last.q); NAV.stack = pt.slice(); NAV.idx = pt.length - 1; navUpdate(); surfCloseAction(false); if (lastQ) originExplore(lastQ, { nav: true }); } }));
  p.querySelectorAll(".path-x").forEach(a => a.addEventListener("click", e => { e.preventDefault(); const ps = _lsGet("dx_paths", []); ps.splice(+a.dataset.i, 1); _lsSet("dx_paths", ps); refresh(); }));
  p.querySelector("#lens-save").addEventListener("click", () => { const name = p.querySelector("#lens-name").value.trim(), words = p.querySelector("#lens-words").value.trim(); if (name && words) { const ls = _lsGet("dx_lenses", []); ls.push({ name, words }); _lsSet("dx_lenses", ls); refresh(); } else { const n = p.querySelector("#shelf-note"); if (n) n.textContent = jp ? "観点の名前と語を入力してから保存してください。" : "Enter a lens name and terms before saving."; } });
  p.querySelectorAll(".lens-use").forEach(a => a.addEventListener("click", e => { e.preventDefault(); const l = _lsGet("dx_lenses", [])[+a.dataset.i]; if (l && cur) { surfCloseAction(false); dispatchAction("combine", { term: cur }, currentViewState(), { surface: "shelf-panel", b: l.words.split(/[,、\s]+/).filter(Boolean).join(" "), op: "and" }); } else gToast(jp ? "先に語を選んでください" : "pick a word"); }));
  p.querySelectorAll(".lens-x").forEach(a => a.addEventListener("click", e => { e.preventDefault(); const ls = _lsGet("dx_lenses", []); ls.splice(+a.dataset.i, 1); _lsSet("dx_lenses", ls); refresh(); }));
}

async function gPerspectivePanel(word) {
  const jp = LANG === "ja", sel = { p: "一般向け", u: "知りたい", l: "ふつう" };
  const chips = (obj, g, cur) => Object.keys(obj).map(k => `<button type="button" class="psp-chip${k === cur ? " on" : ""}" data-g="${g}" data-v="${esc(k)}">${esc(k)}</button>`).join("");
  const html = `<p class="muted">${jp ? "同じ概念を、あなたの見方で。視点・目的・難易度を選ぶと、その見方に合う入口と、その見方で深掘りするAI用プロンプトを作ります。" : "View this concept your way."}</p>
    <div class="psp-g"><span class="psp-l">視点</span>${chips(PERSPECTIVES, "p", sel.p)}</div>
    <div class="psp-g"><span class="psp-l">目的</span>${chips(PURPOSES, "u", sel.u)}</div>
    <div class="psp-g"><span class="psp-l">難易度</span>${chips(LEVELS, "l", sel.l)}</div>
    <div class="psp-ops"><button type="button" id="psp-go" class="cmb-op">この見方で見る</button></div>
    <div id="psp-out"></div>`;
  const p = gPanel((jp ? "見方を選ぶ：" : "View: ") + word, html, word);
  p.querySelectorAll(".psp-chip").forEach(c => c.addEventListener("click", () => {
    const g = c.dataset.g; p.querySelectorAll(`.psp-chip[data-g="${g}"]`).forEach(x => x.classList.remove("on"));
    c.classList.add("on"); sel[g] = c.dataset.v;
  }));
  p.querySelector("#psp-go").addEventListener("click", async () => {
    const out = p.querySelector("#psp-out");
    out.innerHTML = `<p class="muted">${jp ? "この見方の入口とプロンプトを作成中…" : "building…"}</p>`;
    const P = PERSPECTIVES[sel.p], goal = [P.frame, PURPOSES[sel.u], LEVELS[sel.l]].filter(Boolean).join(" ");
    const V = await resolveVariants(word);
    const all = extResources(word, V), flat = {};
    for (const cat in all) all[cat].forEach(([lbl, url]) => flat[lbl] = url);
    const curated = P.cur.filter(n => flat[n]).map(n => `<a class="ext-link" href="${esc(flat[n])}" target="_blank" rel="noopener">${esc(n)}</a>`).join(" ");
    let prompt = "";
    try { const d = await api("/api/deepsearch", { method: "POST", body: { topic: word, goal, service: "generic", lang: LANG } }); prompt = d.level0 || ""; }
    catch (e) { prompt = ""; }
    out.innerHTML = `<h4 class="gp-h">${jp ? "この見方に合う入口（各サイトの言語で・新タブ）" : "Entry points"}</h4><div class="ext-cat">${curated || "—"}</div>
      <h4 class="gp-h">${jp ? `この見方（${esc(sel.p)}／${esc(sel.u)}／${esc(sel.l)}）で深掘りするAI用プロンプト` : "Tailored deep-search prompt"}</h4>
      ${prompt ? `<textarea class="psp-prompt" readonly>${esc(prompt)}</textarea>
      <p class="srcline"><button type="button" id="psp-copy" class="cmb-op">コピー</button> ${jp ? "→ お使いのAI（ChatGPT/Gemini/Claude等）に貼って実行してください" : "→ paste into your AI"}</p>` : softLine(word)}`;   // 否定表示を出さず続行フッターへ
    const cp = p.querySelector("#psp-copy");
    if (cp) cp.addEventListener("click", () => { const ta = p.querySelector(".psp-prompt"); ta.select(); try { document.execCommand("copy"); } catch (e) {} cp.textContent = jp ? "コピーしました" : "copied"; });
  });
}
// 原語空間の共起（DWDS）— the benchmark's『関連概念群』dimension, made real.
// BUGFIX (Codex): a non-Latin node label (Japanese 疎外) can't be sent to DWDS
// directly — resolve it to its German concept-origin (Entfremdung) first, else
// say so. Only German has a collocation source for now (honest).
async function gColloc(term) {
  const jp = LANG === "ja";
  const p = gPanel((jp ? "原語空間の共起：" : "Collocations: ") + term,
    `<p class="muted">${jp ? "読み込み中…" : "loading…"}</p>`, term);
  let deTerm = term;
  if (!/[A-Za-zÀ-ɏ]/.test(term)) {
    try {
      const od = await api(`/api/origin?q=${encodeURIComponent(term)}&lang=${LANG}`);
      const g = (od.concept_origin || []).find(o => o.name === "ドイツ語");
      if (!g) { await autoFallback(term, "colloc", p.querySelector(".gp-body")); return; }   // A3: 独語原語が無い→別源を実走行
      deTerm = g.term;
    } catch (e) { console.error(e); await autoFallback(term, "colloc", p.querySelector(".gp-body")); return; }   // A3
  }
  let d;
  try { d = await api(`/api/collocations?term=${encodeURIComponent(deTerm)}&lang=de`); }
  catch (e) { console.error(e); await autoFallback(term, "colloc", p.querySelector(".gp-body")); return; }   // A3
  const rels = d.relations || {}, keys = Object.keys(rels);
  let html = "";
  if (!keys.length) {
    await autoFallback(term, "colloc", p.querySelector(".gp-body")); return;   // A3: 共起が空→別源（/api/origin多言語）を実走行
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
  dispatchAction("center", { term: q }, currentViewState(), { surface: "scroll-card" });   // 単一Dispatcher経由
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
      if (n) { G.hover = n; G.hl = gHl(G.nodes.indexOf(n)); cv.style.cursor = "pointer"; gMenuRetarget(n); }
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
      // 語ノード選択＝個別menuでなく「概念全景」を開く（単一Dispatcher経由・文脈nodeを渡す・半田様2026-07-30）。
      // domainノード（一般の意味/世界の言語/語源の連鎖 等＝カテゴリ・q無し）は、その文字列でなく親(root語)の
      // 全景を開き、対応する見どころへ寄せる（関心のある箇所へ進む導線）。エッジ選択は従来どおり関係メニュー。
      if (p.n) {
        // CLICK_ENTITY（半田様2026-08-02・「rootだけ全景直行」の特例は廃止）:
        //  ・実体ノード（中心語ノードも含め階層・kindに関係なく）→ 旧Menu/Action破棄・Context保持・Menu(target)を前面
        //  ・構造ノード（domain/区分名/件数＝q無し）は entity ではない → Contextを中心語の全景（該当節）へ
        const n = p.n;
        const isStructure = (n.kind === "domain") || !(n.q || n.label);
        if (isStructure) {
          const secHint = /言語|表記/.test(n.label || "") ? "lang" : /語源|来歴/.test(n.label || "") ? "history" : null;
          dispatchAction("panorama", { term: (G && G.rootQ) || n.label, label: n.label, kind: n.kind, id: n.id, layer: n.layer },
            currentViewState(), { surface: "node", node: null, secHint });
        } else {
          gMenu(e.clientX, e.clientY, n);   // 既存popup（Action ID＋単一Dispatcher・無作用0）
        }
      } else if (p.ei >= 0) gMenuEdge(e.clientX, e.clientY, p.ei);
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

// Context の開閉・window resize で canvas の実寸が変わったら backing store と座標系を追随させる
// （Map が Context の下へ潜り込まず、実クリック座標が常に有効であることを保証する）。
function gResize() {
  if (!G || !G.cv || !G.ctx) return;
  const cv = G.cv, W = cv.clientWidth, H = cv.clientHeight;
  if (!W || !H || (W === G.W && H === G.H)) return;
  const dpr = window.devicePixelRatio || 1;
  cv.width = W * dpr; cv.height = H * dpr;
  G.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  G.W = W; G.H = H; G.cx = W / 2; G.cy = H / 2;
  graphFit();
}
function gFitInstant() { G.view = { x: 0, y: 0, k: 1 }; }
function graphFit() {
  if (!G || !G.nodes || !G.nodes.length) return;
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  G.nodes.forEach(n => { x0 = Math.min(x0, n.x - n.r - 40); y0 = Math.min(y0, n.y - n.r - 20);
    x1 = Math.max(x1, n.x + n.r + 40); y1 = Math.max(y1, n.y + n.r + 20); });
  const W = G.W > 0 ? G.W : 800, H = G.H > 0 ? G.H : 600;   // canvas未計測(0)でも座標が潰れない
  const spanX = (x1 - x0) > 1 ? (x1 - x0) : 1, spanY = (y1 - y0) > 1 ? (y1 - y0) : 1;   // 縮退bbox(単一/同座標)でも0除算しない
  let k = Math.min(W / spanX, H / spanY, 2);
  if (!(k > 0) || !isFinite(k)) k = 1;                       // NaN/0/負を許さない（実クリック座標を確定させる・A4）
  G.view.k = k;
  G.view.x = (W - (x0 + x1) * k) / 2;
  G.view.y = (H - (y0 + y1) * k) / 2;
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
  catch (e) { console.error(e); if (!originStale(tok)) $("origin-status").innerHTML = `<div class="card">${noMiss(q)}</div>`; return; }   // 生エラーを出さず建設的代替へ
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
      html += `<div class="card"><p>${jp ? `「${esc(q)}」に近い項目から辿れます（クリックで探索）：` : `Closest entries to “${esc(q)}” (click to explore):`}</p>
        <div class="dim-disc-list">${sg.map(s => `<a class="dim-disc-l" href="/origin?q=${encodeURIComponent(s)}&lang=${LANG}"${linkAttr}>${esc(s)}</a>`).join("")}</div></div>`;
    } else {
      html += `<div class="card">${noMiss(q, { lead: jp ? `「${q}」は、次の入り口から探索できます（別表記・語幹・ローマ字でも辿れます）。` : `Explore “${q}” from these entry points.` })}</div>`;
    }
    $("origin-results").innerHTML = html; return;
  }

  // ── 探究の次元（ベンチマークの広さ・深さへ辿れる路の一覧・構造の保証） ──
  if (d.dimensions && d.dimensions.length) {
    const badge = (s) => s === "ok" ? `<span class="dim-b dim-ok">${jp ? "辿れる" : "ready"}</span>`
      : s === "partial" ? `<span class="dim-b dim-part">${jp ? "一部" : "partial"}</span>`
      : `<span class="dim-b dim-soon">${jp ? "組合せで探索" : "via combine"}</span>`;   // 未接続機能の宣伝でなく、クリックで実際に起きる操作を示す
    DIMS = d.dimensions;
    html += `<div class="card dim-card"><h3>${jp ? "探究の次元（この言葉をどこから見ていくか）" : "Dimensions of inquiry"}</h3>
      <p class="muted">${jp ? "一つの言葉を、いくつかの次元から見ていく入口です。「辿れる」＝実データに到達する次元／「一部」＝既存機構につながる次元／「組合せで探索」＝クリックでこの語と次元名を組合せ探索（実データ）へ渡します。上は暫定の【共通次元】。その下に、この概念自身の記事構造から【概念ごとに異なる固有の切り口】を発見して示します（固定分類でない）。" : "Entry points into several dimensions of a word. ready = reaches real data; partial = wired to an existing engine; via combine = clicking runs a real combine search of this word × the dimension name. Above are COMMON dimensions; below are facets DISCOVERED from this concept's own article — different per concept."}</p>
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
      <p class="srcline">${jp ? "『立てた人』が一人に定まらない概念でも、通常検索が結びつける主要人物へ届くための層。記事の言及に接地（賛否は判定しない）。" : "A recall layer reaching the figures normal search associates; grounded in the article's mentions."}</p>`;
  }
  // (2) 語形の由来（語源）＋翻訳原点の候補 — 思想家がいる場合は"語源"として明確に降格し警告
  // 由来関係が実源で確認できるものだけを原語・語源として扱い、確認できない併記は「各言語での表記（訳語）」へ
  // 分離する（英訳 contradiction を日本語「矛盾」の原語候補として扱わない・全レンダラ共通・半田様2026-08-02）。
  const _cosp = _groundedOrigSplit(co, o, (d.chain || []).map(c => c.form));
  const coG = _cosp.origs, coT = _cosp.trans;
  if (coG.length || na.length) {
    const label = orig.length
      ? (jp ? "語形の由来（語源・この訳語の《形》が写した語）" : "Word-form etymology")
      : (jp ? "概念-翻訳-原点の候補（この訳語が写した可能性のある原語）" : "Candidate translation-origin (not asserted as the single origin)");
    const items = coG.map(o2 => `<b class="origin-lang">${esc(o2.name)}</b> <span lang="${esc(o2.code||'')}">${esc(o2.term)}</span>`)
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
  // 由来が確認できない併記＝訳語。原語欄でなく「各言語での表記」として示す（分類を混同しない）
  if (coT.length) {
    html += `<p>${jp ? "各言語での表記（訳語・由来関係は確認できていません）" : "Terms in other languages (translations; origin not established)"}: `
      + coT.map(o2 => `<b class="origin-lang">${esc(o2.name)}</b> <span lang="${esc(o2.code||'')}">${esc(o2.term)}</span>`).join("　／　") + `</p>`;
  }
  if (!orig.length && !co.length && !na.length && !o) {
    html += `<p class="muted">${jp ? "この概念の原点は一つに断定しません（無中心・P1）。下の外部の専門情報源や『思想家の系譜』から、実際の言説（誰が・どの著作で・どう使ったか）へ辿れます。" : "We do not assert a single origin (P1). Reach the actual discourse via the external sources / thinkers below."}</p>`;
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
  // 原語での語義: 英語の生glossを主表示しない。日本語の根拠ある語義がある時だけ示す（半田様2026-08-02）
  if (d.senses && d.senses.length) {
    const jaSenses = d.senses.slice(0, 3).map(s => _jaGloss(cleanWikt(s))).filter(Boolean);
    if (jaSenses.length) html += `<p class="muted">${jp ? "原語での語義" : "senses in the original"}: ${esc(jaSenses.join(" / "))}</p>`;
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
    ? `<span class="badge err" title="${esc((LANG === "ja" ? "この情報源は今回取得を見送りました（他の情報源で表示）" : "source skipped; shown via others"))}">${esc(s.source)}</span>`
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
    el.innerHTML = `<p class="srcline muted">${jp ? "この語は、上の共通次元とメニューから探索できます（固有の切り口はデータが増えるほど現れます）。" : "Explore this word via the common dimensions and menu above."}</p>`;   // 否定表示を出さない
    return;
  }
  const link = (x) => `<a class="dim-disc-l" href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.heading)}</a>`;
  el.innerHTML = `<p class="dim-disc-h">${jp ? "この概念に固有の切り口（記事の構造から・出所つき・概念ごとに異なる）" : "Facets specific to this concept (from its own article structure)"}</p>
    ${d.disambiguation ? `<p class="srcline" style="color:var(--warn)">⚠ ${esc(d.note)}</p>` : ""}
    <div class="dim-disc-list">${d.dimensions.map(link).join("")}</div>
    <p class="srcline muted">${jp ? "出所" : "source"}: <a href="${esc(d.article_url)}" target="_blank">Wikipedia (${LANG})「${esc(d.title)}」</a>。固定の共通次元と違い、語ごとに違う切り口が出ます。</p>`;
}

// テスト用の読み取り専用アクセサ（本番でも無害。E2Eが内部状態を検査するため。内部を書き換えない）。
try {
  window.__dx = {
    get G() { return G; },
    get G_raw() { return G_raw; },
    get MENUCTX() { return MENUCTX; },
    setPanelFromMenu(v) { _panelFromMenu = v; },
    // 操作基盤の検査（操作同値性/履歴/失敗継続テスト用・読み取り専用）
    viewState() { return currentViewState(); },
    // txn = dispatchAction の実行区間（true の間は1操作が進行中でcommit未確定）。読み取り専用。
    get nav() { return { idx: NAV.idx, len: NAV.stack.length, stack: NAV.stack, txn: NAV.txn }; },
    get lastDispatch() { return _lastDispatch; },
    // Action registry（effect宣言）とUI面ごとのAction ID宣言＝テストは文言でなくこれと照合する
    registry() { const o = {}; for (const k in ACTIONS) { const a = ACTIONS[k];
      o[k] = { effect: a.effect || null, effectWithArg: a.effectWithArg || null, arg: a.arg || null,
               commits: a.commits !== false, transient: !!a.transient, newPage: !!a.newPage, label: a.label || "" }; }
      return o; },
    effects() { return EFFECTS.slice(); },
    uiActions() { return JSON.parse(JSON.stringify(UI_ACTION_IDS)); },
    // 面の実測状態（存在・対象・矩形）。テストが遮蔽・交差・排他を数値で検査するため
    surfaces() {
      const r = (k) => surfRect(k);
      return { context: !!surfEl("context"), menu: !!surfEl("menu"), action: !!surfEl("action"),
               contextTerm: CONTEXT_CTX ? CONTEXT_CTX.term : null,
               panel: PANEL_CTX ? { action: PANEL_CTX.action, term: PANEL_CTX.term } : null,
               z: { context: surfEl("context") && +surfEl("context").style.zIndex,
                    menu: surfEl("menu") && +surfEl("menu").style.zIndex,
                    action: surfEl("action") && +surfEl("action").style.zIndex },
               rects: { context: r("context"), menu: r("menu"), action: r("action") },
               avail: surfAvail() };
    },
    surfaceIds() { return Object.assign({}, SURFACE_ID); },
    fallbackLog() { return FALLBACK_LOG.slice(); },   // A3: 自動代替の実発火ログ（外部証跡）
    fit() { if (typeof graphFit === "function") graphFit(); return G && G.view; },   // A4: 実クリック座標を確定させるため明示fit
    hitTest(mx, my) { const n = gNodeAt(mx, my); return n ? { id: n.id, label: n.label, layer: n.layer } : null; },   // A4: ヒットテスト検査
    actions() { return Object.keys(ACTIONS); },
    async dispatch(actionId, target, ctx) { return dispatchAction(actionId, target, currentViewState(), ctx || {}); },
    gActions(n) { return gActions(n); },
    // canvasノードのページ座標（実マウスクリック test 用: page.mouse.click(x,y) で実ノードを押す）
    nodeClientXY(sel) {
      if (!G || !G.nodes) return null;
      const n = (typeof sel === "function") ? G.nodes.find(sel)
              : G.nodes.find(x => x.id === sel) || G.nodes.find(x => x.layer === sel) || G.nodes.find(x => x.label === sel);
      if (!n) return null;
      const cv = $("origin-graph"); if (!cv) return null;
      const r = cv.getBoundingClientRect(), s = gToScreen(n);
      return { x: r.left + s.x, y: r.top + s.y, id: n.id, label: n.label, kind: n.kind, layer: n.layer };
    },
  };
} catch (e) {}
