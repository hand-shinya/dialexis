"""つながりの根拠 — 地図の中心の語と、選んだ語が、なぜつながっているのかを実際の文で示す。

2026-10-20 所有者の指摘: 関係パネルが定型文だけで、ヘーゲルと疎外がなぜつながるのかが一行も無い。
共起語（entgegenwirken）を押すと、その語だけで検索し直して行き止まりになる。

ここでは意味を生成しない（D16・D36: LLM を使わない）。Wikipedia の本文から、
  ・中心の語の記事の中で、選んだ語（人名・著作名など）が出てくる文
  ・選んだ語の記事の中で、中心の語（またはその原語）が出てくる文
  ・2語を一緒に使っている文（全文検索の抜粋。共起語の組を、組のまま見せる）
を抜き出して、記事名・URL・取得時刻と一緒に返すだけである。見つからないことは「つながりが無い」
ことではない（取れた範囲を正直に示す）。
"""
import re

from .base import cached_get_json, now

WP_API = "https://{lang}.wikipedia.org/w/api.php"
_SENT_JA = re.compile(r"(?<=[。！？])")
_SENT_EU = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ„\"(])")


async def article_text(title: str, lang: str):
    """記事の本文（平文）。戻り値: (正式な記事名, 本文, 取得時刻)。無ければ (None, "", 時刻)。"""
    body, ts, _ = await cached_get_json(WP_API.format(lang=lang), {
        "action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "plain",
        "titles": title, "redirects": 1, "format": "json", "formatversion": 2}, ttl=7 * 86400)
    pages = (body.get("query") or {}).get("pages") or []
    pg = pages[0] if pages else {}
    if pg.get("missing") or not pg.get("extract"):
        return None, "", ts
    return pg.get("title"), pg["extract"], ts


def sentences(text: str, lang: str) -> list:
    out = []
    for para in (text or "").split("\n"):
        para = para.strip()
        if not para:
            continue
        parts = _SENT_JA.split(para) if lang in ("ja", "zh") else _SENT_EU.split(para)
        out.extend(p.strip() for p in parts if p.strip())
    return out


def name_forms(name: str) -> list:
    """人名・著作名の、本文に現れやすい形。G.W.F. ヘーゲル → ヘーゲル、経済学・哲学草稿（1844年）→ 経済学・哲学草稿。"""
    n = re.sub(r"[（(][^）)]*[）)]\s*$", "", (name or "").strip()).strip()
    forms = [n]
    if re.search(r"[ァ-ヶー]", n) and re.search(r"[・ 　]", n):
        last = re.split(r"[・ 　]", n)[-1]
        if len(last) >= 2:
            forms.append(last)
    elif re.fullmatch(r"[A-Za-zÀ-ÿ.\- ]+", n) and " " in n:
        forms.append(n.split()[-1])
    return [f for f in dict.fromkeys(forms) if len(f) >= 2]


def _hits(sents: list, forms: list, limit: int) -> list:
    out = []
    for s in sents:
        if len(s) < 15:   # 見出しだけの行（「マルクスによる概念」）は文として数えない
            continue
        if any(f in s for f in forms):
            out.append(s if len(s) <= 260 else s[:257] + "…")
            if len(out) >= limit:
                break
    return out


async def evidence(center: str, target: str, lang: str = "ja", target_title: str | None = None,
                   center_alts: list | None = None, limit: int = 4) -> dict:
    """中心の語と選んだ語のつながりの根拠（文・記事・取得時刻）。"""
    out = {"center": center, "target": target, "lang": lang, "forward": None, "backward": None,
           "errors": [], "queried_at": now()}
    tforms = name_forms(target)
    cforms = [f for f in dict.fromkeys([center] + list(center_alts or [])) if f and len(f) >= 2]
    try:
        ct, ctext, cts = await article_text(center, lang)
        if ct:
            hits = _hits(sentences(ctext, lang), tforms, limit)
            out["forward"] = {"article": ct, "url": f"https://{lang}.wikipedia.org/wiki/{ct}",
                              "retrieved_at": cts, "sentences": hits, "looked_for": tforms}
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"center:{type(e).__name__}")
    try:
        tt, ttext, tts = await article_text(target_title or tforms[0] if tforms else target, lang)
        if not tt and len(tforms) > 1:
            tt, ttext, tts = await article_text(tforms[-1], lang)
        if tt:
            hits = _hits(sentences(ttext, lang), cforms, limit)
            out["backward"] = {"article": tt, "url": f"https://{lang}.wikipedia.org/wiki/{tt}",
                               "retrieved_at": tts, "sentences": hits, "looked_for": cforms}
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"target:{type(e).__name__}")
    return out


async def pair_usage(a: str, b: str, lang: str = "de", limit: int = 6) -> dict:
    """2語を一緒に使っている文（Wikipedia 全文検索の抜粋）。共起語を組のまま見せるため。"""
    out = {"a": a, "b": b, "lang": lang, "examples": [], "total": None, "error": None,
           "search_url": f"https://{lang}.wikipedia.org/w/index.php?search=%22{a}%22+{b}&ns0=1",
           "queried_at": now()}
    stem = lambda w: w[:max(4, len(w) - 2)].lower()   # entgegenwirken → entgegenwirk（活用形も拾う）
    try:
        body, ts, _ = await cached_get_json(WP_API.format(lang=lang), {
            "action": "query", "list": "search", "srsearch": f'"{a}" {b}', "srlimit": 20,
            "srprop": "snippet", "format": "json"}, ttl=7 * 86400)
        out["retrieved_at"] = ts
        out["total"] = ((body.get("query") or {}).get("searchinfo") or {}).get("totalhits")
        for x in (body.get("query") or {}).get("search") or []:
            snip = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x.get("snippet") or "")).strip()
            low = snip.lower()
            if stem(a) in low and stem(b) in low:   # 抜粋の中に2語とも在るものだけ（同じ記事の別の所は数えない）
                out["examples"].append({"text": snip, "article": x["title"],
                                        "url": f"https://{lang}.wikipedia.org/wiki/{x['title'].replace(' ', '_')}"})
                if len(out["examples"]) >= limit:
                    break
    except Exception as e:  # noqa: BLE001
        out["error"] = type(e).__name__
    return out
