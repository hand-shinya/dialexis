"""Dialexis — Reflexive Philosophy Infrastructure.

FastAPI application. Read GENESIS.md first: every route here is a consequence
of the seven axioms. In particular:
  axiom 3 (lens): /api/explore queries live scholarly sources, stores nothing
                  but cache + provenance;
  axiom 4 (freshness): every external item carries retrieved_at;
  axiom 5 (ladder): every feature has a Level-0 keyless path;
  axiom 6 (AI transparency): every AI output is labeled and ledgered;
  axiom 7 (exit): full export to Markdown / JSON-LD.
"""
import asyncio
import json
import math
import os
import re
import urllib.parse

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .db import get_conn, init_db, now, rows
from .connectors import wikidata, openalex, crossref, wikipedia, gutendex, opencitations, sep, ndl, cinii, dwds, wiktionary, concept, searxng, etymology
from .connectors.base import cached_get_json, cached_get_text
from . import citations as cites
from . import deepsearch
from . import bibliography
from .llm import adapter

APP_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Dialexis", version="0.1.0")
app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))


def _asset_version() -> str:
    """Content hash of the static assets, computed once at startup (the process
    restarts on every deploy). Appended to /static URLs as ?v=… so a new deploy
    changes the URL and a stale browser cache can never serve old JS against a
    new API — the false-empty grounding bug (old app.js vs new /api/origin)."""
    import hashlib
    h = hashlib.sha1()
    for fn in ("static/app.js", "static/style.css"):
        try:
            with open(os.path.join(APP_DIR, fn), "rb") as f:
                h.update(f.read())
        except OSError:
            pass
    return h.hexdigest()[:10]


ASSET_V = _asset_version()

I18N = {}
for _lang in ("ja", "en"):
    with open(os.path.join(APP_DIR, "i18n", f"{_lang}.json"), encoding="utf-8") as f:
        I18N[_lang] = json.load(f)

with open(os.path.join(APP_DIR, "data", "counter_checklists.json"), encoding="utf-8") as f:
    CHECKLISTS = json.load(f)
with open(os.path.join(APP_DIR, "data", "glossary_seed.json"), encoding="utf-8") as f:
    GLOSSARY = json.load(f)
with open(os.path.join(APP_DIR, "data", "orig_clusters.json"), encoding="utf-8") as f:
    ORIG_CLUSTERS = json.load(f)
# Flat index: every match trigger (lowercased) → its cluster. Built once.
ORIG_CLUSTER_INDEX = {
    m.lower(): c for c in ORIG_CLUSTERS["clusters"] for m in c["match"]
}
with open(os.path.join(APP_DIR, "data", "author_lineage.json"), encoding="utf-8") as f:
    AUTHOR_LINEAGE = json.load(f)
AUTHOR_LINEAGE_INDEX = {
    m.lower(): lg for lg in AUTHOR_LINEAGE["lineages"] for m in lg["match"]
}


# Idempotent; runs at import so tests, uvicorn and the harvester all share it.
init_db()


def pick_lang(request: Request) -> str:
    q = request.query_params.get("lang")
    if q in I18N:
        return q
    c = request.cookies.get("lang")
    if c in I18N:
        return c
    accept = request.headers.get("accept-language", "")
    return "ja" if accept.lower().startswith("ja") else "en"


def render(request: Request, name: str, **ctx):
    lang = pick_lang(request)
    t = I18N[lang]
    resp = templates.TemplateResponse(
        request=request, name=name,
        context={"t": t, "lang": lang, "path": request.url.path,
                 "asset_v": ASSET_V, **ctx})
    if request.query_params.get("lang"):
        resp.set_cookie("lang", lang, max_age=86400 * 365)
    return resp


# ---------- pages ----------

# Question-first entry (PoC A): a curious person who does not yet know any
# philosopher's name still needs a door. Each door is a human-language question
# (the novice's own voice) that opens the primary /origin meaning-space map on a
# concept seed; the older /explore source-search surface remains available as a
# deliberately separate secondary route.
# Every seed below was EMPIRICALLY VERIFIED (2026-07-12, per-language) to return
# a real SEP entry + scholarship — known wrong-sense resolutions (時間→Hour,
# 存在→Entity, 徳→誤爆; en justice→None, freedom→"Divine Freedom") are excluded
# so no door leads to an empty room. Extend only with re-verified seeds.
QUESTION_DOORS = {
    "ja": [
        {"seed": "愛", "q": "愛とは何か"},
        {"seed": "自由", "q": "自由とは何か"},
        {"seed": "正義", "q": "「正しさ」とは何か"},
        {"seed": "幸福", "q": "どう生きれば幸せか"},
        {"seed": "真理", "q": "「本当のこと」はあるのか"},
        {"seed": "意識", "q": "心とは何か"},
        {"seed": "美", "q": "美しさとは何か"},
    ],
    "en": [
        {"seed": "love", "q": "What is love?"},
        {"seed": "happiness", "q": "How should I live to be happy?"},
        {"seed": "truth", "q": "Is there such a thing as truth?"},
        {"seed": "consciousness", "q": "What is the mind?"},
        {"seed": "beauty", "q": "What is beauty?"},
    ],
}


@app.get("/", response_class=HTMLResponse)
def page_home(request: Request):
    lang = pick_lang(request)
    return render(request, "index.html",
                  question_doors=QUESTION_DOORS.get(lang, QUESTION_DOORS["en"]))


@app.get("/explore", response_class=HTMLResponse)
def page_explore(request: Request, q: str = ""):
    return render(request, "explore.html", q=q)


@app.get("/origin", response_class=HTMLResponse)
def page_origin(request: Request, q: str = ""):
    # 原語による探求 (MVP, German lineage). The portal's single deepened purpose.
    return render(request, "origin.html", q=q)


@app.get("/desk", response_class=HTMLResponse)
def page_desk(request: Request):
    return render(request, "desk.html")


@app.get("/project/{pid}", response_class=HTMLResponse)
def page_project(request: Request, pid: int):
    conn = get_conn()
    p = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not p:
        raise HTTPException(404)
    return render(request, "project.html", project=dict(p))


@app.get("/watches", response_class=HTMLResponse)
def page_watches(request: Request):
    return render(request, "watches.html")


@app.get("/levels", response_class=HTMLResponse)
def page_levels(request: Request):
    return render(request, "levels.html",
                  concepts=list(GLOSSARY["concepts"].keys()),
                  levels=GLOSSARY["levels"])


@app.get("/deepsearch", response_class=HTMLResponse)
def page_deepsearch(request: Request):
    return render(request, "deepsearch.html", services=deepsearch.SERVICES)


@app.get("/settings", response_class=HTMLResponse)
def page_settings(request: Request):
    return render(request, "settings.html")


@app.get("/donate", response_class=HTMLResponse)
def page_donate(request: Request):
    return render(request, "donate.html")


@app.get("/about", response_class=HTMLResponse)
def page_about(request: Request):
    return render(request, "about.html")


@app.get("/healthz")
def healthz():
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
    conn.close()
    return {"status": "ok", "projects": n, "time": now()}


# ---------- explore (lens over live sources) ----------

_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")


def _has_cjk(s: str) -> bool:
    return bool(_CJK.search(s or ""))


def _sig_tokens(term: str) -> list:
    toks = [t for t in re.split(r"\W+", (term or "").lower()) if len(t) >= 4]
    return toks or [(term or "").lower()]


def orientation_plan(q: str, entity: dict | None) -> dict:
    """Choose orientation sources by the subject's intellectual tradition instead
    of assuming one universal entry point (SEP is Anglophone-Western). This is the
    routing framework — extend the branch for other traditions (zh/hi/ar).

    SEP is always attempted but its result is relevance-gated (see _sep_relevant);
    Japanese-tradition subjects additionally get NDL + CiNii, the specialist
    Japanese scholarly indexes that actually cover the subject and its literature."""
    ed = entity["data"] if entity and not entity.get("error") and entity.get("data") else {}
    sitelinks = ed.get("wikipedia", {}) or {}
    japanese = _has_cjk(q) or (bool(sitelinks.get("ja")) and not sitelinks.get("en"))
    tradition = "japanese" if japanese else "western"
    return {"tradition": tradition, "sep": True, "ndl": japanese, "cinii": japanese}


def _sep_relevant(entry_title: str, sep_term: str) -> bool:
    """Guard against SEP's fuzzy fallback (共同幻想論 → 'Laozi'). SEP is English-
    only, so a CJK/non-Latin term can never legitimately match — suppress. Else
    the entry title must share a significant token with the term."""
    if _has_cjk(sep_term) or not re.search(r"[A-Za-z]", sep_term or ""):
        return False
    hay = (entry_title or "").lower()
    return any(t in hay for t in _sig_tokens(sep_term))


def _has_latin(s: str) -> bool:
    return bool(re.search(r"[A-Za-z]", s or ""))


# Wikidata P31 classes that can never be the philosophical sense of a bare
# concept query — creative works and person-names whose TITLES shadow concept
# words and defeat the token-overlap SEP gate (freedom → 'Freedom (Beyoncé
# song)' shares the token 'freedom' with SEP's 'Divine Freedom'; 徳 → given
# name 'De'). Small, verified against real entities — not exhaustive.
NONCONCEPT_P31 = frozenset({
    "Q101352",     # family name
    "Q202444",     # given name
    "Q22809413",   # Chinese given name (徳 → 'De')
    "Q11879590", "Q12308941", "Q3409032",   # female/male/unisex given name
    "Q105543609",  # musical work/composition (freedom → Beyoncé single)
    "Q7366", "Q134556", "Q482994",          # song / single / album
    "Q11424", "Q5398426",                   # film / TV series
    "Q215380",     # musical group (truth/en → Indonesian band 'Truth')
    "Q4167410",    # Wikimedia disambiguation page
})


def _orig_cluster(q: str, entity: dict | None) -> dict | None:
    """原語基底: the portal's OWN answer (not an external prompt) to 'which
    original-language siblings collapse into this one Japanese word'. Matches the
    raw query and the resolved English anchor against a curated, source-verified
    seed (ORIG_CLUSTERS). Augments the static cluster with the resolved entity's
    LIVE Wikidata orig_labels so the card is not purely static. Returns None when
    no cluster matches — honest silence beats a fabricated distinction (A3)."""
    keys = {(q or "").strip().lower()}
    if entity and not entity.get("error"):
        ed = entity["data"]
        for k in (ed.get("label_en"), ed.get("wikipedia", {}).get("en")):
            if k:
                keys.add(k.strip().lower())
    cluster = next((ORIG_CLUSTER_INDEX[k] for k in keys if k in ORIG_CLUSTER_INDEX), None)
    if not cluster:
        return None
    live = entity["data"].get("orig_labels", {}) if (entity and not entity.get("error")) else {}
    # shallow copy so the module-level seed is never mutated
    return {**cluster, "provenance": ORIG_CLUSTERS["_meta"],
            "live_orig_labels": {k: v for k, v in live.items() if k != "en"}}


def _author_lineage(q: str, entity: dict | None) -> dict | None:
    """The importance/precedence-ordered author×work map for a concept. Authors
    sit UNDER the word's lineage — never a silently-fixed default (the user's
    structural correction: 言葉が先, 著者はその下). Matched like _orig_cluster;
    returns the sourced seed lineage or None (honest 未整備)."""
    keys = {(q or "").strip().lower()}
    if entity and not entity.get("error"):
        ed = entity["data"]
        for k in (ed.get("label_en"), ed.get("wikipedia", {}).get("en")):
            if k:
                keys.add(k.strip().lower())
    lg = next((AUTHOR_LINEAGE_INDEX[k] for k in keys if k in AUTHOR_LINEAGE_INDEX), None)
    return {**lg, "order_basis": AUTHOR_LINEAGE["_meta"]["order_basis"]} if lg else None


def _nonconcept(ent: dict) -> bool:
    """True when the entity's P31 marks it as a work/name sense that must not
    anchor SEP nor be a rerank target (its title-token overlap is spurious)."""
    if not ent or ent.get("error"):
        return False
    return any(p in NONCONCEPT_P31 for p in ent["data"].get("instance_of", []))


def _entity_anchor(ent: dict) -> str | None:
    """The English anchor a concept would hand to SEP (English-only). None if the
    entity has no English sitelink/label — then SEP cannot be probed for it."""
    ed = ent["data"]
    return ed["wikipedia"].get("en") or ed.get("label_en") or None


def _pick_resolution(scored: list) -> str | None:
    """Choose which Wikidata candidate to resolve a CONCEPT query to. Wikidata's
    search ranks a narrower/unit/name sense first for bare polysemous nouns
    (時間→'hour' not 'Time'; 存在→'Entity' not 'Existence'), so blindly taking
    [0] loses the philosophical sense. Rule, conservative & strictly-improving:
      • keep [0] when it is a person, or already yields a relevant SEP entry
        (every currently-working query is untouched — no regression);
      • only when [0] is a concept with NO relevant SEP entry — or a non-concept
        work/name sense, encoded upstream as sep_ok=False (_nonconcept) — prefer
        the first sibling that DOES (the philosophy authority disambiguates);
      • if none qualifies, fall back to [0] (all-names query: unchanged).
    `scored` is in Wikidata order: [{qid, is_person, anchor, sep_ok}]."""
    if not scored:
        return None
    top = scored[0]
    if top["is_person"] or top["sep_ok"]:
        return top["qid"]
    for c in scored[1:]:
        if c["sep_ok"] and not c["is_person"]:
            return c["qid"]
    return top["qid"]


