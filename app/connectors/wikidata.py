"""Wikidata connector — free, keyless, the identity backbone (QIDs)."""
from .base import cached_get_json, ok, err, now

API = "https://www.wikidata.org/w/api.php"
ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"

PROPS = {
    # Life and identity
    "P569": "born", "P570": "died", "P19": "place_of_birth",
    "P20": "place_of_death", "P106": "occupation", "P742": "pseudonym",
    # Intellectual position and works
    "P101": "field_of_work", "P135": "movement", "P136": "genre",
    "P800": "notable_work", "P407": "original_language",
    "P577": "publication_date", "P50": "author",
    # Relations useful for a cautious intellectual-lineage view
    "P737": "influenced_by", "P1412": "languages_spoken",
    "P69": "educated_at", "P551": "residence",
}

ENTITY_LANGUAGES = "ja|en|da|de|fr|el|grc|la|zh|ru|es|it|pt|nl|sv|no"


async def search(q: str, lang: str = "en", limit: int = 8) -> dict:
    try:
        body, ts, cached = await cached_get_json(API, {
            "action": "wbsearchentities", "search": q, "language": lang,
            "uselang": lang, "format": "json", "limit": limit, "type": "item"})
        hits = [{"qid": h["id"], "label": h.get("label", ""),
                 "description": h.get("description", ""),
                 "url": f"https://www.wikidata.org/wiki/{h['id']}"}
                for h in body.get("search", [])]
        return ok("wikidata", ts, cached, hits)
    except Exception as e:
        return err("wikidata", e)


def _claim_ids(entity: dict, prop: str) -> list:
    out = []
    for c in entity.get("claims", {}).get(prop, []):
        try:
            v = c["mainsnak"]["datavalue"]["value"]
            if isinstance(v, dict) and "id" in v:
                out.append(v["id"])
            elif isinstance(v, dict) and "time" in v:
                out.append(v["time"].lstrip("+")[:10])
        except (KeyError, TypeError):
            continue
    return out


def _entity_data(qid: str, ent: dict, lang: str = "en") -> dict:
    """Normalize one Wikidata item for both single and batched reads.

    Labels and aliases are returned as raw, language-keyed evidence.  The
    application decides how to group or display them; the connector must not
    collapse a Japanese alias into an English translation here.
    """
    labels = ent.get("labels", {}) or {}
    descs = ent.get("descriptions", {}) or {}
    sitelinks = ent.get("sitelinks", {}) or {}
    claims_raw = {name: _claim_ids(ent, pid) for pid, name in PROPS.items()}
    aliases = {
        lg: [x.get("value", "") for x in values if x.get("value")]
        for lg, values in (ent.get("aliases", {}) or {}).items()
    }
    label_map = {lg: value.get("value", "")
                 for lg, value in labels.items() if value.get("value")}
    wikipedia_codes = set(ENTITY_LANGUAGES.split("|"))
    wikipedia = {k[:-4]: v["title"]
                 for k, v in sitelinks.items()
                 if k.endswith("wiki") and k[:-4] in wikipedia_codes}
    wikisource = {k.replace("wikisource", ""): v["title"]
                  for k, v in sitelinks.items() if k.endswith("wikisource")}
    return {
        "qid": qid,
        "label": (labels.get(lang) or labels.get("en") or {}).get("value", qid),
        "label_en": (labels.get("en") or labels.get(lang) or {}).get("value", ""),
        "description": (descs.get(lang) or descs.get("en") or {}).get("value", ""),
        "is_person": "Q5" in _claim_ids(ent, "P31"),
        "instance_of": _claim_ids(ent, "P31"),
        "labels": label_map,
        "aliases": aliases,
        "orig_labels": {lg: label_map[lg] for lg in (
            "en", "de", "fr", "el", "grc", "la", "it", "da")
                        if lg in label_map},
        "claims": claims_raw,
        "wikipedia": wikipedia,
        "wikisource": wikisource,
        "url": f"https://www.wikidata.org/wiki/{qid}",
    }


async def entity(qid: str, lang: str = "en") -> dict:
    try:
        body, ts, cached = await cached_get_json(ENTITY.format(qid=qid), ttl=86400)
        ent = body["entities"][qid]
        data = _entity_data(qid, ent, lang)
        return ok("wikidata", ts, cached, data)
    except Exception as e:
        return err("wikidata", e)


async def batch_entities(qids: list, lang: str = "en") -> dict:
    """Fetch a bounded set of item records in one request.

    Person dossiers need work titles and intellectual relations.  Resolving
    every QID one by one created a sparse, slow surface, so this is the shared
    identity/work expansion path.  It remains best-effort: a failed batch is a
    visible empty enrichment, never an invented biography.
    """
    ids = list(dict.fromkeys(str(q) for q in (qids or [])
                             if str(q).startswith("Q")))[:50]
    if not ids:
        return ok("wikidata", now(), False, [])
    try:
        body, ts, cached = await cached_get_json(API, {
            "action": "wbgetentities", "ids": "|".join(ids),
            "props": "labels|aliases|descriptions|claims|sitelinks",
            "languages": ENTITY_LANGUAGES, "format": "json"}, ttl=86400)
        entities = body.get("entities", {}) or {}
        data = [_entity_data(qid, entities[qid], lang)
                for qid in ids if qid in entities]
        return ok("wikidata", ts, cached, data)
    except Exception as e:
        return err("wikidata", e)


async def resolve_labels(qids: list, lang: str = "en") -> dict:
    """Batch-resolve QID labels (best effort)."""
    if not qids:
        return {}
    try:
        body, _, _ = await cached_get_json(API, {
            "action": "wbgetentities", "ids": "|".join(qids[:50]),
            "props": "labels", "languages": f"{lang}|en", "format": "json"}, ttl=86400)
        out = {}
        for qid, ent in body.get("entities", {}).items():
            lb = ent.get("labels", {})
            out[qid] = (lb.get(lang) or lb.get("en") or {}).get("value", qid)
        return out
    except Exception:
        return {q: q for q in qids}
