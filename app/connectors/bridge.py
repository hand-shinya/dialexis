"""文 → 哲学概念の候補（2026-10-15・隔離試作。本番には入れていない）。

/api/origin が文を記事名として引いて着かなかったとき（found=false）に、候補を出所つきで示す。
二つの段を持つ。どちらの候補も、実在の Wikidata 項目に接地できたものだけを出す（作り話を出さない）。

  keyless（Level 0・鍵不要）
    文の漢字・カタカナの語 → ja.wikipedia opensearch、ja 全文検索、Wikidata Vector DB
    （型なし・concept）の和集合を、Wikidata の型と説明文で「概念らしいもの」に絞り、
    合意した源の数で並べる。tools/bridge_lab の方式 C と同じ規則。
  llm（Level 2・利用者の LLM）
    利用者の LLM が ja.wikipedia の記事名を挙げ、この system が接地する。方式 D。
    隔離試験では、利用者の鍵の代わりに環境変数 DIALEXIS_LAB_LLM_CLI=claude の
    手元 CLI を使う（決裁 D46: 試験 harness の model 利用は製品の規範の対象外）。

既知の限界（tools/bridge_lab の実測で書き足す）: 同じ綴りで別の意味の語・辞書に無い言い回し。
"""
import asyncio
import json
import os
import re
import subprocess
import tempfile

from .base import cached_get_json, now

WP = "https://ja.wikipedia.org/w/api.php"
WD = "https://www.wikidata.org/w/api.php"
VDB = "https://wd-vectordb.wmcloud.org/item/query/"
STOP = {"自分", "感じ", "ように", "何", "人", "ため", "こと", "もの", "とき", "よう", "全て", "前", "同じ"}
WORK_PERSON = {"Q5", "Q7366", "Q134556", "Q482994", "Q11424", "Q5398426", "Q571", "Q7725634",
               "Q47461344", "Q215380", "Q5741069", "Q105543609", "Q21191270", "Q1259759",
               "Q15416", "Q3464665", "Q24856", "Q17537576", "Q1344", "Q169930", "Q4167410"}
CONCEPT_CLASSES = {"Q151885", "Q33104279", "Q23847174", "Q17737", "Q12909644", "Q11862829",
                   "Q1047113", "Q7184903", "Q2915981", "Q5891", "Q60539481"}
CONCEPT_DESC = re.compile(r"哲学|概念|思想|倫理|主義|論|学説|心理|価値|philosoph|concept|ethic|theory|doctrine", re.I)


def terms(q):
    t = re.findall(r"[一-龥々]{2,}|[ァ-ヶー]{2,}", q or "")
    return [x for x in dict.fromkeys(t) if x not in STOP]


async def _titles_to_qids(titles):
    out = {}
    for i in range(0, len(titles), 20):
        chunk = titles[i:i + 20]
        try:
            d, _, _ = await cached_get_json(WP, {"action": "query", "prop": "pageprops",
                                                 "titles": "|".join(chunk), "redirects": 1,
                                                 "format": "json"}, ttl=86400)
        except Exception:
            continue
        q = d.get("query", {})
        norm = {x["from"]: x["to"] for x in q.get("normalized", [])}
        red = {x["from"]: x["to"] for x in q.get("redirects", [])}
        by = {p.get("title"): (p.get("pageprops") or {}).get("wikibase_item")
              for p in q.get("pages", {}).values()}
        for t in chunk:
            t2 = norm.get(t, t)
            out[t] = by.get(red.get(t2, t2))
    return out


async def _opensearch(t, n=3):
    try:
        d, _, _ = await cached_get_json(WP, {"action": "opensearch", "search": t, "limit": n,
                                             "namespace": 0, "format": "json"}, ttl=86400)
        return (d[1] if isinstance(d, list) and len(d) > 1 else [])[:n]
    except Exception:
        return []


async def _fulltext(q):
    try:
        d, _, _ = await cached_get_json(WP, {"action": "query", "list": "search", "srsearch": q,
                                             "srlimit": 10, "format": "json"}, ttl=86400)
        return [x["title"] for x in d.get("query", {}).get("search", [])]
    except Exception:
        return []


async def _vector(q, instanceof=None):
    p = {"query": q, "lang": "ja", "K": 10}
    if instanceof:
        p["instanceof"] = instanceof
    try:
        d, _, _ = await cached_get_json(VDB, p, ttl=86400)
        return [x["QID"] for x in d][:10]
    except Exception:
        return []


async def _info(qids):
    out = {}
    for i in range(0, len(qids), 50):
        try:
            d, _, _ = await cached_get_json(WD, {
                "action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
                "props": "claims|labels|descriptions|sitelinks", "languages": "ja|en",
                "format": "json"}, ttl=86400)
        except Exception:
            continue
        for q, e in (d.get("entities") or {}).items():
            p31 = [((c.get("mainsnak") or {}).get("datavalue") or {}).get("value", {}).get("id")
                   for c in (e.get("claims") or {}).get("P31", [])]
            descs = e.get("descriptions") or {}
            lab = e.get("labels") or {}
            out[q] = {"p31": [x for x in p31 if x],
                      "desc_ja": (descs.get("ja") or {}).get("value", ""),
                      "desc": " ".join(v.get("value", "") for v in descs.values()),
                      "label": (lab.get("ja") or lab.get("en") or {}).get("value", q),
                      "jawiki": ((e.get("sitelinks") or {}).get("jawiki") or {}).get("title")}
    return out