def _sep_anchor_match(entry_title: str, anchor: str) -> bool:
    """STRICT relevance for the rerank probe only (the display gate stays
    _sep_relevant). One shared token is too weak here: anchor 'Edo period'
    matched SEP 'Plato's Middle Period…' on 'period' alone and outranked
    virtue. Require EVERY significant token (len>=3, so 'Edo' counts) of the
    anchor to appear in the SEP title."""
    if _has_cjk(anchor) or not _has_latin(anchor):
        return False
    hay = (entry_title or "").lower()
    toks = [t for t in re.findall(r"[a-z]+", (anchor or "").lower()) if len(t) >= 3]
    return bool(toks) and all(t in hay for t in toks)


async def _sep_ok(anchor: str) -> bool:
    """Does SEP have an entry whose first hit strictly matches `anchor`?
    Uses the search-result title only (cheap; no full-entry fetch)."""
    r = await sep.search(anchor)
    return (not r["error"] and bool(r["data"])
            and _sep_anchor_match(r["data"][0].get("title", ""), anchor))


async def _resolve_entity(cands: list, lang: str, n: int = 12, probes: int = 8) -> dict:
    """SEP-guided concept disambiguation (see _pick_resolution). Fetches [0]
    first and returns it unchanged for persons or when it already resolves to a
    relevant SEP sense — so the common good case costs one entity fetch and one
    (later-cached) SEP probe. Only a concept [0] with no SEP entry — or a
    non-concept [0] (song/name, whose spurious title-token overlap must not
    self-certify) — pays for the bounded sibling scan (`n` siblings fetched in
    parallel & day-cached; at most `probes` SEP probes)."""
    e0 = await wikidata.entity(cands[0]["qid"], lang)
    if e0["error"]:
        return e0
    a0 = _entity_anchor(e0)
    if e0["data"].get("is_person") or not a0 or not _has_latin(a0):
        return e0  # person (or un-probe-able) top → untouched (no regression)
    if not _nonconcept(e0) and await _sep_ok(a0):
        return e0  # [0] already resolves to a relevant SEP sense → untouched
    sibs = cands[1:n]
    if not sibs:
        return e0
    ents = await asyncio.gather(*[wikidata.entity(c["qid"], lang) for c in sibs])
    scored = [{"qid": cands[0]["qid"], "is_person": bool(e0["data"].get("is_person")),
               "anchor": a0, "sep_ok": False, "ent": e0}]
    for c, e in zip(sibs, ents):
        isp = bool(e["data"].get("is_person")) if not e["error"] else False
        anc = _entity_anchor(e) if not e["error"] else None
        scored.append({"qid": c["qid"], "is_person": isp, "anchor": anc,
                       "sep_ok": False, "ent": e})
    idxs = [i for i, s in enumerate(scored)
            if i > 0 and not s["is_person"] and s["anchor"] and _has_latin(s["anchor"])
            and not _nonconcept(s["ent"])][:probes]
    oks = await asyncio.gather(*[_sep_ok(scored[i]["anchor"]) for i in idxs])
    for i, ok in zip(idxs, oks):
        scored[i]["sep_ok"] = ok
    qid = _pick_resolution([{k: s[k] for k in ("qid", "is_person", "anchor", "sep_ok")}
                            for s in scored])
    return next((s["ent"] for s in scored if s["qid"] == qid), e0)


@app.get("/api/explore")
async def api_explore(q: str, lang: str = "en"):
    if not q.strip():
        raise HTTPException(400, "empty query")

    # Step 1: resolve the query to a concept/person via Wikidata FIRST, so the
    # scholarly search can be anchored on the resolved English term rather than
    # a raw (often ambiguous) CJK word. This, plus OpenAlex's humanities lens,
    # is what keeps a query like 存在 in philosophy instead of chemistry.
    # limit=20: the philosophical sense of a bare CJK noun can rank deep below
    # name/place senses (徳 → virtue at index 11) — the resolver's sibling scan
    # needs the tail; the UI does not render this list, so display is unaffected.
    wd = await wikidata.search(q, lang, limit=20)
    entity = None
    wiki = None
    scholar_q = q          # term handed to scholarly APIs
    sep_term = q           # term handed to SEP (English-only)
    is_person = False
    author_ja = ""
    title, wp_lang, all_qids = None, "en", []  # safe defaults if no entity
    if not wd["error"] and wd["data"]:
        # SEP-guided disambiguation instead of a blind [0]: bare polysemous CJK
        # nouns rank a unit/name sense first (時間→hour, 存在→Entity), which lost
        # the philosophical entry. Strictly-improving: persons and already-good
        # top hits are untouched (see _resolve_entity / _pick_resolution).
        entity = await _resolve_entity(wd["data"], lang)
        if not entity["error"]:
            ed = entity["data"]
            is_person = ed.get("is_person", False)
            # English anchor for English-only sources (SEP) and person searches.
            # The English WIKIPEDIA sitelink title is the reliable name — the
            # Wikidata English *label* has data gaps (e.g. Montesquieu's is null,
            # which previously leaked the Japanese name into OpenAlex). Fall back
            # to the English label, then the raw query.
            wp_titles = ed["wikipedia"]
            english_term = wp_titles.get("en") or ed.get("label_en") or q
            # Persons: search by the unambiguous English name. Concepts: keep the
            # user's original-language term (Japanese 存在 → 存在論 scholarship).
            scholar_q = english_term if is_person else q
            sep_term = english_term  # SEP is English-only
            author_ja = ed["label"] if is_person else ""  # for NDL 邦訳 lookup
            title = wp_titles.get(lang) or wp_titles.get("en")
            wp_lang = lang if lang in wp_titles else "en"
            all_qids = [v for vs in ed["claims"].values()
                        for v in vs if str(v).startswith("Q")]

    # Everything below depends only on the resolved entity, so run the branches
    # concurrently instead of in one long sequential chain (cold-load latency:
    # ~6 serial round-trips + 2 large SEP fetches → one parallel wave).
    plan = orientation_plan(q, entity)

    async def sep_chain():
        r = await sep.search(sep_term)
        e = await sep.entry(r["data"][0]["slug"]) if (not r["error"] and r["data"]) else None
        # Relevance gate: suppress an unrelated fallback entry (the 共同幻想論→Laozi
        # leak) so a non-Western subject shows no SEP card rather than a wrong one.
        if e and not e.get("error") and e.get("data") \
                and not _sep_relevant(e["data"].get("title", ""), sep_term):
            e = None
        return r, e

    async def wiki_summary():
        return await wikipedia.summary(title, wp_lang) if (entity and title) else None

    # Japanese-tradition orientation: stand on the specialist Japanese indexes.
    # NDL for books BY/ABOUT the subject; CiNii for Japanese scholarship. These
    # are what surface 吉本隆明's own 共同幻想論 and the monographs about it.
    async def ndl_orientation():
        if not plan["ndl"]:
            return await _empty("ndl")
        calls = [ndl.by_title(q)] + ([ndl.by_author(q)] if is_person else [])
        res = await asyncio.gather(*calls)
        seen, merged = set(), []
        for r in res:
            if r["error"] or not r["data"]:
                continue
            for item in r["data"]:
                k = (item.get("title", ""), item.get("url", ""))
                if k in seen:
                    continue
                seen.add(k)
                merged.append(item)
        errs = [r["error"] for r in res if r["error"]]
        return {"source": "ndl", "retrieved_at": now(),
                "error": errs[0] if errs and not merged else None, "data": merged}

    async def cinii_lookup():
        return await cinii.search(q) if plan["cinii"] else await _empty("cinii")

    # Resolve QID labels up front: needed both to display the entity's claims and
    # to get the Japanese titles of the author's notable works for the 邦訳 lookup.
    labels = await wikidata.resolve_labels(all_qids, lang) if all_qids else {}
    notable_ja = []
    if entity and not entity["error"]:
        for qid in entity["data"]["claims"].get("notable_work", []):
            t = labels.get(qid, qid)
            if t and not str(t).startswith("Q"):
                notable_ja.append(t)

    # Japanese translations (邦訳): the Japanese user's primary text is the
    # translated book, and WHICH translator matters (translation method, JP face).
    # Look up each notable work precisely by author-surname + work-title, so
    # 純粋理性批判 → 天野貞祐訳・中山元訳… rather than name-substring noise.
    async def ja_translations_lookup():
        if not (is_person and author_ja and notable_ja):
            return {"source": "ndl", "retrieved_at": now(), "error": None,
                    "skipped": not (is_person and author_ja), "data": []}
        groups = await asyncio.gather(*[ndl.by_work(author_ja, w) for w in notable_ja[:4]])
        data = [g["data"] for g in groups if not g["error"] and g["data"]["editions"]]
        errs = [g["error"] for g in groups if g["error"]]
        return {"source": "ndl", "retrieved_at": now(),
                "error": errs[0] if errs and not data else None, "data": data}

    (sep_pair, wiki, gutenberg, oa_works, ja_translations,
     ndl_orient, cinii_res) = await asyncio.gather(
        sep_chain(), wiki_summary(),
        gutendex.search(scholar_q) if is_person else _empty("gutendex"),
        openalex.search_works(scholar_q), ja_translations_lookup(),
        ndl_orientation(), cinii_lookup())
    sep_result, sep_entry = sep_pair

    if entity and not entity["error"]:
        ed = entity["data"]
        ed["claims"] = {k: [labels.get(v, v) for v in vs] for k, vs in ed["claims"].items()}
        ed["wikisource_urls"] = {lg: wikipedia.wikisource_url(t, lg)
                                 for lg, t in ed["wikisource"].items()}
    if not oa_works["error"] and oa_works["data"]:
        oa_works["data"] = _relevant(oa_works["data"], english_term if is_person else q)

    return {"query": q, "resolved_term": scholar_q, "lang": lang, "queried_at": now(),
            "orientation": plan,
            "orig_cluster": _orig_cluster(q, entity),
            "sep_search": sep_result, "sep_entry": sep_entry,
            "wikidata_search": wd, "entity": entity, "wikipedia": wiki,
            "primary_texts": gutenberg, "japanese_translations": ja_translations,
            "japanese_scholarship": ndl_orient, "cinii": cinii_res,
            "recent_scholarship": oa_works}


@app.get("/api/origin")
async def api_origin(q: str, lang: str = "ja"):
    """原語による探求 — 無中心の原点エンジン。どの言語の語からでも、Wiktionaryを
    語キーに、その概念が生まれた言語（入力言語自身のこともある）を辿り、通ってきた
    言語と語形の連鎖（翻訳による変容＝宿痾を可視化）と、その語を担う言語の広がりを
    示す。いかなる言語も中心に置かない。原点は「推定」で断定せず、連鎖は常に全て示し、
    breadthはモデルでなくデータの和集合に語らせる。"""
    await wiktionary.ensure_langnames(lang)   # 全言語コード→日本語名を用意（生コード表示の解消）
    if not q.strip():
        raise HTTPException(400, "empty query")
    SECTION = {"ja": "Japanese", "en": "English", "de": "German", "zh": "Chinese",
               "ko": "Korean", "fr": "French", "la": "Latin"}
    section_lang = SECTION.get(lang, "Japanese")

    # TWO complementary paths, run together (they cover each other's gaps):
    #  ・概念経路 concept.node — follows the word's OWN article→Wikidata item (no
    #    biased search), giving the concept-TRANSLATION-origin (疎外→独 Entfremdung,
    #    縁起→梵) and the multilingual WORD fan (the concept in N languages).
    #  ・語経路 wiktionary.trace — the word's linguistic etymology (空→梵 śūnyatā).
    tr, cn = await asyncio.gather(
        wiktionary.trace(q, section_lang), concept.node(q, lang))
    td = tr["data"] if not tr["error"] else {}
    cd = cn["data"] if not cn["error"] else {}
    gen = await wiktionary.ja_senses(q) if lang == "ja" else None
    gen_senses = (gen["data"]["senses"] if gen and not gen["error"] and gen.get("data") else [])

    # 埋没の明示警告（最重要）: この日本語の一語に、原語では複数の別語が一語へ抽象化され
    # 一つになっている——それを具体的に指摘し「注意して扱え」と警告することが、この
    # ポータルの核心価値。verified seed（orig_clusters）から、qに一致する語族を出す。
    cl = _orig_cluster(q, None)
    collapse_warning = None
    if cl:
        collapse_warning = {
            "collapsed_japanese": cl.get("collapsed_japanese"),
            "note": cl.get("note"),
            "primary_source": cl.get("primary_source"),
            "confidence": cl.get("confidence_collapse"),
            "lemmas": [{"lemma": l["lemma"], "lang": l.get("lang"),
                        "gloss": l.get("gloss"), "collapses_to": l.get("collapses_to")}
                       for l in cl.get("lemmas", [])],
        }

    # breadth = the DATA's union of the languages/words carrying this concept,
    # NOT a model-generated list (which would narrow to the few I know — the very
    # affliction we fight). Primary source = the concept node's Wikidata labels
    # (the actual WORD in each language); Wiktionary sections fill any gap.
    # Unmapped codes are shown raw, never dropped.
    breadth = {}
    for code, label in (cd.get("breadth_labels") or {}).items():
        nm = wiktionary.langname(code)
        breadth[nm] = {"name": nm, "term": label, "via": "wikidata"}
    for s in td.get("sections", []):
        if s != "Translingual":
            breadth.setdefault(s, {"name": s, "term": "", "via": "wiktionary"})

    # polysemy: the two paths may resolve different SENSES of a word (空 →『sky』
    # via the article vs 『śūnyatā/梵』via the Buddhist etymology). We show both
    # rather than silently pick one.
    word_origin = td.get("origin_estimate")
    concept_origin = cd.get("original_terms") or []
    # 探究の次元（ベンチマークが示す広さ・深さ・多様性への"確実に辿れる路"）。データの
    # ある次元は ok、既存機構に繋がるものは partial、未整備は soon——構造として常に全次元
    # を提示し、到達可能性を保証する（内容はベンチマークと違ってよい・A3で被覆を正直に）。
    german_term = next((o["term"] for o in concept_origin if o.get("name") == "ドイツ語"), None)
    def _dim(key, label, status, act=""):
        return {"key": key, "label": label, "status": status, "act": act}
    dimensions = [
        _dim("etymology", "語源・変容の連鎖", "ok" if (td.get("origin_chain") or word_origin or concept_origin) else "soon", "scroll:card-origin"),
        _dim("distinction", "概念の区別（埋没した原語）", "ok" if collapse_warning else "soon", "scroll:card-collapse"),
        _dim("related", "関連概念（原語空間の共起）", "ok" if german_term else "soon", ("colloc:" + german_term) if german_term else ""),
        _dim("lineage", "思想家の系譜", "partial", "graph"),
        _dim("breadth", "世界の言語での言い方", "ok" if cd.get("breadth_labels") else "soon", "scroll:card-breadth"),
        _dim("critique", "批判・異論（steelman）", "partial", "counter:" + q),
        _dim("era", "時代性・変遷（流行・衰退・再評価）", "soon", ""),
        _dim("application", "応用領域（労働・消費・AI 等）", "soon", ""),
        _dim("tradition", "他の伝統・文化圏の見方", "soon", ""),
    ]
    polysemy = bool(word_origin and concept_origin
                    and word_origin.get("name") not in {o["name"] for o in concept_origin}
                    and not word_origin.get("native"))

    return {
        "query": q, "lang": lang, "queried_at": now(),
        "word": {"query": q},
        "found": td.get("found", False) or cd.get("found", False),
        "resolved_from": cd.get("resolved_from"),   # 間主観→間主観性 と辿った場合の元語
        "resolved_to": cd.get("title"),             # 実際に辿った記事名
        "suggestions": cd.get("suggestions") or [],  # 見つからない時の候補（行き止まりにしない）
        "dimensions": dimensions,                # 探究の次元（どの語からも辿れる路）
        "general_meaning": gen_senses,           # 広く共有されている意味（入力言語）
        # 分解は語全体→意味のまとまり→文字の順。外部取得なしの構造層を意味面でも共有する。
        "segment_layers": etymology.semantic_layers(q),
        "collapse_warning": collapse_warning,    # ⚠ 埋没の明示警告（A←B・C・D）
        "concept_origin": concept_origin,        # 概念-翻訳-原点（疎外→独 Entfremdung）
        "originators": cd.get("originators") or [],  # 立てた/著した人（P50/P61/P112・決定論）
        "associated": cd.get("associated") or [],    # 関連する思想家（記事言及・重要度順・再現向上）
        "relations": cd.get("relations") or {"near": [], "opposite": []},  # 類語・対義（クイズ等で利用）
        "named_after": cd.get("named_after") or [],  # 語形の由来（P138・語源・概念の原点でない）
        "word_origin": word_origin,              # 語源原点（空→梵・推定）
        "chain": td.get("origin_chain", []),     # 変容の連鎖（言語＋語形・全表示）
        "senses": td.get("senses", []),
        "polysemy": polysemy,
        "breadth": sorted(breadth.values(), key=lambda x: x["name"]),
        "breadth_count": len(breadth),
        "qid": cd.get("qid"),
        "article_url": cd.get("article_url"),
        "wikidata_url": cd.get("wikidata_url"),
        "wiktionary_url": td.get("url"),
        "confidence": {
            "concept_origin": "百科の記述（密度の高い言説からの手がかり・要権威裏取り）",
            "word_origin": "推定（語源チェーンの最古層・断定でない）",
            "breadth": "データの和集合（言語選定はモデルでなくデータ）"},
        "sources": [{"source": r["source"], "retrieved_at": r["retrieved_at"],
                     "error": r["error"]} for r in (tr, cn)],
    }


