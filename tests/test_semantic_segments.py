"""意味単位を文字単位より先に扱う契約のオフライン回帰テスト。"""

from app.connectors.etymology import _semantic_cjk_units, semantic_layers


def test_non_organic_body_prefers_meaningful_units():
    units = _semantic_cjk_units("非有機的肉体")
    assert [u["text"] for u in units] == ["非", "有機的", "肉体"]
    assert [u["role"] for u in units] == ["prefix", "lexical_unit", "lexical_unit"]
    assert all(len(u["text"]) >= 1 for u in units)


def test_layers_keep_characters_secondary_and_children_explicit():
    layers = semantic_layers("非有機的肉体")
    assert [x["level"] for x in layers] == ["whole", "semantic", "character"]
    assert layers[1]["priority"] < layers[2]["priority"]
    assert [u["text"] for u in layers[1]["units"]] == ["非", "有機的", "肉体"]
    assert layers[0]["units"][0]["children"] == list("非有機的肉体")
    assert layers[1]["units"][1]["children"] == list("有機的")
    assert [u["text"] for u in layers[2]["units"]] == list("非有機的肉体")


def test_unknown_cjk_is_preserved_as_a_unit_instead_of_char_split():
    layers = semantic_layers("未登録語彙")
    semantic = next(x for x in layers if x["level"] == "semantic")
    assert "未" in [u["text"] for u in semantic["units"]]
    assert any(len(u["text"]) > 1 for u in semantic["units"])


def test_alphabetic_etymology_has_whole_and_morphology_layers():
    layers = semantic_layers("dialectic")
    assert layers[0]["level"] == "whole"
    assert layers[1]["level"] == "semantic"
