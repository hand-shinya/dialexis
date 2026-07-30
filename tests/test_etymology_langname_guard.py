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
