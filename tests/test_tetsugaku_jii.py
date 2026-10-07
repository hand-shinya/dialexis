"""訳語史層（『哲学字彙』1881年版）の試験。

この層は局所fileなので、外部の状態に左右されず決定論的に試験できる。
守りたいのは3つ。
  1. 半田様が指摘した「権利／通義／公道」の競合が、資料どおりに出ること
  2. 凡例の記法（割注・振り仮名・分野・斜体）を本文から分離すること
  3. 収録が無い語を、黙って空にせず missing と宣言すること
"""
from app.connectors import tetsugaku_jii as tj


def test_source_credit_is_complete():
    """CC BY 4.0 が要求する表示要素を payload から落とさない。"""
    s = tj.SOURCE
    for key in ("title", "base_text", "transcription", "publisher",
                "published", "license", "license_url", "url", "disclaimer"):
        assert s.get(key), key
    assert s["license"] == "CC BY 4.0"


def test_scale_is_what_we_measured():
    st = tj.stats()
    assert st["entries"] > 1900
    assert st["translations"] > 2700
    assert st["japanese_terms"] > 2400
    assert st["foreign_headwords"] >= 20


def test_right_carries_the_competing_translations():
    """半田様の指摘の核。1881年の Right に 権利・公道・通義 が並ぶ。"""
    d = tj.lookup("権利")["data"]
    assert d["headwords"] == ["Right"]
    sib = [s["term"] for s in d["sibling_terms"]]
    assert "通義" in sib and "公道" in sib
    assert "権利" not in sib          # 自分自身は兄弟に入れない


def test_right_has_two_entries_in_the_source():
    """Right は形容詞と名詞で2行ある。片方に畳んではならない。"""
    d = tj.lookup("Right")["data"]
    assert len(d["as_headword"]) == 2
    first = [t["term"] for t in d["as_headword"][0]["translations"]]
    second = [t["term"] for t in d["as_headword"][1]["translations"]]
    assert "正経" in first and "権利" in second


def test_thin_word_gains_siblings():
    """辞書層で読み1本しか出ない『普通』に、訳語史層が候補を与える。"""
    d = tj.lookup("普通")["data"]
    assert set(d["headwords"]) == {"Common", "General"}
    sib = {s["term"] for s in d["sibling_terms"]}
    assert {"一般", "尋常", "平凡"} <= sib


def test_eastern_terms_are_reachable():
    """自然の兄弟に仏教語が入る。東洋側が出ないという欠落への直接の答え。"""
    d = tj.lookup("自然")["data"]
    sib = {s["term"] for s in d["sibling_terms"]}
    assert "無碍" in sib


def test_foreign_headwords_are_marked():
    """Vernunft / Nirvana のような英語以外の見出しを拾い、印を立てる。"""
    d = tj.lookup("理性")["data"]
    assert "Vernunft" in d["headwords"]
    v = [e for e in d["as_translation"] if e["headword"] == "Vernunft"][0]
    assert v["foreign"] is True


def test_gloss_is_separated_from_terms():
    """割注［…］を訳語に混ぜない。涅槃の按文は notes 側に入る。"""
    d = tj.lookup("涅槃")["data"]
    e = d["as_translation"][0]
    assert [t["term"] for t in e["translations"]] == ["涅槃"]
    assert e["notes"] and "楞伽経" in e["notes"][0]


def test_field_label_is_separated():
    """（論）のような分野の略号を訳語の文字列に残さない。"""
    d = tj.lookup("Abduction")["data"]
    t = d["as_headword"][0]["translations"][0]
    assert t["term"] == "不明推測式"
    assert t["field"] == "論理学"


def test_section_letters_are_not_entries():
    """A / B / C のような区切り行を見出しとして拾わない。"""
    heads = {e["headword"] for e in tj._index()["entries"]}
    assert not any(len(h) == 1 and h.isalpha() for h in heads)


def test_missing_word_is_declared_not_silent():
    d = tj.lookup("気分")["data"]
    assert d["missing"] is True
    assert d["as_translation"] == [] and d["as_headword"] == []
    assert d["source"]["license"] == "CC BY 4.0"


def test_old_glyph_does_not_match_by_accident():
    """翻字は新字体に正規化されている。旧字体で引いたときに嘘の一致を作らない。"""
    d = tj.lookup("權利")["data"]
    assert d["missing"] is True


def test_headword_query_offers_its_translations():
    """西洋語の見出しで引いたとき、その訳語が次に辿る先になる。

    2026-10-07 の10人の模擬で、egoism が「主我学派・自利主義」を持つのに
    辺が0本になっていた。日本語から引いた場合しか見ていなかった。
    """
    d = tj.lookup("egoism")["data"]
    terms = [t["term"] for t in d["headword_terms"]]
    assert terms == ["主我学派", "自利主義"]
    assert d["missing"] is False


def test_near_headwords_bridge_without_equating():
    """「愛」自身の見出しは無い。語形が重なる別語を、別語として出す。"""
    d = tj.lookup("愛")["data"]
    assert d["missing"] is True
    near = {(n["term"], n["headword"]) for n in d["near_headwords"]}
    assert ("愛情", "Love") in near
    assert all(n["term"] != "愛" for n in d["near_headwords"])


def test_near_headwords_are_empty_when_the_word_itself_is_found():
    d = tj.lookup("権利")["data"]
    assert d["near_headwords"] == []
