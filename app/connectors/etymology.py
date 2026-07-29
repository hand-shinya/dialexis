"""普遍的な語源解剖（半田様指摘＝弁証法のdia-対話性の脱落を復元）。

Wiktionaryの語源記述から、原語への連鎖（from Old French…, from Ancient Greek…）と、
構成要素（prefix+root, 例 dia+legein）を、意味glossつきで抽出する。特定語のseed不要＝
どんな語にも普遍適用（P11）。翻訳で見えなくなった原義を、原語の実文書に接地して見せる。

第三者提案の ConceptNet差分エンジンは不採用: (1) api.conceptnet.io がVPSから 502/不通
(2) 言語跨ぎの label 集合差分（ja語 − en語）は原理的に無意味（両者は文字列が重ならず差分＝全部）。
真の意味drift差分は多言語埋め込みが要りVPSのRAMで不可＝将来課題。本モジュールは"動く核"に絞る。
"""
import re
import unicodedata

from .base import cached_get_json

WT = "https://en.wiktionary.org/w/api.php"


async def _extract(term):
    try:
        body, ts, cached = await cached_get_json(WT, {
            "action": "query", "titles": term, "prop": "extracts",
            "explaintext": 1, "format": "json"}, ttl=86400)
        page = next(iter(body.get("query", {}).get("pages", {}).values()), {})
        if "missing" in page:
            return None
        return page.get("extract", "") or ""
    except Exception:
        return None


def _gloss(inside):
    g = re.search(r"[“\"]([^”\"]+)[”\"]", inside or "")
    return g.group(1) if g else ""


def parse_etymology(text):
    m = re.search(r"===?\s*Etymology[^\n=]*=+\s*(.+?)(?:\n==|\Z)", text, re.DOTALL)
    seg = (m.group(1) if m else text)[:900]
    chain = []
    # 言語名は複数語がある（Late Latin / Ancient Greek / Old French）→ 大文字始まり語を貪欲に取る
    for lang, term, inside in re.findall(r"from ([A-Z][a-z]+(?: [A-Z][a-z]+)*) ([^\s,(]+)\s*(?:\(([^)]*)\))?", seg):
        chain.append({"lang": lang.strip(), "term": term.strip(" .,"), "gloss": _gloss(inside)})
    comps = []
    cm = re.search(r"([^\s]+\s*\([^)]*[“\"][^”\"]+[”\"][^)]*\)(?:\s*\+\s*[^\s]+\s*\([^)]*\))+)", seg)
    if cm:
        for term, inside in re.findall(r"([^\s+]+)\s*\(([^)]*)\)", cm.group(1)):
            comps.append({"part": term.strip(), "meaning": _gloss(inside) or inside.strip()[:40]})
    return {"summary": re.sub(r"\s+", " ", seg).strip()[:400], "chain": chain[:6], "components": comps[:6]}


def _clean_gloss(s):
    s = re.sub(r"\([^)]*\)", "", s or "")           # 括弧注記を落とす
    s = re.sub(r"[；;].*$", "", s)                    # 全角/半角セミコロン以降を落とす（第一義だけ）
    return s.strip(" \t,.:：、。").strip()


async def _han_gloss(ch):
    """CJK 1文字の英語義（构成要素の意味）を en.wiktionary Definitions から拾う。矛→spear／盾→shield。"""
    text = await _extract(ch)
    if not text:
        return ""
    m = re.search(r"Definitions\s*=*\s*\n+" + re.escape(ch) + r"\s*\n+([^\n]{2,70})", text)
    if m:
        g = _clean_gloss(m.group(1))
        if g:
            return g
    for l in text.split("\n"):                        # 退避: Definitions直下が取れない字は最初の短い英語義
        l = l.strip()
        if re.match(r"^[a-z][A-Za-z ,;-]{1,50}$", l) and not l.startswith(("from ", "see ", "cognate", "alternative")):
            return _clean_gloss(l)
    return ""


