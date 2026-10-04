"""ja.wiktionary — 日本語版辞書から「辞書層の辺」を取る。

なぜ必要か（2026-10-04 実測）:
  我々は en.wiktionary の訳語表だけを引いていた。ja.wiktionary には別の層がある。
  「自然」には呉音「じねん」と語義「あるがまま…無為」が入り、「理性」には
  類義語「ロゴス・論理・知性」と対義語「感性」が、節として構造化されている。
  AIの推論を一切挟まず、節の形から機械で辺が取れる。

層の宣言（公理3）:
  これは一般辞書の関係記述である。哲学術語の定義ではない。
  編集者依存のため網羅性は無い（実測で「正義」「気分」の類義語節は空だった）。
  空であることと、関係が存在しないことは別である。
"""
import re
import urllib.parse

from .base import cached_get_json, err, ok

API = "https://ja.wiktionary.org/w/api.php"
LAYER = "一般辞書の関係記述。哲学術語の定義ではない"

# {{ja-kanjitab|し|ぜん|yomi=kanon}} — 音の種別つきの読み
KANJITAB_RE = re.compile(r"\{\{ja-kanjitab\|([^}]+)\}\}")
# 関係の節。見出しは {{syn}} {{ant}} {{rel}} {{der}} の形で現れる
SECTION_RE = re.compile(r"=+\s*\{\{(syn|ant|rel|der)\}\}\s*=+\n(.*?)(?=\n=|\Z)", re.S)
KIND = {"syn": "synonym", "ant": "antonym", "rel": "related", "der": "derived"}
SENSE_RE = re.compile(r"^\s*(語義\s*\d+)\s*[:：]?\s*(.*)$")
# [[対象|表示]] は表示側を採る。実測で「もつ|持っ」が「もつ」になり語義文が壊れた。
LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")
# 分類リンクは関係語ではない。実測で理性の対義語に Category:{{yue}} が混入した。
NOT_A_TERM_RE = re.compile(r"^(Category|カテゴリ|Image|File|w)\s*:|\{\{|^\s*$", re.I)
TEMPLATE_RE = re.compile(r"\{\{[^}]*\}\}")
# 日本語の節だけを対象にする。実測で理性の対義語に粵語の発音が混入した。
JA_HEAD_RE = re.compile(r"^==\s*\{\{(?:L\|)?ja\}\}\s*==\s*$", re.M)
L2_HEAD_RE = re.compile(r"^==\s*\{\{", re.M)
# 中身を残す必要のあるtemplate。消すと語義文が壊れる（実測: 労働）。
OKURI_RE = re.compile(r"\{\{おくりがな2?\|([^|}]*)\|[^|}]*\|([^|}]*)(?:\|[^|}]*)?\}\}")
FURI_RE = re.compile(r"\{\{ふりがな2?\|([^|}]*)\|[^|}]*\}\}")
W_RE = re.compile(r"\{\{w\|([^|}]*)(?:\|[^}]*)?\}\}")
TAG_RE = re.compile(r"\{\{タグ\|[^|}]*\|([^}]*)\}\}")


def ja_section(wikitext: str) -> str:
    """日本語の節だけを切り出す。見出しが無い項目は全文を返す。"""
    text = wikitext or ""
    m = JA_HEAD_RE.search(text)
    if not m:
        return text
    rest = text[m.end():]
    nxt = L2_HEAD_RE.search(rest)
    return rest[:nxt.start()] if nxt else rest


def _clean_text(s: str) -> str:
    """表示文へ落とす。中身を持つtemplateは残し、意味を変えない。"""
    s = OKURI_RE.sub(lambda m: m.group(1) + m.group(2), s)
    s = FURI_RE.sub(lambda m: m.group(1), s)
    s = W_RE.sub(lambda m: m.group(1), s)
    s = TAG_RE.sub(lambda m: "〔" + m.group(1).replace("|", "・") + "〕", s)
    s = LINK_RE.sub(lambda m: m.group(2) or m.group(1), s)
    s = TEMPLATE_RE.sub("", s)
    return re.sub(r"[']{2,}|\s+", lambda m: "" if "'" in m.group(0) else " ", s).strip()