@app.get("/api/origin/graph")
async def api_origin_graph(q: str, lang: str = "ja"):
    """言語空間の重力分布グラフ（第1〜4階層）。第1=入力語／第2=重力分布の分岐（意味の
    領域・世界の言語）／第3=分岐を構成するもの（埋没した複数原語・各言語での語）／第4=強く
    関与する著者・著作（重要度順）。node の大きさ＝重力（密度の代理指標＝推定）、edge＝
    関係。データのある枝は濃く、無い枝は薄い（捏造しない・A3）。各 node は q を持てば
    クリックで新たな第1階層として展開できる。"""
    await wiktionary.ensure_langnames(lang)   # 全言語コード→日本語名を用意（生コード表示の解消）
    if not q.strip():
        raise HTTPException(400, "empty query")
    cn = await concept.node(q, lang)
    cd = cn["data"] if not cn["error"] else {}
    _sec = {"ja": "Japanese", "en": "English", "de": "German", "zh": "Chinese"}.get(lang, "Japanese")
    tr = await wiktionary.trace(q, _sec)   # 語源trace＝ja記事に無い原語(διά等)でも辿れる（section名で渡す）
    td = tr["data"] if not tr["error"] else {}
    gen = await wiktionary.ja_senses(q) if lang == "ja" else None
    senses = (gen["data"]["senses"] if gen and not gen["error"] and gen.get("data") else [])
    cluster = _orig_cluster(q, None)
    lineage = _author_lineage(q, None)

    nodes, edges, seen = [], [], set()

    def add(nid, label, kind, layer, weight=1.0, qq=None, extra=None):
        if nid in seen:
            return
        seen.add(nid)
        nodes.append({"id": nid, "label": label, "kind": kind, "layer": layer,
                      "weight": weight, "q": qq, **(extra or {})})

    def link(a, b, strength=1.0):
        edges.append({"from": a, "to": b, "strength": strength})

    add("root", q, "word", 1, 3.0, q, {"qid": cd.get("qid")})

    # 第2階層: 分岐（意味の領域）
    if senses:
        add("dom:general", "一般の意味", "domain", 2, 1.4)
        link("root", "dom:general", 1.0)
    origin_terms = cd.get("original_terms") or []
    phil = "dom:phil" if (origin_terms or cluster) else None
    if phil:
        add(phil, "専門・思想の意味", "domain", 2, 2.4)
        link("root", phil, 1.5)

    # 第3階層: 分岐を構成するもの（埋没した複数原語・概念の原語）
    for l in (cluster.get("lemmas", []) if cluster else []):
        nid = f"orig:{l['lemma']}"
        add(nid, l["lemma"], "original", 3, 1.8, l["lemma"], {"gloss": l.get("gloss")})
        link(phil or "root", nid, 1.2)
    for o in origin_terms:
        nid = f"orig:{o['term']}"
        add(nid, o["term"], "original", 3, 1.6, o["term"], {"lang_name": o.get("name")})
        link(phil or "root", nid, 1.0)

    # 第4階層: 概念を立てた思想家（Wikidata P61/P112・決定論・seedでなく動的）。
    # リゾーム→ドゥルーズ・ガタリ。これで語形translationsに埋もれず、次元「思想家の系譜」と
    # 原点カードとグラフが一致する（貧弱記事の語源だけを原点と誤提示しない）。
    # 第4階層: 思想家（立てた/著した人＋関連思想家）。大きさ＝影響度（Wikidata言明数の対数を
    # 集合内で正規化＝マルクスが際立って大きくなる）。思想家どうしは P737(影響を受けた) で線を結ぶ
    # ＝力学レイアウトで関係の近い者が引き寄せられ、距離・並びが関係を反映する。
    thinkers = ([("orig", p) for p in (cd.get("originators") or []) if p.get("label")]
                + [("assoc", p) for p in (cd.get("associated") or []) if p.get("label")])
    if thinkers:
        logs = [math.log1p(p.get("nclaims") or 0) for _, p in thinkers]
        lo, hi = min(logs), max(logs)
        node_of = {}
        for kind, p in thinkers:
            norm = (math.log1p(p.get("nclaims") or 0) - lo) / (hi - lo) if hi > lo else 1.0
            w = round((2.8 if kind == "orig" else 1.0) + norm * 3.4, 2)  # 著者本人を際立たせ＋影響度で大小
            pid = f"auth:{p['label']}"
            add(pid, p["label"], "author", 4, w, None, {"search": p["label"], "qid": p.get("qid")})
            link(phil or "root", pid, 1.4 if kind == "orig" else 0.9)
            if p.get("qid"):
                node_of[p["qid"]] = pid
        for _, p in thinkers:   # 思想家どうしの関係線（影響を受けた・双方が居る時）
            src = node_of.get(p.get("qid"))
            for tgt in (p.get("influenced_by") or []):
                if src and tgt in node_of and node_of[tgt] != src:
                    link(src, node_of[tgt], 1.1)
        for p in (cd.get("originators") or []):   # 思想家→著作の階層（第5階層に分岐）
            if not p.get("qid"):
                continue
            pid = node_of.get(p["qid"])
            works = await _sparql(
                f'SELECT ?wLabel WHERE {{ ?w wdt:P50 wd:{p["qid"]}. '
                f'SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang},en". }} }} LIMIT 8')
            for r in works:
                wl = r.get("wLabel", {}).get("value", "")
                if not wl or wl.startswith("Q"):
                    continue
                wid = f"authwork:{p['label']}:{wl}"
                add(wid, wl, "work", 5, 0.8, wl)
                if pid:
                    link(pid, wid, 0.7)

    # 第4階層: 強く関与する著者・著作（seed系譜・重要度＝史的順）
    for i, a in enumerate(lineage.get("authors", []) if lineage else []):
        w = max(0.9, 2.2 - i * 0.35)
        aid = f"auth:{a['author']}"
        add(aid, a["author"], "author", 4, w, None,
            {"work": a.get("work"), "year": a.get("year"), "term_de": a.get("term_de"),
             "search": a.get("author_de") or a.get("author")})
        link(phil or "root", aid, 0.8)
        if a.get("work"):
            wid = f"work:{a['work']}"
            add(wid, a["work"], "work", 4, max(0.7, w - 0.3))
            link(aid, wid, 0.6)

    # 第3階層: 類語・対義の星座（Wikidata型付き関係＋関連項目・人物除外・決定論）。
    # 近い/類する概念(related)と、対立/区別される概念(opposite)。クリックでその概念へ再中心。
    rel = cd.get("relations") or {}
    for r in (rel.get("near") or []):
        if not r.get("label"):
            continue
        rid = f"rel:{r['label']}"
        add(rid, r["label"], "related", 3, 1.0, r["label"], {"qid": r.get("qid")})
        link(phil or "root", rid, 0.7)
    for r in (rel.get("opposite") or []):
        if not r.get("label"):
            continue
        rid = f"opp:{r['label']}"
        add(rid, r["label"], "opposite", 3, 1.1, r["label"], {"qid": r.get("qid")})
        link("root", rid, 0.7)

    # 第2階層: 世界の言語の広がり（breadth）＋ 第3: 各言語での語（一部）。
    # 一次源＝Wikidata多言語ラベル（各言語の実語）。それが薄い語（διά のようにja記事が無く
    # Wikidataに載らない原語）では Wiktionary の言語節（td.sections）で補い、言語マップを普遍的に出す。
    breadth = []
    for code, label in (cd.get("breadth_labels") or {}).items():
        breadth.append((f"lang:{code}", f"{wiktionary.langname(code)}：{label}", label))
    seen_lang = {b[1] for b in breadth}
    for s in td.get("sections", []):
        if s == "Translingual" or s in seen_lang:
            continue
        breadth.append((f"lang:sec:{s}", s, s))     # Wiktionary言語節（各言語の実語形はWiktへ委譲）
    if breadth:
        add("dom:breadth", f"世界の言語 {len(breadth)}", "domain", 2, 1.9)
        link("root", "dom:breadth", 1.0)
        for nid, lbl, qq in breadth[:14]:
            add(nid, lbl, "language", 3, 0.85, qq)
            link("dom:breadth", nid, 0.4)

    # 第2/3階層: 語源の連鎖（td.origin_chain）を原語ノードに＝ja記事に無い原語でも辿れる。
    # 各層は選べば site内で再中心（.ext-term と同じ普遍ルール／P11）＝クリックで探索が続く。
    chain = td.get("origin_chain") or []
    if chain and not (cluster or origin_terms):    # 既に概念原語が濃い語では重複させない
        add("dom:etym", "語源の連鎖", "domain", 2, 1.7)
        link("root", "dom:etym", 1.0)
        for i, c in enumerate(chain[:6]):
            form = (c.get("form") or "").strip()
            name = (c.get("name") or "").strip()
            if not (form or name):
                continue
            nid = f"etym:{i}"
            lbl = f"{name}：{form}" if (name and form) else (form or name)
            add(nid, lbl, "original", 3, 1.4, form or name, {"lang_name": name})
            link("dom:etym", nid, 0.5)

    return {"query": q, "queried_at": now(), "qid": cd.get("qid"), "nodes": nodes, "edges": edges,
            "note": "重力(nodeの大きさ)・関係(edge)は密度の代理指標＝推定。データのある枝は"
                    "濃く、無い枝は薄い（捏造しない）。著者順は史的順。",
            "sources": [{"source": cn["source"], "retrieved_at": cn["retrieved_at"],
                         "error": cn["error"]}]}


SPARQL = "https://query.wikidata.org/sparql"


async def _sparql(query: str):
    try:
        d, _, _ = await cached_get_json(SPARQL, {"query": query, "format": "json"}, ttl=86400)
        return d.get("results", {}).get("bindings", [])
    except Exception:
        return []