def _etym_prose(text):
    """語自身の Etymology 節の散文（例: 矛盾＝韓非子の故事）。アルファベット連鎖が無い語の語源。"""
    m = re.search(r"===?\s*Etymology[^\n=]*=+\s*(.+?)(?:\n==|\Z)", text or "", re.DOTALL)
    if not m:
        return ""
    seg = re.sub(r"\s+", " ", m.group(1)).strip()
    return seg[:220]


async def _cjk_anatomy(word):
    """CJK 語の解剖: 構成文字に分解し各字の義を取り（矛盾→矛=spear＋盾=shield）、語自身の散文語源も添える。
    翻訳（一語の訳語）で見えなくなる、字ごとの原義を復元する＝alphabet語のdia+legeinのCJK版（普遍化）。"""
    cjk = re.sub(r"[^㐀-鿿豈-﫿]", "", word)
    if len(cjk) < 2:
        return None
    comps = []
    for ch in list(dict.fromkeys(cjk))[:6]:          # 重複字は1回・最大6字
        g = await _han_gloss(ch)
        if g:
            comps.append({"part": ch, "meaning": g})
    summary = _etym_prose(await _extract(word))
    if not comps and not summary:
        return None
    return {"term": word, "chain": [], "components": comps, "summary": summary,
            "wiktionary_url": f"https://en.wiktionary.org/wiki/{word}"}


def _strip_len_marks(s):
    """発音の長符号（マクロン U+0304・ブレーヴェ U+0306）だけを外す。アクセント/気息(希語の tonos 等)は
    保つ＝Wiktionaryが語源で付す計量記号(dialecticē・δῐᾰλεκτῐκή)を、実在するレンマ形へ寄せる。"""
    d = unicodedata.normalize("NFD", s or "")
    d = "".join(c for c in d if c not in ("̄", "̆"))
    return unicodedata.normalize("NFC", d)


async def _resolve_form(term):
    """語源の1形（語尾変化/計量記号つき）を、実在するWiktionaryページの語源テキストへ寄せる。
    そのまま→長符号除去→散文『From X』の次語、の順に試し、語源が取れたテキストを返す。"""
    for cand in [term, _strip_len_marks(term)]:
        if not cand or not re.search(r"[A-Za-zΑ-Ωα-ωÀ-ÿ]", cand):
            continue
        text = await _extract(cand)
        if text and "Etymology" in text:
            return cand, text
    return None, None


# 語の文字（ラテン拡張＋ギリシャ基本/拡張＝アクセント付き含む）
_WORDCHAR = r"A-Za-zÀ-ÿͰ-Ͽἀ-῿"

# 言語名（語源散文の「from Latin …」等で現れる修飾子）。これ自体は語源"語"でなく言語の名前なので、
# 連鎖の追跡対象にしてはならない（追うと言語名ページの語源＝別語の語源を誤接続する。止揚→Aufhebung で
# 言語名 Latin を辿り Latium＋-īnus＝ローマを構成要素と誤表示した事案の是正・Task B到達効果検証で発見・P6）。
_LANG_NAMES = {
    "Latin", "Greek", "German", "French", "English", "Sanskrit", "Dutch", "Italian",
    "Spanish", "Portuguese", "Persian", "Arabic", "Hebrew", "Aramaic", "Chinese",
    "Japanese", "Korean", "Gothic", "Frankish", "Norse", "Slavic", "Germanic", "Celtic",
    "Ancient", "Old", "Middle", "Late", "Vulgar", "Medieval", "Classical", "Modern",
    "Proto", "Koine", "Attic", "Byzantine", "Hellenistic", "Church", "Norman",
    "Anglo", "Saxon", "Indo", "European", "Romance", "Iranian", "Turkic",
}


