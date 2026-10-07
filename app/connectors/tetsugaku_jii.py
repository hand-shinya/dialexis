"""『哲学字彙』1881年版の訳語対応（局所file・外部照会なし）。

何を与える層か:
    1881年（明治14年）に、ある西洋語に対してどの漢語が当てられたかの対応である。
    同じ見出しに並ぶ訳語は、その時点で競合していた候補であり、現代の語義ではない。
    例: Right に 正経・応当・公平・合理／権利・公道・通義 が並ぶ。

出典（CC BY 4.0 の表示義務を満たすために、payload から落としてはならない）:
    資料   『哲学字彙』1881[明治14]年刊
    底本   国立国語研究所蔵本（W21/I55，1002342366）
    翻字   大阪大学大学院文学研究科 岡島昭浩研究室
    公開者 国立国語研究所（2016-09-23）
    licence クリエイティブ・コモンズ 表示 4.0 国際（CC BY 4.0）

翻字の凡例のうち、本moduleが扱うもの:
    3. 漢字は常用漢字新字体による  → 旧字体（權理）では引けない。新字体で引く。
    4. 傍記・振り仮名は ｛ ｝       → 読みとして分離する
    6. 斜体の見出し語は語末に ＊    → 原語が英語以外（独・仏・羅・梵）であることの印
    7. 割注・角書は ［ ］           → 典拠や按文。注記として分離する
    （）は分野の略号（論・心・政・世 など）
"""
from __future__ import annotations

import pathlib
import re
import unicodedata

from .base import ok, now

LAYER = "1881年の訳語対応。訳語選択の一次資料であり、現代の語義ではない"

SOURCE = {
    "id": "ninjal-tetsugaku-jii-1881",
    "title": "哲学字彙（1881年刊）",
    "base_text": "国立国語研究所蔵本（W21/I55，1002342366）",
    "transcription": "大阪大学大学院文学研究科 岡島昭浩研究室",
    "publisher": "国立国語研究所",
    "published": "2016-09-23",
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/deed.ja",
    "url": "https://www2.ninjal.ac.jp/textdb_dataset/tgzi/",
    "disclaimer": "翻字本文は原本の写しであり、OCRではない。現代の語義ではない。",
}

DATA = pathlib.Path(__file__).resolve().parent.parent / "data" / "tetsugaku_jii_1881.txt"

# 見出し行。見出しと訳語は全角空白かtabで区切られる。
# 語末の ＊（斜体＝英語以外）と ＋ は印であり、見出し語そのものではない。
HEAD_RE = re.compile(
    r"^(?P<indent>[_＿]?)"
    r"(?P<head>[A-Za-z][A-Za-zÀ-ɏ'’\-\. ]*?)"
    r"(?P<marks>[＊＋*+]*)"
    r"[　\t]+(?P<body>\S.*)$"
)
PAGE_RE = re.compile(r"^（\d+）")
GLOSS_RE = re.compile(r"［([^］]*)］")          # 割注・角書
RUBY_RE = re.compile(r"｛([^｝]*)｝")           # 振り仮名
FIELD_RE = re.compile(r"（([^）]{1,6})）")      # 分野の略号
SPLIT_RE = re.compile(r"[、，]")

FIELD_LABEL = {
    "論": "論理学", "心": "心理学", "政": "政治学", "世": "世態学",
    "数": "数学", "物": "物理学", "化": "化学", "生": "生物学",
    "法": "法学", "教": "教育学", "医": "医学", "天": "天文学",
}


def _is_section_head(head: str) -> bool:
    """A / B / C … の見出し（アルファベット順の区切り）を除く。"""
    return len(head.strip()) == 1 and head.strip().isalpha()


def _normalize(term: str) -> str:
    """照合用の正規化。全角半角と前後の記号だけを均す（字体は変えない）。"""
    return unicodedata.normalize("NFKC", term).strip().strip("・.,")


def parse(text: str) -> list:
    """翻字本文を見出し単位に分解する。1行1見出しであることを前提にする。"""
    out = []
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or PAGE_RE.match(line):
            continue
        m = HEAD_RE.match(line)
        if not m:
            continue
        head = m.group("head").strip()
        if _is_section_head(head):
            continue
        body = m.group("body")
        glosses = GLOSS_RE.findall(body)
        body_wo = GLOSS_RE.sub("", body)
        terms = []
        for raw in SPLIT_RE.split(body_wo):
            raw = raw.strip()
            if not raw:
                continue
            ruby = RUBY_RE.findall(raw)
            raw = RUBY_RE.sub("", raw)
            fields = [f for f in FIELD_RE.findall(raw) if f in FIELD_LABEL]
            term = FIELD_RE.sub("", raw).strip("＿_ 　")
            if not term:
                continue
            terms.append({
                "term": term,
                "reading": ruby[0] if ruby else "",
                "field": FIELD_LABEL.get(fields[0], "") if fields else "",
            })
        if not terms:
            continue
        out.append({
            "headword": head,
            "foreign": "＊" in m.group("marks") or "*" in m.group("marks"),
            "sub_entry": bool(m.group("indent")),
            "translations": terms,
            "notes": glosses,
            "line": n,
        })
    return out


