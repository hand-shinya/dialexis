"""型・向き・宣言元を保った関係（2026-10-15・隔離試作）の試験。ネットワークを使わない。

守ること:
  1. 自分の言明（out）と相手の言明（in）を、同じ意味の関係として読ませない。
     P361 out は「A は B の一部」、in は「B は A の一部」。
  2. 対称の関係（P460 同一視・P461 対立・P1889 別物）だけが symmetric=True。
  3. 相手側の宣言は、画面の言語のラベルを持つ項目だけ（雑音の除去）。
  4. 人物と自分自身は出さない（星座と同じ）。
"""
from app.connectors import concept


def _claims(**kw):
    return {p: [{"mainsnak": {"datavalue": {"value": {"id": q}}}} for q in qs] for p, qs in kw.items()}


RES = {
    "Q13417770": {"label": "マルクス主義における疎外", "label_in_lang": True, "is_person": False},
    "Q7075072": {"label": "対象化", "label_in_lang": True, "is_person": False},
    "Q111": {"label": "商品物神崇拝", "label_in_lang": True, "is_person": False},
    "Q222": {"label": "red-tagging", "label_in_lang": False, "is_person": False},
    "Q5555": {"label": "カール・マルクス", "label_in_lang": True, "is_person": True},
    "Q9": {"label": "不条理", "label_in_lang": True, "is_person": False},
}


def rows():
    return concept.typed_relations(
        "Q863448", _claims(P361=["Q13417770"], P279=["Q7075072"], P461=["Q9"], P527=["Q5555"]),
        [("P279", "Q111"), ("P279", "Q222")], RES, [], "物象化", "ja")


def test_out_and_in_are_read_in_opposite_directions():
    by = {(r["qid"], r["direction"]): r for r in rows()}
    out = by[("Q13417770", "out")]
    assert out["rel"] == "P361" and out["declared_by"] == "this"
    assert out["reading"] == "{a} は {b} の一部"
    inn = by[("Q111", "in")]
    assert inn["declared_by"] == "other"
    assert inn["reading"] == "{b} は {a} の下位概念"


def test_only_symmetric_properties_are_symmetric():
    sym = {r["rel"]: r["symmetric"] for r in rows()}
    assert sym["P461"] is True
    assert sym["P361"] is False and sym["P279"] is False


def test_incoming_without_a_label_in_the_ui_language_is_dropped():
    assert "Q222" not in {r["qid"] for r in rows()}


def test_persons_are_not_relations():
    assert "Q5555" not in {r["qid"] for r in rows()}


def test_every_row_names_its_source():
    assert all(r["source"].startswith("https://") for r in rows())
