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
from .connectors import wikidata, openalex, crossref, wikipedia, gutendex, opencitations, sep
from . import citations as cites
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

@app.get("/", response_class=HTMLResponse)
def page_home(request: Request):
    return render(request, "index.html")


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
            title = wp_titles.get(lang) or wp_titles.get("en")
            wp_lang = lang if lang in wp_titles else "en"
            all_qids = [v for vs in ed["claims"].values()
                        for v in vs if str(v).startswith("Q")]

    # Everything below depends only on the resolved entity, so run the branches
    # concurrently instead of in one long sequential chain (cold-load latency:
    # ~6 serial round-trips + 2 large SEP fetches → one parallel wave).
    async def sep_chain():
        r = await sep.search(sep_term)
        e = await sep.entry(r["data"][0]["slug"]) if (not r["error"] and r["data"]) else None
        return r, e

    async def wiki_summary():
        return await wikipedia.summary(title, wp_lang) if (entity and title) else None

    async def labels_resolve():
        return await wikidata.resolve_labels(all_qids, lang) if all_qids else {}

    (sep_pair, wiki, labels, gutenberg, oa_works) = await asyncio.gather(
        sep_chain(), wiki_summary(), labels_resolve(),
        gutendex.search(scholar_q) if is_person else _empty("gutendex"),
        openalex.search_works(scholar_q))
    sep_result, sep_entry = sep_pair

    if entity and not entity["error"]:
        ed = entity["data"]
        ed["claims"] = {k: [labels.get(v, v) for v in vs] for k, vs in ed["claims"].items()}
        ed["wikisource_urls"] = {lg: wikipedia.wikisource_url(t, lg)
                                 for lg, t in ed["wikisource"].items()}
    if not oa_works["error"] and oa_works["data"]:
        oa_works["data"] = _relevant(oa_works["data"], english_term if is_person else q)

    return {"query": q, "resolved_term": scholar_q, "lang": lang, "queried_at": now(),
            "sep_search": sep_result, "sep_entry": sep_entry,
            "wikidata_search": wd, "entity": entity, "wikipedia": wiki,
            "primary_texts": gutenberg, "recent_scholarship": oa_works}


def _relevant(works: list, term: str) -> list:
    """Keep only works that actually mention the query term (or a significant
    token of it) in the title or authors. OpenAlex 'search' relevance-ranks even
    when nothing matches, so an unfiltered result is often pure noise (e.g. a
    Montesquieu query returning trout-fishing papers). Dropping non-matches makes
    the panel honest: it shows real hits or nothing."""
    toks = [t for t in re.split(r"\W+", term.lower()) if len(t) >= 4]
    if not toks:
        toks = [term.lower()]
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
    conn.close()
    return {"project": dict(p), "nodes": nodes, "edges": edges, "provenance": prov}


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
            " quote, note) VALUES(?,?,?,?,?,?)",
            (nid, pv.get("source_name", ""), pv.get("source_url", ""),
             pv.get("retrieved_at", now()), pv.get("quote", ""), pv.get("note", "")))
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
        "INSERT INTO provenance(node_id, source_name, source_url, retrieved_at, quote, note)"
        " VALUES(?,?,?,?,?,?)",
        (nid, b.get("source_name", ""), b.get("source_url", ""),
         b.get("retrieved_at", now()), b.get("quote", ""), b.get("note", "")))
    conn.commit()
    pvid = cur.lastrowid
    conn.close()
    return {"id": pvid}


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
                lines.append(f"- source: {src} ({pv['source_url']})"
                             f" retrieved {pv['retrieved_at']}"
                             + (f" — “{pv['quote']}”" if pv["quote"] else ""))
            outgoing = [e for e in edges if e["src"] == n["id"]]
            for e in outgoing:
                lines.append(f"- → *{e['rel']}* → {titles.get(e['dst'], e['dst'])}")
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
    return JSONResponse({"@context": ctx, "project": g["project"]["title"],
                         "exported_at": now(), "@graph": graph},
                        media_type="application/ld+json")


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