def _norm(t):
    import unicodedata
    t = unicodedata.normalize("NFKC", t or "")
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t)
    return re.sub(r"[\s・=＝\-－‐の]", "", t).lower()


def _close(a, b):
    import difflib
    na, nb = _norm(a), _norm(b)
    return na == nb or difflib.SequenceMatcher(None, na, nb).ratio() >= 0.85


def conceptish(inf):
    if not inf:
        return False
    p31 = set(inf["p31"])
    if p31 & WORK_PERSON:
        return False
    return bool(p31 & CONCEPT_CLASSES) or bool(CONCEPT_DESC.search(inf["desc"]))


async def keyless(q, limit=8):
    ts = terms(q)
    os_lists = await asyncio.gather(*[_opensearch(t) for t in ts])
    os_titles = list(dict.fromkeys(x for lst in os_lists for x in lst))
    ft_titles, v1, v2 = await asyncio.gather(_fulltext(q), _vector(q), _vector(q, "Q151885"))
    tq = await _titles_to_qids(os_titles + ft_titles)
    pools = {"語の候補": [tq[t] for t in os_titles if tq.get(t)],
             "全文検索": [tq[t] for t in ft_titles if tq.get(t)],
             "意味検索": v1, "意味検索（概念）": v2}
    allq = list(dict.fromkeys(x for v in pools.values() for x in v))
    inf = await _info(allq) if allq else {}
    votes = {}
    for src, lst in pools.items():
        for rank, x in enumerate(lst):
            if conceptish(inf.get(x)) and inf[x].get("jawiki"):
                v = votes.setdefault(x, {"n": 0, "best": 99, "src": []})
                v["n"] += 1
                v["best"] = min(v["best"], rank)
                v["src"].append(src)
    order = sorted(votes, key=lambda x: (-votes[x]["n"], votes[x]["best"]))[:limit]
    return [{"qid": x, "title": inf[x]["jawiki"], "label": inf[x]["label"],
             "why": inf[x]["desc_ja"] or "", "sources": votes[x]["src"], "level": 0}
            for x in order]


PROMPT = """次の日常的な問いに関係する哲学の概念を、日本語版ウィキペディアに実在する記事名そのもので最大8個挙げてください。
対立する立場や、別の文化圏の概念も含めてかまいません。出力は JSON の配列だけにしてください。
形式: [{{"title": "記事名", "reason": "問いとの関係を一文で"}}]
問い: {q}"""


def _lab_cli(prompt):
    eng = os.environ.get("DIALEXIS_LAB_LLM_CLI", "")
    if eng != "claude":
        return None
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run(["claude", "-p", "--restricted", "--strict-mcp-config",
                            "--no-session-persistence", "--tools", "", "--model", "claude-haiku-5-5",
                            "--output-format", "text"], input=prompt, cwd=td,
                           capture_output=True, text=True, timeout=180)
        return r.stdout


async def llm(q, limit=8):
    text = await asyncio.to_thread(_lab_cli, PROMPT.format(q=q))
    if not text:
        return [], "llm_unavailable"
    m = re.search(r"\[[\s\S]*\]", text)
    try:
        arr = json.loads(m.group(0)) if m else []
    except Exception:
        arr = []
    names = [(str(x.get("title", "")).strip(), str(x.get("reason", ""))) for x in arr
             if isinstance(x, dict) and x.get("title")][:limit]
    tq = await _titles_to_qids([n for n, _ in names])
    out, ung = [], []
    for n, why in names:
        qid = tq.get(n)
        if not qid:
            # 引き直しは、表記がほぼ一致し、先が概念らしいときだけ（2026-10-15: 引き直し18件中6件が別物
            # だった。カント倫理学→カントー大学・白い嘘→白い巨塔・持続（哲学）→持続可能な開発目標）
            alt = await _opensearch(n, 1)
            if alt and _close(n, alt[0]):
                q2 = (await _titles_to_qids(alt)).get(alt[0])
                if q2 and conceptish((await _info([q2])).get(q2)):
                    qid, n = q2, alt[0]
        if qid:
            out.append({"qid": qid, "title": n, "label": n, "why": why,
                        "sources": ["あなたの LLM（接地済み）"], "level": 2})
        else:
            ung.append(n)
    return out, ung


async def candidates(q):
    k, (l, ung) = await asyncio.gather(keyless(q), llm(q))
    return {"query": q, "queried_at": now(), "keyless": k, "llm": l,
            "llm_ungrounded": ung if isinstance(ung, list) else [],
            "llm_status": ung if isinstance(ung, str) else "ok"}
