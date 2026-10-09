"""自由textの問い合わせ層（2026-10-09・半田様の設計）。

なぜ在るか（半田様の指示の要点）:
  入り口が概念語1つである限り、半田様が実際に書いた文が system に入らない。
  非有機的肉体の研究で分岐を作った3つの瞬間は、すべて半田様の発話だった
  （資料0件・AI0件）。文を受ければ、語では出てこないものが出る。
    問いの立て方の候補／前提の誤り／まだ名の無い対象／分野の越境／時代の境界／出典の候補

何を使い、何を使わないか（2026-10-09 の半田様の決裁）:
  使う     鍵の要らない取得先だけ（手元の保全fileと、公開APIで鍵が不要なもの）
  使わない 鍵つきの外部AI検索（Gemini の検索接地など）。P5 の鍵不要原則を崩さない
  投げ方   利用者が押したときだけ。文を書いた時点では外へ出ない

なぜ一般ウェブ検索を主経路にしないか（2026-10-09 の実測）:
  本番のSearXNGは稼働しHTTP 200を返すが、上流engineが全滅して実クエリで0件である。
    ['brave', 'Suspended: too many requests'] / ['duckduckgo', 'CAPTCHA']
    ['google cse', 'unexpected crash'] / ['startpage', 'unexpected crash']
  Brave API は 2026-02 に無料枠廃止、Google CSE API は新規停止で 2027-01-01 廃止、
  Mojeek は PoW CAPTCHA、Marginalia は鍵必須。鍵なし一般検索の時代は終わっている。
  したがって一般ウェブは「足せたら足す」層に置き、落ちても画面を壊さない。

この層が保証すること / しないこと（公理3）:
  保証する   どの層へ、どの文字列を投げ、いつ、何件返ったかを receipts に全件残す
             落としたものを drops に残す（黙って減らさない・公理1）
  保証しない 返ってきたものが正しいこと。関連があること。網羅していること
             抽出した語が主題であること（文の形から取るだけで、意味は判断しない）
"""
import asyncio
import re

from .connectors import (crossref, ndl, openalex, sep, tetsugaku_jii, wikidata,
                         wikipedia)
from .connectors.base import now

MAX_TEXT = 8000
MAX_TERMS = 6
MAX_QUESTIONS = 8

# 文が問いとして立てている形。意味の判断はしない（main.TOPIC_PATTERNS と同じ思想）。
# 語は最大12字。20字まで許すと文の断片が語になる（実測で
# 「非有機的肉体という言葉が気にな」が語として外部へ投げられた）。
_W = r"[ぁ-んァ-ヴー一-龥A-Za-zＡ-Ｚａ-ｚ][ぁ-んァ-ヴー一-龥A-Za-zＡ-Ｚａ-ｚ]{0,11}"
# 標識（「とは」「という言葉」等）の前の語は最短一致にする。貪欲だと
# 語側が標識ごと飲み込み、短い正しい語が試されないまま match が成立する。
_WL = r"[ぁ-んァ-ヴー一-龥A-Za-zＡ-Ｚａ-ｚ][ぁ-んァ-ヴー一-龥A-Za-zＡ-Ｚａ-ｚ]{0,11}?"
# 長い接尾辞を先に置く。alternation は左から試すので、「って」を先に置くと
# 語側が貪欲に伸びて「…が気にな」＋「って」で成立してしまう。
TERM_PATTERNS = [
    re.compile(r"[『「“\"]([^』」”\"]{1,20})[』」”\"]"),
    re.compile(r"(" + _WL + r")と(" + _WL + r")の(?:違い|差|区別|混同|関係)"),
    # 裸の「って」は入れない。「気になって」から `気にな` が語になった（実測）。
    # 「〜って何」は「ってなん」で拾える。
    re.compile(r"(" + _WL + r")(?:という言葉|という概念|ってなん|とは)"),
    re.compile(r"(" + _WL + r")の(?:違い|差|定義|意味|由来|起源)"),
    re.compile(r"(" + _WL + r")を(?:どう|なぜ)"),
]

# 語ではなく節であることの印。1つでも含めば語として採らない。
NOT_A_TERM = ("という", "こと", "ます", "ませ", "です", "てい", "れる", "ない",
              "ある", "いる", "する", "した", "しま", "だろ", "でしょ", "ので",
              "から", "けれ", "ながら", "について", "に関し")

