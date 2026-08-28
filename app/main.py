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
import copy
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import unicodedata
import urllib.parse

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
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


# ---------------------------------------------------------------------------
# Public-instance boundary
# ---------------------------------------------------------------------------
# Dialexis intentionally has a keyless Level-0 surface.  That does not mean
# that one anonymous browser may read or mutate another browser's research
# assets.  Until a full account provider is introduced, a signed pseudonymous
# workspace cookie supplies the minimum isolation boundary.  It is not an
# identity system: deployment operators MUST set DIALEXIS_SESSION_SECRET and
# MUST use HTTPS at the reverse proxy before treating this as a public service.
WORKSPACE_COOKIE = "dialexis_workspace"
WORKSPACE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365
_PUBLIC_INSTANCE = str(os.environ.get("DIALEXIS_PUBLIC_INSTANCE", "")).lower() in {
    "1", "true", "yes", "on"
}
_LOCAL_WORKSPACE = os.environ.get("DIALEXIS_LEGACY_WORKSPACE_ID", "single-user-local")
_SESSION_SECRET_CONFIGURED = bool(os.environ.get("DIALEXIS_SESSION_SECRET"))
_SESSION_SECRET = os.environ.get("DIALEXIS_SESSION_SECRET", "")
if _PUBLIC_INSTANCE and not _SESSION_SECRET_CONFIGURED:
    raise RuntimeError(
        "DIALEXIS_PUBLIC_INSTANCE=1 requires DIALEXIS_SESSION_SECRET; "
        "configure a persistent secret before exposing Dialexis publicly")
if _PUBLIC_INSTANCE and len(_SESSION_SECRET) < 32:
    raise RuntimeError(
        "DIALEXIS_SESSION_SECRET must be at least 32 characters in public mode")
if not _SESSION_SECRET:
    # Local development/tests remain deterministic within one process.  A
    # restart intentionally rotates anonymous workspaces when the operator has
    # not configured a persistent secret, preventing a false sense of durable
    # identity on an unsafe staging process.
    _SESSION_SECRET = secrets.token_hex(32)
_CSP_REPORT_ONLY = (
    "default-src 'self'; base-uri 'self'; object-src 'none'; "
    "frame-ancestors 'self'; form-action 'self'; "
    "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; font-src 'self' data:; "
    "connect-src 'self';"
)


def _workspace_signature(payload: str) -> str:
    return hmac.new(_SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _new_workspace_token() -> tuple[str, str]:
    payload = secrets.token_urlsafe(24)
    return payload, f"{payload}.{_workspace_signature(payload)}"


def _workspace_from_cookie(raw: str | None) -> tuple[str, bool]:
    if not raw or "." not in raw:
        payload, _ = _new_workspace_token()
        return payload, False
    payload, signature = raw.rsplit(".", 1)
    if not payload or not hmac.compare_digest(signature, _workspace_signature(payload)):
        payload, _ = _new_workspace_token()
        return payload, False
    return payload, True


def workspace_id(request: Request) -> str:
    """Return the request's signed anonymous workspace identifier."""
    if not _PUBLIC_INSTANCE:
        request.state.workspace_id = _LOCAL_WORKSPACE
        return _LOCAL_WORKSPACE
    value = getattr(request.state, "workspace_id", "")
    if value:
        return value
    value, _ = _workspace_from_cookie(request.cookies.get(WORKSPACE_COOKIE))
    request.state.workspace_id = value
    return value


def _expose_workspace_record(row, wid: str = "", can_edit: bool = True) -> dict:
    """Return a browser-safe record without the internal owner token.

    ``workspace_id`` is an authorization key, not research metadata.  The UI
    receives only the derived capability flag; the server remains the final
    authority for every write operation.
    """
    data = dict(row)
    owner = data.pop("workspace_id", None)
    if can_edit and owner is not None:
        data["can_edit"] = bool(wid and owner == wid)
    return data


def _request_is_https(request: Request) -> bool:
    """Recognize HTTPS both at Uvicorn and behind the documented proxy."""
    if request.url.scheme == "https":
        return True
    # The reverse proxy overwrites this header with its own scheme.  If an
    # untrusted direct client supplies it, the worst outcome is a Secure
    # cookie that is not sent over HTTP (a fresh workspace), not plaintext
    # credential transport.
    return request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower() == "https"


def _append_vary(response, value: str) -> None:
    current = [part.strip() for part in response.headers.get("Vary", "").split(",") if part.strip()]
    if value.lower() not in {part.lower() for part in current}:
        current.append(value)
        response.headers["Vary"] = ", ".join(current)


@app.middleware("http")
async def public_response_headers(request: Request, call_next):
    """Small, transport-neutral baseline for the public instance.

    TLS/HSTS belongs at the reverse proxy and is deliberately not asserted
    here: the current IP-only staging endpoint is still HTTP. These headers
    are safe on both the staging endpoint and the eventual HTTPS endpoint.
    """
    if _PUBLIC_INSTANCE:
        wid, valid_cookie = _workspace_from_cookie(request.cookies.get(WORKSPACE_COOKIE))
        new_token = None
        if not valid_cookie:
            wid, new_token = _new_workspace_token()
    else:
        wid, valid_cookie, new_token = _LOCAL_WORKSPACE, True, None
    request.state.workspace_id = wid
    response = await call_next(request)
    if new_token:
        response.set_cookie(WORKSPACE_COOKIE, new_token,
                            max_age=WORKSPACE_COOKIE_MAX_AGE,
                            httponly=True, samesite="lax",
                            secure=_request_is_https(request),
                            path="/")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy-Report-Only", _CSP_REPORT_ONLY)
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault(
        "X-Dialexis-Workspace-Mode",
        "anonymous-signed-cookie" if _PUBLIC_INSTANCE else "single-user-local")
    # Public pages can contain workspace-specific visibility and capability
    # flags.  Prevent a reverse proxy or browser cache from replaying one
    # anonymous workspace's HTML to another; static assets remain cacheable.
    if _PUBLIC_INSTANCE and not request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-store")
        _append_vary(response, "Cookie")
    elif request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


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
with open(os.path.join(APP_DIR, "data", "translation_history_seed.json"), encoding="utf-8") as f:
    TRANSLATION_HISTORY = json.load(f)
with open(os.path.join(APP_DIR, "data", "person_profiles.json"), encoding="utf-8") as f:
    PERSON_PROFILES = json.load(f)
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
                 "asset_v": ASSET_V, "site_origin": str(request.base_url).rstrip("/"), **ctx})
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
    wid = workspace_id(request)
    p = conn.execute(
        "SELECT * FROM projects WHERE id=? AND (workspace_id=? OR is_public=1)",
        (pid, wid)).fetchone()
    conn.close()
    if not p:
        raise HTTPException(404)
    return render(request, "project.html", project=_expose_workspace_record(p, wid))


@app.get("/ledger/{lid}", response_class=HTMLResponse)
def page_ledger(request: Request, lid: int):
    conn = get_conn()
    wid = workspace_id(request)
    l = conn.execute(
        "SELECT * FROM ledgers WHERE id=? AND (workspace_id=? OR is_public=1)",
        (lid, wid)).fetchone()
    conn.close()
    if not l:
        raise HTTPException(404)
    return render(request, "ledger.html", ledger=_expose_workspace_record(l, wid))


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


@app.get("/validation", response_class=HTMLResponse)
def page_validation(request: Request):
    """A public, reproducible entry point for third-party human validation."""
    return render(request, "validation.html")


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt(request: Request):
    """Keep API and mutable research surfaces out of ordinary indexing.

    The app is intentionally usable without an account, so this is a
    discoverability boundary, not an access-control boundary. Private data
    must never be entered into the shared public instance.
    """
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /desk\n"
        "Disallow: /ledger/\n"
        "Disallow: /project/\n"
        "Disallow: /settings\n"
        "Disallow: /watches\n"
        f"Sitemap: {str(request.base_url).rstrip('/')}/sitemap.xml\n"
    )


@app.get("/sitemap.xml")
def sitemap_xml(request: Request):
    """Expose only stable public entry points, never query-derived results."""
    base = str(request.base_url).rstrip("/")
    urls = ("/", "/origin", "/explore", "/validation", "/about", "/donate")
    body = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
    body += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    for path in urls:
        body += f"<url><loc>{urllib.parse.quote(base + path, safe=':/')}</loc></url>"
    body += "</urlset>"
    return Response(content=body, media_type="application/xml")


@app.get("/healthz")
def healthz(request: Request):
    conn = get_conn()
    if _PUBLIC_INSTANCE:
        n = conn.execute(
            "SELECT COUNT(*) c FROM projects WHERE workspace_id=? OR is_public=1",
            (workspace_id(request),)).fetchone()["c"]
    else:
        n = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
    conn.close()
    return {"status": "ok", "projects": n, "time": now(),
            "public_instance": _PUBLIC_INSTANCE,
            "session_secret_configured": _SESSION_SECRET_CONFIGURED,
            "workspace_mode": "anonymous-signed-cookie" if _PUBLIC_INSTANCE else "single-user-local"}


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
    if not q.strip():
        raise HTTPException(400, "empty query")
    # A person name is not a concept word.  Resolve curated identity aliases
    # before the word-origin engine so カールマルクス and Karl Marx enter the
    # same person-first surface rather than an empty/irrelevant etymology card.
    person = await _person_profile_for_query_async(q, lang)
    if person:
        return _person_origin(person, q, lang)
    await wiktionary.ensure_langnames(lang)   # 全言語コード→日本語名を用意（生コード表示の解消）
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


