"""文→概念の候補の接地（2026-10-15・隔離試作）。ネットワークを使わない。

LLM が挙げた記事名が無いとき opensearch の1位で引き直すと、18件中6件が別物だった
（カント倫理学→カントー大学・白い嘘→白い巨塔・持続（哲学）→持続可能な開発目標・
ジェームズ・ボーク→ジェームズ・ボンド・ウーバンツ→ウーバン（マサチューセッツ州）・相互承認→相互承認協定）。
引き直しは「表記がほぼ一致」かつ「概念らしい」ときだけ採る。2段のどちらでも落とせることを固定する。
"""
from app.connectors import bridge


def test_spelling_variants_are_close():
    assert bridge._close("人格同一性", "人格の同一性")
    assert bridge._close("サピア=ウォーフの仮説", "サピア＝ウォーフの仮説")
    assert bridge._close("業 (仏教)", "業")


def test_different_things_are_not_close():
    for a, b in [("カント倫理学", "カントー大学"), ("白い嘘", "白い巨塔 (2003年のテレビドラマ)"),
                 ("持続 (哲学)", "持続可能な開発目標"), ("ジェームズ・ボーク", "ジェームズ・ボンド"),
                 ("相互承認", "相互承認協定")]:
        assert not bridge._close(a, b), (a, b)


def test_a_place_is_not_a_concept_even_if_the_spelling_is_close():
    # ウーバンツ → ウーバン（マサチューセッツ州）は表記では近いが、市（Q1093829）は概念ではない
    assert bridge._close("ウーバンツ", "ウーバン (マサチューセッツ州)")
    city = {"p31": ["Q1093829"], "desc": "アメリカ合衆国マサチューセッツ州の都市"}
    assert not bridge.conceptish(city)


def test_persons_and_works_are_never_concepts():
    assert not bridge.conceptish({"p31": ["Q5"], "desc": "哲学者"})
    assert not bridge.conceptish({"p31": ["Q11424"], "desc": "哲学的な映画"})
    assert bridge.conceptish({"p31": ["Q151885"], "desc": ""})