# 文を問いへ割る。句読点で割るだけで、解釈はしない（deepsearch._sub_questions と同型）。
_SPLIT = re.compile(r"[。\n！？?!]|そして|また|および|ただし|しかし")

_PARTICLE_EDGE = re.compile(r"^(?:や|と|の|を|が|は|も|で|に)|(?:や|と|の|を|が|は|も|で|に)$")


def extract_terms(text: str) -> list:
    """文の形から、問われている語を取る。

    「意味の判断はしない」が契約である。希少さ・頻度・重要度を測らない。
    取れた理由（どのpatternか）を必ず添える。添えないと、なぜ挙がったかが消える。
    """
    out, seen = [], set()
    for i, pat in enumerate(TERM_PATTERNS):
        for m in pat.finditer(text or ""):
            for g in m.groups():
                g = (g or "").strip("　 、。・")
                g = _PARTICLE_EDGE.sub("", g).strip()
                if not (1 <= len(g) <= 12) or g in seen:
                    continue
                if any(x in g for x in NOT_A_TERM):
                    continue
                seen.add(g)
                out.append({"term": g, "why": "文がこの形で問うている",
                            "pattern": i, "evidence": "candidate"})
    return out[:MAX_TERMS]


def split_questions(text: str) -> list:
    """文を問いの単位へ割る。句読点で割るだけで、言い換えも補完もしない。"""
    out = []
    for part in _SPLIT.split(text or ""):
        p = part.strip("　 、,；;・")
        if len(p) >= 8:
            out.append(p[:200])
    return out[:MAX_QUESTIONS]


def _rows(res, pick):
    """connector の封筒から行を取り出す。error は呼び出し側が receipts に残す。"""
    if not isinstance(res, dict) or res.get("error"):
        return []
    data = res.get("data")
    if isinstance(data, dict):
        data = data.get("items") or data.get("results") or []
    if not isinstance(data, list):
        return []
    out = []
    for r in data:
        if isinstance(r, dict):
            row = pick(r)
            if row and row.get("title"):
                out.append(row)
    return out


def _receipt(layer, query, res, count, licence=""):
    """どの層へ何を投げ、いつ、何件返ったか。これが無い取得は会話に反映できない（C5）。"""
    return {"layer": layer, "query_sent": query,
            "retrieved_at": (res or {}).get("retrieved_at") or now(),
            "cached": bool((res or {}).get("cached")),
            "error": (res or {}).get("error"),
            "count": count, "licence": licence}


# 哲学字彙1881 の索引が本当に引けているかを、既知の語で毎回確かめる。
# 2026-10-09 に、封筒（ok()）を data として読んだため全語0件になった。
# 索引の故障と、その語が無いことは別である。区別できない0件は作らない（公理1）。
JII_SELFTEST = "理性"


def _jii_index_alive() -> bool:
    try:
        env = tetsugaku_jii.lookup(JII_SELFTEST)
        d = (env or {}).get("data") or {}
        return bool(d.get("as_translation") or d.get("as_headword"))
    except Exception:
        return False


async def _local_jii(term):
    """哲学字彙1881（手元の保全file・CC BY 4.0）。外部へ出ない。

    lookup は ok() の封筒を返すので data を開ける。開けないと常に0件になる。
    """
    try:
        env = tetsugaku_jii.lookup(term)
        if not isinstance(env, dict):
            return None, "unexpected envelope: %s" % type(env).__name__
        if env.get("error"):
            return None, str(env["error"])
        return (env.get("data") or {}), None
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


