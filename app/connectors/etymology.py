"""普遍的な語源解剖（所有者指摘＝弁証法のdia-対話性の脱落を復元）。

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
    # 2026-10-13: 構成（A + B + C）を取る。旧版は全部分に（“意味”）が付く形しか取れず、
    # 「ver- +‎ Antwort (“answer”) +‎ -ung」（Verantwortung）のように意味の無い接辞が入ると全体を落としていた。
    # さらに Wiktionary は「+」の後に U+200E（左右制御文字）を置き、\s に一致しない。
    # 独・羅・英 37語で構成を取れたのは2語だった（sim_runs/_mut/etym_before.json）。
    # 意味の無い部分は meaning を空のまま返す（捏造しない・P6）。
    seg_c = re.sub("[\u200e\u200f]", "", seg)
    # 言語名の並び（Middle English・Proto-Indo-European 等）は部分ではない。duty の
    # 「Middle English dewe + Middle English -te」で Middle を部分に取っていた。
    seg_c = re.sub(r"\b[A-Z][A-Za-z]+(?:[\s\-]+[A-Z][A-Za-z]+)*\b\s*",
                   lambda m: "" if _is_langname(m.group(0)) else m.group(0), seg_c)
    tok = r"[^\s+(),.;:“”\"]+"
    cm = re.search(r"(" + tok + r"(?:\s*\([^)]*\))?(?:\s*\+\s*" + tok + r"(?:\s*\([^)]*\))?)+)", seg_c)
    if cm:
        for term, inside in re.findall(r"(" + tok + r")(?:\s*\(([^)]*)\))?", cm.group(1)):
            comps.append({"part": term.strip(), "meaning": (_gloss(inside) or inside.strip()[:40]) if inside else ""})
    return {"summary": re.sub(r"\s+", " ", seg).strip()[:400], "chain": chain[:6], "components": comps[:6]}


def _clean_gloss(s):
    s = re.sub(r"\([^)]*\)", "", s or "")           # 括弧注記を落とす
    s = re.sub(r"[；;].*$", "", s)                    # 全角/半角セミコロン以降を落とす（第一義だけ）
    return s.strip(" \t,.:：、。").strip()


# 「一文字＝最小単位」と決め打ちしないための、保守的な意味境界辞書。
# これは意味を生成する辞書ではなく、既にまとまりとして読める語を保つための境界辞書である。
# 未登録語を無理に切らず、whole-term として返すことで、誤った分解を確定しない。
_SEMANTIC_LEXEMES = {
    "有機的", "有機体", "肉体", "身体", "身体性", "精神", "意識", "主体", "客体",
    "自由", "意志", "自由意志", "共同", "幻想", "共同幻想", "意味", "空間", "意味空間",
    "言語", "哲学", "概念", "構成", "要素", "構成要素", "弁証法", "弁証", "唯物論",
    "唯心論", "存在", "存在論", "現象学", "間主観性", "自己", "自己意識", "社会",
    "構造", "社会構造", "生産", "関係", "生産関係", "対話", "対立", "矛盾", "他者",
    "権力", "贈与", "実存", "疎外", "歴史", "時間", "空", "無", "知的", "好奇心",
    "知的好奇心", "教育", "心理", "研究", "言語研究", "思想", "文化", "世界",
}

# 明確に複数の語彙単位へ読める代表的な連接。ここでも文字単位には落とさない。
_SEMANTIC_SPLITS = {
    "非有機的肉体": ["非", "有機的", "肉体"],
    "非有機的身体": ["非", "有機的", "身体"],
    "自由意志": ["自由", "意志"],
    "共同幻想": ["共同", "幻想"],
    "意味空間": ["意味", "空間"],
    "社会構造": ["社会", "構造"],
    "生産関係": ["生産", "関係"],
    "自己意識": ["自己", "意識"],
    "知的好奇心": ["知的", "好奇心"],
    "言語研究": ["言語", "研究"],
}

_SEMANTIC_PREFIXES = (
    "非", "無", "不", "未", "反", "超", "脱", "再", "前", "後", "新", "旧", "半", "準",
)
_SEMANTIC_AFFIX_GLOSSES = {
    "非": "否定・非〜",
    "無": "欠如・無〜",
    "不": "否定・不〜",
    "未": "未成立・まだ〜でない",
    "反": "反対・対抗",
    "超": "越える・超〜",
    "脱": "外れる・脱〜",
    "再": "もう一度・再〜",
}


def _is_cjk_word(s):
    return bool(re.search(r"[㐀-鿿豈-﫿]", s or ""))


def _semantic_unit(text, role="lexical_unit", source="lexical-boundary", confidence="medium"):
    return {
        "text": text,
        "role": role,
        "gloss": _SEMANTIC_AFFIX_GLOSSES.get(text, ""),
        "children": list(text),
        "source": source,
        "confidence": confidence,
    }


# 接尾の一字（前の語に付ける: 有機＋的→有機的、存在＋論＋的→存在論的）。
_SEMANTIC_SUFFIXES = ("的", "性", "化", "論", "者", "観", "史", "界", "感", "学", "主義")
_SEP = re.compile(r"[・･·\s、,／/\-]+")
# 漢字・カタカナに挟まれた助詞（ひらがなの語の中のものは分けない）。長いものから照合する
# （死への存在 → 死＋への＋存在、他者との対話 → 他者＋との＋対話、ゼノンのパラドックス）。所有者の承認 10/23
_PARTICLE = re.compile(r"(?<=[\u30A0-\u30FF\u4E00-\u9FFF])(における|による|への|との|の|と|や)(?=[\u30A0-\u30FF\u4E00-\u9FFF])")
_NO_PARTICLE = _PARTICLE
_PARTICLES = {"における", "による", "への", "との", "の", "と", "や"}
_KATA = re.compile(r"[\u30A1-\u30FA\u30FC]{2,}")
_KATA_CH = re.compile(r"[\u30A1-\u30FA\u30FC]")
WIKT_JA = "https://ja.wiktionary.org/w/api.php"


async def _wikt_titles(word):
    """語の中の2字以上の部分のうち、ja.wiktionary に見出しとして在るもの（外部取得・キャッシュ）。
    戻り値: (titles:set, retrieved_at, error)。取れないときは空集合と理由（不在と区別する）。"""
    parts = [x for x in _SEP.split(word) if x]
    subs = sorted({c[i:j] for c in parts for i in range(len(c)) for j in range(i + 2, len(c) + 1)})
    subs = [x for x in subs if _is_cjk_word(x) or _KATA.fullmatch(x)][:150]
    found, at, err = set(), None, None
    for k in range(0, len(subs), 50):
        chunk = subs[k:k + 50]
        try:
            d, at, _ = await cached_get_json(WIKT_JA, params={"action": "query", "titles": "|".join(chunk),
                                                              "format": "json", "formatversion": 2},
                                             ttl=30 * 86400)
            for pg in (d.get("query") or {}).get("pages") or []:
                if not pg.get("missing") and not pg.get("invalid") and pg.get("title"):
                    found.add(pg["title"])
        except Exception as e:  # noqa: BLE001 — 取れないことは「見出しが無い」ことではない
            err = type(e).__name__
    return found, at, err


def _dp_units(chunk, known):
    """known（見出し・境界辞書）だけを使い、まとまりの数が最小になる分け方を求める。
    先頭の接頭辞1字・接尾の字は許すが、根拠の無い字は「未解決」として最小限に残す。"""
    n = len(chunk)
    INF = (10 ** 6, 0)
    best = [INF] * (n + 1)   # (未解決の字数*10+まとまり数, -)
    back = [None] * (n + 1)
    best[0] = (0, 0)
    for i in range(n):
        if best[i] == INF:
            continue
        for j in range(i + 1, n + 1):
            piece = chunk[i:j]
            # カタカナの語は内側で切らない（ヘーゲル を ヘー＋ゲル にしない）。カタカナの連なり全体が見出しの時だけ採る
            kata_ok = not _KATA.fullmatch(piece) or ((i == 0 or not _KATA_CH.match(chunk[i - 1])) and (j == n or not _KATA_CH.match(chunk[j])))
            if len(piece) >= 2 and piece in known and kata_ok:
                kind, cost = "lexical_unit", 1
            elif i == 0 and piece in _SEMANTIC_PREFIXES and n - j >= 2:
                kind, cost = "prefix", 1
            elif i > 0 and piece in _SEMANTIC_SUFFIXES:
                kind, cost = "suffix", 0
            elif j == i + 1:
                kind, cost = "unresolved_unit", 10
            else:
                continue
            c = (best[i][0] + cost, 0)
            if c < best[j]:
                best[j], back[j] = c, (i, kind)
    out, j = [], n
    while j > 0:
        i, kind = back[j]
        out.append((chunk[i:j], kind)); j = i
    out.reverse()
    merged = []
    for piece, kind in out:   # 接尾は前のまとまりに付ける。続く未解決の字は一つにまとめる
        if kind == "suffix" and merged and merged[-1][1] != "prefix":
            merged[-1] = (merged[-1][0] + piece, merged[-1][1])
        elif kind == "unresolved_unit" and merged and merged[-1][1] == "unresolved_unit":
            merged[-1] = (merged[-1][0] + piece, kind)
        else:
            merged.append((piece, "lexical_unit" if kind == "suffix" else kind))
    return merged


async def grounded_cjk_units(word):
    """辞書（ja.wiktionary の見出し）に接地した意味のまとまり。境界辞書で分かれない語にだけ使う。
    語全体が見出しにあるときは分けない（弁証法を 弁証＋法 にしない）。"""
    word = unicodedata.normalize("NFKC", word or "").strip()
    # 漢字を含む語に加え、助詞でつながるカタカナの語（ゼノンのパラドックス）も分ける
    if not word or not (_is_cjk_word(word) or _PARTICLE.search(word)) or word in _SEMANTIC_SPLITS:
        return None
    titles, at, err = await _wikt_titles(word)
    known = titles | _SEMANTIC_LEXEMES
    if word in known or (len(word) < 3 and not _SEP.search(word)):
        return None
    units = []
    for chunk0 in [x for x in _SEP.split(word) if x]:
        # 助詞「の」は前後の語と分ける（ライプニッツの記法 → ライプニッツ＋の＋記法。
        # 以前は「ライプニッツの」を一つの未確認のまとまりにしていた・所有者の写し 10/23 17:34）
        for chunk in [x for x in _PARTICLE.split(chunk0) if x]:
            if chunk in _PARTICLES and chunk != chunk0:
                units.append((chunk, "particle")); continue
            if chunk in known:
                units.append((chunk, "lexical_unit")); continue
            units.extend(_dp_units(chunk, known))
    if len([u for u in units if u[1] != "particle"]) < 2:
        return None
    out = []
    for piece, kind in units:
        if kind == "particle":
            out.append(_semantic_unit(piece, "particle", "particle", "high")); continue
        u = _semantic_unit(piece, kind,
                           "ja.wiktionary" if piece in titles else
                           ("lexical-boundary" if kind == "lexical_unit" else
                            ("derivational-boundary" if kind == "prefix" else "whole-term-preserved")),
                           "high" if kind in ("lexical_unit", "prefix") else "low")
        stem = piece if piece in titles else next((piece[:k] for k in range(len(piece) - 1, 1, -1) if piece[:k] in titles), None)
        if stem:   # 接尾を付けたまとまり（存在＋論的）は、語幹の見出しを根拠として示す
            u["source"] = "ja.wiktionary"
            u["url"] = f"https://ja.wiktionary.org/wiki/{stem}"
            u["retrieved_at"] = at
        out.append(u)
    if err:
        out[0]["source_error"] = err
    return out


async def semantic_layers_grounded(word, **kw):
    """semantic_layers と同じ契約。CJK 語の「意味のまとまり」だけを辞書の見出しで補う。"""
    layers = _semantic_layers(word, **kw)
    try:
        g = await grounded_cjk_units(word)
    except Exception:  # noqa: BLE001
        g = None
    if g:
        for L in layers:
            if L.get("level") == "semantic":
                cur = L.get("units") or []
                weak = len(cur) < 2 or any(u.get("role") == "unresolved_unit" for u in cur)
                if weak:
                    L["units"] = g
    return layers


def _semantic_cjk_units(word):
    """CJK語を、意味を担うまとまりの層へ保守的に分ける。

    重要な契約:
      * 既知の意味単位を先に採用する。
      * 未知の連続部分は一つのまとまりとして保持する。
      * 文字分解はこの関数の責務ではなく、常に下位層へ置く。
    """
    word = unicodedata.normalize("NFKC", word or "").strip()
    if not word or not _is_cjk_word(word):
        return []
    if word in _SEMANTIC_SPLITS:
        return [_semantic_unit(x, "prefix" if x in _SEMANTIC_PREFIXES else "lexical_unit",
                               "curated-semantic-boundary", "high")
                for x in _SEMANTIC_SPLITS[word]]

    rest = word
    units = []
    # 接頭辞は、後続に少なくとも2文字の語彙的なまとまりがある時だけ分ける。
    for prefix in sorted(_SEMANTIC_PREFIXES, key=len, reverse=True):
        if rest.startswith(prefix) and len(rest) - len(prefix) >= 2:
            units.append(_semantic_unit(prefix, "prefix", "derivational-boundary", "high"))
            rest = rest[len(prefix):]
            break

    lexemes = sorted(_SEMANTIC_LEXEMES, key=len, reverse=True)
    while rest:
        hit = next((x for x in lexemes if rest.startswith(x)), None)
        if hit:
            units.append(_semantic_unit(hit, "lexical_unit", "lexical-boundary", "high"))
            rest = rest[len(hit):]
            continue
        # 根拠のない一文字分解を避ける。未知の残りは一まとまりで示す。
        units.append(_semantic_unit(rest, "unresolved_unit", "whole-term-preserved", "low"))
        break

    if not units:
        return [_semantic_unit(word, "whole_term", "whole-term-preserved", "high")]
    return units


def _semantic_layers(word, components=None, char_units=None):
    """UIが同じ契約で扱える分解層を作る（外部取得なし）。"""
    word = unicodedata.normalize("NFKC", word or "").strip()
    if not word:
        return []
    chars = list(dict.fromkeys(re.sub(r"[^㐀-鿿豈-﫿]", "", word)))
    layers = [{
        "level": "whole",
        "label": "語全体",
        "priority": 0,
        "units": [{"text": word, "role": "whole_term", "gloss": "", "children": chars,
                   "source": "user-term", "confidence": "high"}],
    }]
    if _is_cjk_word(word):
        semantic = _semantic_cjk_units(word)
        layers.append({"level": "semantic", "label": "意味のまとまり", "priority": 1, "units": semantic})
        if char_units is None:
            char_units = [{"text": ch, "role": "character", "gloss": "", "children": [],
                           "source": "character-boundary", "confidence": "secondary"} for ch in chars]
        layers.append({"level": "character", "label": "文字構成（補助）", "priority": 3, "units": char_units})
        return layers

    morph = []
    for c in components or []:
        text = c.get("part") or c.get("text")
        if text:
            morph.append({"text": text, "role": "etymological_component", "gloss": c.get("meaning", ""),
                          "children": [], "source": "Wiktionary", "confidence": "grounded"})
    if morph:
        layers.append({"level": "morphology", "label": "語源的な構成要素", "priority": 2, "units": morph})
    else:
        layers.append({"level": "semantic", "label": "意味のまとまり", "priority": 1,
                       "units": [{"text": word, "role": "whole_term", "gloss": "", "children": [],
                                  "source": "whole-term-preserved", "confidence": "medium"}]})
    return layers


def semantic_layers(word):
    """外部取得を伴わない、全API共通の意味分解契約。"""
    return _semantic_layers(word)


_HAN_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")


async def _han_senses(ch, limit=10):
    """CJK 1文字の辞書義を、辞書に載っている順に複数拾う（2026-10-14 所有者決裁）。

    第一義だけを出すと、語の中での意味と取り違える（物象化の 象＝elephant。
    物象の象は「かたち・現れ」）。この型の誤りは4回目だった（引き継ぎ第7世代 類型D）。
    用例行（幼象 ― young elephant）・引用（漢字を含む行）・見出しは語義として数えない。"""
    text = await _extract(ch)
    if not text:
        return []
    m = re.search(r"Definitions\s*=*\s*\n+" + re.escape(ch) + r"\s*\n+", text)
    if not m:
        return []
    out = []
    for line in text[m.end():].split("\n")[:60]:
        line = line.strip()
        if line.startswith("=="):
            break
        bare = re.sub(r"\([^)]*\)", "", line)      # (Classifier: 頭) の漢字は語義の注記で、用例ではない
        if not line or "―" in line or _HAN_CJK.search(bare) or len(bare) > 90:
            continue
        if not re.match(r"^[(A-Za-z]", line):
            continue
        g = _clean_gloss(line)
        # 「elephant: 🩩」のような、既に挙げた語義の記号の注記は重ねない
        if g and any(g.startswith(x + ":") for x in out):
            continue
        if g and g not in out:
            out.append(g)
        if len(out) >= limit:
            break
    return out


def _sense_confirmed(senses, word_text):
    """この語での字の意味を、機械で確かめられるか。

    確かめたことにするのは2つだけ: 字の辞書義が1つしかない（取り違えようがない）、
    または語そのものの辞書項の本文に、字の語義の語が現れる。どちらでもなければ未確認。"""
    if len(senses) == 1:
        return True
    body = (word_text or "").lower()
    if not body:
        return False
    for g in senses:
        for tok in re.findall(r"[a-z]{4,}", re.sub(r"\([^)]*\)", "", g.lower())):
            if re.search(r"\b" + re.escape(tok) + r"\b", body):
                return True
    return False


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
    """CJK 語の解剖: 意味単位を先に確定し、文字の義は補助層として添える。
    旧来の文字分解は保持するが、表示優先順位は
    語全体 → 意味のまとまり → 文字構成、で固定する。

    2026-10-09: 字義が語義として読まれる害を閉じる。
      「非有機的肉体」で 機=weaving machine・的=bright・体=alternative form of 笨
      が返るが、この3字はいずれも「有機的」「肉体」という意味単位の内側の字で
      あって、語の意味の構成要素ではない。字義をそのまま並べると、語の由来を
      説明しているように読める。各字に、どの意味単位の内側に居るか（in_unit）と、
      語そのものに適用できるか（applies_to_term）を持たせ、
      何字が語義として読めないかを components_note に書く。
      字義そのものは削らない（削ると沈黙する欠落になる・公理1）。"""
    word = unicodedata.normalize("NFKC", word or "")   # F3: 互換漢字で印が外れるのを防ぐ
    cjk = re.sub(r"[^㐀-鿿豈-﫿]", "", word)
    if len(cjk) < 2:
        return None
    semantic = _semantic_cjk_units(word)
    if len(semantic) < 2 or any(u.get("role") == "unresolved_unit" for u in semantic):
        try:
            semantic = (await grounded_cjk_units(word)) or semantic   # 辞書の見出しで補う（意味の層と同じ分け方）
        except Exception:  # noqa: BLE001
            pass
    # F1: 語そのものが1つの単位なら、その字は「内側」ではない。
    #     矛盾 は 1 単位（矛盾）なので、矛=spear・盾=shield は語の由来そのものである
    #     （同じ応答の summary が「韓非子の故事に由来」と言い、
    #      tests/e2e/anatomy.e2e.js は矛+盾を正解として守っている）。
    #     ここに印を付けると、この repository 自身の gate が守る情報を画面で否定する。
    whole_is_one_unit = (len(semantic) == 1
                         and (semantic[0].get("text") or "") == word)
    # F2: 未解決の残り（role=unresolved_unit・confidence=low）は語ではない。
    #     「越論的」「夜城」「機的身体」のような機械推定を「意味のまとまり」と呼ばない。
    unit_of, unit_kind = {}, {}
    if not whole_is_one_unit:
        for u in semantic:
            t = u.get("text") or ""
            if len(t) < 2 or t == word:
                continue
            for ch in t:
                unit_of.setdefault(ch, t)
                unit_kind.setdefault(t, "unresolved"
                                     if u.get("role") == "unresolved_unit"
                                     or u.get("confidence") == "low" else "lexical")
    comps = []
    char_units = []
    word_text = await _extract(word)
    for ch in list(dict.fromkeys(cjk))[:6]:          # 重複字は1回・最大6字
        senses = await _han_senses(ch)
        g = senses[0] if senses else await _han_gloss(ch)
        if g and not senses:
            senses = [g]
        confirmed = _sense_confirmed(senses, word_text)
        # 確かめられない字は、第一義だけを断定せず、辞書義を並べて示す
        shown = g if confirmed else " / ".join(senses)
        inside = unit_of.get(ch, "")
        kind = unit_kind.get(inside, "")
        char_units.append({"text": ch, "role": "character", "gloss": shown,
                           "children": [], "source": "Wiktionary",
                           "in_unit": inside, "unit_kind": kind,
                           "applies_to_term": not inside,
                           "senses": senses, "sense_confirmed": confirmed,
                           "confidence": "grounded" if (g and confirmed) else "unverified"})
        if g:
            comps.append({"part": ch, "meaning": shown,
                          "in_unit": inside, "unit_kind": kind,
                          "applies_to_term": not inside,
                          "senses": senses, "sense_confirmed": confirmed})
    # F4: 文面はUI側が LANG で組めるよう、構造でも返す。
    lex = list(dict.fromkeys(c["in_unit"] for c in comps
                             if c["in_unit"] and c["unit_kind"] == "lexical"))
    unres = list(dict.fromkeys(c["in_unit"] for c in comps
                               if c["in_unit"] and c["unit_kind"] == "unresolved"))
    parts = {
        "inside_count": sum(1 for c in comps if not c["applies_to_term"]),
        "lexical_units": lex,
        "unresolved_units": unres,
        "whole_is_one_unit": whole_is_one_unit,
        "unconfirmed_sense_count": sum(1 for c in comps if not c["sense_confirmed"]),
    }
    # F5: 画面に出る文に否定表現を使わない（「ありません」は
    #     tests/e2e/aspect_no_recenter.e2e.js の禁止語で、deploy gate が落ちた）。
    bits = []
    if lex:
        bits.append("うち {n} 字は「{u}」という意味のまとまりの内側にある字です".format(
            n=sum(1 for c in comps if c["unit_kind"] == "lexical"),
            u="」「".join(lex)))
    if unres:
        bits.append("「{u}」はまだ意味のまとまりへ切り分けられていない部分です（機械推定・低確度）".format(
            u="」「".join(unres)))
    note = ""
    if bits:
        note = "下は1字ごとの辞書義です。" + "。".join(bits) + "。語の意味は「意味のまとまり」の層で見てください。"
    if parts["unconfirmed_sense_count"]:
        note = (note + " " if note else "") + (
            "1字に辞書義が複数あるときは並べて示します。この語の中でどの意味かは、"
            "辞書で確かめていない字（未確認）があります。")
    summary = _etym_prose(word_text)
    return {"term": word, "chain": [], "components": comps, "summary": summary,
            "components_note": note, "components_note_parts": parts,
            "semantic_segments": semantic,
            "segment_layers": await semantic_layers_grounded(word, char_units=char_units),
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
    表層で Latin 止まりの語も、英語 dialectic と同じ深さ（希語の dia+legein）へ統一する（所有者指摘・普遍）。
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
        # 意味の付いた部分が1つも無い構成（dialecticus + -ē のような接尾辞付加）は根の構成要素ではない。
        # ここで止めると Dialektik が dia+legein まで届かない（所有者指摘「どの言語形からも同じ深さ」）。
        # 深く辿れなかったときの控えとしてだけ持つ。
        if sub.get("components") and any(c.get("meaning") for c in sub["components"]):
            r["components"] = sub["components"]
            break
        if sub.get("components") and not r.get("_shallow"):
            r["_shallow"] = sub["components"]
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
    # 入力がラテン文字などの原語なら、まずその語自身の項を試す。訳語（英語等）を先に試すと、
    # Verantwortung を入れて英語 responsibility の来歴が返っていた（P1 無中心: 特定言語を経由させない）。
    own_first = bool(word and re.search(r"[A-Za-zΑ-Ωα-ωÀ-ÿ]", word))
    order = ([word] if own_first else []) + [t for t in orig_terms if t and t != word] + ([] if own_first else [word])
    for term in order:
        if not term or not re.search(r"[A-Za-zΑ-Ωα-ωÀ-ÿ]", term):
            continue
        text = await _extract(term)
        if text and "Etymology" in text:
            r = parse_etymology(text)
            if r["chain"] or r["components"]:
                r["term"] = term
                r["wiktionary_url"] = f"https://en.wiktionary.org/wiki/{term}"
                await _deepen_chain(r)   # 連鎖を最古層まで辿り、根の構成要素まで到達＝どの言語形から入っても同じ深さ（統一）
                shallow = r.pop("_shallow", None)
                if not r.get("components") and shallow:
                    r["components"] = shallow
                r["segment_layers"] = _semantic_layers(term, components=r.get("components"))
                r.setdefault("components_note", "")   # 契約: どの経路でもキーが在る
                r.setdefault("components_note_parts", {})
                return r
    cjk = await _cjk_anatomy(word)                    # CJK 語の構成文字分解（矛盾→矛＋盾）
    if cjk:
        return cjk
    return {"term": None, "chain": [], "components": [], "summary": "",
            "components_note": "", "components_note_parts": {},
            "segment_layers": await semantic_layers_grounded(word)}