def _app_domain(labels: str) -> str:
    """作品の型・ジャンルから大分野を決める（応用・波及レンズ）。中立の粗分類・出所は型ラベル。"""
    s = labels.lower()
    if any(k in s for k in ["film", "映画", "cinema", "theatre", "演劇", "音楽", "music", "opera",
                            "painting", "絵画", "art", "芸術", "sculpture", "album", "song"]):
        return "芸術・映画"
    if any(k in s for k in ["novel", "小説", "poem", "詩", "literary", "文学", "fiction", "戯曲", "play"]):
        return "文学"
    if any(k in s for k in ["war", "戦争", "revolution", "革命", "event", "事件", "battle", "movement", "運動"]):
        return "歴史・事件"
    if any(k in s for k in ["political", "政治", "law", "法", "policy", "manifesto", "宣言"]):
        return "政治・社会"
    return "著作・研究"


@app.get("/api/applications")
async def api_applications(q: str, lang: str = "ja"):
    """応用・波及レンズ: この概念を主題とする作品（P921）を、文学・芸術・映画・歴史等の
    分野に粗分類して『分野別の枝＋作品の点』のグラフで返す。データはWikidataの作品claim＝
    捏造しない・分野は型/ジャンルラベルに接地（中立）。無ければ正直に空。"""
    cn = await concept.node(q, lang)
    cd = cn["data"] if not cn["error"] else {}
    qid, title = cd.get("qid"), cd.get("title") or q
    nodes = [{"id": "root", "label": q, "kind": "word", "layer": 1, "weight": 3.0, "q": q}]
    edges, seen = [], {"root"}

    def dom(name, w=2.0):
        did = f"appdom:{name}"
        if did not in seen:
            seen.add(did)
            nodes.append({"id": did, "label": name, "kind": "appdomain", "layer": 2, "weight": w})
            edges.append({"from": "root", "to": did, "strength": 1.2})
        return did

    def leaf(label, did, weight=1.0):
        wid = f"appwork:{label}"
        if not label or wid in seen:
            return
        seen.add(wid)
        nodes.append({"id": wid, "label": label, "kind": "application", "layer": 3, "weight": weight, "q": label})
        edges.append({"from": did, "to": wid, "strength": 0.7})

    # A) この概念を主題とする作品（P921）＝文学・芸術・映画・歴史への応用
    if qid:
        rows_ = await _sparql(f"""SELECT DISTINCT ?workLabel ?typeLabel ?genreLabel ?date WHERE {{
          ?work wdt:P921 wd:{qid}. OPTIONAL {{ ?work wdt:P31 ?type. }} OPTIONAL {{ ?work wdt:P136 ?genre. }}
          OPTIONAL {{ ?work wdt:P577 ?date. }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang},en". }} }} ORDER BY ?date LIMIT 40""")
        for r in rows_:
            wl = r.get("workLabel", {}).get("value", "")
            if not wl or wl.startswith("Q"):
                continue
            d = _app_domain(f"{r.get('typeLabel',{}).get('value','')} {r.get('genreLabel',{}).get('value','')}")
            yr = (r.get("date", {}).get("value", "") or "")[:4]
            leaf(wl + (f"（{yr}）" if yr else ""), dom(d))

    # B) 社会体制・思想・運動への波及（記事が言及する非人物の概念を重要度順）＝資本論→
    #    共産主義/社会主義/マルクス経済学… ご指摘の「社会体制のきっかけ」を機械的に出す。
    concepts = await concept.article_concepts(title, lang, {qid} if qid else set())
    if concepts:
        did = dom("思想・体制・運動への波及", 2.4)
        for i, c in enumerate(concepts):
            leaf(c["label"], did, weight=max(0.8, 1.6 - i * 0.08))

    note = ("この概念の応用（主題とする作品）と波及（結びつく思想・体制・運動）を分野別に。"
            if len(nodes) > 1 else "応用・波及はデータが増えると現れます（現状は空・捏造しない）。")
    return {"query": q, "queried_at": now(), "qid": qid, "nodes": nodes, "edges": edges, "note": note,
            "sources": [{"source": "wikidata:P921 + article-concepts", "retrieved_at": now(), "error": None}]}


@app.get("/api/usage")
async def api_usage(q: str, lang: str = "ja"):
    """使用例・引用レンズ: この語が実テキスト（学術）で実際にどう使われたかを、OpenAlexの
    著作（題・著者・年・出典）として引用カードで返す。捏造せず出所つき（賛否・評価は判定
    しない・中立）。原語でも引ける。"""
    cn = await concept.node(q, lang)
    cd = cn["data"] if not cn["error"] else {}
    terms = [q] + [o.get("term") for o in (cd.get("original_terms") or []) if o.get("term")]
    seen, cards = set(), []
    for term in terms[:2]:
        try:
            d, _, _ = await cached_get_json("https://api.openalex.org/works",
                {"search": term, "per_page": 8, "mailto": "handa.shinya@gmail.com"}, ttl=86400)
        except Exception:
            continue
        for w in d.get("results", []):
            t = w.get("title")
            if not t or t in seen:
                continue
            seen.add(t)
            au = [a.get("author", {}).get("display_name") for a in (w.get("authorships") or [])[:3]]
            cards.append({"title": t, "year": w.get("publication_year"), "term": term,
                          "authors": [a for a in au if a], "url": w.get("doi") or w.get("id"),
                          "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name")})
        if len(cards) >= 12:
            break
    # 現代の研究者（OpenAlex著者集計・被研究度順）。歴史的正典（マルクス等）でなく「いま最も
    # この概念を論じている研究者」＝文脈的prominence。歴史的思想家は思想家レンズが担う（区別）。
    scholars = []
    try:
        term0 = (cd.get("original_terms") or [{}])[0].get("term") or q
        sd, _, _ = await cached_get_json("https://api.openalex.org/works",
            {"search": term0, "group_by": "authorships.author.id", "mailto": "handa.shinya@gmail.com"}, ttl=86400)
        for g in sd.get("group_by", [])[:10]:
            nm = g.get("key_display_name")
            if nm and nm != "unknown":
                scholars.append({"name": nm, "count": g.get("count")})
    except Exception:
        pass
    return {"query": q, "queried_at": now(), "cards": cards[:12], "scholars": scholars,
            "note": "この語が学術テキストで実際に使われた著作（OpenAlex・出典つき／賛否は判定しない）。"
                    if cards else "実テキストの用例はデータが増えると現れます（現状は空・捏造しない）。"}


@app.get("/api/timeline")
async def api_timeline(q: str, lang: str = "ja"):
    """時代・変遷レンズ: この概念（原語）がいつ流行り・衰退し・再評価されたかを、Google Books
    Ngram の通時頻度で返す（無料・鍵不要）。カタカナ入力語は書物コーパスに乏しいため、原語
    （独/英/仏など）の語形で引く。捏造せず、取得できた系列だけ返す。"""
    await wiktionary.ensure_langnames(lang)
    cn = await concept.node(q, lang)
    cd = cn["data"] if not cn["error"] else {}
    labels = cd.get("breadth_labels") or {}
    # 原語の語形を、対応するNgramコーパスで引く（英・独・仏・西・伊・露）
    plan = [(labels.get("en"), "en-2019", "英語"), (labels.get("de"), "de-2019", "ドイツ語"),
            (labels.get("fr"), "fr-2019", "フランス語"), (labels.get("es"), "es-2019", "スペイン語"),
            (labels.get("it"), "it-2019", "イタリア語"), (labels.get("ru"), "ru-2019", "ロシア語")]
    for o in (cd.get("original_terms") or []):
        plan.append((o.get("term"), "de-2019" if o.get("name") == "ドイツ語" else "en-2019", o.get("name")))
    series, seen = [], set()
    for term, corpus, langname in plan:
        if not term or not re.match(r"^[A-Za-zÀ-ÿ' -]+$", term) or (term, corpus) in seen:
            continue
        seen.add((term, corpus))
        try:
            d, _, _ = await cached_get_json("https://books.google.com/ngrams/json",
                {"content": term, "year_start": 1800, "year_end": 2019, "corpus": corpus, "smoothing": 3}, ttl=86400)
        except Exception:
            continue
        if d and d[0].get("timeseries"):
            ts = d[0]["timeseries"]
            series.append({"term": term, "lang": langname, "start": 1800, "end": 2019,
                           "values": [round(v, 10) for v in ts],
                           "peak_year": 1800 + max(range(len(ts)), key=lambda i: ts[i])})
        if len(series) >= 4:
            break
    return {"query": q, "queried_at": now(), "series": series,
            "note": "原語の語形の通時頻度（Google Books Ngram・書物コーパス）。いつ現れ・広まり・"
                    "衰退し・再評価されたか。カタカナ語でなく原語で辿る。" if series
                    else "通時頻度は原語形が揃うと現れます（現状は空・捏造しない）。"}


_REGION_EU = {"de", "fr", "en", "es", "it", "la", "grc", "el", "ru", "nl", "pt", "pl", "sv",
              "da", "no", "nb", "fi", "uk", "cs", "ro", "hu", "tr", "he", "ar", "fa", "ca", "eo"}


def _region_of(code):
    if code == "ja":
        return "日本"
    if code in {"zh", "ko", "vi", "yue", "wuu", "za"}:
        return "漢字圏"
    return "欧" if code in _REGION_EU else "その他"


async def _ndl_works(q, n=6):
    """国立国会図書館サーチ（鍵不要・文化圏:日本の受容史）。RSSの<item><title>を抽出。"""
    try:
        import xml.etree.ElementTree as ET
        txt, _, _ = await cached_get_text("https://ndlsearch.ndl.go.jp/api/opensearch",
                                          {"any": q, "cnt": n}, ttl=86400)
        root = ET.fromstring(txt)
        out = []
        for it in root.iter("item"):
            t = it.findtext("title")
            if t:
                out.append(t.strip())
        return out[:n]
    except Exception:
        return []


@app.get("/api/culture")
async def api_culture(q: str, lang: str = "ja"):
    """文化圏レンズ: この概念を担う言語を欧/漢字圏/日本/その他で束ね、日本圏には国立国会図書館
    （NDL・鍵不要）の国内文献を実データで足す＝どの文化圏を基準にするかで重力場が変わる。"""
    await wiktionary.ensure_langnames(lang)
    cn = await concept.node(q, lang)
    cd = cn["data"] if not cn["error"] else {}
    labels = cd.get("breadth_labels") or {}
    nodes = [{"id": "root", "label": q, "kind": "word", "layer": 1, "weight": 3.0, "q": q}]
    edges, seen = [], {"root"}

    def region(name):
        rid = f"reg:{name}"
        if rid not in seen:
            seen.add(rid)
            nodes.append({"id": rid, "label": name, "kind": "appdomain", "layer": 2, "weight": 2.2})
            edges.append({"from": "root", "to": rid, "strength": 1.2})
        return rid

    for code, label in list(labels.items())[:40]:
        rid = region(_region_of(code))
        nid = f"lang:{code}"
        if nid not in seen:
            seen.add(nid)
            nodes.append({"id": nid, "label": f"{wiktionary.langname(code)}：{label}", "kind": "language",
                          "layer": 3, "weight": 0.85, "q": label})
            edges.append({"from": rid, "to": nid, "strength": 0.5})
    # 日本圏: NDLの国内文献（受容史）
    ndl = await _ndl_works(q)
    if ndl:
        rid = region("日本")
        for i, t in enumerate(ndl):
            wid = f"ndl:{i}"
            nodes.append({"id": wid, "label": (t[:40] + "…") if len(t) > 40 else t,
                          "kind": "application", "layer": 3, "weight": 0.9})
            edges.append({"from": rid, "to": wid, "strength": 0.5})
    note = ("文化圏で束ねる: 欧／漢字圏／日本／その他。日本圏は国立国会図書館の国内文献も。"
            if len(nodes) > 1 else "文化圏データはデータが増えると現れます（現状は空・捏造しない）。")
    return {"query": q, "queried_at": now(), "nodes": nodes, "edges": edges, "note": note,
            "sources": [{"source": "wikidata-breadth + NDL", "retrieved_at": now(), "error": None}]}


@app.get("/api/websearch")
async def api_websearch(q: str, lang: str = "ja"):
    """一般ウェブ検索ボックス（SearXNG）。Wikipedia系＝構造の背骨に対し、一般ウェブの広さ。
    賛否・順位はエンジン由来（中立に列挙）。出所つき・新タブ。未稼働時は正直に空。"""
    res = await searxng.search(q, lang, n=20, drop_commercial=True)
    cards = [{"title": r["title"], "url": r["url"], "content": r["content"][:160], "engine": r["engine"]}
             for r in res if r["title"] and r["url"]]
    return {"query": q, "queried_at": now(), "cards": cards[:16],
            "note": "一般ウェブ検索（SearXNG＝Google等を束ねる自前メタ検索・鍵不要）。順位はエンジン由来。"
                    if cards else "一般ウェブ検索は現在準備中です（SearXNG）。"}


# 一般ウェブの「重力分布」を測るためのドメイン語彙（頻度で意味の重い領域を推定）
_GRAV_DOMAINS = {
    "哲学・思想": ["哲学", "思想", "思想家", "形而上学", "存在論", "認識論", "現象学", "弁証法"],
    "植物・生物": ["植物", "地下茎", "根茎", "生物", "植物学", "園芸", "茎", "花"],
    "経済": ["経済", "経済学", "資本", "市場", "金融", "産業", "貨幣"],
    "政治・社会": ["政治", "社会", "社会学", "制度", "運動", "革命", "階級"],
    "歴史": ["歴史", "時代", "世紀", "古代", "近代"],
    "宗教": ["宗教", "仏教", "キリスト", "神学", "信仰", "禅"],
    "芸術・文学": ["芸術", "美術", "文学", "小説", "詩", "音楽", "映画", "建築", "デザイン"],
    "科学・技術": ["科学", "物理", "数学", "化学", "工学", "技術", "情報", "コンピュータ", "医学"],
    "心理": ["心理", "精神", "認知", "無意識"],
}


