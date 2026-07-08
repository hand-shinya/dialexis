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

function exploreInit(q) {
  if (q && q.trim()) exploreRun(q.trim());
}

async function exploreRun(q) {
  $("explore-status").innerHTML = `<p class="muted">${T.loading}</p>`;
  $("explore-results").innerHTML = "";
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
          `<li>${esc(b.text)}${b.url ? ` <a href="${esc(b.url)}" target="_blank">↗</a>` : ""}</li>`).join("")}</ul>
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
            — ${esc((b.creators || []).join(" / "))}${b.publisher ? ` · ${esc(b.publisher)}` : ""}${b.year ? ` · ${esc(b.year)}` : ""}</li>`).join("")}</ul>`;
      }
      if (cnHits.length) {
        html += `<h3>${jp ? "論文・書籍（CiNii Research）" : "Articles & books (CiNii)"}</h3>
          <ul class="biblist">${cnHits.map(w => `<li>
            ${w.type ? `<span class="badge">${esc(w.type)}</span> ` : ""}
            ${w.url ? `<a href="${esc(w.url)}" target="_blank">${esc(w.title)}</a>` : esc(w.title)}
            — ${esc((w.creators || []).join(" / "))}${w.year ? ` · ${esc(w.year)}` : ""}</li>`).join("")}</ul>`;
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
          <div class="srcline">${esc(b.authors.join(", "))} · ${esc(b.languages.join(","))} · Project Gutenberg</div></div>`).join("");
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
        <div class="srcline">${esc(w.authors.join(", "))}${w.cited_by_count ? ` · cited ${w.cited_by_count}` : ""}</div></div>`).join("");
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

let PROJ = null;
const NODE_COLORS = { question: "#2e5c7a", claim: "#7a5c2e", evidence: "#2f7d4f",
  counterclaim: "#b91c1c", uncertainty: "#b45309", interpretation: "#6d28d9",
  decision: "#1d2430", note: "#6b7280", source: "#0e7490" };

async function projectInit(pid) {
  PROJ = pid;
  await projRefresh();
}

async function projRefresh() {
  const g = await api(`/api/projects/${PROJ}/graph`);
  const provByNode = {};
  g.provenance.forEach(p => (provByNode[p.node_id] ||= []).push(p));

  for (const selId of ["e-src", "e-dst"]) {
    $(selId).innerHTML = g.nodes.map(n =>
      `<option value="${n.id}">[${n.type}] ${esc(n.title.slice(0, 40))}</option>`).join("");
  }
  const nodeOpts = g.nodes.map(n =>
    `<option value="${n.id}">[${n.type}] ${esc(n.title.slice(0, 40))}</option>`).join("");
  if ($("arg-cnode")) $("arg-cnode").innerHTML = `<option value="">— ${T.arg_conclusion || "conclusion node"} —</option>` + nodeOpts;
  argRender(g.arguments || []);

  if (window.cytoscape) {
    const cy = cytoscape({
      container: $("graph"),
      elements: [
        ...g.nodes.map(n => ({ data: { id: "n" + n.id, label: n.title.slice(0, 30),
          type: n.type, raw: n } })),
        ...g.edges.map(e => ({ data: { id: "e" + e.id, source: "n" + e.src,
          target: "n" + e.dst, label: e.rel } })),
      ],
      style: [
        { selector: "node", style: {
          "background-color": ele => NODE_COLORS[ele.data("type")] || "#888",
          label: "data(label)", "font-size": "10px", "text-wrap": "wrap",
          "text-max-width": "90px", "text-valign": "bottom", "text-margin-y": "4px",
          width: 26, height: 26 } },
        { selector: "edge", style: {
          width: 1.5, "line-color": "#b9b09c", "target-arrow-shape": "triangle",
          "target-arrow-color": "#b9b09c", "curve-style": "bezier",
          label: "data(label)", "font-size": "8px", color: "#6b7280" } },
      ],
      layout: { name: "cose", animate: false },
    });
    cy.on("tap", "node", evt => projShowNode(evt.target.data("raw"), provByNode));
    $("graph-fallback").innerHTML = "";
  } else {
    $("graph").style.display = "none";
    $("graph-fallback").innerHTML = `<div class="card"><table class="plain">` +
      g.nodes.map(n => `<tr><td><span class="badge">${n.type}</span></td>
        <td>${esc(n.title)}</td><td><span class="badge conf-${n.confidence}">${n.confidence}</span></td></tr>`).join("")
      + "</table></div>";
  }
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
