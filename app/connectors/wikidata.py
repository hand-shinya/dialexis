"""Wikidata connector — free, keyless, the identity backbone (QIDs)."""
from .base import cached_get_json, ok, err

API = "https://www.wikidata.org/w/api.php"
ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"

PROPS = {
    "P569": "born", "P570": "died", "P106": "occupation",
    "P800": "notable_work", "P135": "movement", "P737": "influenced_by",
}


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


async def entity(qid: str, lang: str = "en") -> dict:
    try:
        body, ts, cached = await cached_get_json(ENTITY.format(qid=qid), ttl=86400)
        ent = body["entities"][qid]
        labels = ent.get("labels", {})
        descs = ent.get("descriptions", {})
        sitelinks = ent.get("sitelinks", {})
        claims_raw = {name: _claim_ids(ent, pid) for pid, name in PROPS.items()}
        # instance_of (P31) tells us person vs concept; used to route scholarly search.
        instance_of = _claim_ids(ent, "P31")
        data = {
            "qid": qid,
            "label": (labels.get(lang) or labels.get("en") or {}).get("value", qid),
            # English label is the canonical term for scholarly APIs (fixes CJK
            # queries: 存在/自由 search OpenAlex as the resolved concept, not the raw word).
            "label_en": (labels.get("en") or labels.get(lang) or {}).get("value", ""),
            "description": (descs.get(lang) or descs.get("en") or {}).get("value", ""),
            "is_person": "Q5" in instance_of,
            # raw P31 class QIDs — lets the resolver tell a concept from a
            # same-named song/name (freedom → 2016 Beyoncé single).
            "instance_of": instance_of,
            # Original-language labels in scholarly languages — the raw material
            # for naming the source-language term(s) in a deep-search prompt
            # (間主観 → Intersubjektivität; 疎外 → Entfremdung).
            "orig_labels": {lg: labels[lg]["value"]
                            for lg in ("en", "de", "fr", "el", "grc", "la", "it")
                            if lg in labels and labels[lg].get("value")},
            "claims": claims_raw,
            "wikipedia": {k.replace("wiki", ""): v["title"]
                          for k, v in sitelinks.items()
                          if k.endswith("wiki") and k[:-4] in ("en", "ja", "de", "fr", "el", "zh")},
            "wikisource": {k.replace("wikisource", ""): v["title"]
                           for k, v in sitelinks.items() if k.endswith("wikisource")},
            "url": f"https://www.wikidata.org/wiki/{qid}",
        }
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