def _wiki_title_from_url(url):
    m = re.search(r"wikipedia\.org/wiki/([^?#]+)", url or "")
    if not m:
        return None
    t = urllib.parse.unquote(m.group(1)).replace("_", " ")
    return t if ":" not in t else None   # 特別ページ等を除外


@app.get("/api/gravity")
async def api_gravity(q: str, lang: str = "ja"):
    """重力探索: 一般ウェブ検索で「意味の重力分布」を測り、重い領域を語とAND検索して次階層へ
    連続展開する（半田様設計）。リゾーム→哲学/植物が重い→『リゾーム 哲学』のAND検索で
    ドゥルーズ等を次階層に。頻度＝重力に従い、重い枝ほど大きく深く掘る。SearXNG依存・鍵不要。"""
    root = {"id": "root", "label": q, "kind": "word", "layer": 1, "weight": 3.0, "q": q}
    res = await searxng.search(q, lang, n=20, drop_commercial=True)
    if not res:
        return {"query": q, "nodes": [root], "edges": [],
                "note": "一般ウェブ検索（SearXNG）が利用できないため重力分布を測れませんでした。"}
    # 意味アンカー（Wikidataの思想家・関連概念＝件数でなく"意味"の重み。ハイブリッド重力）
    cn = await concept.node(q, lang)
    cd = cn["data"] if not cn["error"] else {}
    anchors = set()
    for p in (cd.get("originators") or []) + (cd.get("associated") or []):
        if p.get("label"):
            anchors.add(p["label"])
    for r in ((cd.get("relations") or {}).get("near") or []) + ((cd.get("relations") or {}).get("opposite") or []):
        if r.get("label"):
            anchors.add(r["label"])

    def _sem(e):   # 意味一致（Wikidataの関係集合と一致/包含）
        return any(a == e or (len(a) > 2 and a in e) or (len(e) > 2 and e in a) for a in anchors)

    # Pass 1: 一般検索の結果テキストで各領域語の出現頻度＝重力分布を測る
    blob = " ".join((r["title"] + " " + r["content"]) for r in res)
    grav = {d: sum(blob.count(k) for k in kws) for d, kws in _GRAV_DOMAINS.items()}
    top = [(d, g) for d, g in sorted(grav.items(), key=lambda x: -x[1]) if g > 0][:5]
    nodes, edges, used = [root], [], set()
    maxg = top[0][1] if top else 1
    # Pass 2: 重い領域ごとに『語 AND 領域』検索→次階層の実体を、意味一致(Wikidata)で優先・加重
    for d, g in top:
        sub = await searxng.search(q, lang, extra=_GRAV_DOMAINS[d][0], n=12, drop_commercial=True)
        ents, seene = [], set()
        for r in sub:
            t = _wiki_title_from_url(r["url"])
            if t and t != q and t not in seene:
                seene.add(t); ents.append(t)
        for r in sub:
            if len(ents) >= 8:
                break
            t = (r["title"] or "").split(" - ")[0].split("｜")[0].strip()
            if t and t != q and t not in seene and len(t) <= 40:
                seene.add(t); ents.append(t)
        ents = [e for e in ents if _sem(e)] + [e for e in ents if not _sem(e)]   # 意味一致を先に
        picked = ents[:5]
        semc = sum(1 for e in picked if _sem(e))
        did = f"gdom:{d}"
        # ドメイン重力＝ウェブ頻度 ＋ 意味一致数（件数だけでなく意味で重みづけ）
        nodes.append({"id": did, "label": f"{d}（{g}{'＋意味'+str(semc) if semc else ''}）",
                      "kind": "appdomain", "layer": 2, "weight": round(1.6 + 2.0 * g / maxg + 0.5 * semc, 2)})
        edges.append({"from": "root", "to": did, "strength": 0.8 + 0.6 * g / maxg})
        for e in picked:
            eid = f"gent:{d}:{e}"
            nodes.append({"id": eid, "label": e, "kind": "application", "layer": 3,
                          "weight": 1.8 if _sem(e) else 1.0, "q": e})   # 意味一致は大きく
            edges.append({"from": did, "to": eid, "strength": 0.7 if _sem(e) else 0.5})
            used.add(e)
    # 意味的に近い（Wikidata）が、ウェブ結果に現れなかったもの＝意味が拾う分を明示的に追加
    orphan = [a for a in anchors if a not in used and not any(a in u or u in a for u in used)][:5]
    if orphan:
        did = "gdom:意味的に近い（Wikidata）"
        nodes.append({"id": did, "label": "意味的に近い（Wikidata）", "kind": "appdomain", "layer": 2, "weight": 2.6})
        edges.append({"from": "root", "to": did, "strength": 1.1})
        for a in orphan:
            eid = f"gsem:{a}"
            nodes.append({"id": eid, "label": a, "kind": "related", "layer": 3, "weight": 1.6, "q": a})
            edges.append({"from": did, "to": eid, "strength": 0.7})
    note = ("重力分布＝一般ウェブの頻度 × 意味（Wikidataの思想家・関連概念）のハイブリッド。"
            "重い順: " + "・".join(d for d, _ in top) + "。意味一致は大きく・先に。クリックでその語へ。")
    return {"query": q, "queried_at": now(), "nodes": nodes, "edges": edges, "note": note,
            "sources": [{"source": "SearXNG(一般ウェブ) + Wikidata(意味)", "retrieved_at": now(), "error": None}]}


def _web_entities(results, exclude, limit=10):
    """SearXNG結果から綺麗な実体名を抽出（Wikipedia項目→上位結果の題）。重複/除外を排す。"""
    ents, seen = [], set(x for x in exclude if x)
    for r in results:
        t = _wiki_title_from_url(r.get("url"))
        if t and t not in seen:
            seen.add(t); ents.append(t)
    for r in results:
        if len(ents) >= limit:
            break
        t = (r.get("title") or "").split(" - ")[0].split("｜")[0].split(" | ")[0].strip()
        if t and t not in seen and 1 < len(t) <= 40:
            seen.add(t); ents.append(t)
    return ents[:limit]


async def _combine_web_search(q: str, lang: str, extra: str = "", n: int = 20):
    """組合せ検索の主経路＋同一操作内の退避経路。

    SearXNGの空配列は「検索語に一致なし」と「検索源が停止中」の区別が難しい。
    そこで空の時だけWikipedia全文検索を同じ条件で実行し、出所を返す。一般ウェブ
    全体をWikipediaと偽らず、APIのnoteに退避経路を明示する。
    """
    try:
        # SearXNG側の再試行（無料検索源の不通）が画面を長時間占有しないよう、
        # 組合せ操作では8秒で同じ条件の退避検索へ移る。
        primary = await asyncio.wait_for(
            searxng.search(q, lang, extra=extra, n=n, drop_commercial=True), timeout=8.0)
    except asyncio.TimeoutError:
        primary = []
    if primary:
        return primary, "SearXNG"
    query = " ".join(x for x in (q, extra) if x).strip()
    fallback = await wikipedia.search(query, lang, limit=n)
    if not fallback.get("error") and fallback.get("data"):
        return fallback["data"], "Wikipedia全文検索"
    return [], "検索源未応答"


@app.get("/api/combine")
async def api_combine(a: str, b: str = "", op: str = "and", lang: str = "ja"):
    """ユーザー主導の組み合わせ探索（半田様のAND案）。op= and(絞り込み)/not(除外)/or(合わせる)/
    compare(比較)/semand(意味で絞る)。一般ウェブ(SearXNG)＋Wikidata意味で、選んだ語に条件を
    足して重力場を絞る/広げる/比べる。鍵不要・出所つき・fail-safe。"""
    def root(label, wid="root", w=3.0, layer=1, q=None):
        return {"id": wid, "label": label, "kind": "word", "layer": layer, "weight": w, "q": q or label}
    nodes, edges = [], []

    if op == "compare":   # 2語を並べ、共有(中央)と各固有(左右)を見る
        ra, sa = await _combine_web_search(a, lang, n=16)
        rb, sb = await _combine_web_search(b, lang, n=16)
        ea, eb = _web_entities(ra, [a, b], 12), _web_entities(rb, [a, b], 12)
        setb = set(eb)
        shared = [e for e in ea if e in setb]
        onlyA = [e for e in ea if e not in setb][:6]
        onlyB = [e for e in eb if e not in set(ea)][:6]
        nodes += [root(a, "rootA", 3.0, 1), root(b, "rootB", 3.0, 1)]
        if shared:
            nodes.append({"id": "cshared", "label": "共有（両方に関わる）", "kind": "appdomain", "layer": 2, "weight": 2.4})
            edges += [{"from": "rootA", "to": "cshared", "strength": 1.0}, {"from": "rootB", "to": "cshared", "strength": 1.0}]
            for e in shared[:8]:
                nodes.append({"id": f"cs:{e}", "label": e, "kind": "related", "layer": 3, "weight": 1.4, "q": e})
                edges.append({"from": "cshared", "to": f"cs:{e}", "strength": 0.7})
        for side, only, rid in (("A", onlyA, "rootA"), ("B", onlyB, "rootB")):
            for e in only:
                nodes.append({"id": f"c{side}:{e}", "label": e, "kind": "application", "layer": 2, "weight": 1.0, "q": e})
                edges.append({"from": rid, "to": f"c{side}:{e}", "strength": 0.6})
        note = f"「{a}」と「{b}」の比較。中央＝両方に関わる概念、左右＝それぞれ固有。クリックでその語へ。"
        source = "・".join(dict.fromkeys(x for x in (sa, sb) if x))
        return {"query": a, "nodes": nodes, "edges": edges, "note": note + f" 出所：{source}。",
                "has_results": bool(shared or onlyA or onlyB), "queried_at": now()}

    if op == "semand":   # 意味で絞る: aの意味アンカー(Wikidata)のうち、bの文脈に現れるものへ
        cn = await concept.node(a, lang); cd = cn["data"] if not cn["error"] else {}
        anchors = [p["label"] for p in (cd.get("originators") or []) + (cd.get("associated") or []) if p.get("label")]
        anchors += [r["label"] for r in ((cd.get("relations") or {}).get("near") or []) if r.get("label")]
        res, source = await _combine_web_search(a, lang, extra=b, n=20)
        blob = " ".join((r["title"] + " " + r["content"]) for r in res)
        hit = [x for x in dict.fromkeys(anchors) if x and x in blob]        # 意味アンカー ∩ a+b文脈
        rest = [x for x in dict.fromkeys(anchors) if x and x not in blob][:4]
        nodes.append(root(f"「{a}」を〈{b}〉の意味で"))
        for e in (hit or rest)[:10]:
            k = "related" if e in hit else "application"
            nodes.append({"id": f"s:{e}", "label": e, "kind": k, "layer": 2, "weight": 1.8 if e in hit else 1.0, "q": e})
            edges.append({"from": "root", "to": f"s:{e}", "strength": 0.7})
        note = (f"「{a}」の意味的な近縁（Wikidata）のうち、〈{b}〉の文脈に現れるものを大きく。件数でなく意味で絞る。"
                if hit else f"〈{b}〉の意味文脈に一致する近縁は少なめ。近い候補を薄く示します。")
        return {"query": a, "nodes": nodes, "edges": edges,
                "note": note + f" 出所：{source}。", "has_results": bool(hit or rest), "queried_at": now()}

    # and / not / or ＝一般ウェブで絞る/除外/合わせる
    if op == "or":
        ra, sa = await _combine_web_search(a, lang, n=14)
        rb, sb = await _combine_web_search(b, lang, n=14)
        nodes += [root(a, "rootA", 3.0, 1), root(b, "rootB", 3.0, 1)]
        for side, res, rid in (("A", ra, "rootA"), ("B", rb, "rootB")):
            for e in _web_entities(res, [a, b], 8):
                nodes.append({"id": f"o{side}:{e}", "label": e, "kind": "application", "layer": 2, "weight": 1.0, "q": e})
                edges.append({"from": rid, "to": f"o{side}:{e}", "strength": 0.6})
        note = f"「{a}」と「{b}」を合わせて（OR）。両方の周辺を一度に。クリックでその語へ。"
        source = "・".join(dict.fromkeys(x for x in (sa, sb) if x))
        return {"query": a, "nodes": nodes, "edges": edges, "note": note + f" 出所：{source}。",
                "has_results": bool(_web_entities(ra, [a, b], 8) or _web_entities(rb, [a, b], 8)),
                "queried_at": now()}

    extra = b if op == "and" else (f"-{b}" if op == "not" else "")
    res, source = await _combine_web_search(a, lang, extra=extra, n=20)
    label = f"「{a}」{'＋' if op == 'and' else '−'}「{b}」" if b else a
    nodes.append(root(label))
    if not res:
        return {"query": a, "nodes": nodes, "edges": edges, "queried_at": now(),
                "has_results": False,
                "note": f"「{a}」と「{b}」に一致する結果は、SearXNGとWikipedia全文検索の双方で得られませんでした。出所：{source}。"}
    for e in _web_entities(res, [a, b], 12):
        nodes.append({"id": f"c:{e}", "label": e, "kind": "application", "layer": 2, "weight": 1.0, "q": e})
        edges.append({"from": "root", "to": f"c:{e}", "strength": 0.6})
    note = (f"「{a}」を「{b}」で絞り込み（AND）。両方に関わるものだけ。" if op == "and"
            else f"「{a}」から「{b}」を除外（NOT）。" if op == "not" else f"「{a}」の一般ウェブ。")
    return {"query": a, "nodes": nodes, "edges": edges,
            "note": note + f" 出所：{source}。クリックでその語へ。",
            "has_results": True, "queried_at": now()}


