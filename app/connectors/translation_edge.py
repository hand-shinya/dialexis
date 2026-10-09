"""訳語辺 — 日本語の訳語から、同一語義枠に並ぶ原語へ（2026-10-02）。

所有者の指摘を受けて作った。逐語で引く。

    すでにウェブ上に様々な我々のsystemにとって有益な情報やsystemが存在しているのに、
    それをあえて使わないという選択肢を取っていること自体が大問題だ。

この module が存在する理由は、まさにその失敗の是正である。実際に起きた失敗:

- `en.wiktionary` の `love` 本体には `{{see translation subpage}}` があり、下位ページ
  `love/translations` の「strong affection」枠に ja=愛/愛情/愛好、
  grc=ἀγάπη/φιλία/ἔρως/στοργή、la=amor/cāritās が揃っていた。本体だけを見て
  「データ不足」と報告した。下位ページを辿らなかっただけである。
- Wikidata の `agape` を検索し、上位5件（女性名・昆虫属・村・植物属・トビケラ属）の
  先頭を採って「日本語ラベルが無い」と報告した。正しい項目は Q210143「アガペー」で
  grc=ἀγάπη を持つ。

したがってこの module は次を設計上の義務とする。

1. 下位ページ（`X/translations`）を必ず試す。本体だけで空と判定しない。
2. ピボット語の候補を必ず複数試す。1件目が空でも終わらない。
3. 試した経路と試していない経路を応答に残す。空を「無い」と言い換えない。

得られるのは一般辞書の等価語である。哲学術語の原語ではない。実測で
`objectification` の訳表は de=Objektifizierung/Verdinglichung を持ち、マルクスの
Vergegenständlichung を持たない。検証済みseedが原語を定める語では seed を優先する。
"""
import re

from . import wikidata
from .base import cached_get_json, err, now, ok

EN_WT = "https://en.wiktionary.org/w/api.php"

# 原語として提示する言語。古典語を先に置く。
ORIG_CODES = ("grc", "la", "el", "sa", "pi", "de", "fr", "it", "he", "ar", "zh")

# 語義枠。引数（語義ラベル）を持つものだけを採る。引数の無い {{trans-top}} は
# 語義が特定できず、枠を跨いだ収集になる。labour の grc には「出産」の枠に
# τοκετός があり、跨ぐと「労働←出産」というもっともらしい誤りになる。
TRANS_TOP_RE = re.compile(r"\{\{trans-top\|([^}]+)\}\}(.*?)\{\{trans-bottom\}\}", re.S)
TRANS_TOP_BARE_RE = re.compile(r"\{\{trans-top\}\}")
SUBPAGE_MARK = "see translation subpage"


def _entries(body: str, code: str) -> list:
    """翻訳行から指定言語の語を取り出す。"""
    out = []
    for m in re.finditer(r"\{\{t{1,2}\+?\|" + re.escape(code) + r"\|([^|}]+)", body):
        w = m.group(1).strip()
        if w and w not in out:
            out.append(w)
    return out


def _plain_entries(body: str, code: str) -> list:
    """`{{t|..}}` 以外の素の `|code|語` 形も拾う（表記揺れの吸収）。"""
    out = []
    for m in re.finditer(r"\|" + re.escape(code) + r"\|([^|}]+)", body):
        w = m.group(1).strip()
        if w and not w.startswith(("tr=", "alt=", "sc=")) and w not in out:
            out.append(w)
    return out


def _lang_words(body: str, code: str) -> list:
    seen = _entries(body, code)
    for w in _plain_entries(body, code):
        if w not in seen:
            seen.append(w)
    return seen


def headword_variants(en: str) -> list:
    """Wiktionary の見出し語の候補。語形のずれを吸収する。

    実測で Wikidata の en label と Wiktionary の見出し語はずれる。
    rights/right、normality/normal、work/labour が食い違った。
    """
    e = (en or "").strip()
    if not e:
        return []
    low = e.lower()
    out = [e, low]
    if low.endswith("s") and not low.endswith(("ss", "us", "is")):
        out.append(low[:-1])
    if low.endswith("ity"):
        out += [low[:-3], low[:-3] + "al"]
    if low.endswith("ness"):
        out.append(low[:-4])
    if low.endswith("ism"):
        out.append(low[:-3] + "ist")
    if low == "work":
        out += ["labour", "labor"]
    return [x for i, x in enumerate(out) if x and x not in out[:i]]


async def _wikitext(title: str) -> str:
    try:
        body, _, _ = await cached_get_json(EN_WT, {
            "action": "parse", "page": title, "prop": "wikitext",
            "format": "json"}, ttl=86400)
        return ((body.get("parse") or {}).get("wikitext") or {}).get("*", "") or ""
    except Exception:
        return ""


