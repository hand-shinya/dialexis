"""哲学典拠への解決（2026-09-28・半田様提案）。

ja.wikipedia の記事名と opensearch 順位を一次の解決器にしていたため、哲学語が
無関係な項目へ吸い寄せられていた。実測（2026-09-28・基準値42語）:

    対象化   → 対象関係論（Q1399895）
    間主観   → ロバート・ストロロウ（Q3656697・精神分析家）
    間主観性  → ロバート・ストロロウ（Q3656697）
    非有機的肉体／非有機的身体／仮象 → 解決できず

一方 Wikidata は正しい項目を持ち、SEP は英語名で正しい典拠を返す。

    間主観性 → Q583467 → intersubjectivity → SEP: Alfred Schutz / Edmund Husserl
    物象化  → Q863448 → reification      → SEP: Georg Lukács
    無常   → Q129261421 → anitya        → SEP: Abhidharma
    縁起   → Q522046 → pratītyasamutpāda → SEP: Śāntarakṣita

SEP は日本語入力では破綻する（間主観性 → Zhu Xi）。したがって Wikidata を
ja→原語/英語の橋として使い、典拠本体は SEP に置く。

このモジュールは単独で完結する。既存の concept.py／node() の解決経路には手を入れず、
呼び出し側が「弱い解決」と判断したときだけ併せて使う（回帰面を最小にする）。
返すのは候補であり、項目の存在は語義の同一性を証明しない（P6）。
"""
from . import sep, wikidata
from .base import err, now, ok

# 原語をそのまま見せるための言語（この順で拾う）。翻訳ではなく原語の提示が目的。
ORIG_LANGS = ("de", "grc", "la", "el", "fr", "sa", "pi", "zh", "it", "en")

# 語の項目として採らない種別。表記が重なるだけで論文や曖昧さ回避ページを拾うのを防ぐ
# （Entfremdung が論文 "Entfremdung, Verfremdung: Alienation, Estrangement" に一致した）。
NOT_A_TERM = {
    "Q13442814",   # scholarly article
    "Q4167410",    # Wikimedia disambiguation page
    "Q13406463",   # Wikimedia list article
    "Q17442446",   # Wikimedia internal item
    "Q571",        # book
    "Q7725634",    # literary work
    "Q11424",      # film
    "Q134556",     # single
    "Q7366",       # song
    "Q482994",     # album
}


def _looks_like_a_term(label: str, word: str) -> bool:
    """項目名が「語」として妥当な長さか。題名は語ではない。"""
    label, word = (label or "").strip(), (word or "").strip()
    if not label:
        return False
    # 題名は語より極端に長い。閾値は語長に比例させ、短い語でも余裕を持たせる。
    return len(label) <= max(len(word) * 3, len(word) + 8)


def _overlaps(a: str, b: str) -> bool:
    """表記が重なるか。間主観 ↔ 間主観性 を同族と見なすための最小判定。"""
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return False
    return a == b or a in b or b in a


async def pick_item(word: str, lang: str = "ja") -> dict | None:
    """Wikidata から、表記が問いと重なる非人物の項目を選ぶ。

    無関係な上位ヒットは採らない。人物項目も採らない（P8 語と著者は別次元）。
    該当が無ければ None を返し、呼び出し側の既存経路をそのまま使わせる。
    """
    try:
        res = await wikidata.search(word, lang, limit=8)
        if res.get("error"):
            return None
        hits = [h for h in (res.get("data") or [])
                if _overlaps(word, str(h.get("label") or ""))]
        if not hits:
            return None
        batch = await wikidata.batch_entities([h.get("qid") for h in hits][:8], lang)
        if batch.get("error"):
            return None
        by_qid = {e.get("qid"): e for e in (batch.get("data") or [])}
        for h in hits:
            ent = by_qid.get(h.get("qid"))
            if not ent or ent.get("is_person"):
                continue
            # wikidata._entity_data は ja/en のラベルが無いとき label に QID を入れる。
            # それを解決名として見せると利用者には「Q121180776」と出る。人間可読な
            # ラベルを持たない項目は採らない（外化・Entfremdung で実際に起きた）。
            lb = str(ent.get("label") or "")
            if not lb or lb == ent.get("qid"):
                continue
            if set(ent.get("instance_of") or []) & NOT_A_TERM:
                continue
            if not _looks_like_a_term(lb, word):
                continue
            return ent
    except Exception:
        return None
    return None


def original_labels(ent: dict) -> list:
    """項目の原語表記を、言語つきで並べる。翻訳語ではなく原語を見せるための層。"""
    labels = (ent or {}).get("labels") or {}
    out = []
    for code in ORIG_LANGS:
        v = labels.get(code)
        if v:
            out.append({"lang": code, "term": v})
    return out


async def resolve(word: str, lang: str = "ja") -> dict:
    """ja語 → Wikidata項目 → 原語/英語名 → SEP の典拠。

    どの段も欠けうる。欠けた段は空で返し、埋めた推測を混ぜない（P6・公理3）。
    """
    try:
        ent = await pick_item(word, lang)
        if not ent:
            return ok("canon", now(), False, {
                "query": word, "matched": False, "item": None,
                "original_terms": [], "canon_entries": [],
                "note": "Wikidataに、表記が問いと重なる非人物の項目を見つける段まで到達していない。"
                        "既存の記事経路の結果をそのまま使う",
            })
        labels = ent.get("labels") or {}
        en = labels.get("en") or ent.get("label_en") or ""
        entries = []
        if en:
            s = await sep.search(en, limit=5)
            if not s.get("error"):
                for h in (s.get("data") or []):
                    if isinstance(h, dict) and h.get("title"):
                        entries.append({
                            "authority": "Stanford Encyclopedia of Philosophy",
                            "title": h.get("title"), "url": h.get("url") or "",
                            "evidence": "candidate",
                            "note": "英語名で照会した典拠候補。項目がこの語を論じている"
                                    "ことの確認は本文で行う",
                        })
        return ok("canon", now(), False, {
            "query": word,
            "matched": True,
            "item": {"qid": ent.get("qid"), "label": ent.get("label"),
                     "label_en": en, "description": ent.get("description"),
                     "url": ent.get("url") or f"https://www.wikidata.org/wiki/{ent.get('qid')}"},
            "original_terms": original_labels(ent),
            "canon_entries": entries,
            "wikipedia": ent.get("wikipedia") or {},
            "note": "解決の一次を記事名からWikidata項目へ移し、典拠はSEPで確かめる経路。"
                    "項目の存在は語義の同一性を証明しない",
        })
    except Exception as e:
        return err("canon", e)