@app.get("/api/anatomy")
async def api_anatomy(q: str, lang: str = "ja", own: int = 0):
    """普遍的な語源解剖: 語を原語へ辿り、構成要素(prefix+root)と連鎖を意味glossつきで返す。
    翻訳で見えなくなった原義(弁証法→dia-=間・対話)を原語の実文書(Wiktionary)に接地して復元。

    own=1: 訳語(en/la/de/grc/fr の候補)を経由せず、**その語そのものの来歴**だけを解剖する
    （概念全景の意味契約「語そのものの来歴」用。矛盾→矛+盾/韓非子 を決定論的に返す。既定 own=0 は従来通り）。"""
    if own:
        cands = []   # 訳語候補を使わない＝語そのもの→(自身のページ)→CJK構成文字、の順で語自身の来歴を取る
    else:
        v = await concept.variants(q, lang)
        labels = (v["data"] if not v["error"] else {}).get("labels", {})
        cands = [labels.get("en"), labels.get("la"), labels.get("de"), labels.get("grc"), labels.get("fr")]
    r = await etymology.anatomy(q, cands, lang)
    r.update({"query": q, "queried_at": now(), "own": bool(own)})
    return r


@app.get("/api/variants")
async def api_variants(q: str, lang: str = "ja"):
    """語の多言語variants（外部リンクを各サイトが受け付ける言語形で開くため・普遍適用）。"""
    cn = await concept.variants(q, lang)
    cd = cn["data"] if not cn["error"] else {}
    return {"query": q, "labels": cd.get("labels") or {}, "qid": cd.get("qid"),
            "retrieved_at": cn.get("retrieved_at"), "queried_at": now()}


@app.get("/api/dimensions")
async def api_dimensions(q: str, lang: str = "ja"):
    """概念固有の次元を発見する層（#1・固定分類の先）。その概念自身の Wikipedia 記事の
    節見出し＝その概念に固有の切り口を動的に返す。疎外なら「マルクスの疎外論/ヘーゲル/
    実存主義」等、別の語なら別の切り口が出る。無料・鍵不要・記事構造に接地・編集しない
    （節をそのまま出す＝中立 P2）・出所つき。記事が無ければ正直に空。"""
    if not q.strip():
        raise HTTPException(400, "empty query")
    WP = f"https://{lang}.wikipedia.org/w/api.php"
    try:
        sb, _, _ = await cached_get_json(WP, {"action": "query", "list": "search",
                                              "srsearch": q, "srlimit": 1, "format": "json"})
    except Exception as e:
        return {"query": q, "found": False, "error": f"{type(e).__name__}: {e}", "dimensions": []}
    hits = sb.get("query", {}).get("search", [])
    if not hits:
        return {"query": q, "found": False, "dimensions": [],
                "note": f"「{q}」は共通次元とメニューから探索できます（固有の切り口はデータが増えると現れます）。"}
    title = hits[0]["title"]
    # 曖昧さ回避ページ検出（道→楽曲/映画… のような多義ノイズを正直に警告する）
    disambig = False
    try:
        pp, _, _ = await cached_get_json(WP, {"action": "query", "prop": "pageprops",
                                              "ppprop": "disambiguation", "titles": title, "format": "json"})
        pg = next(iter(pp.get("query", {}).get("pages", {}).values()), {})
        disambig = "disambiguation" in pg.get("pageprops", {})
    except Exception:
        pass
    ps, ts, _ = await cached_get_json(WP, {"action": "parse", "page": title,
                                           "prop": "sections", "format": "json", "redirects": 1})
    secs = ps.get("parse", {}).get("sections", [])
    SKIP = {"脚注", "注釈", "出典", "出典・脚注", "参考文献", "関連項目", "外部リンク", "参照",
            "文献", "ギャラリー", "画像", "References", "Notes", "See also", "External links",
            "Bibliography", "Further reading", "Citations"}
    dims = []
    art = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title)}"
    for s in secs:
        # level 1 (主な切り口) と level 2 (その内訳＝思想家・立場など) を採る。
        # 疎外は上位節が薄く、ヘーゲル/マルクス等は level 2 に居るため両方拾う。
        if str(s.get("toclevel")) in ("1", "2"):
            line = re.sub(r"<[^>]+>", "", s.get("line", "")).strip()
            if line and line not in SKIP:
                dims.append({"heading": line, "level": s.get("toclevel"),
                             "anchor": s.get("anchor", ""),
                             "url": art + "#" + urllib.parse.quote(s.get("anchor", ""))})
        if len(dims) >= 14:                    # cap（無音truncationを避け note で明示）
            break
    return {"query": q, "found": True, "title": title, "article_url": art,
            "disambiguation": disambig,
            "note": ("この語は多義（曖昧さ回避ページ）です。下は特定の概念でなく別義の一覧の可能性があります。"
                     if disambig else ""),
            "dimensions": dims, "queried_at": now(),
            "sources": [{"source": f"wikipedia:{lang}", "retrieved_at": ts, "error": None}]}


@app.get("/api/author")
async def api_author(name: str, lang: str = "ja"):
    """著者を調べる（実データの検出・抽出）— 人物名から記事を検索し、経歴（生没・
    職業）・主要著作・要約を portal 内に出典つきで取得する。著者は語とは別次元なので
    語源エンジンでなくこの人物取得を使う。空なら失敗箇所を正直に示す（捏造しない）。"""
    if not name.strip():
        raise HTTPException(400, "name required")
    WP = f"https://{lang}.wikipedia.org/w/api.php"
    try:
        sb, _, _ = await cached_get_json(WP, {"action": "query", "list": "search",
                                              "srsearch": name, "srlimit": 1, "format": "json"})
    except Exception as e:
        return {"name": name, "found": False, "error": f"{type(e).__name__}: {e}"}
    hits = sb.get("query", {}).get("search", [])
    if not hits:
        return {"name": name, "found": False, "note": f"「{name}」は別表記・原綴からも辿れます。"}
    title = hits[0]["title"]
    summ = await wikipedia.summary(title, lang)
    pb, _, _ = await cached_get_json(WP, {"action": "query", "prop": "pageprops",
                                          "titles": title, "format": "json"})
    page = next(iter(pb.get("query", {}).get("pages", {}).values()), {})
    qid = page.get("pageprops", {}).get("wikibase_item")
    born, died, occ, works = [], [], [], []
    if qid:
        ent = await wikidata.entity(qid, lang)
        if not ent["error"]:
            cl = ent["data"]["claims"]
            born, died = cl.get("born", []), cl.get("died", [])
            oq, nq = cl.get("occupation", [])[:5], cl.get("notable_work", [])[:8]
            labels = await wikidata.resolve_labels(oq + nq, lang)
            occ = [labels.get(x, x) for x in oq if not str(labels.get(x, x)).startswith("Q")]
            works = [labels.get(x, x) for x in nq if not str(labels.get(x, x)).startswith("Q")]
    return {
        "name": name, "found": True, "title": title,
        "extract": (summ["data"]["extract"] if not summ["error"] else ""),
        "born": born, "died": died, "occupation": occ, "works": works,
        "wikipedia_url": (summ["data"]["url"] if not summ["error"]
                          else f"https://{lang}.wikipedia.org/wiki/{title}"),
        "wikidata_url": (f"https://www.wikidata.org/wiki/{qid}" if qid else None),
        "queried_at": now(),
        "sources": [{"source": f"wikipedia:{lang}", "retrieved_at": summ.get("retrieved_at"),
                     "error": summ["error"]}],
    }


@app.get("/api/collocations")
async def api_collocations(term: str, lang: str = "de"):
    """原語空間の共起（この語が原語コーパスで共に使われる語）。独語は DWDS Wortprofil。
    ベンチマークの『関連概念群』次元＝Entfremdung なら Verdinglichung/Aufhebung/
    überwinden 等が文法関係別に出る。他言語は現状データ源未整備（正直に空）。"""
    if not term.strip():
        raise HTTPException(400, "empty term")
    if lang != "de":
        return {"term": term, "lang": lang, "relations": {},
                "note": "共起データは現状ドイツ語（DWDS）のみ。他言語の権威コーパスは整備中。",
                "queried_at": now(), "sources": []}
    wp = await dwds.wortprofil(term)
    return {"term": term, "lang": lang,
            "relations": wp["data"]["relations"] if not wp["error"] else {},
            "scraped": True,
            "note": "DWDS Wortprofil（独語コーパス全体・特定著者に固有ではない）。",
            "queried_at": now(),
            "sources": [{"source": wp["source"], "retrieved_at": wp["retrieved_at"],
                         "error": wp["error"]}]}


def _general_block(gen, wiki) -> dict | None:
    """広く共有されている意味: the everyday ja.wiktionary senses (primary), plus the
    encyclopedic summary as fuller context. None only when BOTH are absent."""
    senses = (gen["data"]["senses"] if gen and not gen.get("error") and gen.get("data") else [])
    wd = wiki["data"] if (wiki and not wiki.get("error") and wiki.get("data")) else None
    if not senses and not wd:
        return None
    return {
        "senses": senses,
        "senses_url": (gen["data"]["url"] if gen and not gen.get("error") and gen.get("data") else None),
        "senses_retrieved_at": (gen.get("retrieved_at") if gen else None),
        "encyclopedic": ({"extract": wd.get("extract"), "url": wd.get("url"),
                          "lang": wd.get("lang"), "retrieved_at": wiki.get("retrieved_at")} if wd else None),
    }


def _relevant(works: list, term: str) -> list:
    """Keep only works that actually mention the query term (or a significant
    token of it) in the title or authors. OpenAlex 'search' relevance-ranks even
    when nothing matches, so an unfiltered result is often pure noise (e.g. a
    Montesquieu query returning trout-fishing papers). Dropping non-matches makes
    the panel honest: it shows real hits or nothing."""
    toks = _sig_tokens(term)
    out = []
    for w in works:
        hay = (w.get("title", "") + " " + " ".join(w.get("authors", []))).lower()
        if any(t in hay for t in toks):
            out.append(w)
    return out


async def _empty(source: str) -> dict:
    """Placeholder for source branches skipped for concept (non-person) queries:
    author/full-text-book search is only meaningful for people."""
    return {"source": source, "retrieved_at": now(), "cached": False,
            "error": None, "data": [], "skipped": True}


@app.get("/api/citations")
async def api_citations(doi: str):
    return await opencitations.citation_count(doi)


@app.get("/api/deepsearch/services")
def deepsearch_services():
    return deepsearch.SERVICES


async def _deepsearch_context(topic: str, lang: str) -> dict:
    """Resolve a term via Wikidata + SEP to ground the deep-search prompt.
    Best-effort: any errored source is simply omitted (never fabricated)."""
    ctx = {}
    try:
        wd = await wikidata.search(topic, lang)
        if not wd["error"] and wd["data"]:
            ent = await wikidata.entity(wd["data"][0]["qid"], lang)
            if not ent["error"]:
                ed = ent["data"]
                ctx["orig_labels"] = ed.get("orig_labels", {})
                ctx["description"] = ed.get("description", "")
                infl = ed.get("claims", {}).get("influenced_by", [])
                labels = await wikidata.resolve_labels(
                    [q for q in infl if str(q).startswith("Q")], lang)
                ctx["influences"] = [labels.get(q, q) for q in infl][:8]
                sep_term = ed.get("wikipedia", {}).get("en") or ed.get("orig_labels", {}).get("en") or topic
            else:
                sep_term = topic
        else:
            sep_term = topic
        sr = await sep.search(sep_term)
        if not sr["error"] and sr["data"]:
            se = await sep.entry(sr["data"][0]["slug"])
            if not se["error"]:
                ctx["sep_title"] = se["data"]["title"]
                ctx["debate"] = [re.sub(r"^\d+(\.\d+)*\.?\s*", "", s)
                                 for s in se["data"]["sections"]][:8]
                ctx["related"] = [r["title"] for r in se["data"]["related"]][:10]
    except Exception:
        pass  # grounding is a bonus; never block prompt generation on it
    return ctx


@app.post("/api/deepsearch")
async def api_deepsearch(request: Request):
    """Generate a deep-research prompt for the user to paste into another AI.
    Level 0 = deterministic template embedding the value proposition (true
    intent, term genealogy / lost distinctions, source precision, bias check).
    Level 2 = LLM refinement with the user's key."""
    b = await request.json()
    topic = (b.get("topic") or "").strip()
    if not topic:
        raise HTTPException(400, "topic required")
    lang = b.get("lang", "ja")
    service = b.get("service", "generic")

    # Ground the prompt in the system's own knowledge so it ADAPTS to the term
    # (original-language word, adjacent concepts, debate structure) instead of
    # being a fill-in-the-blank template.
    ctx = await _deepsearch_context(topic, lang)
    level0 = deepsearch.generate(topic, b.get("goal", ""), service, lang, ctx)

    result = {"service": service, "level0": level0, "level2": None}
    llm = b.get("llm") or {}
    if llm.get("provider") and llm.get("key"):
        sys_p = ("You refine deep-research prompts for humanities/philosophy. "
                 "Given a draft prompt, improve it for the target service while "
                 "PRESERVING its core demands: uncover the user's true question, "
                 "trace term genealogy and translation history and recover lost "
                 "distinctions (e.g. German Leib/Körper collapsed into one word), "
                 "demand primary-source precision with critical editions and "
                 "standard locators, check the asker's biases, and require "
                 "confidence-graded, cited output. Return ONLY the improved "
                 "prompt, in " + ("Japanese" if lang == "ja" else "English") + ".")
        try:
            out = await adapter.run(llm["provider"], llm.get("model", ""), llm["key"],
                                    "deepsearch_prompt", sys_p,
                                    f"Target service: {service}\n\nDraft:\n{level0}")
            result["level2"] = out
        except Exception as e:
            result["level2"] = {"error": f"{type(e).__name__}: {e}"}
    return result


@app.get("/api/locator")
def api_locator(author: str, work: str = "", locator: str = ""):
    """Resolve a standard philosophical locator (Stephanus/Bekker/Kant A-B) to a
    deep link + citation guidance — the reference unit philosophers actually use."""
    return {"schemes": cites.SCHEMES,
            "result": cites.resolve(author, work, locator) if author else None}


