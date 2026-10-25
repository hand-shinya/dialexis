"""原語版の記事から見る（所有者 2026-10-25 承認）。

所有者の提案（10/25）: 日本語圏の情報だけで見ると、翻訳を経たあとの、範囲の限られたものしか見えない。
翻訳される前の、原点に近い言語の情報構造を外から得て使えば、一挙に範囲が広がる。

ここでは機械翻訳を使わない（製品に AI を入れない D16/D36）。原語版の Wikipedia 記事の
  ・節の構成（見出しは原語のまま）
  ・各節の本文がリンクしている項目（言語に依存しない Wikidata の ID で日本語の名前を付ける）
を取り、その項目が日本語版の記事の本文にも在るかを並べる。日本語版に無い項目＝日本語だけでは見えない手がかり。
"""
import re

from .base import cached_get_json, now
from . import concept

WD_API = "https://www.wikidata.org/w/api.php"
WP_API = "https://{lang}.wikipedia.org/w/api.php"
_SKIP_HEAD = re.compile(r"^(references?|notes?|see also|external links|further reading|bibliography|sources|"
                        r"literatur|einzelnachweise|anmerkungen|weblinks|siehe auch|"
                        r"notes et références|références|voir aussi|liens externes|bibliographie|articles connexes|"
                        r"note|bibliografia|voci correlate|collegamenti esterni|referencias|véase también|enlaces externos)$", re.I)


async def _sitelinks(qid):
    body, _, _ = await cached_get_json(WD_API, {"action": "wbgetentities", "ids": qid, "props": "sitelinks|claims",
                                                "format": "json"}, ttl=7 * 86400)
    return (body.get("entities") or {}).get(qid) or {}


