"""新字体と旧字体の展開試験（2026-10-05）。

実測（10-04）: 『權理提綱』の本文OCRで「權理」は109回、「権理」は1回だった。
新字体だけで全文検索すると、近代の一次資料はほぼ取り逃がす。
この試験は、展開が常に自分自身を含み、既知の対応を漏らさないことを固定する。

外部取得なし・純関数・決定論。
"""
from app.connectors import kanji_variants as kv


def test_always_includes_itself():
    """展開は必ず元の語を含む。見つからなくても空にしない。"""
    for w in ("権理", "あいうえお", "nature", ""):
        assert w in kv.expand(w), f"自分自身が落ちている: {w}"


def test_shinjitai_to_kyujitai():
    """実測で必要だった対応を固定する。権理→權理。"""
    out = kv.expand("権理")
    assert "權理" in out, out


def test_kyujitai_to_shinjitai():
    """逆方向も引く。利用者が旧字体で打つ場合がある。"""
    assert "権利" in kv.expand("權利")


def test_multiple_characters_expand_together():
    """2文字とも対応を持つ語は、組み合わせを出す。"""
    out = kv.expand("学会")
    assert "學會" in out, out


def test_no_mapping_returns_single():
    """対応の無い語で候補を増やさない。騒音を出さない。"""
    assert kv.expand("退屈") == ["退屈"]


def test_bounded():
    """組み合わせ爆発を起こさない。上限を超えない。"""
    out = kv.expand("学会国体数学")
    assert len(out) <= kv.MAX_VARIANTS, len(out)


def test_table_is_bidirectional_and_disjoint():
    """表が双方向に引けて、同じ字を両側に持たない。"""
    for new, old in kv.TABLE.items():
        assert new != old
        assert kv.REVERSE[old] == new