# ---------- research desk (research-process graph) ----------

@app.get("/api/projects")
def list_projects():
    conn = get_conn()
    data = rows(conn.execute(
        "SELECT p.*, (SELECT COUNT(*) FROM nodes n WHERE n.project_id=p.id) node_count"
        " FROM projects p ORDER BY updated_at DESC"))
    conn.close()
    return data


@app.post("/api/projects")
async def create_project(request: Request):
    b = await request.json()
    if not b.get("title", "").strip():
        raise HTTPException(400, "title required")
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO projects(title, description, question, created_at, updated_at)"
        " VALUES(?,?,?,?,?)",
        (b["title"].strip(), b.get("description", ""), b.get("question", ""), now(), now()))
    pid = cur.lastrowid
    if b.get("question", "").strip():
        conn.execute(
            "INSERT INTO nodes(project_id, type, title, origin, created_at, updated_at)"
            " VALUES(?,?,?,?,?,?)",
            (pid, "question", b["question"].strip(), "human", now(), now()))
    conn.commit()
    conn.close()
    return {"id": pid}


@app.delete("/api/projects/{pid}")
def delete_project(pid: int):
    conn = get_conn()
    conn.execute("DELETE FROM projects WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return {"ok": True}


def _load_arguments(conn, pid: int) -> list:
    """Load a project's reconstructed arguments (E1-E5), each with its ordered
    premises (P1..Pn). Shared by the graph endpoint and the exporters."""
    args = rows(conn.execute(
        "SELECT * FROM arguments WHERE project_id=? ORDER BY id", (pid,)))
    by_arg = {a["id"]: a for a in args}
    for a in args:
        a["premises"] = []
    for pr in rows(conn.execute(
            "SELECT ap.* FROM argument_premises ap"
            " JOIN arguments a ON ap.argument_id=a.id"
            " WHERE a.project_id=? ORDER BY ap.argument_id, ap.seq, ap.id", (pid,))):
        by_arg[pr["argument_id"]]["premises"].append(pr)
    return args


@app.get("/api/projects/{pid}/graph")
def project_graph(pid: int):
    conn = get_conn()
    p = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not p:
        conn.close()
        raise HTTPException(404)
    nodes = rows(conn.execute("SELECT * FROM nodes WHERE project_id=?", (pid,)))
    edges = rows(conn.execute("SELECT * FROM edges WHERE project_id=?", (pid,)))
    prov = rows(conn.execute(
        "SELECT pr.* FROM provenance pr JOIN nodes n ON pr.node_id=n.id"
        " WHERE n.project_id=?", (pid,)))
    args = _load_arguments(conn, pid)
    conn.close()
    return {"project": dict(p), "nodes": nodes, "edges": edges,
            "provenance": prov, "arguments": args}


@app.post("/api/projects/{pid}/nodes")
async def create_node(pid: int, request: Request):
    b = await request.json()
    if b.get("type") not in db.NODE_TYPES:
        raise HTTPException(400, f"type must be one of {db.NODE_TYPES}")
    if not b.get("title", "").strip():
        raise HTTPException(400, "title required")
    conf = b.get("confidence", "unverified")
    origin = b.get("origin", "human")
    if conf not in db.CONFIDENCE or origin not in db.ORIGINS:
        raise HTTPException(400, "bad confidence/origin")
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO nodes(project_id, type, title, body, confidence, origin,"
        " status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (pid, b["type"], b["title"].strip(), b.get("body", ""), conf, origin,
         b.get("status", "open"), now(), now()))
    nid = cur.lastrowid
    for pv in b.get("provenance", []):
        conn.execute(
            "INSERT INTO provenance(node_id, source_name, source_url, retrieved_at,"
            " quote, note, locator) VALUES(?,?,?,?,?,?,?)",
            (nid, pv.get("source_name", ""), pv.get("source_url", ""),
             pv.get("retrieved_at", now()), pv.get("quote", ""), pv.get("note", ""),
             pv.get("locator", "")))
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), pid))
    conn.commit()
    conn.close()
    return {"id": nid}


@app.patch("/api/nodes/{nid}")
async def update_node(nid: int, request: Request):
    b = await request.json()
    fields, vals = [], []
    for k in ("title", "body", "confidence", "origin", "status", "type"):
        if k in b:
            fields.append(f"{k}=?")
            vals.append(b[k])
    if not fields:
        raise HTTPException(400, "nothing to update")
    vals += [now(), nid]
    conn = get_conn()
    conn.execute(f"UPDATE nodes SET {', '.join(fields)}, updated_at=? WHERE id=?", vals)
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/nodes/{nid}")
def delete_node(nid: int):
    conn = get_conn()
    conn.execute("DELETE FROM nodes WHERE id=?", (nid,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/projects/{pid}/edges")
async def create_edge(pid: int, request: Request):
    b = await request.json()
    if b.get("rel") not in db.RELATIONS:
        raise HTTPException(400, f"rel must be one of {db.RELATIONS}")
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO edges(project_id, src, dst, rel, created_at) VALUES(?,?,?,?,?)",
        (pid, int(b["src"]), int(b["dst"]), b["rel"], now()))
    conn.commit()
    eid = cur.lastrowid
    conn.close()
    return {"id": eid}


@app.delete("/api/edges/{eid}")
def delete_edge(eid: int):
    conn = get_conn()
    conn.execute("DELETE FROM edges WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/nodes/{nid}/provenance")
async def add_provenance(nid: int, request: Request):
    b = await request.json()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO provenance(node_id, source_name, source_url, retrieved_at,"
        " quote, note, locator) VALUES(?,?,?,?,?,?,?)",
        (nid, b.get("source_name", ""), b.get("source_url", ""),
         b.get("retrieved_at", now()), b.get("quote", ""), b.get("note", ""),
         b.get("locator", "")))
    conn.commit()
    pvid = cur.lastrowid
    conn.close()
    return {"id": pvid}


# ---------- argument reconstruction (E1-E5: P1..C, hidden premises, voice,
#            per-premise locator, validity ≠ soundness) ----------

def _argument_or_404(conn, aid: int):
    a = conn.execute("SELECT * FROM arguments WHERE id=?", (aid,)).fetchone()
    if not a:
        conn.close()
        raise HTTPException(404, "unknown argument id")
    return a


@app.get("/api/projects/{pid}/arguments")
def list_arguments(pid: int):
    conn = get_conn()
    data = _load_arguments(conn, pid)
    conn.close()
    return data


@app.post("/api/projects/{pid}/arguments")
async def create_argument(pid: int, request: Request):
    b = await request.json()
    if not b.get("title", "").strip():
        raise HTTPException(400, "title required")
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO arguments(project_id, title, conclusion, conclusion_node_id,"
        " note, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
        (pid, b["title"].strip(), b.get("conclusion", ""),
         b.get("conclusion_node_id"), b.get("note", ""), now(), now()))
    aid = cur.lastrowid
    conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), pid))
    conn.commit()
    conn.close()
    return {"id": aid}


@app.get("/api/arguments/{aid}")
def get_argument(aid: int):
    conn = get_conn()
    a = dict(_argument_or_404(conn, aid))
    a["premises"] = rows(conn.execute(
        "SELECT * FROM argument_premises WHERE argument_id=? ORDER BY seq, id", (aid,)))
    conn.close()
    return a


