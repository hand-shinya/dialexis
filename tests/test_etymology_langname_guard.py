"""語源解剖の言語名guard 最小回帰（2026-07-30・止揚→Aufhebungで言語名Latinを辿り Latium+-īnus=ローマ
を構成要素に誤表示した事案の再発防止）。ネットワーク非依存＝parse_etymology と _is_langname の決定論検査のみ。"""
from app.connectors import etymology as e


def test_langname_detected_and_not_followed():
    # 言語名（単独/複合）は語源"語"でない＝辿ってはならない
    for name in ["Latin", "German", "French", "Ancient", "Old", "Middle",
                 "Ancient Greek", "Old French", "Late Latin", "Proto-Germanic"]:
        assert e._is_langname(name), f"{name} が言語名として検出されない"


def test_real_etymons_not_treated_as_langname():
    # 実在の語源語は言語名扱いしない（弁証法 dia+legein / 疎外 alienation 連鎖 / Aufhebung 等を潰さない）
    for term in ["dialectica", "διαλεκτική", "διά", "λέγειν", "aliēnātiōnem",
                 "alienation", "Aufhebung", "probare", "प्रतीत्यसमुत्पाद"]:
        assert not e._is_langname(term), f"{term} を言語名と誤判定した"


def test_prose_from_langname_not_used_as_component_source():
    # 「Borrowed from German Aufhebung.」型: 言語名 German/Latin を語源語として辿らない
    # ＝parse_etymology は言語名を term として構成要素抽出に使わない（Latium/-īnus 混入なし）
    text = ("==Etymology==\nBorrowed from German Aufhebung, from Latin. "
            "Doublet of something.\n==Noun==")
    r = e.parse_etymology(text)
    parts = [c["part"] for c in r.get("components", [])]
    assert "Latium" not in parts and "-īnus" not in parts, f"言語名由来の誤構成要素が混入: {parts}"


# ---- 構成（A + B + C）の抽出（2026-10-13・シミュレーションで発見） --------------------
# 本文は en.wiktionary の extracts を 2026-10-13 に実測したもの。「+」の後の U+200E も実物どおり。
# 旧版は全部分に（“意味”）が付く形しか取れず、独・羅・英 37語で構成を取れたのは2語だった。
# 原典から入るペルソナが「責任」に落ちた Antwort（応答）へ届かなかった。

def _comps(text):
    return [(c["part"], c["meaning"]) for c in e.parse_etymology("==Etymology==\n" + text + "\n==Noun==")["components"]]


def test_confix_with_unglossed_affixes_is_read():
    assert _comps("ver- +‎ Antwort (“answer”) +‎ -ung.") == [("ver-", ""), ("Antwort", "answer"), ("-ung", "")]


def test_equivalent_to_compound_is_read():
    t = ("From Middle High German vrīheit, from Old High German frīheit. "
         "Equivalent to frei (“free”) +‎ heit (“-hood”).")
    assert _comps(t) == [("frei", "free"), ("heit", "-hood")]


def test_language_names_are_not_parts():
    """duty: 言語名の後ろ半分（Middle）を部分に取っていた。"""
    t = "From Middle English duete, from Middle English dewe + Middle English -te. Equivalent to due + -ty."
    parts = [p for p, _ in _comps(t)]
    assert parts == ["dewe", "-te"], parts
    assert not any(e._is_langname(p) for p in parts)


def test_parenthesised_gloss_without_quotes_is_kept():
    """virtue: 括弧の中身を意味として使う代替を落とすと「abstract noun-forming suffix」が消える。"""
    t = "From vir (“man, male”) + -tūs (abstract noun-forming suffix)."
    assert _comps(t) == [("vir", "man, male"), ("-tūs", "abstract noun-forming suffix")]


def test_no_plus_no_components():
    """「+」の無い散文から構成を作らない（捏造しない・P6）。"""
    assert _comps("Inherited from Middle High German dīalectike, from Latin dialecticē.") == []
