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
import os
import re

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .db import get_conn, init_db, now, rows
from .connectors import wikidata, openalex, crossref, wikipedia, gutendex, opencitations, sep, ndl, cinii
from . import citations as cites
from . import deepsearch
from . import bibliography
from .llm import adapter

APP_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Dialexis", version="0.1.0")
app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))

I18N = {}
for _lang in ("ja", "en"):
    with open(os.path.join(APP_DIR, "i18n", f"{_lang}.json"), encoding="utf-8") as f:
        I18N[_lang] = json.load(f)

with open(os.path.join(APP_DIR, "data", "counter_checklists.json"), encoding="utf-8") as f:
    CHECKLISTS = json.load(f)
with open(os.path.join(APP_DIR, "data", "glossary_seed.json"), encoding="utf-8") as f:
    GLOSSARY = json.load(f)


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
        context={"t": t, "lang": lang, "path": request.url.path, **ctx})
    if request.query_params.get("lang"):
        resp.set_cookie("lang", lang, max_age=86400 * 365)
    return resp


# ---------- pages ----------

# Question-first entry (PoC A): a curious person who does not yet know any
# philosopher's name still needs a door. Each door is a human-language question
# (the novice's own voice) that runs the existing /explore on a concept SEED.
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


@app.get("/api/explore")
async def api_explore(q: str, lang: str = "en"):
    if not q.strip():
        raise HTTPException(400, "empty query")

    # Step 1: resolve the query to a concept/person via Wikidata FIRST, so the
    # scholarly search can be anchored on the resolved English term rather than
    # a raw (often ambiguous) CJK word. This, plus OpenAlex's humanities lens,
    # is what keeps a query like 存在 in philosophy instead of chemistry.
    wd = await wikidata.search(q, lang)
    entity = None
    wiki = None
    scholar_q = q          # term handed to scholarly APIs
    sep_term = q           # term handed to SEP (English-only)
    is_person = False
    author_ja = ""
    title, wp_lang, all_qids = None, "en", []  # safe defaults if no entity
    if not wd["error"] and wd["data"]:
        entity = await wikidata.entity(wd["data"][0]["qid"], lang)
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
            "sep_search": sep_result, "sep_entry": sep_entry,
            "wikidata_search": wd, "entity": entity, "wikipedia": wiki,
            "primary_texts": gutenberg, "japanese_translations": ja_translations,
            "japanese_scholarship": ndl_orient, "cinii": cinii_res,
            "recent_scholarship": oa_works}


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
    Best-effort: any failed source is simply omitted (never fabricated)."""
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
        raise HTTPException(404, "argument not found")
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
        raise HTTPException(404, "premise not found")
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
        if not found["error"] and found["data"]:
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