async def gather(text: str, lang: str = "ja", want_web: bool = True) -> dict:
    """自由textを受け、鍵の要らない層へ問い合わせる。

    want_web=False なら、外部へ一切出ずに手元の層だけで答える（退化階梯の底）。
    """
    text = (text or "")[:MAX_TEXT]
    terms = extract_terms(text)
    questions = split_questions(text)
    receipts, sources, drops = [], [], []

    if not terms:
        drops.append({"what": "語の抽出", "why": "文がこの形で問うている語を取れなかった",
                      "how_to_fix": "問いたい語を「」で括ると、その語を主題として取る"})

    head = [t["term"] for t in terms[:3]]
    # 文が同時に問うている他の語。結果の並べ替えの根拠に使う。
    # 「意味が近い」ではなく「文字列として同時に現れた」だけを数える（実測できる範囲）。
    all_terms = [t["term"] for t in terms]

    def with_context(row, term):
        """すべての層の source に同じ欄を持たせる。層ごとに欄が違うと、
        画面も試験も層ごとに分岐し、並べ替えの基準が黙って変わる。"""
        blob = (row.get("title") or "") + " " + (row.get("note") or "")
        others = [x for x in all_terms if x != term and x and x in blob]
        row["context_hits"] = len(others)
        row["context_terms"] = others
        row["why_ranked"] = ("文の他の語（%s）と同時に現れた" % "・".join(others)
                             if others else "この語の検索一致のみ")
        return row

    # ---- 手元の層（外部へ出ない。検索engineが全滅していても必ず動く） --------
    jii_alive = _jii_index_alive()
    if not jii_alive:
        drops.append({"what": "哲学字彙1881（手元の保全file）",
                      "why": "既知の語「%s」でも引けないので、索引が壊れている" % JII_SELFTEST,
                      "how_to_fix": "保全fileのpathと parse() を確かめる。0件は語の不在ではない"})
    for term in head:
        jii, e = await _local_jii(term)
        n = 0
        if jii:
            n = len(jii.get("as_translation") or []) + len(jii.get("as_headword") or [])
            for row in (jii.get("as_translation") or [])[:4]:
                sources.append(with_context({
                    "layer": "哲学字彙1881（手元の保全file）", "term": term,
                    "title": "%s ← %s" % (term, row.get("headword") or ""),
                    "url": "", "note": "1881年の訳語対応。手元のfileから引いた",
                    "licence": "CC BY 4.0", "evidence": "candidate"}, term))
        rec = {"layer": "哲学字彙1881（local）", "query_sent": term,
               "retrieved_at": now(), "cached": True,
               "error": e, "count": n, "licence": "CC BY 4.0",
               "index_selftest": "ok" if jii_alive else "broken"}
        if n == 0 and not e:
            rec["zero_means"] = ("1881年の訳語としてこの語が無い（索引は既知の語で引けている）"
                                 if jii_alive else
                                 "索引が壊れているので、0件は語の不在を意味しない")
        receipts.append(rec)

    if not want_web:
        sources.sort(key=lambda s: -s["context_hits"])
        return _payload(text, terms, questions, sources, receipts, drops, web=False)

    # ---- 鍵の要らない公開API（落ちても画面を壊さない） ----------------------
    jobs, meta = [], []
    for term in head:
        jobs.append(wikipedia.search(term, lang, limit=5))
        meta.append(("Wikipedia全文検索", term, "CC BY-SA 4.0"))
        jobs.append(wikidata.search(term, lang, limit=5))
        meta.append(("Wikidata", term, "CC0"))
        jobs.append(sep.search(term, limit=4))
        meta.append(("SEP（スタンフォード哲学百科）", term, "各項目の表示に従う"))
        jobs.append(openalex.search_works(term, limit=5))
        meta.append(("OpenAlex", term, "CC0"))
        jobs.append(crossref.search_works(term, limit=5))
        meta.append(("Crossref", term, "メタデータは再利用可"))
        jobs.append(ndl.by_title(term, limit=5))
        meta.append(("NDLサーチ（作品名で照会）", term, "書誌は再利用可"))

    results = await asyncio.gather(*jobs, return_exceptions=True)

    ZERO_MEANS = {
        "NDLサーチ（作品名で照会）": "作品名として照会したので、概念語では0件になりやすい",
        "SEP（スタンフォード哲学百科）": "英語の項目を検索するので、日本語の語では0件になりやすい",
        "OpenAlex": "論文の題と抄録を検索するので、日本語の語では0件になりやすい",
        "Crossref": "DOIを持つ文献の題を検索するので、日本語の語では0件になりやすい",
        "Wikidata": "この表記の項目が無い（別表記なら在ることがある）",
        "Wikipedia全文検索": "この表記での全文一致が無い",
    }

    PICK = {
        "Wikipedia全文検索": lambda r: {"title": r.get("title"), "url": r.get("url"),
                                        "note": (r.get("content") or "")[:160]},
        "Wikidata": lambda r: {"title": r.get("label") or r.get("title"),
                               "url": r.get("url") or r.get("concepturi") or "",
                               "note": (r.get("description") or "")[:160]},
        "SEP（スタンフォード哲学百科）": lambda r: {"title": r.get("title"), "url": r.get("url"),
                                                    "note": (r.get("snippet") or "")[:160]},
        # key は実測して合わせた（推測で書いた display_name / issued は実在しなかった）
        "OpenAlex": lambda r: {"title": r.get("title"),
                               "url": r.get("url") or r.get("doi") or r.get("id") or "",
                               "note": " ".join(x for x in (
                                   str(r.get("year") or ""),
                                   "被引用 %s" % r["cited_by_count"]
                                   if r.get("cited_by_count") else "") if x)},
        "Crossref": lambda r: {"title": r.get("title"),
                               "url": r.get("url") or r.get("doi") or "",
                               "note": " ".join(x for x in (str(r.get("year") or ""),
                                                            r.get("publisher") or "") if x)[:160]},
        "NDLサーチ（作品名で照会）": lambda r: {"title": r.get("title"),
                                "url": r.get("url") or r.get("link") or "",
                                "note": " ".join(x for x in (
                                    r.get("creator") or r.get("author") or "",
                                    str(r.get("date") or r.get("year") or "")) if x)[:160]},
    }

    for (layer, term, licence), res in zip(meta, results):
        if isinstance(res, Exception):
            receipts.append({"layer": layer, "query_sent": term, "retrieved_at": now(),
                             "cached": False,
                             "error": "%s: %s" % (type(res).__name__, res),
                             "count": 0, "licence": licence})
            continue
        rows = _rows(res, PICK[layer])
        rec = _receipt(layer, term, res, len(rows), licence)
        if not rows and not rec["error"]:
            # 沈黙する0件を作らない。0 の意味は層ごとに違う（公理1）。
            rec["zero_means"] = ZERO_MEANS.get(layer, "この層にこの語での一致が無かった")
        receipts.append(rec)
        for row in rows[:4]:
            # 0 でも捨てない（公理1）。捨てると黙って減る。
            sources.append(with_context(
                {"layer": layer, "term": term, "title": row["title"],
                 "url": row.get("url") or "", "note": row.get("note") or "",
                 "licence": licence, "evidence": "candidate"}, term))

    # 落ちた層を黙って減らさない（公理1）
    for r in receipts:
        if r.get("error"):
            drops.append({"what": r["layer"], "why": "取得に失敗した（%s）" % r["error"][:80],
                          "how_to_fix": "時間をおいて押し直すと、別の層の結果は残ったまま再取得する"})

    # 共起の多い順に並べる。同数なら取得順を保つ（並べ替えの根拠を明示できる範囲で）。
    sources.sort(key=lambda s: -s["context_hits"])
    return _payload(text, terms, questions, sources, receipts, drops, web=True)


