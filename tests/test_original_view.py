"""原語版の記事から見る（所有者 2026-10-25 承認）。外部取得はすべて差し替える。

日本語版の記事だけでは、翻訳を経たあとの限られた範囲しか見えない。原語版の記事の節の構成と、本文がリンク
する項目に Wikidata の日本語の名前を付け、日本語版の本文にも在るかを並べる。機械翻訳は使わない。
"""
import asyncio

from app.connectors import original_view as ov

WT = """{{Infobox Livre|auteur=[[Michel Foucault]]}}'''Les Mots et les Choses''' est un [[essai (littérature)|essai]] de [[Michel Foucault]] (1966).
== Notion d’épistémè ==
[[Les Ménines]] de [[Diego Vélasquez]] ; [[1662]] ; [[14 septembre]] ; [[Fichier:x.jpg]]
== Réception ==
[[Jacques Lacan]] et [[Michel Foucault]].
== Notes et références ==
[[Ignoré]]
"""


def test_sections_keep_original_headings_and_drop_dates_files_and_reference_sections():
    secs = [(h, ov._links(t)) for h, t in ov._sections(WT) if not ov._SKIP_HEAD.match(h or "")]
    assert [h for h, _ in secs] == ["", "Notion d’épistémè", "Réception"]   # 見出しは原語のまま・参考文献の節は外す
    assert secs[0][1] == ["Essai (littérature)", "Michel Foucault"]          # 案内用の枠（テンプレート）の中のリンクは数えない
    assert secs[1][1] == ["Les Ménines", "Diego Vélasquez"]                 # 年・日付・ファイルは外す


def test_view_marks_what_the_japanese_article_also_has(monkeypatch):
    async def node(word, lang="ja"):
        return {"data": {"found": True, "qid": "Q1215306", "title": "言葉と物", "original_terms": []}}

    async def get(url, params=None, **k):
        p = params or {}
        if "wikidata" in url and p.get("props") == "sitelinks|claims":
            return {"entities": {"Q1215306": {"sitelinks": {"frwiki": {"title": "Les Mots et les Choses"}, "jawiki": {"title": "言葉と物"}},
                                              "claims": {"P1476": [{"mainsnak": {"datavalue": {"value": {"text": "Les Mots et les Choses", "language": "fr"}}}}]}}}}, "t", True
        if p.get("action") == "parse":
            return {"parse": {"wikitext": {"*": WT}}}, "t", True
        if p.get("prop") == "pageprops":
            m = {"Essai (littérature)": "Q35760", "Michel Foucault": "Q44272", "Les Ménines": "Q205418", "Diego Vélasquez": "Q297", "Jacques Lacan": "Q169845"}
            return {"query": {"pages": {str(i): {"title": t, "pageprops": {"wikibase_item": q}} for i, (t, q) in enumerate(m.items())}}}, "t", True
        if "wikidata" in url:
            ja = {"Q35760": "随筆", "Q44272": "ミシェル・フーコー", "Q205418": "ラス・メニーナス", "Q297": "ディエゴ・ベラスケス", "Q169845": "ジャック・ラカン"}
            return {"entities": {q: {"labels": {"ja": {"value": v}}} for q, v in ja.items()}}, "t", True
        raise AssertionError(p)

    async def resolved(title, lang):
        return [{"qid": "Q44272", "in_body": True}, {"qid": "Q205418", "in_body": True}, {"qid": "Q297", "in_body": False}]
    monkeypatch.setattr(ov.concept, "node", node)
    monkeypatch.setattr(ov.concept, "_article_resolved", resolved)
    monkeypatch.setattr(ov, "cached_get_json", get)
    d = asyncio.run(ov.view("言葉と物"))
    assert d["applies"] and d["lang"] == "fr" and d["title"] == "Les Mots et les Choses"
    first = {i["orig"]: (i["ja"], i["in_ja_article"]) for s in d["sections"] for i in s["items"] if not i["repeat"]}
    assert first["Michel Foucault"] == ("ミシェル・フーコー", True)
    assert first["Diego Vélasquez"] == ("ディエゴ・ベラスケス", False)    # 日本語版では案内用の枠だけ＝本文には無い
    assert d["counts"] == {"items": 5, "in_ja": 2, "only_here": 3}