def _is_langname(t):
    """語源"語"でなく言語名かどうか（単独 or 複合語名の各語が言語名）。空/記号は言語名扱いしない。"""
    t = (t or "").strip(" .,-")
    if not t:
        return False
    parts = re.split(r"[\s\-]+", t)
    return all(p in _LANG_NAMES for p in parts if p)


def _prose_from(text):
    """語源散文の最初の『From <語>』の語を返す（der/inh テンプレで取れない派生・語尾変化を補う）。
    ギリシャ語のアクセント付き（διά 等）も full で取る（切詰め『διαλ』の是正）。"""
    m = re.search(r"===?\s*Etymology[^\n=]*=+\s*(.+?)(?:\n==|\Z)", text or "", re.DOTALL)
    seg = (m.group(1) if m else text or "")[:300]
    fm = re.search(r"[Ff]rom\s+([" + _WORDCHAR + r"][" + _WORDCHAR + r"'’\-]{1,40})", seg)
    return fm.group(1).strip(" .,") if fm else ""


async def _deepen_chain(r, max_hops=6):
    """連鎖の最古層を再帰的に辿り、根の構成要素（dia+legein 等）まで到達させる。独語 Dialektik のように
    表層で Latin 止まりの語も、英語 dialectic と同じ深さ（希語の dia+legein）へ統一する（半田様指摘・普遍）。
    追加する語は必ず実在ページで裏取り（junk 混入・切詰めを防ぐ）。構成要素に到達したら止める。"""
    seen = {c.get("term") for c in r.get("chain", []) if c.get("term")}
    cur = (r.get("chain") or [{}])[-1].get("term") if r.get("chain") else None
    for _ in range(max_hops):
        if r.get("components") or not cur:
            break
        cand, text = await _resolve_form((cur or "").strip(" .,"))
        if not text:
            break
        sub = parse_etymology(text)
        if sub.get("components"):
            r["components"] = sub["components"]
            break
        nxt = None
        for c in sub.get("chain", []):                 # 清潔な der/inh 連鎖を優先
            t = _strip_len_marks(c.get("term") or "")  # 表示・クリックとも計量記号を外した実在形へ
            if t and t not in seen and not _is_langname(t):   # 言語名は語源語でない＝辿らない（誤接続防止・P6）
                seen.add(t); r["chain"].append({**c, "term": t}); nxt = t
        if not nxt:                                     # 無ければ散文 From X（実在ページで裏取りしてから追加）
            pf = _strip_len_marks(_prose_from(text))
            if pf and pf not in seen and not _is_langname(pf):   # 言語名（Latin/German…）を語源として辿らない
                vcand, vtext = await _resolve_form(pf)
                if vtext:
                    seen.add(pf); r["chain"].append({"lang": "", "term": pf, "gloss": ""}); nxt = pf
        cur = nxt


async def anatomy(word, orig_terms, lang="ja"):
    """候補の原語（英/羅/独/希ラベル、無ければ入力語）を順に試し、語源が取れた最初のものを解剖。
    アルファベット語で取れない場合は、CJK 語なら構成文字へ分解して解剖する（矛盾＝矛＋盾・普遍化）。"""
    for term in [t for t in orig_terms if t] + [word]:
        if not term or not re.search(r"[A-Za-zΑ-Ωα-ωÀ-ÿ]", term):
            continue
        text = await _extract(term)
        if text and "Etymology" in text:
            r = parse_etymology(text)
            if r["chain"] or r["components"]:
                r["term"] = term
                r["wiktionary_url"] = f"https://en.wiktionary.org/wiki/{term}"
                await _deepen_chain(r)   # 連鎖を最古層まで辿り、根の構成要素まで到達＝どの言語形から入っても同じ深さ（統一）
                return r
    cjk = await _cjk_anatomy(word)                    # CJK 語の構成文字分解（矛盾→矛＋盾）
    if cjk:
        return cjk
    return {"term": None, "chain": [], "components": [], "summary": ""}