_CACHE: dict = {}


def _index() -> dict:
    """見出し順の entries と、日本語からの逆引きを1度だけ作る。"""
    if _CACHE:
        return _CACHE
    entries = parse(DATA.read_text(encoding="utf-8-sig"))
    reverse: dict = {}
    for i, e in enumerate(entries):
        for t in e["translations"]:
            reverse.setdefault(_normalize(t["term"]), []).append(i)
    forward: dict = {}
    for i, e in enumerate(entries):
        forward.setdefault(_normalize(e["headword"]).lower(), []).append(i)
    _CACHE.update(entries=entries, reverse=reverse, forward=forward)
    return _CACHE


def stats() -> dict:
    idx = _index()
    return {
        "entries": len(idx["entries"]),
        "translations": sum(len(e["translations"]) for e in idx["entries"]),
        "japanese_terms": len(idx["reverse"]),
        "foreign_headwords": sum(1 for e in idx["entries"] if e["foreign"]),
    }


def _entry_view(e: dict, focus: str = "") -> dict:
    sib = [t for t in e["translations"] if _normalize(t["term"]) != _normalize(focus)]
    return {
        "headword": e["headword"],
        "foreign": e["foreign"],
        "translations": e["translations"],
        "siblings": sib,
        "notes": e["notes"],
        "line": e["line"],
    }


MAX_NEAR = 8


def _near_headwords(key_ja: str, idx: dict) -> list:
    """同一ではないが語形が重なる見出し。別語として別枠で出す。

    「愛」で引いたとき 1881年版の Love → 愛情 に届かせるための経路である。
    愛と愛情は別語なので、同一視せず「近い見出し」として示す（公理3: 宣言は実力を超えない）。
    """
    if len(key_ja) < 1:
        return []
    out = []
    for ja, rows in idx["reverse"].items():
        if ja == key_ja:
            continue
        if key_ja in ja or (len(ja) >= 2 and ja in key_ja):
            for i in rows:
                e = idx["entries"][i]
                out.append({"term": ja, "headword": e["headword"],
                            "translations": [t["term"] for t in e["translations"]]})
    out.sort(key=lambda x: (len(x["term"]), x["term"]))
    return out[:MAX_NEAR]


def lookup(term: str) -> dict:
    """日本語の語からも西洋語の見出しからも引ける。どちらも空なら missing を立てる。

    返すのは1881年時点の対応だけである。現代の語義を混ぜない。
    """
    idx = _index()
    key_ja = _normalize(term)
    key_en = key_ja.lower()
    as_translation = [_entry_view(idx["entries"][i], term)
                      for i in idx["reverse"].get(key_ja, [])]
    as_headword = [_entry_view(idx["entries"][i])
                   for i in idx["forward"].get(key_en, [])]
    siblings, seen = [], {key_ja}
    for v in as_translation:
        for t in v["siblings"]:
            k = _normalize(t["term"])
            if k not in seen:
                seen.add(k)
                siblings.append({**t, "via": v["headword"]})
    # 西洋語の見出しで引かれた場合、その訳語自身が次に辿る先になる。
    # 2026-10-07 の10人の模擬で、egoism が「主我学派・自利主義」を持つのに
    # 辺が0本になっていた。日本語から引いた場合しか見ていなかった欠陥である。
    headword_terms = []
    for v in as_headword:
        for t in v["translations"]:
            k = _normalize(t["term"])
            if k not in seen:
                seen.add(k)
                headword_terms.append({**t, "via": v["headword"]})
    data = {
        "query": term,
        "as_translation": as_translation,
        "as_headword": as_headword,
        "sibling_terms": siblings,
        "headword_terms": headword_terms,
        "near_headwords": ([] if (as_translation or as_headword)
                           else _near_headwords(key_ja, idx)),
        "headwords": [v["headword"] for v in as_translation],
        "missing": not as_translation and not as_headword,
        "layer": LAYER,
        "source": SOURCE,
        "stats": stats(),
    }
    return ok(SOURCE["id"], now(), True, data)
