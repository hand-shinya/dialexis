"""NDL次世代デジタルライブラリー Book API — 「用例層」を取る。

なぜ必要か（2026-10-04 実測）:
  辞書層は関係の型（類義・対義・関連）を与えるが、その語が実際に
  いつ・誰によって・どの分野で使われたかを言わない。
  この API は年・著者・訳者・NDC分類・出現箇所を返す。実測では
  「権理」が1870-80年代に集中し1900年代以降ほぼ消え、「権利」が
  1880年代から現在まで続くことが、解釈でなく件数の分布として出た。

字体（2026-10-04 実測・重要）:
  『權理提綱』の本文OCRは旧字体で、「權理」109回に対し「権理」1回だった。
  新字体のみで引くと近代の一次資料にほぼ当たらない。kanji_variants で展開する。

宣言の限界（公理3）:
  総hitは10,000で上限に見える。`sort=publishyear` は500を返し非対応である。
  したがって年代分布は「先頭 sample 件の標本」であり、全体の分布ではない。
  標本であることを payload に書き、呼び出し側が隠せないようにする。
"""
import asyncio
import collections
import datetime
import html as _html
import re

from . import kanji_variants
from .base import cached_get_json, err, ok

SEARCH = "https://lab.ndl.go.jp/dl/api/book/search"
FULLTEXT = "https://lab.ndl.go.jp/dl/api/book/fulltext-json/{}"
VIEWER = "https://lab.ndl.go.jp/dl/book/{}"
LAYER = "近代刊行物の全文OCRの出現分布。標本であり全体の分布ではない"
MAX_SAMPLE = 100
TRANSLATOR_RE = re.compile(r"(.+?)\s*訳(?:述)?$")
AUTHOR_RE = re.compile(r"(.+?)\s*(?:共著|共編|著|編|撰|稿|講述|講義|述|輯|校|共)$")
# 1つの責任表示に複数名が並ぶ。実測「山田俊蔵, 大角豊次郎 共」。
NAME_SPLIT_RE = re.compile(r"[、,]\s*")
# 役割語。分割後の各名にも付くことがある（実測「原野彦太郎 訳||斎田功太郎 編」）。
ROLE_TAIL_RE = re.compile(r"\s*(?:共著|共編|著|編|撰|稿|講述|講義|述|輯|校|訳述|訳|共)+$")
# 刊年として成立しない値。実測でNDL側に西暦1000年が入っていた。
YEAR_MIN = 1500
# NDLが代入値として使うと思われる年。実在しうるので消さず、件数だけ出す。
SUSPECT_YEARS = (1800,)
PAREN_RE = re.compile(r"[（(][^）)]*[）)]")


