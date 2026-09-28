"""典拠経路の差し替え条件の恒久試験（2026-09-28）。

ja.wikipedia の記事名を一次の解決器にしていたため、哲学語が無関係な項目へ
吸い寄せられていた（間主観性→ロバート・ストロロウ／対象化→対象関係論）。
典拠経路（Wikidata項目→原語→SEP）で是正したが、典拠経路も外すことがある
（現存在→現存在分析／道→thoroughfare）。ゆえに差し替えは「弱い解決」に限る。
この条件が緩むと36語の正しい解決が壊れるため、条件そのものを機械で固定する。
外部取得なし・決定論。
"""
from app.connectors.canon import _overlaps
from app.main import _canon_should_override


def test_overlaps_family():
    assert _overlaps("間主観", "間主観性")
    assert _overlaps("間主観性", "間主観")
    assert _overlaps("疎外", "疎外")
    assert not _overlaps("間主観性", "ロバート・ストロロウ")
    assert not _overlaps("対象化", "対象関係論")
    assert not _overlaps("", "疎外")


def test_override_fires_only_on_weak_resolution():
    # 弱い: 解決できていない
    assert _canon_should_override("仮象", "", False)
    assert _canon_should_override("非有機的肉体", "", False)
    # 弱い: 辿った名が問いと表記を共有しない（人物・別概念へ流れた）
    assert _canon_should_override("間主観性", "ロバート・ストロロウ", True)
    assert _canon_should_override("対象化", "対象関係論", True)
    # 強い: 触ってはならない（典拠経路が外す語を含む）
    assert not _canon_should_override("疎外", "疎外", True)
    assert not _canon_should_override("現存在", "現存在", True)
    assert not _canon_should_override("道", "道", True)
    assert not _canon_should_override("間主観", "間主観性", True)
    assert not _canon_should_override("縁起", "縁起", True)


def test_verified_lemmas_lookup():
    """検証済みの埋没語族が与える原語を、seedから正しく引けること。"""
    from app.main import _verified_lemmas_for
    assert "Vergegenständlichung" in _verified_lemmas_for("対象化")
    assert "Entfremdung" in _verified_lemmas_for("疎外")
    assert _verified_lemmas_for("間主観性") == []


def test_reject_override_that_contradicts_verified_seed():
    """検証済みの原語を持たない項目への差し替えを拒否すること。

    対象化 は Q7075072（objectification・「人間や動物を物として扱うこと」）に
    表記が一致してしまうが、検証済みseedは原語を Vergegenständlichung とし
    「本来は否定的でない」と定めている。dehumanization の文献へ導く誤りは
    空より危険なので、この差し替えは通してはならない。
    """
    from app.main import _canon_contradicts_verified
    objectification = {"ja": "対象化", "en": "objectification", "de": "Objektifizierung"}
    assert _canon_contradicts_verified(objectification, ["Vergegenständlichung"])
    alienation = {"ja": "疎外", "en": "social alienation", "de": "Entfremdung"}
    assert not _canon_contradicts_verified(alienation, ["Entfremdung", "Entäußerung"])
    # 検証済み原語が無い語では、この検査は何も止めない
    assert not _canon_contradicts_verified(objectification, [])
