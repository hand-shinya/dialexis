"""ja.wiktionary — 日本語版辞書から「辞書層の辺」を取る。

なぜ必要か（2026-10-04 実測）:
  我々は en.wiktionary の訳語表だけを引いていた。ja.wiktionary には別の層がある。
  「自然」には呉音「じねん」と語義「あるがまま…無為」が入り、「理性」には
  類義語「ロゴス・論理・知性」と対義語「感性」が、節として構造化されている。
  AIの推論を一切挟まず、節の形から機械で辺が取れる。

2026-10-08 に直したこと（10人の模擬の分析から）:
  1. 読み落ちていた節を読む。`{{drv}} {{comp}} {{prov}} {{idiom}}` は正規表現に
     一致していなかった。10語のうち9語で未読の節が在った。
     自然の複合語10件は消え、労働の15件は related として残っていた。
     同じ下位複合語が、pageの書き方次第で欠落か無名の関連に分かれていた。
  2. `sections_found` と `sections_read` を両方返す。これが「資料に無い」と
     「我々が読んでいない」を分ける唯一の欄である（公理1）。
  3. 語義の番号を品詞blockごとに一意にする。自然は品詞blockが2つあり、
     どちらにも「語義1」が在る。番号だけで解決すると黙って別の本文を指す。
  4. `{{trans}}` 節を読む。語義ごとに外国語lemmaが並んでおり、これが層をまたぐ
     鍵になる（原語pivot）。これまで1本も読んでいなかった。

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
# 関係の節。読む節と、在ることだけを記録する節を分ける。
READ_TAGS = ("syn", "ant", "rel", "der", "drv", "comp", "prov", "idiom")
SECTION_RE = re.compile(
    r"=+\s*\{\{(" + "|".join(READ_TAGS) + r")\}\}\s*=+\n(.*?)(?=\n=|\Z)", re.S)
# 節の見出しに現れる全てのtemplate名。読んでいない節を数えるために使う。
SECTION_ANY_RE = re.compile(r"=+\s*\{\{([a-z-]+)\}\}\s*=+", re.M)
KIND = {"syn": "synonym", "ant": "antonym", "rel": "related", "der": "derived",
        "drv": "derived", "comp": "compound", "prov": "idiom", "idiom": "idiom"}
# 関係の節ではない見出し（品詞・発音・活用・語源・異表記）。未読に数えない。
NON_RELATION = {
    "noun", "verb", "adj", "adjective", "adjectivenoun", "adverb", "pron",
    "pronunciation", "conjug", "conj", "etym", "etymology", "alter", "interj",
    "prefix", "suffix", "counter", "name", "proper", "abbr", "ref", "anagram",
}
KIND_NOTE = {
    "synonym": "辞書が類義として並べた語",
    "antonym": "辞書が対義として並べた語",
    "related": "辞書が関連として並べた語。関係の種別は書かれていない",
    "derived": "この語から作られた語",
    "compound": "この語を語構成に含む複合語",
    "idiom": "この語を含む成句・熟語",
}
SENSE_RE = re.compile(r"^\s*(語義\s*\d+)\s*[:：]?\s*(.*)$")
# [[対象|表示]] は表示側を採る。実測で「もつ|持っ」が「もつ」になり語義文が壊れた。
LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")
# 分類リンクは関係語ではない。実測で理性の対義語に Category:{{yue}} が混入した。
NOT_A_TERM_RE = re.compile(r"^(Category|カテゴリ|Image|File|w)\s*:|\{\{|^\s*$", re.I)
TEMPLATE_RE = re.compile(r"\{\{[^}]*\}\}")
# 日本語の節だけを対象にする。実測で理性の対義語に粵語の発音が混入した。
JA_HEAD_RE = re.compile(r"^==\s*\{\{(?:L\|)?ja\}\}\s*==\s*$", re.M)
L2_HEAD_RE = re.compile(r"^==\s*\{\{", re.M)
# 品詞blockの見出し（=== 名詞 === など）。関係の節の見出しは除く。
BLOCK_RE = re.compile(r"^===+\s*([^=\n]+?)\s*===+\s*$", re.M)
# 中身を残す必要のあるtemplate。消すと語義文が壊れる（実測: 労働）。
OKURI_RE = re.compile(r"\{\{おくりがな2?\|([^|}]*)\|[^|}]*\|([^|}]*)(?:\|[^|}]*)?\}\}")
FURI_RE = re.compile(r"\{\{ふりがな2?\|([^|}]*)\|[^|}]*\}\}")
W_RE = re.compile(r"\{\{w\|([^|}]*)(?:\|[^}]*)?\}\}")
TAG_RE = re.compile(r"\{\{タグ\|[^|}]*\|([^}]*)\}\}")

# {{trans}} 節。語義の区切りは {{trans-top|語義1}} と {{top}} の2形がある。
TRANS_SEC_RE = re.compile(r"=+\s*\{\{trans\}\}\s*=+\n(.*?)(?=\n==[^=]|\Z)", re.S)
TRANS_GROUP_RE = re.compile(r"\{\{(?:trans-)?top(?:\|([^}]*))?\}\}")
TRANS_SEE_RE = re.compile(r"\{\{trans-see\|([^|}]*)\|?([^|}]*)\}\}")
# 英語の行は3形ある（2026-10-08 実測。私の正規表現は3回取りこぼした）。
EN_LINE_RE = re.compile(
    r"^\*+\s*(?:\{\{T\|en\}\}|\[\[\{\{en\}\}\]\])[^\n:]*:\s*(.*)$", re.M)
EN_TMPL_RE = re.compile(r"\{\{t[+-]?\|en\|([^|}]+)")
EN_LINK_RE = re.compile(r"\[\[([^\]|#{]+)")
EN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z \-']*")


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


def _blocks(ja_text: str) -> list:
    """品詞blockに切る。各blockの見出し名と本文を返す。

    自然は「名詞」と「形容動詞」の2 blockを持ち、どちらにも語義1が在る。
    blockを跨いで番号を解決すると、黙って別の本文を指す。
    """
    def _is_block(name: str) -> bool:
        tag = name.strip().strip("{}").lower()
        return tag not in KIND and tag != "trans"
    heads = [m for m in BLOCK_RE.finditer(ja_text) if _is_block(m.group(1))]
    if not heads:
        return [{"name": "", "start": 0, "end": len(ja_text), "text": ja_text}]
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(ja_text)
        out.append({"name": m.group(1).strip(), "start": m.start(), "end": end,
                    "text": ja_text[m.end():end]})
    if heads[0].start() > 0:
        out.insert(0, {"name": "", "start": 0, "end": heads[0].start(),
                       "text": ja_text[:heads[0].start()]})
    return out


def sense_map(wikitext: str) -> list:
    """語義を品詞block込みで一意にする。sense_id は block番号つき。"""
    out = []
    for bi, b in enumerate(_blocks(ja_section(wikitext))):
        n = 0
        for line in b["text"].split("\n"):
            if line.startswith("#") and not line.startswith(("#*", "#:")):
                t = _clean_text(line.lstrip("#").strip())
                if not t:
                    continue
                n += 1
                out.append({"sense_id": "b{}-{}".format(bi, n),
                            "block": b["name"], "label": "語義{}".format(n),
                            "text": t})
    return out


def sections(wikitext: str) -> dict:
    """在った節と、読んだ節を返す。差が『我々が読んでいない』分である。

    品詞・発音・活用の節は関係の節ではないので、未読には数えない。
    数えると「読み落ち」を実際より多く見せる（公理3: 宣言は実力を一語も超えない）。
    """
    ja = ja_section(wikitext)
    found = sorted({m.group(1).lower() for m in SECTION_ANY_RE.finditer(ja)})
    read = [t for t in found if t in KIND]
    read_elsewhere = [t for t in found if t == "trans"]
    unread = [t for t in found
              if t not in KIND and t != "trans" and t not in NON_RELATION]
    return {"found": found, "read": read, "read_elsewhere": read_elsewhere,
            "unread": unread,
            "not_relation": [t for t in found if t in NON_RELATION]}


def _terms_in(line: str) -> list:
    """1行から語を割り出す。読点・中点で並んだものを1語ずつにする。"""
    links = [(d or t).strip() for t, d in LINK_RE.findall(line)]
    if links:
        return [t for t in links if t and not NOT_A_TERM_RE.search(t)]
    bare = TEMPLATE_RE.sub("", line.lstrip("*#:").strip())
    return [t.strip() for t in re.split(r"[、,・／/]", bare)
            if t.strip() and not NOT_A_TERM_RE.search(t.strip())]


def relations(wikitext: str) -> list:
    """類義・対義・関連・派生・複合・成句の辺を返す。

    `sense` は従来どおり「語義1」等のlabelである（既存の契約を壊さない）。
    `sense_id` と `sense_text` を足し、どのblockのどの語義かを一意にする。
    """
    ja = ja_section(wikitext)
    smap = sense_map(wikitext)
    blocks = _blocks(ja)
    out, seen = [], set()
    for m in SECTION_RE.finditer(ja):
        tag, body = m.group(1), m.group(2)
        kind = KIND[tag]
        # この節が属する品詞blockを位置から決める
        bi = 0
        for i, b in enumerate(blocks):
            if b["start"] <= m.start() < b["end"]:
                bi = i
                break
        sense = ""
        for line in body.split("\n"):
            raw = line.strip()
            if not raw:
                continue
            # 語義の見出しは「語義1:」と「* 語義1:」の両形で書かれる
            sm = SENSE_RE.match(raw) or SENSE_RE.match(raw.lstrip("*#: 　"))
            if sm:
                sense = sm.group(1).replace(" ", "")
                raw = sm.group(2).strip()
                if not raw:
                    continue
            if not raw.startswith(("*", "#", "[[")) and not sm:
                continue
            sid, stext = "", ""
            if sense:
                want = "b{}-{}".format(bi, sense.replace("語義", ""))
                hit = [s for s in smap if s["sense_id"] == want]
                if hit:
                    sid, stext = hit[0]["sense_id"], hit[0]["text"]
            for term in _terms_in(raw):
                key = (kind, term, sense)
                if term and key not in seen:
                    seen.add(key)
                    out.append({"kind": kind, "term": term, "sense": sense,
                                "sense_id": sid, "sense_text": stext,
                                "block": blocks[bi]["name"],
                                "note": KIND_NOTE.get(kind, "")})
    return out


def _en_terms(line: str) -> list:
    seen, keep = set(), []
    for x in EN_TMPL_RE.findall(line) + EN_LINK_RE.findall(line):
        x = x.strip()
        if x and EN_WORD_RE.fullmatch(x) and x.lower() not in seen:
            seen.add(x.lower())
            keep.append(x)
    return keep


def translations(wikitext: str) -> dict:
    """語義ごとの外国語lemma（英語）と、別pageへの転送先を返す。

    これが層をまたぐ鍵である。2026-10-08 まで1本も読んでいなかった。
    """
    ja = ja_section(wikitext)
    sec = TRANS_SEC_RE.search(ja)
    body = sec.group(1) if sec else ""
    rows, see, seen = [], [], set()
    for m in EN_LINE_RE.finditer(body):
        label = ""
        for g in TRANS_GROUP_RE.finditer(body, 0, m.start()):
            label = (g.group(1) or "").strip()
        label = label or "語義指定なし"
        ens = _en_terms(m.group(1))
        key = (label, tuple(ens))
        if not ens or key in seen:
            continue
        seen.add(key)
        rows.append({"sense_label": label, "en": ens})
    for m in TRANS_SEE_RE.finditer(body):
        target = (m.group(2) or "").strip()
        if target:
            see.append({"sense_label": (m.group(1) or "").strip(), "page": target})
    return {"has_section": bool(sec), "rows": rows, "see": see}


def parse(wikitext: str) -> dict:
    """1語ぶんの辞書層。層の宣言と出所を必ず付ける。"""
    return {"readings": readings(wikitext), "senses": senses(wikitext),
            "relations": relations(wikitext), "sense_map": sense_map(wikitext),
            "sections": sections(wikitext), "translations": translations(wikitext),
            "layer": LAYER, "source": "ja.wiktionary"}


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
