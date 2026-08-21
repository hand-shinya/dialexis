"""人物グラフの同一性表示と著作系譜データの回帰検証。"""

from app.main import _person_graph, _person_profile_for_query


def _marx_graph():
    profile = _person_profile_for_query("Karl Marx")
    assert profile
    return _person_graph(profile, "Karl Marx")


def test_person_aliases_are_one_visual_node_but_profile_data_survives():
    graph = _marx_graph()
    labels = [n["label"] for n in graph["nodes"] if n["kind"] == "language"]
    assert "カール・マルクス" in labels
    assert "カールマルクス" not in labels
    assert len(labels) == len({label.casefold().replace("・", "") for label in labels})
    forms = [x["form"] for x in graph["person_profile"]["name_forms"]]
    assert "カールマルクス" in forms


def test_manifest_has_work_lineage_and_curiosity_questions():
    profile = _person_profile_for_query("Karl Marx")
    work = next(w for w in profile["works"] if "共産党宣言" in w["japanese_titles"])
    assert work["original_title"] == "Manifest der Kommunistischen Partei"
    assert len(work["lineage"]) >= 3
    assert len(work["curiosity"]) >= 2
    assert any(x["stage"] == "公刊" for x in work["lineage"])


def test_manifest_node_keeps_stable_original_title_for_lineage_lookup():
    graph = _marx_graph()
    node = next(n for n in graph["nodes"] if n["label"] == "共産党宣言")
    assert node["kind"] == "work"
    assert node["original_title"] == "Manifest der Kommunistischen Partei"
    assert node["person_id"] == "karl-marx"