def _clean(s: str) -> str:
    """OCRスニペットを読める形にする。強調記法と座標の尾を落とす。"""
    s = re.sub(r"</?em>", "", s or "")
    s = _html.unescape(s)
    s = re.sub(r"\s*\(\d{4}\.jp2\)\s*$", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _plausible_year(y) -> int:
    """刊年として使える値だけを返す。使えなければ0（不明）にする。"""
    try:
        y = int(y or 0)
    except (TypeError, ValueError):
        return 0
    return y if YEAR_MIN <= y <= datetime.date.today().year else 0


def _strip_role(name: str) -> str:
    return ROLE_TAIL_RE.sub("", (name or "").strip()).strip()


def _people(responsibility: str) -> tuple:
    """責任表示を著者と訳者に分ける。訳者が誰かは訳語史の核である。"""
    authors, translators = [], []
    for part in (responsibility or "").split("||"):
        name = PAREN_RE.sub("", part).strip()
        if not name:
            continue
        m = TRANSLATOR_RE.match(name)
        if m:
            translators.extend(_strip_role(x) for x in NAME_SPLIT_RE.split(m.group(1).strip()))
            continue
        m = AUTHOR_RE.match(name)
        authors.extend(_strip_role(x) for x in NAME_SPLIT_RE.split((m.group(1) if m else name).strip()))
    return [a for a in authors if a], [t for t in translators if t]


def tally(items: list) -> dict:
    """標本から年代・分野・人・書名の分布を作る（純関数）。"""
    dec, ndc, suspect = collections.Counter(), collections.Counter(), collections.Counter()
    au, tr = collections.Counter(), collections.Counter()
    unknown_year = unknown_ndc = 0
    works: dict = {}
    for it in items or []:
        y = _plausible_year(it.get("publishyear"))
        if y:
            dec[int(y) // 10 * 10] += 1
            if y in SUSPECT_YEARS:
                suspect[y] += 1
        else:
            unknown_year += 1
        code = (it.get("ndc") or "").strip()
        if code:
            ndc[code] += 1
        else:
            unknown_ndc += 1
        a, t = _people(it.get("responsibility") or "")
        for x in a:
            au[x] += 1
        for x in t:
            tr[x] += 1
        title = (it.get("title") or "").strip()
        if not title:
            continue
        w = works.setdefault(title, {"title": title, "year": y or 0, "editions": 0,
                                     "authors": [], "translators": [],
                                     "locators": [], "id": it.get("id") or ""})
        w["editions"] += 1
        if y and (not w["year"] or y < w["year"]):
            w["year"] = y
            w["id"] = it.get("id") or w["id"]
        for x in a:
            if x not in w["authors"]:
                w["authors"].append(x)
        for x in t:
            if x not in w["translators"]:
                w["translators"].append(x)
        for h in (it.get("highlights") or [])[:3]:
            c = _clean(h)
            if c and c not in w["locators"]:
                w["locators"].append(c)
    ordered = sorted(works.values(), key=lambda w: (w["year"] or 9999, w["title"]))
    for w in ordered:
        w["url"] = VIEWER.format(w["id"]) if w["id"] else ""
    return {"by_decade": dict(sorted(dec.items())), "by_ndc": dict(ndc.most_common()),
            "suspect_years": dict(sorted(suspect.items())),
            "authors": au.most_common(20), "translators": tr.most_common(20),
            "unknown_year": unknown_year, "unknown_ndc": unknown_ndc,
            "works": ordered, "sampled": len(items or [])}


def merge_variants(per_variant: dict) -> dict:
    """字体ごとの結果を1つに畳む。どの表記で何件だったかを残す。"""
    items, hits, seen = [], {}, set()
    for variant, res in per_variant.items():
        hits[variant] = res.get("hit") or 0
        for it in res.get("items") or []:
            # 字体を変えて引くとAPIが同じ資料を返す。idで畳んで二重に数えない。
            key = it.get("id") or (it.get("title"), it.get("publishyear"))
            if key in seen:
                continue
            seen.add(key)
            items.append(it)
    out = tally(items)
    out.update({"variants_tried": list(per_variant.keys()), "hit_by_variant": hits,
                "hit_total_reported": sum(hits.values()), "layer": LAYER})
    return out


async def _one(word: str, sample: int, ndc: str = "") -> dict:
    params = {"keyword": word, "size": max(1, min(sample, MAX_SAMPLE))}
    if ndc:
        params["f-ndc"] = ndc
    body, ts, cached = await cached_get_json(SEARCH, params, ttl=86400)
    return {"hit": body.get("hit") or 0, "items": body.get("list") or [],
            "retrieved_at": ts, "cached": cached}


async def survey(word: str, sample: int = MAX_SAMPLE, variants: int = 2) -> dict:
    """1語の用例層。新旧字体の両方で引き、標本であることを明示して返す。"""
    try:
        forms = kanji_variants.expand(word, limit=max(1, variants))
        res = await asyncio.gather(*[_one(f, sample) for f in forms],
                                   return_exceptions=True)
        per, errors = {}, []
        for f, r in zip(forms, res):
            if isinstance(r, Exception):
                errors.append(f"{f}: {type(r).__name__}")
                continue
            per[f] = r
        if not per:
            raise RuntimeError("; ".join(errors) or "no result")
        d = merge_variants(per)
        d.update({"word": word, "sample_size": sample, "errors": errors,
                  "note": "総hitは上限10000に見え、年での並べ替えは非対応。"
                          "分布は先頭{}件の標本である。".format(sample)})
        ts = next(iter(per.values()))["retrieved_at"]
        cached = all(v["cached"] for v in per.values())
        return ok("ndl-fulltext", ts, cached, d)
    except Exception as e:
        return err("ndl-fulltext", e)


async def by_field(word: str, codes: tuple = ("100", "121", "130", "321", "324",
                                              "331", "360", "371")) -> dict:
    """分野（NDC）ごとの件数。標本でなく総件数が返るため分布として使える。"""
    try:
        forms = kanji_variants.expand(word, limit=2)
        jobs = [(c, f) for c in codes for f in forms]
        res = await asyncio.gather(*[_one(f, 1, ndc=c) for c, f in jobs],
                                   return_exceptions=True)
        counts: dict = collections.Counter()
        for (c, _f), r in zip(jobs, res):
            if isinstance(r, Exception):
                continue
            counts[c] += r.get("hit") or 0
        return ok("ndl-fulltext", _now_of(res), True,
                  {"word": word, "by_ndc_total": dict(counts),
                   "variants_tried": forms, "codes_tried": list(codes)})
    except Exception as e:
        return err("ndl-fulltext", e)


def _now_of(res: list) -> str:
    for r in res:
        if isinstance(r, dict) and r.get("retrieved_at"):
            return r["retrieved_at"]
    from .base import now
    return now()
