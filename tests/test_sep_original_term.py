"""原語そのままで典拠を引く経路の固定試験（2026-10-02）。

半田様の指摘に対する、最も直接的な是正である。

    すでにウェブ上に有益な情報源が存在しているのに、それをあえて使わない
    という選択肢を取っていること自体が大問題だ。

実測で確認した事実（2026-10-02）。
  sep.search("Stimmung")      → ['Ludwik Fleck', 'Martin Heidegger']
  sep.search("Befindlichkeit") → ['Edith Stein', 'Martin Heidegger']

SEP は原語をそのまま投げれば正解を返す。壊れていたのは connector ではなく連携である。
main.py の3か所と canon.py の1か所、計4か所すべてが Wikidata の英語ラベル経由で
sep.search を呼んでいた。原語そのままで叩く経路が存在しなかった。
だから Stimmung はテレビ局（Stimmungsgarten TV）へ流れた。

同時に、日本語をそのまま投げてはならない。実測で「間主観性」は Zhu Xi を返す。
したがって条件は「ラテン文字を主体とする語のときだけ原語で叩く」である。

外部取得なし・決定論。
"""
import asyncio
import os
import tempfile

os.environ.setdefault("DIALEXIS_DB", os.path.join(tempfile.mkdtemp(), "test.db"))

from app.connectors import canon  # noqa: E402
from app.connectors.base import ok  # noqa: E402

# ── 実取得（2026-10-02）を縮約した応答 ──
SEP_STIMMUNG = [
    {"slug": "fleck", "title": "Ludwik Fleck",
     "url": "https://plato.stanford.edu/entries/fleck/",
     "snippet": "Jarnicki, Paweł, 2021, “Stimmung/Nastrój as Content of Modern Science”"},
    {"slug": "heidegger", "title": "Martin Heidegger",
     "url": "https://plato.stanford.edu/entries/heidegger/",
     "snippet": "“Mood (Stimmung)”, in Wrathall 2021a: 500–503"},
]
SEP_EN_LABEL = [
    {"slug": "dewey-moral", "title": "Dewey’s Moral Philosophy",
     "url": "https://plato.stanford.edu/entries/dewey-moral/", "snippet": ""},
]
ENT_TV = {
    "qid": "Q112973352", "label": "Stimmungsgarten TV", "label_en": "Stimmungsgarten TV",
    "is_person": False, "instance_of": [], "description": "TV channel",
    "labels": {"en": "Stimmungsgarten TV", "de": "Stimmungsgarten TV"},
}


def _install(monkeypatch, calls, by_term):
    """sep.search を語ごとの固定応答へ差し替え、呼ばれた語を記録する。"""
    async def fake_sep(q, limit=6):
        calls.append(q)
        return ok("sep", "fixture", True, list(by_term.get(q, [])))

    async def fake_search(q, lang="en", limit=8):
        return ok("wikidata", "fixture", True,
                  [{"qid": "Q112973352", "label": "Stimmungsgarten TV"}])

    async def fake_batch(qids, lang="en"):
        return ok("wikidata", "fixture", True, [ENT_TV] if "Q112973352" in qids else [])

    monkeypatch.setattr(canon.sep, "search", fake_sep)
    monkeypatch.setattr(canon.wikidata, "search", fake_search)
    monkeypatch.setattr(canon.wikidata, "batch_entities", fake_batch)


def test_latin_script_query_is_sent_to_sep_verbatim(monkeypatch):
    """ラテン文字の語は、原語そのままで典拠へ投げる。

    これが Stimmung 事故の正確な再現防止である。
    """
    calls = []
    _install(monkeypatch, calls,
             {"Stimmung": SEP_STIMMUNG, "Stimmungsgarten TV": SEP_EN_LABEL})
    d = asyncio.run(canon.resolve("Stimmung", "ja"))["data"]
    assert "Stimmung" in calls, (
        "原語そのままで sep.search を呼んでいない。"
        f"呼ばれたのは {calls} だけである")
    titles = [e["title"] for e in (d.get("canon_entries") or [])]
    assert "Martin Heidegger" in titles, f"Heidegger に到達していない: {titles}"


def test_japanese_query_is_not_sent_to_sep(monkeypatch):
    """日本語はそのまま典拠へ投げない。実測で間主観性は Zhu Xi を返す。"""
    calls = []
    _install(monkeypatch, calls, {})
    asyncio.run(canon.resolve("間主観性", "ja"))
    assert "間主観性" not in calls, (
        f"日本語をそのまま sep.search へ投げている: {calls}")


def test_sep_snippet_is_kept(monkeypatch):
    """典拠の該当箇所（節名）を捨てない。

    実測で Stimmung の結果には「Mood (Stimmung)」が snippet に出る。
    これは利用者が本文のどこを読むべきかを示す材料である。
    """
    calls = []
    _install(monkeypatch, calls,
             {"Stimmung": SEP_STIMMUNG, "Stimmungsgarten TV": SEP_EN_LABEL})
    d = asyncio.run(canon.resolve("Stimmung", "ja"))["data"]
    heid = [e for e in (d.get("canon_entries") or [])
            if e["title"] == "Martin Heidegger"]
    assert heid, "Heidegger の項目が無い"
    assert "Mood (Stimmung)" in (heid[0].get("locator") or ""), (
        f"snippet を捨てている: {heid[0]}")


def test_routes_tried_is_recorded(monkeypatch):
    """どの語で典拠を引いたかを応答に残す。空を「無い」と言い換えない。"""
    calls = []
    _install(monkeypatch, calls,
             {"Stimmung": SEP_STIMMUNG, "Stimmungsgarten TV": SEP_EN_LABEL})
    d = asyncio.run(canon.resolve("Stimmung", "ja"))["data"]
    terms = d.get("authority_terms_tried") or []
    assert "Stimmung" in terms, f"試した語が記録されていない: {terms}"


def test_is_latin_script_judgement():
    """ラテン文字主体かの判定を固定する。"""
    assert canon.is_latin_script("Stimmung")
    assert canon.is_latin_script("Befindlichkeit")
    assert canon.is_latin_script("unorganischer Leib")
    assert not canon.is_latin_script("間主観性")
    assert not canon.is_latin_script("アガペー")
    assert not canon.is_latin_script("")
