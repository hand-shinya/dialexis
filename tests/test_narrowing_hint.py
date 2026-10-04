"""抽出語が多いときの絞り込み案内の試験（2026-10-05）。

半田様の指摘（10-05）: 対象語が多い場合、範囲を狭めれば抽出語が限定される、
という案内が出ると使いやすい。案内は画面の飾りではなく、payload に根拠
（何語出たか・閾値・具体的な狭め方）を持たせ、画面が勝手に言わない形にする。

純関数・外部取得なし・決定論。
"""
from app.main import narrowing_hint


def test_no_hint_when_few_candidates():
    """少ないときは出さない。黙って邪魔をしない。"""
    assert narrowing_hint(4, 120) is None


def test_hint_when_many_candidates():
    h = narrowing_hint(28, 9000)
    assert h is not None
    assert h["flagged"] == 28 and h["threshold"] > 0
    assert "狭め" in h["message"] or "絞" in h["message"]


def test_hint_suggests_a_concrete_action():
    """具体的な操作を示す。「工夫してください」で終わらせない。"""
    h = narrowing_hint(40, 20000)
    assert h["suggestions"] and len(h["suggestions"]) >= 2
    assert any("段落" in s or "一文" in s for s in h["suggestions"])


def test_hint_mentions_long_text_when_text_is_long():
    """長文のときは長さにも触れる。短文で多いときは長さの話をしない。"""
    assert "字" in narrowing_hint(30, 18000)["message"]
    short = narrowing_hint(30, 200)
    assert "字" not in short["message"], short["message"]


def test_threshold_is_declared_not_hidden():
    """閾値を payload に出す。画面が独自の基準を名乗れないようにする。"""
    h = narrowing_hint(12, 500)
    assert h is None or h["threshold"] == 10