def _payload(text, terms, questions, sources, receipts, drops, web):
    live = [r for r in receipts if not r.get("error")]
    return {
        "schema_version": "dialexis.inquiry.v1",
        "queried_at": now(),
        "text_chars": len(text),
        "web_used": bool(web),
        "terms": terms,
        "questions": questions,
        "sources": sources,
        "receipts": receipts,
        "drops": drops,
        "layers_asked": len(receipts),
        "layers_answered": len(live),
        "found": len(sources),
        # 落とし所。取得しただけでは価値にならない（M0 C2）。
        # どの欄へ何を記録できるかを payload が自分で言う。
        "record_as": {
            "question": {"type": "provisional",
                         "note": "問いの言い換えは、人の判断の欄（追記のみ）へ記録する"},
            "open": {"type": "open_question",
                     "note": "まだ答えの無い問いは open_question として立てる"},
            "memory": {"type": "memory",
                       "note": "出典を持たない記憶は memory として別の枝に立てる"},
            "source": {"endpoint": "POST /api/nodes/{id}/provenance",
                       "note": "候補の出典は node へ付ける。確度は candidate で始まる"},
        },
        "honesty": ("この層が保証するのは、どの層へ何を投げ何件返ったかの記録だけである。"
                    "返ってきたものが正しいこと・関連があること・網羅していることは保証しない。"
                    "抽出した語は、文の形から取ったものであって、主題の判定ではない。"),
    }