def _person_norm(value: str) -> str:
    """Normalize a person-name query for identity matching only.

    This deliberately removes punctuation/spacing used by Japanese and Latin
    name displays, but never changes the text shown as evidence.  A name match
    is therefore an identity/display decision, not a translation claim.
    """
    # NFKD + combining-mark removal makes Sören/Soren and accented Latin
    # spellings one identity key while the original display form remains
    # untouched in the evidence record.
    s = unicodedata.normalize("NFKD", str(value or "")).casefold()
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[\s\u3000・･.,，．:：;；'’\"“”()（）\[\]【】{}｛｝_\-‐‑‒–—]+", "", s)


def _person_profile_for_query(q: str) -> dict | None:
    """Resolve the curated person registry without treating a name as a word.

    Exact normalized aliases are preferred.  The registry is intentionally
    small and explicit: a generic fuzzy hit must not silently turn an ordinary
    concept into a person.
    """
    nq = _person_norm(q)
    if not nq:
        return None
    for profile in PERSON_PROFILES.get("profiles", []):
        for alias in profile.get("match", []):
            if nq == _person_norm(alias):
                return copy.deepcopy(profile)
    return None


_PERSON_EVIDENCE_RANK = {
    "unverified": 0, "candidate": 1, "strong": 2,
    "bibliography_confirmed": 3, "confirmed": 4,
}
_PERSON_LANG_NAMES = {
    "ja": "日本語", "en": "英語", "de": "ドイツ語", "da": "デンマーク語",
    "fr": "フランス語", "es": "スペイン語", "it": "イタリア語",
    "pt": "ポルトガル語", "nl": "オランダ語", "sv": "スウェーデン語",
    "no": "ノルウェー語", "ru": "ロシア語", "zh": "中国語", "ko": "韓国語",
    "el": "ギリシャ語", "grc": "古典ギリシャ語", "la": "ラテン語",
}


def _person_lang_name(code: str) -> str:
    return _PERSON_LANG_NAMES.get(str(code or ""), str(code or "言語未確認"))


def _person_language_summary(codes: list, names: list) -> str:
    """Keep the full language list in JSON but make the default label readable."""
    pairs = list(zip(codes or [], names or []))
    known = [name for code, name in pairs if code in _PERSON_LANG_NAMES]
    unknown = [name for code, name in pairs if code not in _PERSON_LANG_NAMES]
    visible = list(dict.fromkeys(known + unknown))[:8]
    extra = max(0, len(list(dict.fromkeys(known + unknown))) - len(visible))
    if extra:
        visible.append(f"ほか{extra}言語")
    return "・".join(visible) or "言語未確認"


def _person_profile_from_entity(q: str, entity, lang: str = "ja",
                                work_records: list | None = None,
                                relation_records: list | None = None,
                                bibliography: list | None = None,
                                summary: str = "",
                                wikipedia_url: str = "",
                                extra_sources: list | None = None,
                                primary_texts: list | None = None,
                                scholarship: list | None = None) -> dict | None:
    """Build a cautious generic person dossier from a Wikidata entity.

    It supplies identity/name/work discovery but does not invent a reception
    history.  The latter remains an explicit next verification task.
    """
    ed = entity.get("data", entity) if isinstance(entity, dict) else {}
    if not isinstance(ed, dict) or not ed.get("is_person"):
        return None
    label = str(ed.get("label") or ed.get("label_en") or q).strip()
    latin = str(ed.get("label_en") or ed.get("wikipedia", {}).get("en") or label).strip()

    # One visual record per identity spelling.  Wikidata often repeats the
    # same Latin label for en/de/fr/it; language coverage is retained on that
    # one record instead of producing a misleading stack of duplicates.
    forms, form_by_key = [], {}
    def add_form(form, language, kind, evidence="candidate"):
        form = str(form or "").strip()
        if not form:
            return
        code = str(language or "").strip()
        key = _person_norm(form) or form.casefold()
        rec = form_by_key.get(key)
        if rec is None:
            rec = {"form": form, "language": _person_lang_name(code),
                   "languages": [_person_lang_name(code)],
                   "language_codes": [code] if code else [],
                   "language_count": 1, "kind": kind, "kinds": [kind], "evidence": evidence}
            form_by_key[key] = rec
            forms.append(rec)
            return
        if code and code not in rec.setdefault("language_codes", []):
            rec["language_codes"].append(code)
        language_name = _person_lang_name(code)
        if language_name not in rec.setdefault("languages", []):
            rec["languages"].append(language_name)
        rec["language_count"] = len(rec["languages"])
        rec["language"] = _person_language_summary(rec.get("language_codes", []), rec["languages"])
        if kind not in rec.setdefault("kinds", []):
            rec["kinds"].append(kind)
        if len(rec["kinds"]) > 1:
            rec["kind"] = "／".join(rec["kinds"][:3])
        if _PERSON_EVIDENCE_RANK.get(evidence, 0) > _PERSON_EVIDENCE_RANK.get(rec.get("evidence"), 0):
            rec["evidence"] = evidence

    aliases = ed.get("aliases") or {}
    labels = ed.get("labels") or {}
    if not labels:
        labels = {**(ed.get("orig_labels") or {})}
        if label:
            labels.setdefault(lang, label)
        if latin:
            labels.setdefault("en", latin)
    relation_records = relation_records or []
    relation_by_qid = {str(x.get("qid")): x for x in relation_records
                       if isinstance(x, dict) and x.get("qid")}

    def record_labels(rec: dict | None) -> dict:
        if not isinstance(rec, dict):
            return {}
        out = dict(rec.get("labels") or {})
        if rec.get("label") and lang not in out:
            out[lang] = rec["label"]
        if rec.get("label_en") and "en" not in out:
            out["en"] = rec["label_en"]
        return out

    def qid_label(qid: str, prefer_lang: str = "ja") -> str:
        rec = relation_by_qid.get(str(qid))
        ls = record_labels(rec)
        return str(ls.get(prefer_lang) or ls.get("en") or ls.get("da")
                   or ls.get("de") or ls.get("fr") or (rec or {}).get("label") or qid)

    # Pseudonyms are a distinct authorship layer, not transliterations.  Do
    # not put them into the identity/transliteration cards.
    pseudonym_qids = [str(x) for x in (ed.get("claims", {}).get("pseudonym") or []) if str(x).startswith("Q")]
    pseudonym_names = [qid_label(x) for x in pseudonym_qids]
    pseudonym_keys = {_person_norm(x) for x in pseudonym_names if x}

    add_form(q, lang, "入力された人物名", "candidate")
    for lg, form in labels.items():
        add_form(form, lg, "Wikidataラベル", "confirmed")
    if latin:
        add_form(latin, "en", "ラテン文字表記", "confirmed" if labels.get("en") else "candidate")
    for lg, values in aliases.items():
        for form in values if isinstance(values, list) else []:
            if _person_norm(form) not in pseudonym_keys:
                add_form(form, lg, "別表記・検索別名", "candidate")
    for lg, title in (ed.get("wikipedia") or {}).items():
        if lg not in _PERSON_LANG_NAMES:
            continue
        if _person_norm(title) not in pseudonym_keys:
            add_form(title, lg, "Wikipedia記事名", "candidate")

    work_records = work_records or []
    works = []
    for rec in work_records[:12]:
        if not isinstance(rec, dict):
            continue
        ls = record_labels(rec)
        wikis = rec.get("wikipedia") or {}
        # Prefer the work's source-language title.  For a Danish author this
        # keeps the Danish title visible instead of silently using English.
        source_code = rec.get("original_language_code")
        source_priority = [source_code] if source_code else []
        source_priority += [x for x in ("da", "de", "fr", "en", "la", "grc") if x not in source_priority]
        original_title = next((ls.get(x) or wikis.get(x) for x in source_priority
                               if ls.get(x) or wikis.get(x)), None)
        if not original_title:
            original_title = rec.get("label") or rec.get("label_en") or rec.get("qid")
        jp_title = ls.get("ja") or wikis.get("ja")
        language_titles = []
        seen_titles = set()
        for code, title in list(ls.items()) + list(wikis.items()):
            title = str(title or "").strip()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            language_titles.append({"language": _person_lang_name(code), "code": code, "title": title})
        works.append({
            "qid": rec.get("qid"), "original_title": str(original_title or ""),
            "original_language": rec.get("original_language_label") or (_person_lang_name(source_code) if source_code else "要確認"),
            "original_language_code": source_code or "",
            "japanese_titles": [jp_title] if jp_title else [],
            "language_titles": language_titles,
            "year": (rec.get("claims") or {}).get("publication_date", [""])[0] or "刊年未取得",
            "role": rec.get("role") or "Wikidataの主要著作候補。原題・訳題・刊年は書誌照合が必要。",
            "evidence": rec.get("evidence", "candidate"),
            "source_ids": ["dynamic-wikidata"],
            "url": rec.get("url") or (f"https://www.wikidata.org/wiki/{rec.get('qid')}" if rec.get("qid") else ""),
            "japanese_editions": copy.deepcopy(rec.get("japanese_editions", [])),
            "edition_count": rec.get("edition_count", 0),
            "wikipedia_urls": {code: f"https://{code}.wikipedia.org/wiki/{urllib.parse.quote(title)}"
                               for code, title in wikis.items() if code in {"ja", "en", "da", "de", "fr"}},
        })

    bibliography = bibliography or []
    bib_seen, bibliography_clean = set(), []
    for item in bibliography[:24]:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        creators = item.get("creators") or item.get("authors") or []
        if isinstance(creators, str):
            creators = [creators]
        key = (_person_norm(item.get("title")), str(item.get("year") or ""),
               "|".join(str(x) for x in creators[:5]))
        if key in bib_seen:
            continue
        bib_seen.add(key)
        bibliography_clean.append({
            "title": str(item.get("title")), "creators": [str(x) for x in creators[:5]],
            "publisher": str(item.get("publisher") or ""), "year": str(item.get("year") or ""),
            "url": str(item.get("url") or ""), "edition_of": str(item.get("edition_of") or ""),
            "source": str(item.get("source") or "NDL書誌候補"),
            "type": str(item.get("type") or ""), "evidence": "bibliography_confirmed",
            "source_ids": ["dynamic-ndl"],
        })

    claims = ed.get("claims", {}) or {}
    concepts = []
    concept_seen = set()
    for claim_name, kind in (("field_of_work", "学問分野"), ("movement", "思想運動"), ("genre", "著作・表現ジャンル")):
        for qid in claims.get(claim_name, [])[:8]:
            qid = str(qid)
            rec = relation_by_qid.get(qid)
            ls = record_labels(rec)
            term = ls.get("en") or ls.get("da") or ls.get("de") or ls.get(lang) or qid_label(qid)
            ja = ls.get("ja") or qid_label(qid, "ja")
            key = _person_norm(term)
            if not key or key in concept_seen:
                continue
            concept_seen.add(key)
            jp_candidates = [ja] if ja == term else [x for x in [ja, term] if x]
            concepts.append({
                "qid": qid, "source_term": term, "language": "Wikidataラベル",
                "japanese_candidates": jp_candidates,
                "note": f"{kind}として登録された関連項目。人物名の翻訳でも、本人がその語を定義した証拠でもありません。",
                "kind": kind, "evidence": "candidate", "source_ids": ["dynamic-wikidata"],
            })

    influences = []
    reception = []
    for qid in claims.get("influenced_by", [])[:12]:
        qid = str(qid)
        who = qid_label(qid)
        if not who or who.startswith("Q") or _person_norm(who) == _person_norm(label):
            continue
        influences.append({"qid": qid, "label": who, "evidence": "candidate", "source_ids": ["dynamic-wikidata"]})
        reception.append({
            "who": who, "when": "Wikidata P737記録時点", "where": "知的系譜・影響関係の候補",
            "what": f"{label}が影響を受けた人物として登録された候補。直接引用・影響の方向・受容史は未確認。",
            "why": "人物の思想的な前史・対話相手を探索するため",
            "how": "Wikidataの影響関係プロパティを入口に本文と年代順を照合する",
            "relation": "影響源候補（本文照合前）", "evidence": "candidate",
            "source_ids": ["dynamic-wikidata"],
        })

    description = str(ed.get("description") or "").strip()
    domain_ids = list(dict.fromkeys((claims.get("field_of_work") or []) + (claims.get("movement") or [])))
    domains = [qid_label(x) for x in domain_ids[:8] if qid_label(x) and not qid_label(x).startswith("Q")]
    if not domains and description:
        domains = [description]
    born = (claims.get("born") or [""])[0]
    died = (claims.get("died") or [""])[0]
    timeline = []
    if born or died:
        timeline.append({
            "when": f"{born or '生年未取得'}–{died or '没年未取得'}", "who": label,
            "where": "人物同定・生涯", "what": description or "人物として登録された対象の生没年。",
            "relation": "人物史の基礎記録", "evidence": "confirmed", "source_ids": ["dynamic-wikidata"],
        })
    for work in works[:10]:
        timeline.append({
            "when": work.get("year") or "刊年未取得", "who": label,
            "where": work.get("japanese_titles", [""])[0] or work.get("original_title"),
            "what": work.get("role") or "主要著作候補", "relation": "著作史の入口",
            "evidence": work.get("evidence", "candidate"), "source_ids": work.get("source_ids", []),
        })

    wiki_title = ed.get("wikipedia", {}).get(lang) or ed.get("wikipedia", {}).get("en")
    if not wikipedia_url and wiki_title:
        wiki_lang = lang if ed.get("wikipedia", {}).get(lang) else "en"
        wikipedia_url = f"https://{wiki_lang}.wikipedia.org/wiki/{urllib.parse.quote(wiki_title)}"
    sources = [
        {"id": "dynamic-wikidata", "label": f"Wikidata：{label}", "url": ed.get("url") or "https://www.wikidata.org/",
         "status": "人物ID・多言語ラベル・主要著作・関係プロパティの入口。引用・影響関係の証明ではない。", "evidence": "confirmed"},
        {"id": "dynamic-wikipedia", "label": f"Wikipedia：{label}", "url": wikipedia_url,
         "status": "人物紹介・著作・章立ての探索入口。一次資料や訳語の証明には使わない。", "evidence": "candidate"},
        {"id": "dynamic-ndl", "label": f"NDLサーチ：{label}",
         "url": f"https://ndlsearch.ndl.go.jp/search?keyword={urllib.parse.quote(label)}",
         "status": "日本語版・翻訳版・受容研究の書誌を確認する入口。本文の訳語は版面照合が必要。", "evidence": "bibliography_confirmed" if bibliography_clean else "candidate"},
    ]
    for source in extra_sources or []:
        if isinstance(source, dict) and source.get("id") and not any(x.get("id") == source["id"] for x in sources):
            sources.append(copy.deepcopy(source))
    if primary_texts:
        sources.append({"id": "dynamic-gutenberg", "label": "Project Gutenberg：公開テキスト候補", "url": "https://www.gutenberg.org/", "status": "公開テキストの入口。版・本文の同一性は別途確認。", "evidence": "candidate"})
    if scholarship:
        sources.append({"id": "dynamic-openalex", "label": "OpenAlex：研究書誌候補", "url": "https://openalex.org/", "status": "研究文献の探索入口。引用・影響関係の証明ではない。", "evidence": "candidate"})

    curiosity = [
        {"question": f"{label}は、どの問題をどの著作で別の言葉に言い換えたのか", "axis": "問題系と著作", "evidence": "candidate"},
        {"question": "同じ著作の原題・日本語題・英訳題は、何を保存し、何を前景化しているのか", "axis": "題名・翻訳", "evidence": "candidate"},
        {"question": "影響関係として登録された人物は、直接引用・反論・後世の再構成のどれなのか", "axis": "知的系譜と反証", "evidence": "candidate"},
    ]
    if concepts:
        curiosity.append({"question": f"関連概念「{concepts[0].get('japanese_candidates', [concepts[0].get('source_term')])[0]}」は、本人の用語か後世の分類か", "axis": "概念の帰属", "evidence": "candidate"})

    return {
        "id": "wikidata-person:" + str(ed.get("qid") or _person_norm(label)),
        "qid": ed.get("qid"), "match": [q, label, latin], "display_name": label, "latin_name": latin,
        "identity_note": "人物名の異表記・転写は、意味の翻訳ではなく同一人物の識別候補として表示します。同じ表記が複数言語で使われる場合は一つに束ね、言語群だけを併記します。",
        "description": description or "Wikidataが人物として解決した対象。",
        "summary": summary, "domains": domains, "name_forms": forms,
        "pen_names": [{"qid": qid, "form": name, "kind": "筆名・著者名義（異表記ではない）", "evidence": "candidate", "source_ids": ["dynamic-wikidata"]}
                     for qid, name in zip(pseudonym_qids, pseudonym_names)],
        "works": works, "bibliography": bibliography_clean, "concepts": concepts,
        "influences": influences, "timeline": timeline, "reception": reception,
        "curiosity": curiosity, "primary_texts": primary_texts or [], "scholarship": scholarship or [],
        "sources": sources,
        "next_actions": [
            {"label": "人物名の表記・転写と同一人物性を確認する（同一表記は重複表示しない）", "kind": "identity", "source_ids": ["dynamic-wikidata"]},
            {"label": "主要著作を原題・日本語題・訳者・版・標準ロケータで並置する", "kind": "translation", "source_ids": ["dynamic-wikidata", "dynamic-ndl"]},
            {"label": "関連概念を本人の用語・後世の分類・翻訳語に分けて本文照合する", "kind": "concept", "source_ids": ["dynamic-wikidata", "dynamic-wikipedia"]},
            {"label": "影響候補を直接引用・反論・受容のどれかに分類する", "kind": "reception", "source_ids": ["dynamic-wikidata", "dynamic-ndl"]},
        ],
    }


_PERSON_DISCOVERY_CACHE = {}


def _person_entity_matches_query(q: str, entity) -> bool:
    """Require an explicit identity-form match before entering person mode.

    Wikidata search is a candidate generator, not an identity proof.  A bare
    concept such as 「自由」 may return a person, song, or place with a related
    label.  Person mode is allowed only when the input itself matches a
    label, alias, sitelink title, or preserved source-language form.
    """
    ed = entity.get("data", entity) if isinstance(entity, dict) else {}
    if not isinstance(ed, dict) or not ed.get("is_person"):
        return False
    needle = _person_norm(q)
    if not needle:
        return False
    forms = [ed.get("label"), ed.get("label_en")]
    forms.extend((ed.get("labels") or {}).values())
    forms.extend((ed.get("orig_labels") or {}).values())
    forms.extend((ed.get("wikipedia") or {}).values())
    for values in (ed.get("aliases") or {}).values():
        forms.extend(values if isinstance(values, list) else [])
    return needle in {_person_norm(x) for x in forms if x}


def _person_work_language_code(record: dict, language_records: dict) -> str:
    """Map a Wikidata P407 item to a display language code, cautiously."""
    claims = record.get("claims", {}) or {}
    qid = str((claims.get("original_language") or [""])[0])
    language_record = language_records.get(qid, {}) or {}
    labels = language_record.get("labels") or {}
    english = str(labels.get("en") or language_record.get("label_en") or "").casefold()
    by_name = {
        "danish": "da", "german": "de", "french": "fr", "english": "en",
        "latin": "la", "ancient greek": "grc", "greek": "el",
        "italian": "it", "spanish": "es", "portuguese": "pt",
        "dutch": "nl", "swedish": "sv", "norwegian": "no",
    }
    if english in by_name:
        return by_name[english]
    wikis = record.get("wikipedia") or {}
    for code in ("da", "de", "fr", "en", "la", "grc", "el", "it", "es"):
        if wikis.get(code) or (record.get("labels") or {}).get(code):
            return code
    return ""


def _person_text_matches(name: str, value: str) -> bool:
    """Match a person in author metadata without treating mere co-occurrence as proof."""
    left = _person_norm(name)
    right = _person_norm(value)
    if not left or not right:
        return False
    if left in right or right in left:
        return True
    tokens = [x.casefold() for x in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]{3,}", str(name or ""))]
    return bool(tokens) and all(_person_norm(token) in right for token in tokens)


async def _discover_person_profile(q: str, lang: str = "ja") -> dict | None:
    """Expand a Wikidata person into an identity/works/concepts dossier.

    This is deliberately a bounded, best-effort enrichment wave.  Wikidata
    supplies the stable identity and relationship graph; NDL supplies Japanese
    edition candidates; Wikipedia supplies orientation only; Gutenberg and
    OpenAlex are separate discovery layers.  A missing source never becomes a
    fabricated fact.
    """
    cache_key = f"{lang}:{_person_norm(q)}"
    if cache_key in _PERSON_DISCOVERY_CACHE:
        cached = _PERSON_DISCOVERY_CACHE[cache_key]
        return copy.deepcopy(cached) if cached else None
    if not _history_person_candidate(q):
        _PERSON_DISCOVERY_CACHE[cache_key] = None
        return None
    try:
        wd = await _history_bounded(wikidata.search(q, lang, limit=16), timeout=6.0)
        candidates = wd.get("data") if isinstance(wd, dict) and not wd.get("error") else []
        if not candidates:
            _PERSON_DISCOVERY_CACHE[cache_key] = None
            return None
        entity = await _history_bounded(
            _resolve_entity(candidates, lang, n=12, probes=4), timeout=9.0)
        if not _person_entity_matches_query(q, entity):
            _PERSON_DISCOVERY_CACHE[cache_key] = None
            return None
        ed = entity.get("data", {})
        claims = ed.get("claims", {}) or {}
        work_qids = [str(x) for x in claims.get("notable_work", [])
                     if str(x).startswith("Q")][:12]
        relation_names = ("field_of_work", "movement", "genre", "influenced_by", "pseudonym")
        relation_qids = [str(x) for name in relation_names
                        for x in claims.get(name, []) if str(x).startswith("Q")]
        work_batch, relation_batch = await asyncio.gather(
            _history_bounded(wikidata.batch_entities(work_qids, lang), timeout=10.0),
            _history_bounded(wikidata.batch_entities(list(dict.fromkeys(relation_qids))[:35], lang), timeout=10.0),
        )
        records = {str(x.get("qid")): x
                   for result in (work_batch, relation_batch)
                   for x in (result.get("data") or []) if isinstance(result, dict)
                   if isinstance(x, dict) and x.get("qid")}

        language_qids = [str((records[qid].get("claims", {}).get("original_language") or [""])[0])
                         for qid in work_qids if qid in records]
        language_qids = [x for x in dict.fromkeys(language_qids) if x.startswith("Q")]
        language_records = {}
        if language_qids:
            language_batch = await _history_bounded(
                wikidata.batch_entities(language_qids, lang), timeout=7.0)
            language_records = {str(x.get("qid")): x for x in (language_batch.get("data") or [])
                                if isinstance(x, dict) and x.get("qid")}

        work_records = []
        for qid in work_qids:
            rec = records.get(qid)
            if not rec:
                continue
            rec = copy.deepcopy(rec)
            source_code = _person_work_language_code(rec, language_records)
            rec["original_language_code"] = source_code
            if source_code:
                language_record = language_records.get(
                    str((rec.get("claims", {}).get("original_language") or [""])[0]), {})
                language_labels = language_record.get("labels") or {}
                rec["original_language_label"] = (
                    language_labels.get(lang) or language_labels.get("en")
                    or language_labels.get(source_code) or _person_lang_name(source_code))
            rec["role"] = "Wikidataが主要著作として登録した候補。原題・訳題・版面は別途照合。"
            work_records.append(rec)

        label = str(ed.get("label") or ed.get("label_en") or q)
        latin = str(ed.get("label_en") or label)
        name_records = ed.get("labels") or {}
        japanese_names = [label]
        for code, value in name_records.items():
            if code == "ja" or _has_cjk(str(value)):
                japanese_names.append(str(value))
        for values in (ed.get("aliases") or {}).values():
            for value in values if isinstance(values, list) else []:
                if _has_cjk(str(value)):
                    japanese_names.append(str(value))
        japanese_names = list(dict.fromkeys(x for x in japanese_names if x.strip()))[:5]

        async def _ndl_author_records():
            responses = await asyncio.gather(
                *[ndl.by_author(name, limit=14) for name in japanese_names],
                return_exceptions=True)
            out = []
            for response in responses:
                if isinstance(response, dict) and not response.get("error"):
                    out.extend(response.get("data") or [])
            return out

        work_japanese_titles = []
        for rec in work_records:
            ls = rec.get("labels") or {}
            wikis = rec.get("wikipedia") or {}
            title = ls.get("ja") or wikis.get("ja")
            if title:
                work_japanese_titles.append((rec.get("qid"), title))

        async def _ndl_work_records():
            responses = await asyncio.gather(
                *[ndl.by_work(label, title, limit=8)
                  for _, title in work_japanese_titles[:6]],
                return_exceptions=True)
            return [response for response in responses
                    if isinstance(response, dict) and not response.get("error")]

        wiki_titles = ed.get("wikipedia") or {}
        wiki_lang = lang if wiki_titles.get(lang) else "en"
        wiki_title = wiki_titles.get(wiki_lang)
        source_results = await asyncio.gather(
            _history_bounded(_ndl_author_records(), timeout=9.0),
            _history_bounded(_ndl_work_records(), timeout=10.0),
            _history_bounded(wikipedia.summary(wiki_title, wiki_lang), timeout=7.0)
            if wiki_title else asyncio.sleep(0, result={}),
            _history_bounded(gutendex.search(latin, limit=10), timeout=8.0),
            _history_bounded(openalex.search_works(latin, limit=12), timeout=8.0),
        )
        ndl_author_items, ndl_work_groups, wiki_result, gut_result, oa_result = source_results

        bibliography_items = []
        for item in ndl_author_items if isinstance(ndl_author_items, list) else []:
            if isinstance(item, dict):
                row = copy.deepcopy(item)
                row["source"] = "NDL書誌（著者名検索）"
                bibliography_items.append(row)
        for group in ndl_work_groups if isinstance(ndl_work_groups, list) else []:
            data = group.get("data") or {}
            work_title = data.get("work") or ""
            for item in data.get("editions") or []:
                if isinstance(item, dict):
                    row = copy.deepcopy(item)
                    row["edition_of"] = work_title
                    row["source"] = "NDL書誌（著作題名検索）"
                    bibliography_items.append(row)
        # Keep the NDL edition result attached to its actual work.  A work
        # without a Japanese label must not shift every subsequent pair.
        work_by_qid = {str(rec.get("qid")): rec for rec in work_records}
        for work_qid, title in work_japanese_titles:
            rec = work_by_qid.get(str(work_qid))
            if not rec:
                continue
            matching = [x for x in bibliography_items
                        if _person_norm(x.get("edition_of")) == _person_norm(title)]
            if matching:
                rec["japanese_editions"] = matching[:8]
                rec["edition_count"] = len(matching)

        wiki_data = wiki_result.get("data") if isinstance(wiki_result, dict) and not wiki_result.get("error") else {}
        summary = str((wiki_data or {}).get("extract") or "")
        wikipedia_url = str((wiki_data or {}).get("url") or "")

        primary_texts = []
        gut_items = gut_result.get("data") if isinstance(gut_result, dict) and not gut_result.get("error") else []
        for item in gut_items if isinstance(gut_items, list) else []:
            authors = item.get("authors") or []
            if not authors or any(_person_text_matches(label, author) or _person_text_matches(latin, author)
                                  for author in authors):
                row = copy.deepcopy(item)
                row["evidence"] = "candidate"
                row["source_ids"] = ["dynamic-gutenberg"]
                primary_texts.append(row)

        scholarship = []
        oa_items = oa_result.get("data") if isinstance(oa_result, dict) and not oa_result.get("error") else []
        for item in _relevant(oa_items if isinstance(oa_items, list) else [], latin)[:12]:
            row = copy.deepcopy(item)
            row["evidence"] = "candidate"
            row["source_ids"] = ["dynamic-openalex"]
            scholarship.append(row)

        relation_records = [records[qid] for qid in relation_qids if qid in records]
        profile = _person_profile_from_entity(
            q, entity, lang, work_records=work_records,
            relation_records=relation_records, bibliography=bibliography_items,
            summary=summary, wikipedia_url=wikipedia_url,
            primary_texts=primary_texts, scholarship=scholarship)
        _PERSON_DISCOVERY_CACHE[cache_key] = copy.deepcopy(profile) if profile else None
        return copy.deepcopy(profile) if profile else None
    except Exception:
        # A source connector may change shape or fail independently.  The
        # caller must fall back to the ordinary research surface, never show a
        # half-person graph with an unverified identity.
        _PERSON_DISCOVERY_CACHE[cache_key] = None
        return None


async def _person_profile_for_query_async(q: str, lang: str = "ja") -> dict | None:
    curated = _person_profile_for_query(q)
    if curated:
        return curated
    return await _discover_person_profile(q, lang)


def _person_dossier(profile: dict, domain: str, query: str) -> dict:
    """Turn a person profile into the same ledger contract as a term dossier.

    The fields are deliberately typed: name_forms are identity variants,
    works are title/edition candidates, and concepts are separate translation
    objects.  This is the structural correction that prevents Karl Marx from
    being rendered as if his name itself had a philosophical etymology.
    """
    p = copy.deepcopy(profile)
    display = p.get("display_name") or query
    term_map = []
    name_source_ids = ["dynamic-wikidata"] if str(p.get("id", "")).startswith("wikidata-person:") else []
    for n in p.get("name_forms", []):
        term_map.append({
            "source_term": n.get("form"), "language": n.get("language"),
            "kind": "人物名の表記・転写（翻訳ではない）",
            "japanese_candidates": [display],
            "distinction": n.get("kind") or "同一人物の識別候補",
            "preserved": "人物同一性の候補",
            "lost_or_shifted": "表記体系を変えると発音・中黒・語順などの情報が見えにくくなる",
            "added": "各言語・文字体系の転写慣行",
            "evidence": n.get("evidence", "candidate"),
            "source_ids": ["marx-name-variants"] if p.get("id") == "karl-marx" else name_source_ids,
        })
    for w in p.get("works", []):
        term_map.append({
            "source_term": w.get("original_title"), "language": w.get("original_language"),
            "kind": "著作題名・翻訳版",
            "japanese_candidates": w.get("japanese_titles") or [query],
            "distinction": w.get("role") or "著作と翻訳版を照合する候補",
            "preserved": "著作を同定する題名・刊年の手がかり",
            "lost_or_shifted": "題名の翻訳で語順・語感・概念の焦点が変わる可能性",
            "added": "受け入れ言語の出版・思想上の連想",
            "evidence": w.get("evidence", "candidate"), "source_ids": w.get("source_ids") or [],
        })
    for c in p.get("concepts", []):
        term_map.append({
            "source_term": c.get("source_term"), "language": c.get("language"),
            "kind": "人物に関係する概念語（人物名とは別）",
            "japanese_candidates": c.get("japanese_candidates") or [query],
            "distinction": c.get("note") or "著作・時期ごとに本文を照合する概念語",
            "preserved": "概念の比較対象となる語形",
            "lost_or_shifted": "訳者・版・受容者による意味の移動",
            "added": "受容言語の専門語彙",
            "evidence": c.get("evidence", "candidate"), "source_ids": c.get("source_ids") or [],
        })
    sources = p.get("sources", [])
    source_ids = {s.get("id") for s in sources if isinstance(s, dict)}
    for item in term_map:
        item["source_ids"] = [x for x in item.get("source_ids", []) if x in source_ids]
    transformations = [
        {"stage": "人物名の表記・転写", "preserved": "同一人物を指す候補", "lost": "文字体系を越えると発音・表記慣行の差が圧縮される", "added": "各言語圏の表記・転写慣行", "test": "Wikidata・図書館書誌・各言語の著作記録を人物IDで照合する", "evidence": "candidate", "source_ids": [s["id"] for s in sources[:2] if isinstance(s, dict) and s.get("id")]},
        {"stage": "著作題名の翻訳・版の差", "preserved": "著作の同一性を示す書誌的手がかり", "lost": "題名の語順・語感・概念の焦点が変わる可能性", "added": "受容言語の出版・思想的連想", "test": "原題・訳題・訳者・出版社・刊年・該当頁を版ごとに並置する", "evidence": "unverified", "source_ids": [s["id"] for s in sources if isinstance(s, dict) and s.get("id")]},
    ]
    default_counter = [
        {"claim": "人物名のラテン文字表記が見つかったので、名前が翻訳された意味も確定した", "counterargument": "人物名の違いは多くの場合、翻訳ではなく表記・転写の差である", "test": "同一人物ID、書誌、各言語版の著作記録を照合する"},
        {"claim": "人物が検索結果で共起したので影響関係が証明された", "counterargument": "共起は引用・継承・反論を証明しない", "test": "直接引用、参照文献、刊年順、反対解釈を確認する"},
    ]
    return {
        "id": p.get("id"), "mode": "person", "subject_kind": "person", "person": p,
        "domain": domain, "query": query,
        "title": f"「{display}」――人物・著作の翻訳／受容史台帳",
        "center_question": f"「{display}」は、{domain}の人物史・著作翻訳・受容史の中で、どの表記・どの著作・どの版を通って受け取られてきたのか。",
        "scope_note": "人物名そのものの表記・転写と、人物の著作・概念の翻訳・受容を分離して表示します。自動抽出は候補であり、引用・影響関係は本文照合まで確定しません。",
        "identity_note": p.get("identity_note", ""), "summary": p.get("summary", ""),
        "domains": p.get("domains", []),
        "name_forms": p.get("name_forms", []), "works": p.get("works", []),
        "pen_names": p.get("pen_names", []), "bibliography": p.get("bibliography", []),
        "concepts": p.get("concepts", []), "influences": p.get("influences", []),
        "term_map": term_map, "timeline": p.get("timeline", []),
        "reception_ledger": p.get("reception", []), "curiosity": p.get("curiosity", []),
        "primary_texts": p.get("primary_texts", []), "scholarship": p.get("scholarship", []),
        "transformations": transformations, "counterchecks": p.get("counterchecks") or default_counter,
        "sources": sources, "next_actions": p.get("next_actions", []),
    }


def _person_graph(profile: dict, query: str, lang: str = "ja") -> dict:
    """A person-first graph: identity → domains → works/concepts → reception."""
    display = profile.get("display_name") or query
    nodes, edges, seen = [], [], set()

    def add(nid, label, kind, layer, weight=1.0, q=None, extra=None):
        if nid in seen or not label:
            return
        seen.add(nid)
        nodes.append({"id": nid, "label": label, "kind": kind, "layer": layer,
                      "weight": weight, "q": q, **(extra or {})})

    def link(a, b, strength=1.0):
        edges.append({"from": a, "to": b, "strength": strength})

    add("root", display, "author", 1, 5.5, query,
        {"person_id": profile.get("id"), "qid": profile.get("qid"),
         "person_mode": True, "search": display})
    add("dom:identity", "人物同定・異表記", "domain", 2, 2.3)
    add("dom:works", "著作・翻訳版", "domain", 2, 2.8)
    add("dom:concepts", "概念・思想", "domain", 2, 2.5)
    add("dom:reception", "受容・影響の検証", "domain", 2, 2.1)
    for did in ("dom:identity", "dom:works", "dom:concepts", "dom:reception"):
        link("root", did, 1.25)
    # 表記・転写はプロフィールには全件を残すが、地図では同一人物の同一性キー
    # （中黒・空白・ハイフン等を除いた正規化）ごとに一つへ束ねる。検索表記を
    # 捨てずに保持しながら、「カール・マルクス」と「カールマルクス」が別人の
    # ように見える視覚的重複を防ぐ。
    identity_nodes = {}
    identity_index = 0
    for n in profile.get("name_forms", [])[:12]:
        form = n.get("form")
        if not form:
            continue
        key = _person_norm(form) or form
        if key in identity_nodes:
            prior = next((x for x in nodes if x.get("id") == identity_nodes[key]), None)
            if prior is not None:
                prior.setdefault("variants", []).append({
                    "form": form, "language": n.get("language"),
                    "languages": n.get("languages", []), "kind": n.get("kind"),
                    "evidence": n.get("evidence"),
                })
            continue
        nid = f"name:{identity_index}:{form}"
        identity_index += 1
        add(nid, form, "language", 3, 1.2, form,
            {"language": n.get("language"), "languages": n.get("languages", []),
             "language_codes": n.get("language_codes", []), "person_id": profile.get("id"),
             "variants": [{"form": form, "language": n.get("language"),
                           "languages": n.get("languages", []), "kind": n.get("kind"),
                           "evidence": n.get("evidence")}]} )
        identity_nodes[key] = nid
        link("dom:identity", nid, 0.8)
    for i, pen in enumerate(profile.get("pen_names", [])[:8]):
        form = pen.get("form") if isinstance(pen, dict) else str(pen)
        if not form or str(form).startswith("Q"):
            continue
        nid = f"pseudonym:{i}:{form}"
        add(nid, form, "pseudonym", 3, 1.15, form,
            {"person_id": profile.get("id"), "kind_label": "筆名・著者名義",
             "evidence": pen.get("evidence", "candidate") if isinstance(pen, dict) else "candidate"})
        link("dom:identity", nid, 0.75)
    for i, w in enumerate(profile.get("works", [])[:10]):
        title = w.get("japanese_titles", [None])[0] or w.get("original_title")
        wid = f"work:{i}:{title}"
        add(wid, title, "work", 3, 1.7, w.get("original_title") or title,
            {"original_title": w.get("original_title"), "year": w.get("year"),
             "qid": w.get("qid"), "japanese_titles": w.get("japanese_titles", []),
             "language_titles": w.get("language_titles", []),
             "person_id": profile.get("id")})
        link("dom:works", wid, 0.9)
    for i, c in enumerate(profile.get("concepts", [])[:12]):
        term = c.get("source_term") or (c.get("japanese_candidates") or [""])[0]
        cid = f"concept:{i}:{term}"
        add(cid, term, "related", 3, 1.4, term,
            {"language": c.get("language"), "japanese_candidates": c.get("japanese_candidates", []),
             "qid": c.get("qid"), "person_id": profile.get("id")})
        link("dom:concepts", cid, 0.8)
    for i, r in enumerate(profile.get("reception", [])[:8]):
        who = r.get("who")
        if not who or _person_norm(who) == _person_norm(display):
            continue
        rid = f"reception:{i}:{who}"
        add(rid, who, "author", 4, 1.0, who, {"search": who, "person_id": profile.get("id")})
        link("dom:reception", rid, 0.65)
    return {
        "query": query, "queried_at": now(), "qid": profile.get("qid"),
        "research_mode": "person", "entity_kind": "person", "person_profile": profile,
        "input_resolution": {
            "query": query, "canonical": display, "kind": "person",
            "qid": profile.get("qid"), "matched_forms": len(profile.get("name_forms", [])),
            "work_count": len(profile.get("works", [])),
            "note": "入力は人物IDへ解決されました。名前の異表記と著作・概念は別レイヤーで展開しています。",
        },
        "nodes": nodes, "edges": edges,
        "note": "人物研究モード：名前の表記・著作の翻訳・概念の受容・影響関係を別レイヤーで表示しています。人物名を一般語の語源としては扱いません。",
        "sources": [{"source": "person-profile", "retrieved_at": now(), "error": None}],
    }


def _person_origin(profile: dict, query: str, lang: str = "ja") -> dict:
    display = profile.get("display_name") or query
    forms = profile.get("name_forms", [])
    return {
        "query": query, "lang": lang, "queried_at": now(), "found": True,
        "subject_kind": "person", "person_profile": profile,
        "word": {"query": query}, "resolved_to": display,
        "general_meaning": [], "segment_layers": [], "collapse_warning": None,
        "concept_origin": [], "originators": [{"label": display, "is_person": True}],
        "associated": [], "relations": {"near": [], "opposite": []}, "named_after": [],
        "word_origin": None, "chain": [], "senses": [],
        "breadth": [{"name": x.get("language", "表記"), "term": x.get("form"), "via": "person-name-form"} for x in forms],
        "breadth_count": len(forms), "qid": profile.get("qid"),
        "summary": profile.get("summary", ""), "works": profile.get("works", []),
        "bibliography": profile.get("bibliography", []), "concepts": profile.get("concepts", []),
        "timeline": profile.get("timeline", []), "reception": profile.get("reception", []),
        "curiosity": profile.get("curiosity", []),
        "input_resolution": {
            "query": query, "canonical": display, "kind": "person", "qid": profile.get("qid"),
            "matched_forms": len(forms), "note": "人物IDで同定し、名前の表記と著作・概念・受容を分離しています。",
        },
        "article_url": next((s.get("url") for s in profile.get("sources", []) if "Wikipedia" in str(s.get("label"))), None),
        "wikidata_url": next((s.get("url") for s in profile.get("sources", []) if "Wikidata" in str(s.get("label"))), None),
        "wiktionary_url": None,
        "dimensions": [
            {"key": "identity", "label": "人物同定・異表記", "status": "ok", "act": "person:identity"},
            {"key": "works", "label": "著作・翻訳版", "status": "ok", "act": "person:works"},
            {"key": "concepts", "label": "概念・思想", "status": "ok", "act": "person:concepts"},
            {"key": "reception", "label": "受容・影響関係", "status": "partial", "act": "person:reception"},
        ],
        "confidence": {"identity": "表記・人物同定の候補", "works": "書誌・原典入口", "reception": "本文照合前の候補"},
        "sources": [{"source": "person-profile", "retrieved_at": now(), "error": None}],
    }


def _person_pair_for_queries(a: str, b: str) -> dict | None:
    """Return a curated person pair only when both sides are explicit people."""
    pa, pb = _person_profile_for_query(a), _person_profile_for_query(b)
    if not pa or not pb or pa.get("id") == pb.get("id"):
        return None
    ids = (pa.get("id"), pb.get("id"))
    relation = None
    for candidate in PERSON_PROFILES.get("relations", []):
        matches = candidate.get("match") or []
        if any(tuple(x) == ids for x in matches if isinstance(x, list)):
            relation = copy.deepcopy(candidate)
            break
    if relation is None:
        relation = {
            "id": f"pair:{ids[0]}:{ids[1]}",
            "title": f"{pa.get('display_name', a)} × {pb.get('display_name', b)}――比較・受容の調査台帳",
            "center_question": f"{pa.get('display_name', a)}と{pb.get('display_name', b)}は、どの著作・概念・引用を通じて関係づけられるのか。",
            "status_note": "人物名同士には通常の語のような翻訳語対応はありません。表記・著作・概念・引用・受容関係を別々に確認します。",
            "shared_terms": [], "timeline": [], "counterchecks": [], "sources": [],
        }
    return {"a": pa, "b": pb, "relation": relation, "ids": ids}


def _person_pair_dossier(pair: dict, domain: str, a: str, b: str) -> dict:
    pa, pb, relation = pair["a"], pair["b"], pair["relation"]
    profiles = [pa, pb]
    sources, seen_sources = [], set()
    for profile in profiles:
        for source in profile.get("sources", []):
            if isinstance(source, dict) and source.get("id") not in seen_sources:
                seen_sources.add(source["id"])
                sources.append(copy.deepcopy(source))
    shared = copy.deepcopy(relation.get("shared_terms") or [])
    relation_source_ids = [s for s in relation.get("sources", []) if s in seen_sources]
    term_map = []
    for profile in profiles:
        label = profile.get("display_name")
        for form in profile.get("name_forms", [])[:8]:
            term_map.append({
                "source_term": form.get("form"), "language": form.get("language"),
                "kind": f"人物名の表記・転写（{label}）",
                "japanese_candidates": [label],
                "distinction": "同一人物の識別候補。人物名同士の翻訳対応とは扱わない。",
                "preserved": "人物同一性の候補", "lost_or_shifted": "発音・中黒・文字体系の差",
                "added": "各言語圏の転写慣行", "evidence": form.get("evidence", "candidate"),
                "source_ids": [x.get("id") for x in profile.get("sources", [])[:1] if x.get("id")],
            })
        for work in profile.get("works", [])[:8]:
            term_map.append({
                "source_term": work.get("original_title"), "language": work.get("original_language"),
                "kind": f"著作題名・翻訳版（{label}）",
                "japanese_candidates": work.get("japanese_titles") or [label],
                "distinction": work.get("role") or "著作の同定・翻訳版照合",
                "preserved": "著作の同一性を示す書誌情報", "lost_or_shifted": "題名・概念の焦点差",
                "added": "受容言語の出版・思想的連想", "evidence": work.get("evidence", "candidate"),
                "source_ids": [x for x in work.get("source_ids", []) if x in seen_sources],
            })
    for item in shared:
        term_map.append({
            "source_term": item.get("term"), "language": "比較軸", "kind": "共有語彙・接点候補",
            "japanese_candidates": [item.get("term")], "distinction": item.get("role"),
            "preserved": "両者を比較するための問題設定", "lost_or_shifted": "直接引用・版・文脈は未確認",
            "added": "比較研究上の仮説", "evidence": item.get("evidence", "candidate"),
            "source_ids": relation_source_ids,
        })
    return {
        "id": relation.get("id"), "mode": "person_pair", "subject_kind": "person_pair",
        "pair": {"a": pa, "b": pb}, "relation": relation, "domain": domain,
        "title": relation.get("title") or f"{pa.get('display_name')} × {pb.get('display_name')}",
        "center_question": relation.get("center_question") or "2人の著作・概念・受容関係を確認する。",
        "scope_note": relation.get("status_note") or "人物名の表記と著作・概念・引用関係を分離して確認します。",
        "term_map": term_map, "timeline": relation.get("timeline") or [],
        "transformations": [{
            "stage": "人物名 → 著作・概念・受容関係",
            "preserved": "2人を比較する検索条件",
            "lost": "AND共起だけでは引用・影響・反論の向きは分からない",
            "added": "共有語彙・接点候補という比較仮説",
            "test": "本文の直接引用、参照文献、刊年順、対立解釈を確認する",
            "evidence": "candidate", "source_ids": relation_source_ids,
        }],
        "reception_ledger": relation.get("timeline") or [],
        "counterchecks": relation.get("counterchecks") or [], "sources": sources,
        "next_actions": [
            {"label": "2人の人物名の表記・転写を別々に確認する", "kind": "identity", "source_ids": relation_source_ids},
            {"label": "著作・版・訳者・標準ロケータを人物ごとに並置する", "kind": "translation", "source_ids": relation_source_ids},
            {"label": "引用・影響関係を本文で確認し、検索共起を証拠と混同しない", "kind": "reception", "source_ids": relation_source_ids},
        ],
    }


def _person_pair_graph(pair: dict, a: str, b: str, lang: str = "ja") -> dict:
    """Return a structured pair map instead of a generic web-result cloud."""
    pa, pb, relation = pair["a"], pair["b"], pair["relation"]
    nodes, edges, seen = [], [], set()

    def add(nid, label, kind, layer, weight=1.0, q=None, extra=None):
        if nid in seen or not label:
            return
        seen.add(nid)
        nodes.append({"id": nid, "label": label, "kind": kind, "layer": layer,
                      "weight": weight, "q": q, **(extra or {})})

    def link(x, y, strength=1.0):
        edges.append({"from": x, "to": y, "strength": strength})

    add("rootA", pa.get("display_name", a), "author", 1, 5.2, a,
        {"person_id": pa.get("id"), "search": pa.get("display_name", a)})
    add("rootB", pb.get("display_name", b), "author", 1, 5.2, b,
        {"person_id": pb.get("id"), "search": pb.get("display_name", b)})
    add("pair:relation", "翻訳・著作・受容関係", "domain", 2, 3.0)
    link("rootA", "pair:relation", 1.2); link("rootB", "pair:relation", 1.2)
    for i, item in enumerate(relation.get("shared_terms") or []):
        term = item.get("term")
        nid = f"pair:term:{i}"
        add(nid, term, "related", 3, 1.8, term, {"role": item.get("role"), "evidence": item.get("evidence")})
        link("pair:relation", nid, 0.9)
    for side, profile, root in (("a", pa, "rootA"), ("b", pb, "rootB")):
        for i, work in enumerate(profile.get("works", [])[:6]):
            title = work.get("japanese_titles", [None])[0] or work.get("original_title")
            nid = f"pair:{side}:work:{i}"
            add(nid, title, "work", 3, 1.35, work.get("original_title") or title,
                {"original_title": work.get("original_title"), "year": work.get("year"), "person_id": profile.get("id")})
            link(root, nid, 0.7)
    return {
        "query": a, "queried_at": now(), "research_mode": "person_pair",
        "entity_kind": "person_pair", "person_pair": {"a": pa, "b": pb, "relation": relation},
        "nodes": nodes, "edges": edges,
        "note": "人物ペア研究モード：人物名の翻訳語を作るのではなく、表記・著作・概念・引用・受容関係を比較します。検索共起は影響関係の証拠ではありません。",
        "has_results": True, "sources": [{"source": "person-pair-profile", "retrieved_at": now(), "error": None}],
    }


def _history_person_candidate(q: str) -> bool:
    """Allow person-shaped input while keeping long prose on the word path.

    The final identity gate is still Wikidata label/alias equality.  This
    heuristic only decides whether a bounded probe is worth attempting; it is
    intentionally broad enough to cover CJK names without spaces such as
    「孔子」 and 「西田幾多郎」.
    """
    s = str(q or "").strip()
    if not s:
        return False
    if len(s) > 80 or re.search(r"[。！？!?]", s):
        return False
    if re.search(r"[A-Za-z]", s) and (re.search(r"\s", s) or re.search(r"[A-Z]", s)):
        return True
    if re.fullmatch(r"[ァ-ヶー・\s]+", s) and len(re.sub(r"[・\s]", "", s)) >= 3:
        return True
    if re.fullmatch(r"[一-龯々〆ヵヶぁ-んァ-ヶー・·･\s]+", s):
        compact = re.sub(r"[・·･\s]", "", s)
        # Katakana transliterations are a high-value name-shaped input.  For
        # kanji-only input, avoid sending ordinary two-to-six-character
        # concepts (自由・共同幻想・量子力学) through a slow identity probe.
        # Full Japanese names with common given-name endings remain eligible;
        # the final Wikidata form gate still decides whether they are people.
        if re.fullmatch(r"[ァ-ヶー]+", compact):
            return len(compact) >= 3
        if "·" in s or "･" in s:
            return len(compact) >= 3
        if len(compact) < 3:
            return compact in {"孔子", "老子", "孟子", "荘子", "墨子", "荀子", "朱子"}
        if compact[-1] in "郎子夫男美明一二三介助之彦平雄江代信樹":
            return True
        if compact[-1] in "学論性体化理語法義想念主義":
            return False
        return False
    return bool(re.search(r"\s", s) and len(s) >= 3)


async def _history_person_discovery(q: str, lang: str) -> dict | None:
    """Compatibility wrapper for the shared person expansion path."""
    return await _discover_person_profile(q, lang)


def _history_norm(value: str) -> str:
    """Normalize only for matching a dossier trigger, never for displayed evidence."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")).casefold())


def _history_domain(value: str) -> str:
    key = _history_norm(value) or "philosophy"
    for domain, aliases in (TRANSLATION_HISTORY.get("domain_aliases") or {}).items():
        if key == _history_norm(domain) or any(key == _history_norm(a) for a in aliases):
            return domain
    return key


def _history_dossier(q: str, domain: str):
    """Return a copy of a curated dossier only when the query is an explicit match.

    This endpoint intentionally does not synthesize a history from a generic search
    hit. An absent domain/query is a visible, actionable not-seeded state.
    """
    nq = _history_norm(q)
    for dossier in TRANSLATION_HISTORY.get("dossiers", []):
        if dossier.get("domain") != domain:
            continue
        for match in dossier.get("match", []):
            nm = _history_norm(match)
            if nq and (nq == nm or (len(nq) >= 4 and (nq in nm or nm in nq))):
                return copy.deepcopy(dossier), match
    return None, None


def _history_source_candidates(q: str):
    """Build generic discovery links for a new research term.

    These are entry points, not evidence. Keeping them generated from the
    user's query means an unknown term still becomes a usable research start
    instead of an inert ``not_seeded`` response.
    """
    encoded = urllib.parse.quote(str(q or "").strip(), safe="")
    return [
        {
            "id": "candidate-wiktionary-ja",
            "label": "Wiktionary 日本語（語義・別綴りの探索）",
            "url": f"https://ja.wiktionary.org/wiki/Special:Search?search={encoded}",
            "purpose": "語形・別綴り・語義の候補を見つける",
            "evidence": "candidate",
            "status": "探索入口。原典・版・頁の証明には使わない。",
        },
        {
            "id": "candidate-ndl",
            "label": "国立国会図書館サーチ（書誌・翻訳版の探索）",
            "url": f"https://ndlsearch.ndl.go.jp/search?keyword={encoded}",
            "purpose": "日本語訳、訳者、刊年、版、所蔵を確認する",
            "evidence": "candidate",
            "status": "書誌確認の入口。本文の訳語は該当頁で別途確認する。",
        },
        {
            "id": "candidate-cinii",
            "label": "CiNii Research（研究・書誌の探索）",
            "url": f"https://cir.nii.ac.jp/all?q={encoded}",
            "purpose": "論文・図書・研究者・引用関係の候補を探す",
            "evidence": "candidate",
            "status": "研究候補の探索入口。引用・影響関係は本文で検証する。",
        },
        {
            "id": "candidate-books",
            "label": "Google Books（版・全文候補の探索）",
            "url": f"https://books.google.com/books?q={encoded}",
            "purpose": "異版、翻訳、引用箇所の候補を探索する",
            "evidence": "candidate",
            "status": "探索入口。表示された書誌や断片を証拠と同一視しない。",
        },
    ]


def _history_research_brief(q: str, domain: str):
    """Return a reusable first-pass brief without pretending the research is done."""
    return {
        "title": f"「{q}」の翻訳・受容史 調査台帳",
        "center_question": f"「{q}」は、{domain}の原典・翻訳・受容史の中で、誰が、いつ、どの版で、どのように使ったのか。",
        "status": "new_research_workspace",
        "first_pass": [
            "原語・異綴り・関連する語形を確定する",
            "原典と代表的な版の書誌・該当頁を確定する",
            "翻訳者・刊年・訳語の差を版ごとに並べる",
            "受容者の引用・再構成・反対解釈を原著者の主張から分離する",
        ],
    }


def _saved_ledgers_for_query(q: str, domain: str, workspace: str = "") -> list:
    conn = get_conn()
    try:
        visibility = "l.workspace_id=? OR l.is_public=1"
        return rows(conn.execute(
            "SELECT l.id, l.title, l.subject, l.central_question, l.domain, l.status, l.version,"
            " (SELECT COUNT(*) FROM ledger_entries e WHERE e.ledger_id=l.id) AS entry_count,"
            " (SELECT COUNT(*) FROM project_ledger_links pll JOIN projects p ON p.id=pll.project_id"
            "  WHERE pll.ledger_id=l.id AND pll.status='active'"
            "  AND (p.workspace_id=? OR p.is_public=1)) AS project_count"
            " FROM ledgers l WHERE l.subject=? AND l.domain=? AND l.status!='archived'"
            f" AND ({visibility}) ORDER BY l.updated_at DESC",
            (workspace, str(q or "").strip(), str(domain or "philosophy"), workspace)))
    finally:
        conn.close()


def _history_payload(value):
    """Unwrap a connector envelope without exposing connector error internals."""
    if not isinstance(value, dict):
        return {}
    data = value.get("data")
    return data if isinstance(data, (dict, list)) else value


def _history_items(value) -> list:
    data = _history_payload(value)
    return data if isinstance(data, list) else []


def _history_discovery_from_sources(q: str, domain: str, lang: str,
                                    origin=None, anatomy=None, explore=None):
    """Normalize existing source responses into a preliminary evidence ledger.

    This is deliberately an extraction layer, not an AI-authored history. It
    only copies meanings, labels, bibliographic records, and source links that
    the existing connectors returned. Missing translation or reception claims
    remain explicit next verification tasks.
    """
    origin = origin if isinstance(origin, dict) else {}
    anatomy = anatomy if isinstance(anatomy, dict) else {}
    explore = explore if isinstance(explore, dict) else {}
    meta = TRANSLATION_HISTORY.get("_meta", {})
    sources = [copy.deepcopy(s) for s in _history_source_candidates(q)]
    source_by_id = {s["id"]: s for s in sources}

    def add_source(source_id, label, url="", evidence="candidate", status=""):
        rec = source_by_id.get(source_id)
        if rec is None:
            rec = {"id": source_id, "label": label, "url": url or "",
                   "purpose": "", "evidence": evidence, "status": status}
            source_by_id[source_id] = rec
            sources.append(rec)
        else:
            if label:
                rec["label"] = label
            if url:
                rec["url"] = url
            rec["evidence"] = evidence or rec.get("evidence", "candidate")
            if status:
                rec["status"] = status
        return source_id

    wiki_url = origin.get("wiktionary_url") or ""
    dict_source = add_source(
        "candidate-wiktionary-ja", "Wiktionary 日本語（辞書・語形）", wiki_url,
        "confirmed" if (origin.get("general_meaning") or origin.get("senses")) else "candidate",
        "辞書義・語形を自動抽出。原典の意図や翻訳史の証明には使わない。")
    if origin.get("wikidata_url"):
        wd_source = add_source("auto-wikidata", "Wikidata（概念・人物・多言語ラベル）",
                               origin["wikidata_url"], "candidate",
                               "概念・人物・多言語ラベルの候補。関係の意味は本文で照合する。")
    else:
        wd_source = add_source("auto-wikidata", "Wikidata（概念・人物・多言語ラベル）",
                               "https://www.wikidata.org/w/api.php", "candidate",
                               "検索候補の入口。関係の意味は本文で照合する。")

    term_map, term_seen = [], set()

    def add_term(source_term, language, kind, japanese_candidates=None,
                 distinction="", evidence="candidate", source_ids=None,
                 preserved="", lost_or_shifted="", added=""):
        source_term = str(source_term or "").strip()
        if not source_term or (source_term, language) in term_seen:
            return
        term_seen.add((source_term, language))
        term_map.append({
            "source_term": source_term, "language": language, "kind": kind,
            "japanese_candidates": japanese_candidates or [q],
            "distinction": distinction, "preserved": preserved,
            "lost_or_shifted": lost_or_shifted, "added": added,
            "evidence": evidence, "source_ids": source_ids or [dict_source],
        })

    senses = [str(x).strip() for x in (origin.get("general_meaning") or origin.get("senses") or []) if str(x).strip()]
    if senses:
        add_term(q, "日本語", "入力語・辞書見出し", [q],
                 "辞書に記載された現在語義：" + " ／ ".join(senses[:4]),
                 "confirmed", [dict_source], "辞書に記載された語義",
                 "原典・版・訳者ごとの意味差はこの自動抽出では未比較")
    else:
        add_term(q, "日本語", "入力語", [q],
                 "この語を調査対象として各情報源へ照会した", "candidate",
                 [dict_source], "入力語を保持", "辞書義は今回の抽出で未取得")

    layers = (origin.get("segment_layers") or anatomy.get("segment_layers") or [])
    for layer in layers:
        if layer.get("level") not in {"semantic", "morphology"}:
            continue
        for unit in (layer.get("units") or [])[:8]:
            text = unit.get("text") if isinstance(unit, dict) else unit
            gloss = unit.get("gloss") if isinstance(unit, dict) else ""
            add_term(text, "日本語", "意味のまとまり", [text],
                     gloss or "辞書・語源データが示した構成単位",
                     "confirmed", [dict_source], "意味のまとまりとして抽出",
                     "文字単位より上位の意味単位", "翻訳史上の対応は未比較")

    for comp in (anatomy.get("components") or [])[:8]:
        if not isinstance(comp, dict):
            continue
        add_term(comp.get("part"), comp.get("lang") or "原語候補", "語源的構成要素",
                 [q], comp.get("meaning") or "語源データの構成要素",
                 "candidate", [dict_source], "語形の候補", "概念史上の原点とは別経路", "後世の解釈を混入させない")

    for item in (origin.get("concept_origin") or [])[:10]:
        if isinstance(item, dict):
            add_term(item.get("term"), item.get("name") or "原語候補", "概念・翻訳候補",
                     [q], "Wikipedia/Wikidata記事に併記された語形候補。翻訳関係は別途照合する。",
                     "candidate", [wd_source], "候補語形を保持", "原典・訳語対応は未確認", "記事の併記を翻訳の証明としない")

    for item in (origin.get("chain") or [])[:10]:
        if not isinstance(item, dict):
            continue
        add_term(item.get("form") or item.get("term"), item.get("name") or item.get("lang") or "語源経路",
                 "語形変化候補", [q], item.get("gloss") or "語源チェーンから抽出",
                 "candidate", [dict_source], "語形の経路候補", "概念の原点ではない", "訳者・受容者の付加は未比較")

    for item in (origin.get("breadth") or [])[:12]:
        if isinstance(item, dict) and item.get("term"):
            add_term(item.get("term"), item.get("name") or "多言語", "多言語表記",
                     [q], "Wikidata/Wiktionaryが保持する多言語ラベル。意味の同一性は個別照合する。",
                     "confirmed", [wd_source, dict_source], "各言語の表記を保持", "語の使用文脈は未比較", "翻訳語の焦点差は未比較")

    timeline = []

    def add_bibliography(items, source_key, label, evidence="bibliography_confirmed"):
        for i, item in enumerate(items[:8]):
            if not isinstance(item, dict) or not item.get("title"):
                continue
            sid = add_source(
                f"{source_key}-{i}", item.get("title"), item.get("url") or "",
                evidence, f"自動検索で得た書誌候補。{item.get('year') or '刊年未取得'}")
            creators = item.get("creators") or item.get("authors") or []
            if isinstance(creators, str):
                creators = [creators]
            who = "・".join(str(x) for x in creators[:5] if str(x).strip()) or label
            year = str(item.get("year") or "刊年未取得")
            timeline.append({
                "when": year, "who": who, "where": item.get("title", ""),
                "what": f"「{q}」に関係する{label}の書誌候補",
                "why": "翻訳・受容史の入口として自動抽出",
                "how": f"{label}で語を検索",
                "evidence": evidence,
                "evidence_note": "書誌の存在は確認材料だが、本文の引用・訳語・影響関係そのものではない。",
                "source_ids": [sid],
            })

    explore_ndl = _history_items(explore.get("japanese_scholarship"))
    explore_cinii = _history_items(explore.get("cinii"))
    # /api/explore currently uses a philosophy precision lens for OpenAlex.
    # NDL/CiNii remain useful cross-domain bibliographic discovery, but do not
    # present the philosophy-lens OpenAlex/SEP hits as science, literature, or
    # art evidence merely because the user selected that menu domain.
    explore_openalex = (_history_items(explore.get("recent_scholarship"))
                        if domain == "philosophy" else [])
    add_bibliography(explore_ndl, "auto-ndl", "NDL書誌")
    add_bibliography(explore_cinii, "auto-cinii", "CiNii研究書誌")
    add_bibliography(explore_openalex, "auto-openalex", "OpenAlex研究候補", "candidate")
    for group_index, group in enumerate(_history_items(explore.get("japanese_translations"))):
        if isinstance(group, dict):
            add_bibliography(group.get("editions") or [], f"auto-translation-{group_index}", "NDL翻訳版書誌")

    sep_entry = _history_payload(explore.get("sep_entry"))
    if domain == "philosophy" and isinstance(sep_entry, dict) and sep_entry.get("title"):
        sid = add_source("auto-sep", sep_entry.get("title"), sep_entry.get("url") or "",
                         "candidate", "SEPの関連候補。日本語語の直接的な受容史の証明ではない。")
        timeline.append({
            "when": sep_entry.get("pubinfo") or "改訂情報を参照",
            "who": "Stanford Encyclopedia of Philosophy",
            "where": sep_entry.get("title", ""),
            "what": "英語圏の概念・論争構造候補",
            "why": "比較対象としての自動抽出",
            "how": "SEP検索と関連性ゲート",
            "evidence": "candidate", "source_ids": [sid],
        })

    reception_ledger = []
    people = (origin.get("originators") or []) + (origin.get("associated") or [])
    seen_people = set()
    for person in people[:12]:
        if not isinstance(person, dict) or not person.get("label") or person["label"] in seen_people:
            continue
        seen_people.add(person["label"])
        reception_ledger.append({
            "who": person["label"], "when": "書誌・Wikidata記録時点",
            "where": origin.get("resolved_to") or q,
            "what": f"「{q}」との著者・考案者・関連人物候補として抽出",
            "why": "受容史の人物候補を先に可視化するため",
            "how": "Wikidataの著者・考案者・関連項目から抽出",
            "relation": "候補。実際の引用・影響関係は本文照合が必要",
            "evidence": "candidate", "source_ids": [wd_source],
        })

    transformations = [{
        "stage": "辞書・書誌の自動予備抽出",
        "preserved": "入力語、辞書義、候補語形、書誌レコード、人物候補",
        "lost": "原典の前後文脈、版ごとの訳語差、受容者の実際の引用",
        "added": "検索インデックスが返した候補順と自動分類",
        "test": "原典・代表版・訳者・該当頁を一件ずつ照合する",
        "evidence": "unverified", "source_ids": [dict_source, wd_source],
    }]
    if origin.get("resolved_from") and origin.get("resolved_to"):
        transformations.insert(0, {
            "stage": "見出し解決",
            "preserved": f"入力語「{origin['resolved_from']}」",
            "lost": "入力語と解決先記事の用法差は未比較",
            "added": f"解決先記事「{origin['resolved_to']}」",
            "test": "記事本文・辞書・書誌を並置し、同一概念と断定しない",
            "evidence": "confirmed", "source_ids": [dict_source],
        })

    counterchecks = [
        {"claim": "辞書に語義があるので、その語の原典上の意味も確定した", "counterargument": "辞書は現在語義の入口であり、原典・版・受容の使用場面を保証しない", "test": "原典の該当箇所と代表訳をページ単位で比較する"},
        {"claim": "NDL・CiNii・OpenAlexの書誌ヒットは、その人物の影響関係を証明する", "counterargument": "書誌の存在は出版・収録の確認であり、引用・継承・対立までは示さない", "test": "本文の引用、引用先、刊年順、反対解釈を確認する"},
    ]
    discovery = {
        "id": "auto-discovery:" + _history_norm(q),
        "mode": "automated_discovery",
        "domain": domain,
        "title": f"「{q}」――自動予備調査台帳（翻訳・受容史）",
        "center_question": f"「{q}」は、{domain}の辞書・原典・翻訳・受容史の中で、誰が、いつ、どの版で、どのように使ったのか。",
        "scope_note": "これは既存の辞書・概念・書誌コネクタから自動抽出した予備台帳である。自動収集できた情報を先に整理し、原典・版・訳語・影響関係の未確認部分は次の照合課題として残す。",
        "term_map": term_map,
        "timeline": timeline[:24],
        "transformations": transformations,
        "reception_ledger": reception_ledger,
        "counterchecks": counterchecks,
        "sources": sources,
        "next_actions": [
            {"label": "自動抽出された原語・語形候補を原典で照合する", "kind": "verify", "source_ids": [dict_source, wd_source]},
            {"label": "NDL・CiNiiの書誌候補から訳者・刊年・版を確認する", "kind": "verify", "source_ids": ["candidate-ndl", "candidate-cinii"]},
            {"label": "人物候補を本文の引用・受容史と照合する", "kind": "verify", "source_ids": [wd_source]},
        ],
    }
    useful = bool(senses or len(term_map) > 1 or timeline or reception_ledger
                 or origin.get("resolved_to") or origin.get("wikidata_url"))
    return discovery if useful else None


async def _history_bounded(coro, timeout: float = 8.0):
    """Run one discovery source without letting cancellation hold the UI hostage.

    A few third-party HTTP/DNS stacks can take time to finish cancellation after
    their socket timeout.  ``asyncio.wait_for`` waits for that cancellation to
    complete, so a nominal eight-second limit can still look like a stopped
    screen.  ``asyncio.wait`` returns at the deadline; the pending task is
    cancelled in the background and its partial result is intentionally not used.
    """
    # Keep a misbehaving resolver off the ASGI event loop.  In particular, a
    # DNS/proxy failure can make a third-party client's await point effectively
    # non-cancellable in some deployments; a worker thread lets the request
    # still return the honest partial/fallback state at the deadline.
    task = asyncio.create_task(asyncio.to_thread(asyncio.run, coro))
    done, _ = await asyncio.wait({task}, timeout=timeout)
    if not done:
        task.cancel()
        return {}
    try:
        return task.result()
    except Exception:
        return {}


async def _history_discovery(q: str, domain: str, lang: str):
    try:
        origin, anatomy, explore = await asyncio.gather(
            _history_bounded(api_origin(q, lang)),
            _history_bounded(api_anatomy(q, lang)),
            _history_bounded(api_explore(q, lang)),
        )
        return _history_discovery_from_sources(q, domain, lang, origin, anatomy, explore)
    except Exception:
        # A malformed partial response must fall through to the visible,
        # query-specific research workspace; it must never become a blank panel.
        return None


@app.get("/api/translation-history")
async def api_translation_history(q: str, domain: str = "philosophy", lang: str = "ja",
                                  request: Request = None):
    """特別モード: 原語・翻訳・受容史を証拠階層つきで追跡する。

    通常の /api/origin と違い、これは一つの語の一般的な語源を返すAPIではない。
    版・訳者・受容者・変形・欠損を同じ証拠台帳に束ねる。curated seed がある語は
    確定台帳を返し、未登録の語は既存情報源から自動予備台帳を作る。未整備の分野や
    語に哲学の結果を流用しない。
    """
    if not q.strip():
        raise HTTPException(400, "empty query")
    domain_key = _history_domain(domain)
    meta = TRANSLATION_HISTORY.get("_meta", {})
    available = sorted({d.get("domain") for d in TRANSLATION_HISTORY.get("dossiers", []) if d.get("domain")})
    supported_domains = sorted((TRANSLATION_HISTORY.get("domain_aliases") or {}).keys())
    dossier, matched = _history_dossier(q, domain_key)
    base = {
        "schema_version": meta.get("schema", "dialexis.translation-history.v1"),
        "query": q,
        "lang": lang,
        "domain": domain_key,
        "subject_kind": "term",
        "queried_at": now(),
        "verified_at": meta.get("verified_at"),
        "honesty": meta.get("honesty"),
        "evidence_levels": copy.deepcopy(meta.get("evidence_levels", [])),
        "source_policy": copy.deepcopy(meta.get("source_policy", [])),
        "source_plan": copy.deepcopy(meta.get("source_plan", [])),
        "available_domains": supported_domains,
        "seeded_domains": available,
        "saved_ledgers": _saved_ledgers_for_query(
            q, domain_key, workspace_id(request) if request else ""),
    }
    if not dossier:
        # Person names use a different contract: identity variants are not
        # word translations, and the useful translation/reception object is the
        # person's works and concepts.  Prefer the curated registry, then use a
        # cautious Wikidata person probe for names outside the seed.
        person = await _person_profile_for_query_async(q, lang)
        if person:
            pd = _person_dossier(person, domain_key, q)
            base.update({
                "status": "ready", "matched": True, "matched_term": person.get("display_name"),
                "subject_kind": "person", "dossier": pd,
                "note": "人物研究モードです。人物名の表記・転写、著作題名の翻訳・版、概念語の受容、影響関係の証拠を別々に表示します。人物名を一般語の語源としては扱いません。",
                "next_actions": copy.deepcopy(pd.get("next_actions", [])),
            })
            return base
        discovery = await _history_discovery(q, domain_key, lang)
        if discovery:
            base.update({
                "status": "discovery",
                "matched": False,
                "matched_term": None,
                "dossier": discovery,
                "note": "これは辞書・概念・書誌情報源から自動抽出した予備台帳です。原典・版・訳語・影響関係の未確認部分は、証拠レベルを下げて次の照合課題として表示しています。",
                "next_actions": copy.deepcopy(discovery.get("next_actions", [])),
            })
            return base
        candidates = _history_source_candidates(q)
        base.update({
            "status": "not_seeded",
            "matched": False,
            "matched_term": None,
            "dossier": None,
            "research_brief": _history_research_brief(q, domain_key),
            "source_candidates": candidates,
            "note": (f"「{q}」の「{domain_key}」分野について、原典・翻訳・受容史を一つの台帳に"
                      "束ねたデータはまだ登録されていません。既存の哲学資料を別分野へ流用せず、"
                      "下の情報源計画から調査を開始できます。"),
            "next_actions": [
                {"label": "原語・別綴り・代表的な版を登録する", "kind": "seed", "source_ids": ["candidate-wiktionary-ja"]},
                {"label": "原典→翻訳→受容の順に証拠を集める", "kind": "research", "source_ids": ["candidate-ndl", "candidate-cinii"]},
                {"label": "一般の多言語・外部検索へ戻る", "kind": "continue", "source_ids": ["candidate-books"]},
            ],
        })
        return base
    base.update({
        "status": "ready",
        "matched": True,
        "matched_term": matched,
        "dossier": dossier,
        "note": "これは網羅的な検索結果ではなく、現時点で接地できた資料範囲を証拠階層つきで整理した台帳です。",
        "next_actions": copy.deepcopy(dossier.get("next_actions", [])),
    })
    return base


@app.get("/api/translation-history/pair")
async def api_translation_history_pair(a: str, b: str, domain: str = "philosophy", lang: str = "ja"):
    """人物同士を語の翻訳辞書として扱わず、比較・受容台帳として束ねる。"""
    if not a.strip() or not b.strip():
        raise HTTPException(400, "two person queries required")
    domain_key = _history_domain(domain)
    pair = _person_pair_for_queries(a, b)
    if not pair:
        return {
            "status": "not_seeded", "matched": False, "subject_kind": "person_pair",
            "query": a, "other_query": b, "domain": domain_key, "dossier": None,
            "note": "2人とも人物として同定できる記録が揃っていないため、人物ペア台帳は作成していません。まず各人物を別々に同定してください。",
            "next_actions": [{"label": "2人を個別に人物として調査する", "kind": "identity", "source_ids": ["candidate-wikidata"]}],
        }
    dossier = _person_pair_dossier(pair, domain_key, a, b)
    return {
        "status": "ready", "matched": True, "subject_kind": "person_pair",
        "query": a, "other_query": b, "domain": domain_key, "dossier": dossier,
        "person_pair": pair, "queried_at": now(),
        "evidence_levels": copy.deepcopy(TRANSLATION_HISTORY.get("_meta", {}).get("evidence_levels", [])),
        "source_plan": copy.deepcopy(TRANSLATION_HISTORY.get("_meta", {}).get("source_plan", [])),
        "saved_ledgers": [], "next_actions": copy.deepcopy(dossier.get("next_actions", [])),
        "note": "人物ペア研究モードです。名前の翻訳対応ではなく、表記・著作・概念・引用・受容関係を比較します。",
    }


@app.get("/api/origin/graph")
async def api_origin_graph(q: str, lang: str = "ja"):
    """言語空間の重力分布グラフ（第1〜4階層）。第1=入力語／第2=重力分布の分岐（意味の
    領域・世界の言語）／第3=分岐を構成するもの（埋没した複数原語・各言語での語）／第4=強く
    関与する著者・著作（重要度順）。node の大きさ＝重力（密度の代理指標＝推定）、edge＝
    関係。データのある枝は濃く、無い枝は薄い（捏造しない・A3）。各 node は q を持てば
    クリックで新たな第1階層として展開できる。"""
    if not q.strip():
        raise HTTPException(400, "empty query")
    person = await _person_profile_for_query_async(q, lang)
    if person:
        return _person_graph(person, q, lang)
    await wiktionary.ensure_langnames(lang)   # 全言語コード→日本語名を用意（生コード表示の解消）
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

    # A person pair is not a generic AND word query.  If both names are
    # explicitly identifiable, return a structured comparison surface even
    # when the general web search has no useful hit.  This prevents the old
    # failure mode where Karl Marx × 吉本隆明 became an empty cloud or a list
    # of unrelated page titles.
    person_pair = _person_pair_for_queries(a, b) if op in {"and", "compare", "semand"} else None
    if person_pair:
        return _person_pair_graph(person_pair, a, b, lang)

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
                                    f"Target service: {service}\n\nDraft:\n{level0}",
                                    workspace=workspace_id(request))
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


# ---------- reusable research ledgers ----------

def _ledger_enum(value, allowed, default):
    value = str(value or "").strip()
    return value if value in allowed else default


def _public_flag(value) -> int:
    """Normalize JSON/form truth values before changing public visibility."""
    if isinstance(value, bool):
        return 1 if value else 0
    return 1 if str(value or "").strip().lower() in {
        "1", "true", "yes", "on"
    } else 0


def _ledger_evidence_level(level: str, source_label: str = "") -> str:
    """Map the older translation-history labels to typed ledger evidence.

    A dictionary hit must not become a primary-text confirmation merely because
    the old UI used the generic word ``confirmed``.
    """
    level = str(level or "candidate").strip()
    label = str(source_label or "").lower()
    if level == "confirmed":
        if "wiktionary" in label or "辞書" in label:
            return "dictionary_confirmed"
        return "strong"
    if level in db.LEDGER_EVIDENCE_LEVELS:
        return level
    return {
        "bibliography_confirmed": "bibliography_confirmed",
        "interpretive": "interpretive",
        "strong": "strong",
    }.get(level, "candidate")


def _ledger_source_role(source: dict) -> str:
    label = str(source.get("label") or source.get("source_name") or "").lower()
    evidence = str(source.get("evidence") or "candidate")
    if "wiktionary" in label or "辞書" in label:
        return "dictionary"
    if "wikidata" in label or "多言語" in label:
        return "authority_label"
    if evidence == "bibliography_confirmed" or "ndl" in label or "cinii" in label:
        return "bibliographic_catalog"
    if "sep" in label or "openalex" in label or "研究" in label:
        return "secondary_scholarship"
    return "candidate_index"


def _ledger_or_404(conn, lid: int, request: Request, write: bool = False):
    """Resolve a ledger under the request workspace boundary.

    Public ledgers are readable for discovery, but only their owning workspace
    may mutate them.  This preserves the intended many-project reuse model
    without turning an unguessable numeric id into write access.
    """
    wid = workspace_id(request)
    if write:
        row = conn.execute(
            "SELECT * FROM ledgers WHERE id=? AND workspace_id=?", (lid, wid)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM ledgers WHERE id=? AND (workspace_id=? OR is_public=1)",
            (lid, wid)
        ).fetchone()
    if not row:
        raise HTTPException(404, "unknown ledger")
    return row


def _ledger_snapshot(conn, lid: int) -> dict:
    ledger = conn.execute("SELECT * FROM ledgers WHERE id=?", (lid,)).fetchone()
    if not ledger:
        raise HTTPException(404, "unknown ledger")
    entries = rows(conn.execute(
        "SELECT * FROM ledger_entries WHERE ledger_id=? ORDER BY id", (lid,)))
    sources = rows(conn.execute(
        "SELECT * FROM ledger_sources WHERE ledger_id=? ORDER BY id", (lid,)))
    entry_sources = rows(conn.execute(
        "SELECT les.entry_id, les.source_id FROM ledger_entry_sources les"
        " JOIN ledger_entries e ON e.id=les.entry_id"
        " WHERE e.ledger_id=? ORDER BY les.entry_id, les.source_id", (lid,)))
    relations = rows(conn.execute(
        "SELECT * FROM ledger_relations WHERE ledger_id=? ORDER BY id", (lid,)))
    tasks = rows(conn.execute(
        "SELECT * FROM ledger_tasks WHERE ledger_id=? ORDER BY priority DESC, id", (lid,)))
    return {"ledger": dict(ledger), "entries": entries, "sources": sources,
            "entry_sources": entry_sources, "relations": relations, "tasks": tasks}


def _record_ledger_version(conn, lid: int, note: str = "", bump: bool = False) -> int:
    if bump:
        conn.execute("UPDATE ledgers SET version=version+1, updated_at=? WHERE id=?",
                     (now(), lid))
    snapshot = _ledger_snapshot(conn, lid)
    version = int(snapshot["ledger"]["version"])
    conn.execute(
        "INSERT OR REPLACE INTO ledger_versions(ledger_id, version, snapshot_json, note, created_at)"
        " VALUES(?,?,?,?,?)",
        (lid, version, json.dumps(snapshot, ensure_ascii=False, sort_keys=True), note, now()))
    return version


def _ledger_detail(conn, lid: int, visible_workspace: str | None = None) -> dict:
    data = _ledger_snapshot(conn, lid)
    if visible_workspace is not None:
        data["ledger"] = _expose_workspace_record(data["ledger"], visible_workspace)
    project_visibility = ""
    project_params = [lid]
    if visible_workspace is not None:
        project_visibility = " AND (p.workspace_id=? OR p.is_public=1)"
        project_params.append(visible_workspace)
    data["linked_projects"] = rows(conn.execute(
        "SELECT p.id, p.title, pll.role, pll.pinned_version, pll.status, pll.note,"
        " pll.created_at, pll.updated_at"
        " FROM project_ledger_links pll JOIN projects p ON p.id=pll.project_id"
        " WHERE pll.ledger_id=?" + project_visibility +
        " ORDER BY p.updated_at DESC", tuple(project_params)))
    data["versions"] = rows(conn.execute(
        "SELECT ledger_id, version, note, created_at FROM ledger_versions"
        " WHERE ledger_id=? ORDER BY version DESC", (lid,)))
    source_by_id = {s["id"]: s for s in data["sources"]}
    entry_sources = {}
    for link in data["entry_sources"]:
        entry_sources.setdefault(link["entry_id"], []).append(source_by_id[link["source_id"]])
    for entry in data["entries"]:
        entry["sources"] = entry_sources.get(entry["id"], [])
    data["counts"] = {
        "entries": len(data["entries"]),
        "confirmed": sum(1 for e in data["entries"] if e["status"] == "confirmed"),
        "candidate": sum(1 for e in data["entries"] if e["status"] == "candidate"),
        "open": sum(1 for t in data["tasks"] if t["status"] == "open"),
        "projects": len(data["linked_projects"]),
    }
    return data


def _ledger_add_source(conn, lid: int, source: dict) -> int:
    cur = conn.execute(
        "INSERT INTO ledger_sources(ledger_id, external_id, role, source_name, source_url,"
        " citation, retrieved_at, locator, quote, note) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (lid, str(source.get("external_id") or source.get("id") or ""),
         str(source.get("role") or _ledger_source_role(source)),
         str(source.get("source_name") or source.get("label") or ""),
         str(source.get("source_url") or source.get("url") or ""),
         str(source.get("citation") or ""), str(source.get("retrieved_at") or now()),
         str(source.get("locator") or ""), str(source.get("quote") or ""),
         str(source.get("note") or source.get("status") or "")))
    return cur.lastrowid


def _ledger_add_entry(conn, lid: int, body: dict, source_map=None) -> int:
    kind = _ledger_enum(body.get("kind"), db.LEDGER_ENTRY_KINDS, "note")
    evidence = _ledger_enum(body.get("evidence_level"), db.LEDGER_EVIDENCE_LEVELS, "candidate")
    status = _ledger_enum(body.get("status"), db.LEDGER_ENTRY_STATUSES, "candidate")
    origin = body.get("origin", "external")
    if origin not in db.ORIGINS:
        origin = "external"
    title = str(body.get("title") or body.get("source_term") or "").strip()
    if not title:
        raise HTTPException(400, "ledger entry title required")
    cur = conn.execute(
        "INSERT INTO ledger_entries(ledger_id, kind, title, body, source_term, target_term,"
        " source_language, target_language, author, translator, work, edition, year, locator,"
        " original_quote, translated_quote, preserved_meaning, lost_meaning, added_meaning,"
        " evidence_level, status, origin, created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (lid, kind, title, str(body.get("body") or ""),
         str(body.get("source_term") or ""), str(body.get("target_term") or ""),
         str(body.get("source_language") or ""), str(body.get("target_language") or ""),
         str(body.get("author") or ""), str(body.get("translator") or ""),
         str(body.get("work") or ""), str(body.get("edition") or ""),
         str(body.get("year") or ""), str(body.get("locator") or ""),
         str(body.get("original_quote") or ""), str(body.get("translated_quote") or ""),
         str(body.get("preserved_meaning") or ""), str(body.get("lost_meaning") or ""),
         str(body.get("added_meaning") or ""), evidence, status, origin, now(), now()))
    entry_id = cur.lastrowid
    for source_id in body.get("source_ids") or []:
        resolved = source_map.get(str(source_id)) if source_map else source_id
        if resolved:
            conn.execute("INSERT OR IGNORE INTO ledger_entry_sources(entry_id, source_id) VALUES(?,?)",
                         (entry_id, int(resolved)))
    return entry_id


def _ledger_create(conn, body: dict, title: str | None = None, parent_id=None,
                   workspace: str = "") -> int:
    title = (title or body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "ledger title required")
    subject_type = _ledger_enum(body.get("subject_type"), db.LEDGER_SUBJECT_TYPES, "term")
    status = _ledger_enum(body.get("status"), db.LEDGER_STATUSES, "draft")
    cur = conn.execute(
        "INSERT INTO ledgers(title, description, central_question, subject, subject_type,"
        " domain, status, is_public, workspace_id, parent_ledger_id, version, created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (title, str(body.get("description") or ""), str(body.get("central_question") or body.get("question") or ""),
         str(body.get("subject") or ""), subject_type, str(body.get("domain") or "philosophy"),
         status, _public_flag(body.get("is_public")), workspace, parent_id, 1, now(), now()))
    lid = cur.lastrowid
    _record_ledger_version(conn, lid, "created")
    return lid


def _history_source_payloads(result: dict) -> list:
    dossier = result.get("dossier") or {}
    source_list = dossier.get("sources") or result.get("source_candidates") or []
    return [s for s in source_list if isinstance(s, dict)]


def _history_ledger_body(q: str, domain: str, result: dict, request_body: dict) -> dict:
    dossier = result.get("dossier") or {}
    brief = result.get("research_brief") or {}
    title = request_body.get("title") or dossier.get("title") or brief.get("title") or f"「{q}」の研究台帳"
    question = request_body.get("central_question") or dossier.get("center_question") or brief.get("center_question") or ""
    subject_type = request_body.get("subject_type")
    if not subject_type:
        if result.get("subject_kind") == "person_pair":
            # 二人の人物を比較する調査は単語台帳ではない。既存DBの
            # enumを増やさず、研究課題として扱い、本文の dossier が型を持つ。
            subject_type = "research_question"
        elif result.get("subject_kind") == "person":
            subject_type = "person"
        else:
            subject_type = "discipline" if q in {"哲学", "philosophy"} else "term"
    return {"title": title, "central_question": question, "subject": q,
            "subject_type": subject_type, "domain": domain,
            "description": result.get("note") or dossier.get("scope_note") or "",
            "status": "active" if dossier else "draft"}


def _create_ledger_from_history(result: dict, request_body: dict, workspace: str = "") -> int:
    q = str(result.get("query") or request_body.get("query") or "").strip()
    domain = str(result.get("domain") or request_body.get("domain") or "philosophy")
    conn = get_conn()
    try:
        lid = _ledger_create(conn, _history_ledger_body(q, domain, result, request_body),
                             workspace=workspace)
        source_map = {}
        for source in _history_source_payloads(result):
            external_id = str(source.get("id") or source.get("external_id") or "")
            sid = _ledger_add_source(conn, lid, {**source, "external_id": external_id})
            if external_id:
                source_map[external_id] = sid
        dossier = result.get("dossier") or {}
        for item in dossier.get("term_map") or []:
            if not isinstance(item, dict) or not item.get("source_term"):
                continue
            kind_text = str(item.get("kind") or "")
            kind = "translation" if "翻訳" in kind_text or "原語" in kind_text else "term"
            target = (item.get("japanese_candidates") or [q])[0]
            _ledger_add_entry(conn, lid, {
                "kind": kind, "title": item.get("source_term"),
                "body": item.get("distinction") or "", "source_term": item.get("source_term"),
                "target_term": target, "source_language": item.get("language"),
                "preserved_meaning": item.get("preserved"),
                "lost_meaning": item.get("lost_or_shifted"), "added_meaning": item.get("added"),
                "evidence_level": _ledger_evidence_level(item.get("evidence"), ""),
                "status": "confirmed" if item.get("evidence") == "confirmed" else "candidate",
                "source_ids": item.get("source_ids") or []}, source_map)
        for item in dossier.get("timeline") or []:
            if not isinstance(item, dict) or not item.get("where"):
                continue
            body = "\n".join(x for x in [
                f"Where: {item.get('where', '')}", f"What: {item.get('what', '')}",
                f"Why: {item.get('why', '')}", f"How: {item.get('how', '')}",
                item.get("evidence_note", "")
            ] if x)
            _ledger_add_entry(conn, lid, {
                "kind": "edition", "title": item.get("where"), "body": body,
                "author": item.get("who"), "year": item.get("when"),
                "source_term": q,
                "evidence_level": _ledger_evidence_level(item.get("evidence"), ""),
                "status": "confirmed" if item.get("evidence") == "bibliography_confirmed" else "candidate",
                "source_ids": item.get("source_ids") or []}, source_map)
        for item in dossier.get("transformations") or []:
            if isinstance(item, dict) and item.get("stage"):
                _ledger_add_entry(conn, lid, {
                    "kind": "interpretation", "title": item.get("stage"),
                    "body": "\n".join(x for x in [
                        f"保存: {item.get('preserved', '')}",
                        f"移動・欠損: {item.get('lost', '')}",
                        f"追加: {item.get('added', '')}",
                        f"検証: {item.get('test', '')}"] if x),
                    "evidence_level": _ledger_evidence_level(item.get("evidence"), ""),
                    "status": "candidate", "source_ids": item.get("source_ids") or []}, source_map)
        for item in dossier.get("reception_ledger") or []:
            if isinstance(item, dict) and item.get("who"):
                _ledger_add_entry(conn, lid, {
                    "kind": "reception", "title": item.get("who"),
                    "body": "\n".join(x for x in [
                        f"Where: {item.get('where', '')}", f"What: {item.get('what', '')}",
                        f"Why: {item.get('why', '')}", f"How: {item.get('how', '')}",
                        f"Relation: {item.get('relation', '')}"] if x),
                    "year": item.get("when"), "evidence_level": _ledger_evidence_level(item.get("evidence"), ""),
                    "status": "candidate", "source_ids": item.get("source_ids") or []}, source_map)
        for action in result.get("next_actions") or dossier.get("next_actions") or []:
            if isinstance(action, dict) and action.get("label"):
                conn.execute("INSERT INTO ledger_tasks(ledger_id, title, status, priority, created_at, updated_at)"
                             " VALUES(?,?,?,?,?,?)", (lid, action["label"], "open", 1, now(), now()))
        if not dossier:
            note = result.get("note") or "この語の原典・翻訳・受容史を調査するための開始点です。"
            _ledger_add_entry(conn, lid, {"kind": "open_question", "title": "調査開始",
                                          "body": note, "source_term": q,
                                          "evidence_level": "unverified", "status": "open"}, source_map)
        _record_ledger_version(conn, lid, "saved from translation-history discovery", bump=True)
        conn.commit()
        return lid
    finally:
        conn.close()


@app.get("/api/ledgers")
def list_ledgers(request: Request, status: str = ""):
    conn = get_conn()
    wid = workspace_id(request)
    where = " WHERE (l.workspace_id=? OR l.is_public=1)"
    params = [wid, wid]
    if status in db.LEDGER_STATUSES:
        where += " AND l.status=?"
        params.append(status)
    data = rows(conn.execute(
        "SELECT l.*,"
        " (SELECT COUNT(*) FROM ledger_entries e WHERE e.ledger_id=l.id) entry_count,"
        " (SELECT COUNT(*) FROM ledger_entries e WHERE e.ledger_id=l.id AND e.status='confirmed') confirmed_count,"
        " (SELECT COUNT(*) FROM ledger_entries e WHERE e.ledger_id=l.id AND e.status='candidate') candidate_count,"
        " (SELECT COUNT(*) FROM ledger_tasks t WHERE t.ledger_id=l.id AND t.status='open') open_task_count,"
        " (SELECT COUNT(*) FROM project_ledger_links pll JOIN projects p ON p.id=pll.project_id"
        "  WHERE pll.ledger_id=l.id AND pll.status='active'"
        "  AND (p.workspace_id=? OR p.is_public=1)) project_count"
        " FROM ledgers l" + where + " ORDER BY l.updated_at DESC", tuple(params)))
    conn.close()
    return [_expose_workspace_record(item, wid) for item in data]


@app.get("/api/ledgers/{lid}")
def get_ledger(lid: int, request: Request):
    conn = get_conn()
    try:
        _ledger_or_404(conn, lid, request)
        return _ledger_detail(conn, lid, workspace_id(request))
    finally:
        conn.close()


@app.post("/api/ledgers")
async def create_ledger(request: Request):
    body = await request.json()
    conn = get_conn()
    try:
        lid = _ledger_create(conn, body, workspace=workspace_id(request))
        conn.commit()
        return _ledger_detail(conn, lid, workspace_id(request))
    finally:
        conn.close()


@app.patch("/api/ledgers/{lid}")
async def update_ledger(lid: int, request: Request):
    body = await request.json()
    fields, values = [], []
    for key in ("title", "description", "central_question", "subject", "domain"):
        if key in body:
            fields.append(f"{key}=?")
            values.append(str(body[key] or ""))
    if "status" in body:
        status = _ledger_enum(body.get("status"), db.LEDGER_STATUSES, "draft")
        fields.append("status=?")
        values.append(status)
    if "is_public" in body:
        fields.append("is_public=?")
        values.append(_public_flag(body.get("is_public")))
    if not fields:
        raise HTTPException(400, "nothing to update")
    conn = get_conn()
    try:
        _ledger_or_404(conn, lid, request, write=True)
        values += [now(), lid]
        conn.execute("UPDATE ledgers SET " + ", ".join(fields) + ", updated_at=? WHERE id=?", values)
        _record_ledger_version(conn, lid, "metadata updated", bump=True)
        conn.commit()
        return _ledger_detail(conn, lid, workspace_id(request))
    finally:
        conn.close()


@app.post("/api/ledgers/{lid}/entries")
async def create_ledger_entry(lid: int, request: Request):
    body = await request.json()
    conn = get_conn()
    try:
        _ledger_or_404(conn, lid, request, write=True)
        entry_id = _ledger_add_entry(conn, lid, body)
        _record_ledger_version(conn, lid, "entry added", bump=True)
        conn.commit()
        return {"id": entry_id, "ledger": _ledger_detail(conn, lid, workspace_id(request))}
    finally:
        conn.close()


@app.patch("/api/ledger-entries/{entry_id}")
async def update_ledger_entry(entry_id: int, request: Request):
    body = await request.json()
    conn = get_conn()
    try:
        entry = conn.execute("SELECT * FROM ledger_entries WHERE id=?", (entry_id,)).fetchone()
        if not entry:
            raise HTTPException(404, "unknown ledger entry")
        _ledger_or_404(conn, entry["ledger_id"], request, write=True)
        fields, values = [], []
        for key in ("title", "body", "source_term", "target_term", "source_language",
                    "target_language", "author", "translator", "work", "edition", "year",
                    "locator", "original_quote", "translated_quote", "preserved_meaning",
                    "lost_meaning", "added_meaning"):
            if key in body:
                fields.append(f"{key}=?")
                values.append(str(body[key] or ""))
        if "kind" in body:
            fields.append("kind=?")
            values.append(_ledger_enum(body.get("kind"), db.LEDGER_ENTRY_KINDS, "note"))
        if "evidence_level" in body:
            fields.append("evidence_level=?")
            values.append(_ledger_enum(body.get("evidence_level"), db.LEDGER_EVIDENCE_LEVELS, "candidate"))
        if "status" in body:
            fields.append("status=?")
            values.append(_ledger_enum(body.get("status"), db.LEDGER_ENTRY_STATUSES, "candidate"))
        if not fields:
            raise HTTPException(400, "nothing to update")
        values += [now(), entry_id]
        conn.execute("UPDATE ledger_entries SET " + ", ".join(fields) + ", updated_at=? WHERE id=?", values)
        _record_ledger_version(conn, entry["ledger_id"], "entry updated", bump=True)
        conn.commit()
        return _ledger_detail(conn, entry["ledger_id"], workspace_id(request))
    finally:
        conn.close()


@app.post("/api/ledgers/{lid}/fork")
async def fork_ledger(lid: int, request: Request):
    body = await request.json()
    conn = get_conn()
    try:
        _ledger_or_404(conn, lid, request)
        source = _ledger_snapshot(conn, lid)
        meta = source["ledger"]
        new_lid = _ledger_create(conn, {
            "title": body.get("title") or f"{meta['title']}（分岐）",
            "description": meta["description"], "central_question": meta["central_question"],
            "subject": meta["subject"], "subject_type": meta["subject_type"],
            "domain": meta["domain"], "status": "draft"}, parent_id=lid,
            workspace=workspace_id(request))
        source_map, entry_map = {}, {}
        for s in source["sources"]:
            ns = _ledger_add_source(conn, new_lid, s)
            source_map[s["id"]] = ns
        for e in source["entries"]:
            ne = _ledger_add_entry(conn, new_lid, {k: e.get(k, "") for k in (
                "kind", "title", "body", "source_term", "target_term", "source_language",
                "target_language", "author", "translator", "work", "edition", "year", "locator",
                "original_quote", "translated_quote", "preserved_meaning", "lost_meaning",
                "added_meaning", "evidence_level", "status", "origin")},
                {str(old): new for old, new in source_map.items()})
            entry_map[e["id"]] = ne
        for rel in source["relations"]:
            conn.execute("INSERT OR IGNORE INTO ledger_relations(ledger_id, src_entry_id, dst_entry_id, relation, note, created_at)"
                         " VALUES(?,?,?,?,?,?)", (new_lid, entry_map[rel["src_entry_id"]], entry_map[rel["dst_entry_id"]],
                                                   rel["relation"], rel["note"], now()))
        for task in source["tasks"]:
            conn.execute("INSERT INTO ledger_tasks(ledger_id, entry_id, title, status, priority, created_at, updated_at)"
                         " VALUES(?,?,?,?,?,?,?)", (new_lid, entry_map.get(task.get("entry_id")), task["title"],
                                                      task["status"], task["priority"], now(), now()))
        _record_ledger_version(conn, new_lid, f"forked from ledger {lid}", bump=True)
        conn.commit()
        return _ledger_detail(conn, new_lid, workspace_id(request))
    finally:
        conn.close()


@app.post("/api/ledgers/from-translation-history")
async def create_ledger_from_translation_history(request: Request):
    body = await request.json()
    q = str(body.get("query") or "").strip()
    if not q:
        raise HTTPException(400, "query required")
    other_query = str(body.get("other_query") or "").strip()
    if other_query:
        result = await api_translation_history_pair(
            q, other_query, str(body.get("domain") or "philosophy"), str(body.get("lang") or "ja"))
    else:
        result = await api_translation_history(q, str(body.get("domain") or "philosophy"),
                                               str(body.get("lang") or "ja"), request)
    lid = _create_ledger_from_history(result, body, workspace_id(request))
    conn = get_conn()
    try:
        return {"id": lid, "status": result.get("status"),
                "ledger": _ledger_detail(conn, lid, workspace_id(request))}
    finally:
        conn.close()


def _project_or_404(conn, pid: int, request: Request, write: bool = False):
    wid = workspace_id(request)
    if write:
        p = conn.execute(
            "SELECT * FROM projects WHERE id=? AND workspace_id=?", (pid, wid)
        ).fetchone()
    else:
        p = conn.execute(
            "SELECT * FROM projects WHERE id=? AND (workspace_id=? OR is_public=1)",
            (pid, wid)
        ).fetchone()
    if not p:
        raise HTTPException(404, "unknown project")
    return p


@app.get("/api/projects/{pid}/ledgers")
def project_ledgers(pid: int, request: Request):
    conn = get_conn()
    try:
        _project_or_404(conn, pid, request)
        wid = workspace_id(request)
        data = rows(conn.execute(
            "SELECT l.*, pll.role, pll.pinned_version, pll.status AS link_status, pll.note AS link_note,"
            " pll.created_at AS linked_at, pll.updated_at AS link_updated_at,"
            " (SELECT COUNT(*) FROM project_ledger_entries ple WHERE ple.project_id=? AND ple.entry_id IN"
            "   (SELECT id FROM ledger_entries WHERE ledger_id=l.id)) AS used_entry_count"
            " FROM project_ledger_links pll JOIN ledgers l ON l.id=pll.ledger_id"
            " WHERE pll.project_id=? AND (l.workspace_id=? OR l.is_public=1)"
            " ORDER BY l.updated_at DESC", (pid, pid, wid)))
        return [_expose_workspace_record(item, wid) for item in data]
    finally:
        conn.close()


@app.post("/api/projects/{pid}/ledgers")
async def link_project_ledger(pid: int, request: Request):
    body = await request.json()
    lid = int(body.get("ledger_id") or 0)
    role = _ledger_enum(body.get("role"), db.LEDGER_LINK_ROLES, "background")
    conn = get_conn()
    try:
        _project_or_404(conn, pid, request, write=True)
        ledger = _ledger_or_404(conn, lid, request)
        pinned = int(body.get("pinned_version") or ledger["version"])
        conn.execute(
            "INSERT INTO project_ledger_links(project_id, ledger_id, role, pinned_version, status, note, created_at, updated_at)"
            " VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(project_id, ledger_id) DO UPDATE SET role=excluded.role,"
            " pinned_version=excluded.pinned_version, status='active', note=excluded.note, updated_at=excluded.updated_at",
            (pid, lid, role, pinned, "active", str(body.get("note") or ""), now(), now()))
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), pid))
        conn.commit()
        return {"ok": True, "ledger_id": lid, "pinned_version": pinned}
    finally:
        conn.close()


@app.delete("/api/projects/{pid}/ledgers/{lid}")
def unlink_project_ledger(pid: int, lid: int, request: Request):
    conn = get_conn()
    try:
        _project_or_404(conn, pid, request, write=True)
        conn.execute("DELETE FROM project_ledger_links WHERE project_id=? AND ledger_id=?", (pid, lid))
        conn.execute("DELETE FROM project_ledger_entries WHERE project_id=? AND entry_id IN"
                     " (SELECT id FROM ledger_entries WHERE ledger_id=?)", (pid, lid))
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), pid))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.post("/api/projects/{pid}/ledger-entries")
async def link_project_ledger_entry(pid: int, request: Request):
    body = await request.json()
    entry_id = int(body.get("entry_id") or 0)
    relation = str(body.get("relation") or "evidence")
    conn = get_conn()
    try:
        _project_or_404(conn, pid, request, write=True)
        entry = conn.execute("SELECT e.*, l.version FROM ledger_entries e JOIN ledgers l ON l.id=e.ledger_id WHERE e.id=?",
                             (entry_id,)).fetchone()
        if not entry:
            raise HTTPException(404, "unknown ledger entry")
        _ledger_or_404(conn, entry["ledger_id"], request)
        link = conn.execute("SELECT 1 FROM project_ledger_links WHERE project_id=? AND ledger_id=? AND status='active'",
                            (pid, entry["ledger_id"])).fetchone()
        if not link:
            raise HTTPException(409, "link the ledger to the project first")
        conn.execute(
            "INSERT INTO project_ledger_entries(project_id, entry_id, relation, adopted_version, use_note, created_at)"
            " VALUES(?,?,?,?,?,?) ON CONFLICT(project_id, entry_id) DO UPDATE SET relation=excluded.relation,"
            " adopted_version=excluded.adopted_version, use_note=excluded.use_note",
            (pid, entry_id, relation, int(body.get("adopted_version") or entry["version"]),
             str(body.get("use_note") or ""), now()))
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), pid))
        conn.commit()
        return {"ok": True, "entry_id": entry_id, "adopted_version": int(body.get("adopted_version") or entry["version"])}
    finally:
        conn.close()


@app.get("/api/projects/{pid}/ledger-entries")
def project_ledger_entries(pid: int, request: Request):
    conn = get_conn()
    try:
        _project_or_404(conn, pid, request)
        return rows(conn.execute(
            "SELECT ple.*, e.ledger_id, e.kind, e.title, e.body, e.evidence_level, e.status,"
            " l.title AS ledger_title, l.version AS current_version"
            " FROM project_ledger_entries ple JOIN ledger_entries e ON e.id=ple.entry_id"
            " JOIN ledgers l ON l.id=e.ledger_id"
            " WHERE ple.project_id=? AND (l.workspace_id=? OR l.is_public=1)"
            " ORDER BY ple.created_at DESC", (pid, workspace_id(request))))
    finally:
        conn.close()


# ---------- research desk (research-process graph) ----------

@app.get("/api/projects")
def list_projects(request: Request):
    conn = get_conn()
    wid = workspace_id(request)
    data = rows(conn.execute(
        "SELECT p.*, (SELECT COUNT(*) FROM nodes n WHERE n.project_id=p.id) node_count"
        " FROM projects p WHERE p.workspace_id=? OR p.is_public=1 ORDER BY updated_at DESC",
        (wid,)))
    conn.close()
    return [_expose_workspace_record(item, wid) for item in data]


@app.post("/api/projects")
async def create_project(request: Request):
    b = await request.json()
    if not b.get("title", "").strip():
        raise HTTPException(400, "title required")
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO projects(title, description, question, is_public, workspace_id, created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,?)",
        (b["title"].strip(), b.get("description", ""), b.get("question", ""),
         _public_flag(b.get("is_public")), workspace_id(request), now(), now()))
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
def delete_project(pid: int, request: Request):
    conn = get_conn()
    _project_or_404(conn, pid, request, write=True)
    conn.execute("DELETE FROM projects WHERE id=? AND workspace_id=?", (pid, workspace_id(request)))
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
def project_graph(pid: int, request: Request):
    conn = get_conn()
    p = _project_or_404(conn, pid, request)
    wid = workspace_id(request)
    nodes = rows(conn.execute("SELECT * FROM nodes WHERE project_id=?", (pid,)))
    edges = rows(conn.execute("SELECT * FROM edges WHERE project_id=?", (pid,)))
    prov = rows(conn.execute(
        "SELECT pr.* FROM provenance pr JOIN nodes n ON pr.node_id=n.id"
        " WHERE n.project_id=?", (pid,)))
    args = _load_arguments(conn, pid)
    linked_ledgers = rows(conn.execute(
        "SELECT l.*, pll.role, pll.pinned_version, pll.status AS link_status, pll.note AS link_note,"
        " pll.created_at AS linked_at, pll.updated_at AS link_updated_at"
        " FROM project_ledger_links pll JOIN ledgers l ON l.id=pll.ledger_id"
        " WHERE pll.project_id=? AND (l.workspace_id=? OR l.is_public=1)"
        " ORDER BY l.updated_at DESC", (pid, workspace_id(request))))
    linked_entries = rows(conn.execute(
        "SELECT ple.*, e.ledger_id, e.kind, e.title, e.body, e.evidence_level, e.status,"
        " l.title AS ledger_title, l.version AS current_version"
        " FROM project_ledger_entries ple JOIN ledger_entries e ON e.id=ple.entry_id"
        " JOIN ledgers l ON l.id=e.ledger_id"
        " WHERE ple.project_id=? AND (l.workspace_id=? OR l.is_public=1)"
        " ORDER BY ple.created_at DESC", (pid, workspace_id(request))))
    linked_ledger_sources = rows(conn.execute(
        "SELECT DISTINCT ls.* FROM project_ledger_links pll"
        " JOIN ledger_sources ls ON ls.ledger_id=pll.ledger_id"
        " JOIN ledgers l ON l.id=pll.ledger_id"
        " WHERE pll.project_id=? AND pll.status='active'"
        " AND (l.workspace_id=? OR l.is_public=1) ORDER BY ls.id",
        (pid, workspace_id(request))))
    conn.close()
    project = _expose_workspace_record(p, wid)
    ledgers = [_expose_workspace_record(item, wid) for item in linked_ledgers]
    return {"project": project, "nodes": nodes, "edges": edges,
            "provenance": prov, "arguments": args,
            "ledgers": ledgers, "ledger_entries": linked_entries,
            "ledger_sources": linked_ledger_sources}


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
    _project_or_404(conn, pid, request, write=True)
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
    node = conn.execute(
        "SELECT project_id FROM nodes WHERE id=?", (nid,)).fetchone()
    if not node:
        conn.close()
        raise HTTPException(404, "unknown node")
    _project_or_404(conn, node["project_id"], request, write=True)
    conn.execute(f"UPDATE nodes SET {', '.join(fields)}, updated_at=? WHERE id=?", vals)
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/nodes/{nid}")
def delete_node(nid: int, request: Request):
    conn = get_conn()
    node = conn.execute("SELECT project_id FROM nodes WHERE id=?", (nid,)).fetchone()
    if not node:
        conn.close()
        raise HTTPException(404, "unknown node")
    _project_or_404(conn, node["project_id"], request, write=True)
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
    _project_or_404(conn, pid, request, write=True)
    src = conn.execute("SELECT project_id FROM nodes WHERE id=?", (int(b["src"]),)).fetchone()
    dst = conn.execute("SELECT project_id FROM nodes WHERE id=?", (int(b["dst"]),)).fetchone()
    if not src or not dst or src["project_id"] != pid or dst["project_id"] != pid:
        conn.close()
        raise HTTPException(400, "edge endpoints must belong to the project")
    cur = conn.execute(
        "INSERT INTO edges(project_id, src, dst, rel, created_at) VALUES(?,?,?,?,?)",
        (pid, int(b["src"]), int(b["dst"]), b["rel"], now()))
    conn.commit()
    eid = cur.lastrowid
    conn.close()
    return {"id": eid}


@app.delete("/api/edges/{eid}")
def delete_edge(eid: int, request: Request):
    conn = get_conn()
    edge = conn.execute("SELECT project_id FROM edges WHERE id=?", (eid,)).fetchone()
    if not edge:
        conn.close()
        raise HTTPException(404, "unknown edge")
    _project_or_404(conn, edge["project_id"], request, write=True)
    conn.execute("DELETE FROM edges WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/nodes/{nid}/provenance")
async def add_provenance(nid: int, request: Request):
    b = await request.json()
    conn = get_conn()
    node = conn.execute("SELECT project_id FROM nodes WHERE id=?", (nid,)).fetchone()
    if not node:
        conn.close()
        raise HTTPException(404, "unknown node")
    _project_or_404(conn, node["project_id"], request, write=True)
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

def _argument_or_404(conn, aid: int, request: Request | None = None,
                     write: bool = False):
    if request is None:
        a = conn.execute("SELECT * FROM arguments WHERE id=?", (aid,)).fetchone()
    else:
        wid = workspace_id(request)
        visibility = "p.workspace_id=?" if write else "(p.workspace_id=? OR p.is_public=1)"
        a = conn.execute(
            "SELECT a.* FROM arguments a JOIN projects p ON p.id=a.project_id "
            f"WHERE a.id=? AND {visibility}", (aid, wid)).fetchone()
    if not a:
        raise HTTPException(404, "unknown argument id")
    return a


@app.get("/api/projects/{pid}/arguments")
def list_arguments(pid: int, request: Request):
    conn = get_conn()
    _project_or_404(conn, pid, request)
    data = _load_arguments(conn, pid)
    conn.close()
    return data


@app.post("/api/projects/{pid}/arguments")
async def create_argument(pid: int, request: Request):
    b = await request.json()
    if not b.get("title", "").strip():
        raise HTTPException(400, "title required")
    conn = get_conn()
    _project_or_404(conn, pid, request, write=True)
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
def get_argument(aid: int, request: Request):
    conn = get_conn()
    a = dict(_argument_or_404(conn, aid, request))
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
    _argument_or_404(conn, aid, request, write=True)
    conn.execute(f"UPDATE arguments SET {', '.join(fields)}, updated_at=? WHERE id=?",
                 vals)
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/arguments/{aid}")
def delete_argument(aid: int, request: Request):
    conn = get_conn()
    _argument_or_404(conn, aid, request, write=True)
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
    _argument_or_404(conn, aid, request, write=True)
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
    _argument_or_404(conn, pr["argument_id"], request, write=True)
    conn.execute(f"UPDATE argument_premises SET {', '.join(fields)} WHERE id=?", vals)
    conn.execute("UPDATE arguments SET updated_at=? WHERE id=?",
                 (now(), pr["argument_id"]))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/premises/{prid}")
def delete_premise(prid: int, request: Request):
    conn = get_conn()
    pr = conn.execute("SELECT argument_id FROM argument_premises WHERE id=?",
                      (prid,)).fetchone()
    if not pr:
        conn.close()
        raise HTTPException(404, "unknown premise id")
    _argument_or_404(conn, pr["argument_id"], request, write=True)
    conn.execute("DELETE FROM argument_premises WHERE id=?", (prid,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/arguments/{aid}/premises/reorder")
async def reorder_premises(aid: int, request: Request):
    b = await request.json()
    order = b.get("order") or []
    conn = get_conn()
    _argument_or_404(conn, aid, request, write=True)
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
    a = dict(_argument_or_404(conn, aid, request, write=False))
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
                                "hidden_premise", sys_p, user, a["project_id"],
                                workspace=workspace_id(request))
    except Exception as e:
        return {"level2": {"error": f"{type(e).__name__}: {e}"}}
    return {"level2": out, "notice": "unverified"}


# ---------- export (axiom 7: exit-ability) ----------

TYPE_ORDER = ("question", "claim", "evidence", "counterclaim", "interpretation",
              "uncertainty", "decision", "source", "note")


@app.get("/api/projects/{pid}/export.md", response_class=PlainTextResponse)
def export_md(pid: int, request: Request):
    g = project_graph(pid, request)
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
    if g.get("ledgers"):
        lines += ["## 参照研究台帳", ""]
        for ledger in g["ledgers"]:
            lines.append(f"### {ledger['title']}")
            lines.append(f"- ledger_id: `{ledger['id']}` | role: **{ledger['role']}**"
                         f" | pinned_version: **{ledger['pinned_version']}**"
                         f" | current_version: **{ledger['version']}**")
            lines.append(f"- status: {ledger['link_status']} | linked: {ledger['linked_at']}")
            if ledger.get("link_note"):
                lines.append(f"- note: {ledger['link_note']}")
            lines.append("")
        if g.get("ledger_entries"):
            lines.append("### 採用した台帳エントリ")
            for entry in g["ledger_entries"]:
                lines.append(f"- [{entry['ledger_title']}#{entry['entry_id']}] {entry['title']}"
                             f" — relation: **{entry['relation']}**, adopted_version: **{entry['adopted_version']}**"
                             f" (current: {entry['current_version']})")
                if entry.get("use_note"):
                    lines.append(f"  - use note: {entry['use_note']}")
            lines.append("")
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
    if g.get("ledger_sources"):
        lines.append("## 台帳由来の参照資料")
        for source in g["ledger_sources"]:
            label = source["source_name"] or source["source_url"] or source["external_id"]
            lines.append(f"- {label} ({source['source_url']}) retrieved {source['retrieved_at']}"
                         + (f" @ {source['locator']}" if source.get("locator") else ""))
        lines.append("")
    return "\n".join(lines)


@app.get("/api/projects/{pid}/export.jsonld")
def export_jsonld(pid: int, request: Request):
    g = project_graph(pid, request)
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
    for ledger in g.get("ledgers", []):
        graph.append({"@id": f"ledger:{ledger['id']}", "@type": "ResearchLedger",
                      "title": ledger["title"], "role": ledger["role"],
                      "pinnedVersion": ledger["pinned_version"],
                      "currentVersion": ledger["version"]})
    for entry in g.get("ledger_entries", []):
        graph.append({"@id": f"ledger-entry:{entry['entry_id']}", "@type": "LedgerEntry",
                      "title": entry["title"], "kind": entry["kind"],
                      "ledger": f"ledger:{entry['ledger_id']}",
                      "relation": entry["relation"],
                      "adoptedVersion": entry["adopted_version"],
                      "currentVersion": entry["current_version"]})
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
    for source in g.get("ledger_sources", []):
        add(source.get("source_name", ""), source.get("source_url", ""),
            source.get("retrieved_at", ""), source.get("quote", ""),
            source.get("locator", ""), source.get("source_name", ""))
    return list(seen.values())


@app.get("/api/projects/{pid}/export.bib", response_class=PlainTextResponse)
def export_bib(pid: int, request: Request):
    g = project_graph(pid, request)
    return bibliography.to_bibtex(_collect_refs(g), project=g["project"]["title"])


@app.get("/api/projects/{pid}/export.csl.json")
def export_csl(pid: int, request: Request):
    g = project_graph(pid, request)
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
    project_id = b.get("project_id")
    if project_id:
        try:
            project_id = int(project_id)
        except (TypeError, ValueError):
            raise HTTPException(400, "project_id must be an integer")
        conn = get_conn()
        _project_or_404(conn, project_id, request)
        conn.close()

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
                "counterargument", sys_p, claim, project_id,
                workspace=workspace_id(request))
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
                             f"reading_level:{level}", sys_p, concept,
                             workspace=workspace_id(request))


# ---------- watches (dynamic freshness; harvester runs the same code via cron) ----------

@app.get("/api/watches")
def list_watches(request: Request):
    conn = get_conn()
    wid = workspace_id(request)
    data = rows(conn.execute(
        "SELECT w.*, (SELECT COUNT(*) FROM watch_hits h WHERE h.watch_id=w.id AND h.seen=0)"
        " unseen FROM watches w WHERE w.workspace_id=? ORDER BY id DESC",
        (wid,)))
    conn.close()
    return [_expose_workspace_record(item, wid) for item in data]


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
        "INSERT INTO watches(label, kind, openalex_id, query, workspace_id, created_at)"
        " VALUES(?,?,?,?,?,?)",
        (label, kind, openalex_id, b.get("query", label), workspace_id(request), now()))
    conn.commit()
    wid = cur.lastrowid
    conn.close()
    return {"id": wid, "openalex_id": openalex_id}


@app.delete("/api/watches/{wid}")
def delete_watch(wid: int, request: Request):
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM watches WHERE id=? AND workspace_id=?",
                        (wid, workspace_id(request))).fetchone():
        conn.close()
        raise HTTPException(404, "unknown watch")
    conn.execute("DELETE FROM watches WHERE id=? AND workspace_id=?",
                 (wid, workspace_id(request)))
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
async def run_watch(wid: int, request: Request):
    conn = get_conn()
    w = conn.execute("SELECT * FROM watches WHERE id=? AND workspace_id=?",
                     (wid, workspace_id(request))).fetchone()
    conn.close()
    if not w:
        raise HTTPException(404)
    return await check_watch(dict(w))


@app.get("/api/watches/{wid}/hits")
def watch_hits(wid: int, request: Request):
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM watches WHERE id=? AND workspace_id=?",
                        (wid, workspace_id(request))).fetchone():
        conn.close()
        raise HTTPException(404, "unknown watch")
    data = rows(conn.execute(
        "SELECT * FROM watch_hits WHERE watch_id=? ORDER BY found_at DESC LIMIT 100", (wid,)))
    conn.execute("UPDATE watch_hits SET seen=1 WHERE watch_id=?", (wid,))
    conn.commit()
    conn.close()
    return data


# ---------- AI transparency ledger (axiom 6) ----------

@app.get("/api/ledger")
def ai_ledger(request: Request):
    conn = get_conn()
    wid = workspace_id(request)
    data = rows(conn.execute(
        "SELECT * FROM ai_ledger WHERE workspace_id=?"
        " ORDER BY id DESC LIMIT 200", (wid,)))
    conn.close()
    return [_expose_workspace_record(item, wid, can_edit=False) for item in data]