async def sense_blocks(headword: str) -> tuple:
    """本体と下位ページの語義枠を返す。

    返り値は (枠の列, 試した頁の列, 引数なし枠の数)。
    下位ページを必ず試す。本体だけで空と判定しない。
    """
    pages, blocks, bare = [], [], 0
    for title in (headword, headword + "/translations"):
        wt = await _wikitext(title)
        if not wt:
            continue
        pages.append(title)
        bare += len(TRANS_TOP_BARE_RE.findall(wt))
        for label, body in TRANS_TOP_RE.findall(wt):
            blocks.append({"sense": label.split("|")[-1].strip(), "body": body,
                           "page": title})
        # 本体に下位ページの印があるなら、下位ページは必ず見る
        if SUBPAGE_MARK in wt and title == headword:
            continue
    return blocks, pages, bare


async def pivots(ja_word: str, lang: str = "ja") -> dict:
    """日本語語 → 英語ピボット候補。二つの経路を必ず両方試す。

    経路1は CirrusSearch の逆引きである。`insource:"|ja|愛"` で、日本語欄に
    その語を持つ en.wiktionary の頁を直接引く。
    経路2は Wikidata のラベル完全一致項目の en label である。
    どちらか一方で終わらせない。実測で「権利」は経路2で `rights` を得たが、
    `right/translations` に法的権利の語義枠が無く到達しなかった。
    """
    found, tried = [], []
    try:
        body, _, _ = await cached_get_json(EN_WT, {
            "action": "query", "list": "search",
            "srsearch": f'insource:"|ja|{ja_word}"', "srlimit": 12,
            "format": "json"}, ttl=86400)
        tried.append("insource")
        for row in ((body.get("query") or {}).get("search") or []):
            t = str(row.get("title") or "")
            # 下位ページは本体名へ寄せる。日本語・片仮名の頁は見出しにしない。
            base = t.split("/")[0]
            if base and re.fullmatch(r"[A-Za-z][A-Za-z \-']*", base):
                if base not in found:
                    found.append(base)
    except Exception:
        pass
    try:
        res = await wikidata.search(ja_word, lang, limit=8)
        tried.append("wikidata_label")
        if not res.get("error"):
            for h in (res.get("data") or []):
                if str(h.get("label")) != ja_word:
                    continue
                ent = await wikidata.entity(h.get("qid"), "en")
                en = ((ent.get("data") or {}).get("labels") or {}).get("en")
                if en:
                    for v in headword_variants(en):
                        if v not in found:
                            found.append(v)
                    break
    except Exception:
        pass
    return {"pivots": found[:12], "routes_tried": tried}


async def collapse(ja_word: str, lang: str = "ja", max_pivots: int = 6) -> dict:
    """日本語語が属する語義枠の原語と、同語の別義枠を返す。

    同一語義枠の中に複数の原語が並ぶことが、埋没そのものである。
    枠を跨いで集めない。引数の無い枠は採らない。
    """
    try:
        pv = await pivots(ja_word, lang)
        checked, hit = [], None
        for head in pv["pivots"][:max_pivots]:
            blocks, pages, bare = await sense_blocks(head)
            checked.append({"headword": head, "pages": pages,
                            "sense_blocks": len(blocks), "bare_blocks": bare})
            if not blocks:
                continue
            for b in blocks:
                if ja_word in _lang_words(b["body"], "ja"):
                    originals = []
                    for code in ORIG_CODES:
                        for w in _lang_words(b["body"], code):
                            originals.append({"lang": code, "term": w})
                    siblings = [x["sense"] for x in blocks if x is not b]
                    hit = {
                        "headword": head, "page": b["page"], "sense": b["sense"],
                        "japanese_in_sense": _lang_words(b["body"], "ja"),
                        "originals": originals,
                        "other_senses": siblings,
                        "original_count": len(originals),
                    }
                    break
            if hit:
                break
        return ok("translation-edge", now(), False, {
            "query": ja_word,
            "matched": bool(hit),
            "hit": hit,
            "pivots": pv["pivots"],
            "routes_tried": pv["routes_tried"],
            "headwords_checked": checked,
            "layer": "一般辞書の訳語等価。哲学術語の原語ではない",
            "evidence": "candidate",
            "note": ("同一語義枠に並ぶ原語のみを採る。枠を跨がない。語義ラベルの無い "
                     "{{trans-top}} は採らない。到達できなかった場合は matched=false "
                     "として残し、試した見出し語を headwords_checked に示す"),
        })
    except Exception as e:
        return err("translation-edge", e)