@app.patch("/api/arguments/{aid}")
async def update_argument(aid: int, request: Request):
    b = await request.json()
    if "validity" in b and b["validity"] not in db.VALIDITY:
        raise HTTPException(400, f"validity must be one of {db.VALIDITY}")
    if "soundness" in b and b["soundness"] not in db.SOUNDNESS:
        raise HTTPException(400, f"soundness must be one of {db.SOUNDNESS}")
    fields, vals = [], []
    for k in ("title", "conclusion", "conclusion_node_id", "note",
              "validity", "soundness"):
        if k in b:
            fields.append(f"{k}=?")
            vals.append(b[k])
    if not fields:
        raise HTTPException(400, "nothing to update")
    vals += [now(), aid]
    conn = get_conn()
    _argument_or_404(conn, aid)
    conn.execute(f"UPDATE arguments SET {', '.join(fields)}, updated_at=? WHERE id=?",
                 vals)
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/arguments/{aid}")
def delete_argument(aid: int):
    conn = get_conn()
    conn.execute("DELETE FROM arguments WHERE id=?", (aid,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/arguments/{aid}/premises")
async def add_premise(aid: int, request: Request):
    b = await request.json()
    voice = b.get("voice", "author")
    if voice not in db.VOICES:
        raise HTTPException(400, f"voice must be one of {db.VOICES}")
    conn = get_conn()
    _argument_or_404(conn, aid)
    seq = conn.execute(
        "SELECT COALESCE(MAX(seq),0)+1 FROM argument_premises WHERE argument_id=?",
        (aid,)).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO argument_premises(argument_id, seq, text, hidden, voice,"
        " node_id, locator, source_name, source_url, quote, retrieved_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (aid, seq, b.get("text", ""), 1 if b.get("hidden") else 0, voice,
         b.get("node_id"), b.get("locator", ""), b.get("source_name", ""),
         b.get("source_url", ""), b.get("quote", ""),
         b.get("retrieved_at") or now()))
    conn.execute("UPDATE arguments SET updated_at=? WHERE id=?", (now(), aid))
    prid = cur.lastrowid
    conn.commit()
    conn.close()
    return {"id": prid, "seq": seq}


@app.patch("/api/premises/{prid}")
async def update_premise(prid: int, request: Request):
    b = await request.json()
    if "voice" in b and b["voice"] not in db.VOICES:
        raise HTTPException(400, f"voice must be one of {db.VOICES}")
    fields, vals = [], []
    for k in ("text", "voice", "node_id", "locator", "source_name",
              "source_url", "quote", "retrieved_at"):
        if k in b:
            fields.append(f"{k}=?")
            vals.append(b[k])
    if "hidden" in b:
        fields.append("hidden=?")
        vals.append(1 if b["hidden"] else 0)
    if not fields:
        raise HTTPException(400, "nothing to update")
    vals.append(prid)
    conn = get_conn()
    pr = conn.execute("SELECT argument_id FROM argument_premises WHERE id=?",
                      (prid,)).fetchone()
    if not pr:
        conn.close()
        raise HTTPException(404, "unknown premise id")
    conn.execute(f"UPDATE argument_premises SET {', '.join(fields)} WHERE id=?", vals)
    conn.execute("UPDATE arguments SET updated_at=? WHERE id=?",
                 (now(), pr["argument_id"]))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/premises/{prid}")
def delete_premise(prid: int):
    conn = get_conn()
    conn.execute("DELETE FROM argument_premises WHERE id=?", (prid,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/arguments/{aid}/premises/reorder")
async def reorder_premises(aid: int, request: Request):
    b = await request.json()
    order = b.get("order") or []
    conn = get_conn()
    _argument_or_404(conn, aid)
    owned = {r["id"] for r in conn.execute(
        "SELECT id FROM argument_premises WHERE argument_id=?", (aid,))}
    seq = 0
    for prid in order:
        if int(prid) in owned:
            seq += 1
            conn.execute("UPDATE argument_premises SET seq=? WHERE id=?",
                         (seq, int(prid)))
    conn.execute("UPDATE arguments SET updated_at=? WHERE id=?", (now(), aid))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/arguments/{aid}/suggest_hidden")
async def suggest_hidden(aid: int, request: Request):
    """Level 2 only: ask a BYO-key LLM to name suppressed premises under the
    principle of charity. The Level 0 path for this feature is the user adding a
    premise with hidden=1 by hand, which always works keyless (axiom 5). We never
    auto-insert the suggestion — the human confirms and adds it (axiom 6)."""
    b = await request.json()
    lang = b.get("lang", "en")
    llm = b.get("llm") or {}
    if not (llm.get("provider") and llm.get("key")):
        raise HTTPException(400, "LLM key required for hidden-premise suggestion (Level 2)")
    conn = get_conn()
    a = dict(_argument_or_404(conn, aid))
    prems = rows(conn.execute(
        "SELECT * FROM argument_premises WHERE argument_id=? ORDER BY seq, id", (aid,)))
    conn.close()
    stated = "\n".join(f"P{i+1}. {p['text']}" for i, p in enumerate(prems)) or "(none stated)"
    user = f"Argument: {a['title']}\nStated premises:\n{stated}\nConclusion: {a['conclusion']}"
    sys_p = ("Reconstruct the SUPPRESSED (hidden) premises this argument needs to be "
             "valid, using the principle of charity — supply the premises that make it "
             "the strongest version, not a straw man. List each as 'Ph. <premise>'. "
             "Separate established scholarship from interpretation from speculation, and "
             "never invent textual quotations. Do NOT restate the given premises. "
             f"Answer in {'Japanese' if lang == 'ja' else 'English'}.")
    try:
        out = await adapter.run(llm["provider"], llm.get("model", ""), llm["key"],
                                "hidden_premise", sys_p, user, a["project_id"])
    except Exception as e:
        return {"level2": {"error": f"{type(e).__name__}: {e}"}}
    return {"level2": out, "notice": "unverified"}


# ---------- export (axiom 7: exit-ability) ----------

TYPE_ORDER = ("question", "claim", "evidence", "counterclaim", "interpretation",
              "uncertainty", "decision", "source", "note")


@app.get("/api/projects/{pid}/export.md", response_class=PlainTextResponse)
def export_md(pid: int):
    g = project_graph(pid)
    p, nodes, edges = g["project"], g["nodes"], g["edges"]
    prov_by_node = {}
    for pv in g["provenance"]:
        prov_by_node.setdefault(pv["node_id"], []).append(pv)
    titles = {n["id"]: n["title"] for n in nodes}
    lines = [f"# {p['title']}", "",
             f"> Exported from Dialexis at {now()} — research-process graph,",
             "> confidence-classified, with provenance. (CC-BY-4.0 unless noted)",
             ""]
    if p["question"]:
        lines += [f"**Initial question:** {p['question']}", ""]
    if p["description"]:
        lines += [p["description"], ""]
    for ntype in TYPE_ORDER:
        group = [n for n in nodes if n["type"] == ntype]
        if not group:
            continue
        lines.append(f"## {ntype.capitalize()}s")
        for n in group:
            lines.append(f"### {n['title']}")
            lines.append(f"- confidence: **{n['confidence']}** | origin: {n['origin']}"
                         f" | status: {n['status']} | updated: {n['updated_at']}")
            if n["body"]:
                lines += ["", n["body"]]
            for pv in prov_by_node.get(n["id"], []):
                src = pv["source_name"] or pv["source_url"]
                loc = f" @ {pv['locator']}" if pv.get("locator") else ""
                lines.append(f"- source: {src} ({pv['source_url']}){loc}"
                             f" retrieved {pv['retrieved_at']}"
                             + (f" — “{pv['quote']}”" if pv["quote"] else ""))
            outgoing = [e for e in edges if e["src"] == n["id"]]
            for e in outgoing:
                lines.append(f"- → *{e['rel']}* → {titles.get(e['dst'], e['dst'])}")
            lines.append("")
    for a in g["arguments"]:
        lines.append("## 論証再構成 / Argument reconstruction")
        lines.append(f"### {a['title']}")
        lines.append(f"- validity: **{a['validity']}** | soundness: **{a['soundness']}**")
        if a["note"]:
            lines += ["", a["note"]]
        for i, pr in enumerate(a["premises"]):
            tags = " [hidden]" if pr["hidden"] else ""
            tags += f" (voice: {pr['voice']})"
            loc = f" — {pr['locator']}" if pr["locator"] else ""
            src = ""
            if pr["source_name"] or pr["source_url"]:
                src = f" [{pr['source_name'] or pr['source_url']}]({pr['source_url']})"
            quote = f" “{pr['quote']}”" if pr["quote"] else ""
            lines.append(f"P{i + 1}. {pr['text']}{tags}{loc}{src}{quote}")
        lines.append(f"∴ C. {a['conclusion']}")
        lines.append("")
    return "\n".join(lines)


@app.get("/api/projects/{pid}/export.jsonld")
def export_jsonld(pid: int):
    g = project_graph(pid)
    ctx = {
        "@vocab": "https://dialexis.org/vocab#",
        "prov": "http://www.w3.org/ns/prov#",
        "title": "http://purl.org/dc/terms/title",
        "created": "http://purl.org/dc/terms/created",
        "source_url": {"@id": "prov:hadPrimarySource", "@type": "@id"},
        "retrieved_at": "prov:generatedAtTime",
        "hasPremise": {"@id": "https://dialexis.org/vocab#hasPremise",
                       "@container": "@list"},
    }
    prov_by_node = {}
    for pv in g["provenance"]:
        prov_by_node.setdefault(pv["node_id"], []).append({
            "@type": "prov:Entity", "label": pv["source_name"],
            "source_url": pv["source_url"], "retrieved_at": pv["retrieved_at"],
            "quote": pv["quote"]})
    graph = []
    for n in g["nodes"]:
        graph.append({
            "@id": f"node:{n['id']}", "@type": n["type"].capitalize(),
            "title": n["title"], "body": n["body"],
            "confidence": n["confidence"], "origin": n["origin"],
            "status": n["status"], "created": n["created_at"],
            "prov:wasDerivedFrom": prov_by_node.get(n["id"], [])})
    for e in g["edges"]:
        graph.append({"@id": f"edge:{e['id']}", "@type": "Relation",
                      "rel": e["rel"], "from": f"node:{e['src']}",
                      "to": f"node:{e['dst']}"})
    for a in g["arguments"]:
        premises = []
        for i, pr in enumerate(a["premises"]):
            entry = {"@id": f"premise:{pr['id']}", "@type": "Premise",
                     "seq": i + 1, "text": pr["text"], "hidden": bool(pr["hidden"]),
                     "voice": pr["voice"], "locator": pr["locator"],
                     "source_url": pr["source_url"], "retrieved_at": pr["retrieved_at"]}
            if pr["node_id"]:
                entry["premiseNode"] = f"node:{pr['node_id']}"
            premises.append(entry)
        arg = {"@id": f"argument:{a['id']}", "@type": "Argument",
               "title": a["title"], "conclusion": a["conclusion"],
               "validity": a["validity"], "soundness": a["soundness"],
               "hasPremise": premises}
        if a["conclusion_node_id"]:
            arg["conclusionNode"] = f"node:{a['conclusion_node_id']}"
        graph.append(arg)
    return JSONResponse({"@context": ctx, "project": g["project"]["title"],
                         "exported_at": now(), "@graph": graph},
                        media_type="application/ld+json")


def _collect_refs(g: dict) -> list:
    """Gather a project's cited sources for bibliography export, deduped by URL
    (or name+title when no URL). Sources come from node provenance, source-type
    nodes, and argument-premise sources. No schema change: reads existing rows."""
    seen = {}

    def add(title, url, urldate, quote, locator, source_name):
        title = (title or source_name or url or "").strip()
        url = (url or "").strip()
        if not title and not url:
            return
        key = url or f"name:{(source_name or '').strip()}|{title}"
        if key in seen:
            return
        note = "; ".join(x for x in [(locator or "").strip(),
                                     f'"{quote.strip()}"' if quote and quote.strip() else ""] if x)
        seen[key] = {"title": title, "url": url,
                     "urldate": (urldate or "").strip()[:10],
                     "note": note, "source_name": (source_name or "").strip()}

    prov_by_node = {}
    for pv in g["provenance"]:
        prov_by_node.setdefault(pv["node_id"], []).append(pv)
    for n in g["nodes"]:
        provs = prov_by_node.get(n["id"], [])
        for pv in provs:
            title = pv["source_name"] or (n["title"] if n["type"] == "source" else "")
            add(title, pv["source_url"], pv["retrieved_at"],
                pv.get("quote", ""), pv.get("locator", ""), pv["source_name"])
        if n["type"] == "source" and not provs:
            add(n["title"], "", n.get("updated_at", ""), "", "", "")
    for a in g["arguments"]:
        for pr in a["premises"]:
            if pr.get("source_name") or pr.get("source_url"):
                add(pr.get("source_name", ""), pr.get("source_url", ""),
                    pr.get("retrieved_at", ""), pr.get("quote", ""),
                    pr.get("locator", ""), pr.get("source_name", ""))
    return list(seen.values())


@app.get("/api/projects/{pid}/export.bib", response_class=PlainTextResponse)
def export_bib(pid: int):
    g = project_graph(pid)
    return bibliography.to_bibtex(_collect_refs(g), project=g["project"]["title"])


@app.get("/api/projects/{pid}/export.csl.json")
def export_csl(pid: int):
    g = project_graph(pid)
    return JSONResponse(bibliography.to_csl(_collect_refs(g)),
                        media_type="application/json")


# ---------- counterargument engine (Level 0 always; Level 2 with key) ----------

@app.post("/api/counter")
async def api_counter(request: Request):
    b = await request.json()
    claim = b.get("claim", "").strip()
    lang = b.get("lang", "en")
    if lang not in ("ja", "en"):
        lang = "en"
    if not claim:
        raise HTTPException(400, "claim required")

    level0 = [{"perspective": p["label"].get(lang, p["label"]["en"]),
               "id": p["id"],
               "questions": p["questions"].get(lang, p["questions"]["en"])}
              for p in CHECKLISTS["perspectives"]]
    lit = await openalex.search_works(claim, limit=6)

    result = {"claim": claim, "level0": level0,
              "opposing_literature_search": lit, "level2": None}

    llm = b.get("llm") or {}
    if llm.get("provider") and llm.get("key"):
        persp = ", ".join(p["id"] for p in CHECKLISTS["perspectives"])
        sys_p = ("Generate rigorous counterarguments to the user's claim from these "
                 f"perspectives: {persp}. For each: state the strongest objection, "
                 "what evidence would settle it, and which primary sources to check. "
                 f"Answer in {'Japanese' if lang == 'ja' else 'English'}.")
        try:
            result["level2"] = await adapter.run(
                llm["provider"], llm.get("model", ""), llm["key"],
                "counterargument", sys_p, claim, b.get("project_id"))
        except Exception as e:
            result["level2"] = {"error": f"{type(e).__name__}: {e}"}
    return result


# ---------- reading levels (Level 0 seed; Level 2 with key) ----------

@app.get("/api/levels")
def api_levels(concept: str = ""):
    if concept:
        c = GLOSSARY["concepts"].get(concept)
        if not c:
            raise HTTPException(404, "not in seed glossary; use LLM elevation")
        return {"concept": concept, "origin": "human", "levels": c["levels"],
                "en_label": c.get("en_label", "")}
    return {"concepts": list(GLOSSARY["concepts"].keys()),
            "levels": GLOSSARY["levels"]}


@app.post("/api/levels/llm")
async def api_levels_llm(request: Request):
    b = await request.json()
    concept, level, lang = b.get("concept", ""), b.get("level", "general"), b.get("lang", "en")
    llm = b.get("llm") or {}
    if not (llm.get("provider") and llm.get("key")):
        raise HTTPException(400, "LLM key required for non-seeded concepts (Level 2)")
    sys_p = (f"Explain the philosophical concept at exactly this audience level: {level}. "
             "Be accurate, name key thinkers/works only when standard, flag "
             "contested points, and keep register appropriate to the level. "
             f"Answer in {'Japanese' if lang == 'ja' else 'English'}.")
    return await adapter.run(llm["provider"], llm.get("model", ""), llm["key"],
                             f"reading_level:{level}", sys_p, concept)


# ---------- watches (dynamic freshness; harvester runs the same code via cron) ----------

@app.get("/api/watches")
def list_watches():
    conn = get_conn()
    data = rows(conn.execute(
        "SELECT w.*, (SELECT COUNT(*) FROM watch_hits h WHERE h.watch_id=w.id AND h.seen=0)"
        " unseen FROM watches w ORDER BY id DESC"))
    conn.close()
    return data


@app.post("/api/watches")
async def create_watch(request: Request):
    b = await request.json()
    label = b.get("label", "").strip()
    if not label:
        raise HTTPException(400, "label required")
    openalex_id = b.get("openalex_id", "")
    kind = b.get("kind", "query")
    if kind == "author" and not openalex_id:
        found = await openalex.search_authors(label, limit=1)
        if not found["error"] and found["data"]:  # neg-ok: 変数名found・コード
            openalex_id = found["data"][0]["id"]
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO watches(label, kind, openalex_id, query, created_at)"
        " VALUES(?,?,?,?,?)",
        (label, kind, openalex_id, b.get("query", label), now()))
    conn.commit()
    wid = cur.lastrowid
    conn.close()
    return {"id": wid, "openalex_id": openalex_id}


@app.delete("/api/watches/{wid}")
def delete_watch(wid: int):
    conn = get_conn()
    conn.execute("DELETE FROM watches WHERE id=?", (wid,))
    conn.commit()
    conn.close()
    return {"ok": True}


async def check_watch(watch: dict) -> dict:
    """Shared by the web UI and harvester.py (cron). Returns summary."""
    since = (watch.get("last_checked") or watch.get("created_at") or "2020-01-01")[:10]
    new_items = []
    if watch["kind"] == "author" and watch["openalex_id"]:
        res = await openalex.works_by_author(watch["openalex_id"], from_date=since)
    else:
        res = await openalex.works_search_since(watch["query"] or watch["label"], since)
    cr = await crossref.search_works(watch["query"] or watch["label"],
                                     limit=10, from_date=since)
    conn = get_conn()
    for src_res, src in ((res, "openalex"), (cr, "crossref")):
        if src_res["error"]:
            continue
        for w in src_res["data"]:
            ext = w.get("id") or w.get("doi") or w.get("url") or w["title"]
            cur = conn.execute(
                "INSERT OR IGNORE INTO watch_hits(watch_id, external_id, title, year,"
                " url, source, found_at) VALUES(?,?,?,?,?,?,?)",
                (watch["id"], ext, w["title"], str(w.get("year") or ""),
                 w.get("url", ""), src, now()))
            if cur.rowcount:
                new_items.append(w["title"])
    conn.execute("UPDATE watches SET last_checked=? WHERE id=?", (now(), watch["id"]))
    conn.commit()
    conn.close()
    return {"watch_id": watch["id"], "label": watch["label"],
            "checked_at": now(), "new_count": len(new_items),
            "errors": [r["error"] for r in (res, cr) if r["error"]]}


@app.post("/api/watches/{wid}/run")
async def run_watch(wid: int):
    conn = get_conn()
    w = conn.execute("SELECT * FROM watches WHERE id=?", (wid,)).fetchone()
    conn.close()
    if not w:
        raise HTTPException(404)
    return await check_watch(dict(w))


@app.get("/api/watches/{wid}/hits")
def watch_hits(wid: int):
    conn = get_conn()
    data = rows(conn.execute(
        "SELECT * FROM watch_hits WHERE watch_id=? ORDER BY found_at DESC LIMIT 100", (wid,)))
    conn.execute("UPDATE watch_hits SET seen=1 WHERE watch_id=?", (wid,))
    conn.commit()
    conn.close()
    return data


# ---------- AI transparency ledger (axiom 6) ----------

@app.get("/api/ledger")
def ai_ledger():
    conn = get_conn()
    data = rows(conn.execute("SELECT * FROM ai_ledger ORDER BY id DESC LIMIT 200"))
    conn.close()
    return data