def _sections(wikitext):
    """wikitext を == 見出し == で分ける。[(見出し, 本文)]。最初の節は導入（見出しなし）。"""
    body = concept._strip_templates(wikitext)
    parts = re.split(r"^(={2,3})\s*(.+?)\s*\1\s*$", body, flags=re.M)
    out = [("", parts[0])]
    for i in range(1, len(parts) - 2, 3):
        head = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]|'''?|<[^>]+>", r"\1", parts[i + 1]).strip()
        out.append((head, parts[i + 2]))
    return out


def _links(text):
    out = []
    for m in re.findall(r"\[\[([^\]|#]+)", text):
        t = m.strip().replace("_", " ")
        # 年・日付（1662・14. September・March 3）は手がかりにならないので外す
        if t and ":" not in t[:14] and not re.match(r"^\d", t) and not re.fullmatch(r"[A-Za-zÀ-ÿ]+ \d{1,2}", t):
            out.append(t[:1].upper() + t[1:])
    return list(dict.fromkeys(out))


async def _qids_of(titles, lang):
    """記事名 → Wikidata の ID（転送を辿る）。"""
    res = {}
    for i in range(0, len(titles), 50):
        pp, _, _ = await cached_get_json(WP_API.format(lang=lang), {
            "action": "query", "prop": "pageprops", "titles": "|".join(titles[i:i + 50]), "redirects": 1,
            "format": "json"}, ttl=7 * 86400)
        q = pp.get("query") or {}
        final = {pg.get("title"): (pg.get("pageprops") or {}).get("wikibase_item") for pg in (q.get("pages") or {}).values()}
        hop = {m.get("from"): m.get("to") for m in (q.get("normalized") or []) + (q.get("redirects") or [])}
        for t in titles[i:i + 50]:
            x, guard = t, 0
            while x in hop and guard < 4:
                x, guard = hop[x], guard + 1
            if final.get(x):
                res[t] = final[x]
    return res


async def _ja_names(qids):
    out = {}
    ids = list(dict.fromkeys(qids))
    for i in range(0, len(ids), 50):
        body, _, _ = await cached_get_json(WD_API, {"action": "wbgetentities", "ids": "|".join(ids[i:i + 50]),
                                                    "props": "labels|sitelinks/urls", "languages": "ja",
                                                    "sitefilter": "jawiki", "format": "json"}, ttl=7 * 86400)
        for q, e in (body.get("entities") or {}).items():
            lab = ((e.get("labels") or {}).get("ja") or {}).get("value", "")
            ja_title = ((e.get("sitelinks") or {}).get("jawiki") or {}).get("title", "")
            out[q] = {"ja": lab or ja_title, "ja_article": ja_title}
    return out


async def view(word: str, src_lang: str = "") -> dict:
    cn = await concept.node(word, "ja")
    cd = (cn or {}).get("data") or {}
    qid, ja_title = cd.get("qid"), cd.get("title")
    if not cd.get("found") or not qid:
        return {"applies": False, "reason": "no-item"}
    ent = await _sitelinks(qid)
    sl = {m.group(1): v.get("title") for k, v in (ent.get("sitelinks") or {}).items()
          for m in [re.fullmatch(r"([a-z]{2,3})wiki", k)] if m}
    # 原語の選び方: 著作は原題の言語、それ以外は記事が示す原語（独: Entfremdung など）、無ければ英語
    from .title_lineage import _lang_code, _val, _LANG_NAME
    cl = ent.get("claims") or {}
    orig, orig_by = "", ""
    t1476 = [_val(c) for c in cl.get("P1476") or []]
    if t1476 and isinstance(t1476[0], dict):
        orig = t1476[0].get("language", "")
        orig_by = "work" if orig else ""
    if not orig:
        lq = next((v.get("id") for v in (_val(c) for c in cl.get("P407") or []) if isinstance(v, dict)), "")
        orig = await _lang_code(lq) if lq else ""
        orig_by = "work" if orig else ""
    if not orig:
        name2code = {v: k for k, v in _LANG_NAME.items()}
        orig = next((name2code.get(o.get("name")) for o in (cd.get("original_terms") or []) if name2code.get(o.get("name"))), "")
        orig_by = "lead" if orig else ""   # 日本語版の記事の冒頭が挙げる言語（独: Entfremdung）。語の起源の言語とは限らない
    choices = [l for l in ["en", "de", "fr", "it", "es", "ru", "la", "zh", "el"] if l in sl and l != "ja"]
    if orig and orig in sl and orig not in choices:
        choices.insert(0, orig)
    lang = src_lang if (src_lang and src_lang in sl and src_lang != "ja") else (orig if orig in sl and orig != "ja" else (choices[0] if choices else ""))
    if not lang:
        return {"applies": False, "reason": "no-other-language", "qid": qid}
    title = sl[lang]
    try:
        d, at, _ = await cached_get_json(WP_API.format(lang=lang), {"action": "parse", "page": title, "prop": "wikitext",
                                                                    "redirects": 1, "format": "json"}, ttl=86400)
    except Exception as e:  # noqa: BLE001
        return {"applies": False, "reason": f"{type(e).__name__}", "qid": qid}
    w = (((d.get("parse") or {}).get("wikitext") or {}).get("*")) or ""
    secs = [(h, _links(t)) for h, t in _sections(w) if not _SKIP_HEAD.match(h or "")]
    secs = [(h, ls) for h, ls in secs if ls][:16]
    all_titles = list(dict.fromkeys(t for _, ls in secs for t in ls[:14]))[:220]
    qmap = await _qids_of(all_titles, lang)
    names = await _ja_names(list(qmap.values()))
    # 日本語版の記事の本文に在る項目（同じ ID）
    ja_body = set()
    if ja_title:
        try:
            for v in await concept._article_resolved(ja_title, "ja"):
                if v.get("in_body"):
                    ja_body.add(v["qid"])
        except Exception:  # noqa: BLE001
            ja_body = set()
    out_secs, seen, n_all, n_ja = [], set(), 0, 0
    for h, ls in secs:
        items = []
        for t in ls[:14]:
            q = qmap.get(t)
            if q == qid:
                continue
            nm = names.get(q, {}) if q else {}
            first = q not in seen if q else True
            if q:
                seen.add(q)
            in_ja = bool(q and q in ja_body)
            if first and q:
                n_all += 1
                n_ja += int(in_ja)
            items.append({"orig": t, "qid": q or "", "ja": nm.get("ja", ""), "ja_article": nm.get("ja_article", ""),
                          "in_ja_article": in_ja, "repeat": not first})
        if items:
            out_secs.append({"heading": h, "items": items})
    return {"applies": True, "qid": qid, "lang": lang, "lang_name": _LANG_NAME.get(lang, lang), "title": title,
            "url": f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}", "retrieved_at": at,
            "orig_lang": orig, "orig_by": orig_by, "ja_title": ja_title or "", "choices": [{"lang": l, "lang_name": _LANG_NAME.get(l, l)} for l in choices],
            "sections": out_secs, "counts": {"items": n_all, "in_ja": n_ja, "only_here": n_all - n_ja},
            "queried_at": now()}
