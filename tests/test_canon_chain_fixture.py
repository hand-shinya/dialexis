"""典拠経路（ja語 → Wikidata項目 → 原語/英語名 → SEP）の固定データ試験（2026-09-28）。

test_canon_override.py は「いつ差し替えるか」の条件だけを固定している。
この試験は「差し替え先を正しく選ぶか」を、外部取得なしで固定する。
resolve.e2e.js は ja.wikipedia・Wikidata の現在の状態に依存するため
network依存スイート（情報表示）へ移した（766c92f）。その結果、
「間主観性が精神分析家に解決される」欠陥の再発を、デプロイgateがどこでも
止めていなかった。この試験が pytest（gate対象）の側でそれを止める。

固定データ:
  - 間主観 / Q583467 / SEP 検索結果は 2026-09-28 17:1x JST に実取得した応答を縮約したもの
  - 人物・論文・QIDラベルの3件は、canon.py の docstring とコミット f6be1ae に記録された
    実際の事故（ロバート・ストロロウ、Entfremdung の論文一致、Q121180776 表示）を
    再現するための合成データ（実取得ではない）
"""
import asyncio
import os
import tempfile

os.environ.setdefault("DIALEXIS_DB", os.path.join(tempfile.mkdtemp(), "test.db"))

from app.connectors import canon  # noqa: E402
from app.connectors.base import ok  # noqa: E402

# ── 実取得（2026-09-28）を縮約した応答 ──
SEARCH_KANSHUKAN = [
    {"qid": "Q583467", "label": "間主観性"},
    {"qid": "Q6057182", "label": "間主観的に検証可能である"},
]
ENT_Q583467 = {
    "qid": "Q583467", "label": "間主観性", "label_en": "intersubjectivity",
    "is_person": False, "instance_of": [],
    "description": "psychological relation between people",
    "labels": {"ja": "間主観性", "en": "intersubjectivity",
               "de": "Intersubjektivität", "fr": "intersubjectivité"},
}
ENT_Q6057182 = {
    "qid": "Q6057182", "label": "間主観的に検証可能である",
    "label_en": "Intersubjective verifiability", "is_person": False,
    "instance_of": [], "labels": {"en": "Intersubjective verifiability"},
}
SEP_INTERSUBJECTIVITY = [
    {"title": "Alfred Schutz", "url": "https://plato.stanford.edu/entries/schutz/"},
    {"title": "Embodied Cognition", "url": "https://plato.stanford.edu/entries/embodied-cognition/"},
    {"title": "Edmund Husserl", "url": "https://plato.stanford.edu/entries/husserl/"},
]


def _install(monkeypatch, search_hits, entities, sep_hits=None, calls=None):
    """canon が使う3つの外部呼び出しを固定応答に差し替える。"""
    by_qid = {e["qid"]: e for e in entities}

    async def fake_search(q, lang="en", limit=8):
        return ok("wikidata", "fixture", True, list(search_hits))

    async def fake_batch(qids, lang="en"):
        return ok("wikidata", "fixture", True, [by_qid[q] for q in qids if q in by_qid])

    async def fake_sep(q, limit=6):
        if calls is not None:
            calls.append(q)
        return ok("sep", "fixture", True, list(sep_hits or []))

    monkeypatch.setattr(canon.wikidata, "search", fake_search)
    monkeypatch.setattr(canon.wikidata, "batch_entities", fake_batch)
    monkeypatch.setattr(canon.sep, "search", fake_sep)


def test_kanshukan_resolves_to_intersubjectivity_and_sep(monkeypatch):
    calls = []
    _install(monkeypatch, SEARCH_KANSHUKAN, [ENT_Q583467, ENT_Q6057182],
             SEP_INTERSUBJECTIVITY, calls)
    r = asyncio.run(canon.resolve("間主観", "ja"))
    assert not r["error"]
    d = r["data"]
    assert d["matched"] is True
    assert d["item"]["qid"] == "Q583467"
    assert d["item"]["label_en"] == "intersubjectivity"
    # SEP は日本語でなく英語名で照会する（日本語だと 間主観性 → Zhu Xi に破綻した）
    assert calls == ["intersubjectivity"]
    assert d["canon_entries"][0]["title"] == "Alfred Schutz"
    assert {"lang": "de", "term": "Intersubjektivität"} in d["original_terms"]


def test_person_with_overlapping_label_is_never_picked(monkeypatch):
    # 合成: 人物項目が表記の重なる上位に来ても採らない（P8 語と著者は別次元）
    person = {"qid": "Q3656697", "label": "間主観性", "is_person": True,
              "instance_of": ["Q5"], "labels": {}}
    _install(monkeypatch, [{"qid": "Q3656697", "label": "間主観性"}] + SEARCH_KANSHUKAN,
             [person, ENT_Q583467, ENT_Q6057182], SEP_INTERSUBJECTIVITY)
    ent = asyncio.run(canon.pick_item("間主観", "ja"))
    assert ent["qid"] == "Q583467"


def test_unrelated_top_hit_yields_no_match(monkeypatch):
    # 記事経路が流れた先（ロバート・ストロロウ）しか無い場合、典拠経路は何も選ばず、
    # 無関係な項目を典拠として出さない
    stolorow = {"qid": "Q3656697", "label": "ロバート・ストロロウ", "is_person": True,
                "instance_of": ["Q5"], "labels": {}}
    _install(monkeypatch, [{"qid": "Q3656697", "label": "ロバート・ストロロウ"}], [stolorow])
    r = asyncio.run(canon.resolve("間主観", "ja"))
    assert r["data"]["matched"] is False
    assert r["data"]["canon_entries"] == []


def test_scholarly_article_and_qid_label_are_rejected(monkeypatch):
    # 合成: Entfremdung が論文題名に一致した事故と、ラベルが生QIDで表示された事故
    article = {"qid": "Q1", "label": "Entfremdung", "is_person": False,
               "instance_of": ["Q13442814"], "labels": {}}
    qid_label = {"qid": "Q121180776", "label": "Q121180776", "is_person": False,
                 "instance_of": [], "labels": {}}
    _install(monkeypatch,
             [{"qid": "Q1", "label": "Entfremdung"},
              {"qid": "Q121180776", "label": "Entfremdung"}],
             [article, qid_label])
    assert asyncio.run(canon.pick_item("Entfremdung", "ja")) is None