def readings(wikitext: str) -> list:
    """読みを音の種別つきで返す。呉音・漢音の別を落とさない。"""
    out, seen = [], set()
    for body in KANJITAB_RE.findall(ja_section(wikitext)):
        parts = [p.strip() for p in body.split("|")]
        kana = "".join(p for p in parts if p and "=" not in p)
        yomi = ""
        for p in parts:
            if p.startswith("yomi="):
                yomi = p.split("=", 1)[1].strip()
        if kana and (kana, yomi) not in seen:
            seen.add((kana, yomi))
            out.append({"kana": kana, "yomi": yomi})
    return out


def senses(wikitext: str) -> list:
    """語義を順序どおりに返す。入れ子の用例行（#*）は語義ではないので採らない。"""
    out = []
    for line in ja_section(wikitext).split("\n"):
        if line.startswith("#") and not line.startswith(("#*", "#:")):
            t = _clean_text(line.lstrip("#").strip())
            if t:
                out.append(t)
    return out


def _terms_in(line: str) -> list:
    """1行から語を割り出す。読点・中点で並んだものを1語ずつにする。"""
    links = [(d or t).strip() for t, d in LINK_RE.findall(line)]
    if links:
        return [t for t in links if t and not NOT_A_TERM_RE.search(t)]
    bare = TEMPLATE_RE.sub("", line.lstrip("*#:").strip())
    return [t.strip() for t in re.split(r"[、,・／/]", bare)
            if t.strip() and not NOT_A_TERM_RE.search(t.strip())]


def relations(wikitext: str) -> list:
    """類義・対義・関連・派生の辺を返す。語義の別は sense に保つ。"""
    out, seen = [], set()
    for tag, body in SECTION_RE.findall(ja_section(wikitext)):
        kind, sense = KIND[tag], ""
        for line in body.split("\n"):
            raw = line.strip()
            if not raw:
                continue
            m = SENSE_RE.match(raw)
            if m:
                sense = m.group(1).replace(" ", "")
                raw = m.group(2).strip()
                if not raw:
                    continue
            if not raw.startswith(("*", "#", "[[")) and not m:
                continue
            for term in _terms_in(raw):
                key = (kind, term, sense)
                if term and key not in seen:
                    seen.add(key)
                    out.append({"kind": kind, "term": term, "sense": sense})
    return out


def parse(wikitext: str) -> dict:
    """1語ぶんの辞書層。層の宣言と出所を必ず付ける。"""
    return {"readings": readings(wikitext), "senses": senses(wikitext),
            "relations": relations(wikitext), "layer": LAYER,
            "source": "ja.wiktionary"}


async def lookup(word: str, ttl: int = 86400) -> dict:
    """ja.wiktionary の1項目を取得して辞書層へ落とす。

    項目が無い場合は data=None ではなく、空の辞書層と missing=True を返す。
    「取得できなかった」と「項目が無い」を混同させない（DWDSの200空応答の教訓）。
    """
    try:
        body, ts, cached = await cached_get_json(API, {
            "action": "parse", "page": word, "prop": "wikitext",
            "format": "json", "formatversion": "2", "redirects": "1",
        }, ttl=ttl)
        if "error" in body:
            d = parse("")
            d.update({"word": word, "missing": True,
                      "note": str(body["error"].get("code", "")),
                      "url": f"https://ja.wiktionary.org/wiki/{urllib.parse.quote(word)}"})
            return ok("ja.wiktionary", ts, cached, d)
        wt = (body.get("parse") or {}).get("wikitext") or ""
        d = parse(wt)
        d.update({"word": (body.get("parse") or {}).get("title") or word,
                  "missing": False, "note": "",
                  "url": f"https://ja.wiktionary.org/wiki/{urllib.parse.quote(word)}"})
        return ok("ja.wiktionary", ts, cached, d)
    except Exception as e:
        return err("ja.wiktionary", e)
