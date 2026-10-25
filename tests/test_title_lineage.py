"""著作の題の系譜と、題の語ごとの対応（所有者 2026-10-25 承認）。外部取得はすべて差し替える。

所有者の写し（10/25 21:34・言葉と物）: 「原語・翻訳語の対応」が著作の題を一つの語として「言葉／と／物」に
分けていた。題の単位で、原題 → 各国語の題 → 日本語の訳題をたどり、題の語ごとの対応は原語の辞書から引く。
"""
import asyncio

from app.connectors import title_lineage as tl

FR = {
    "mot": "{{trad+|ja|語}} {{trad-|ja|言葉}} {{trad+|en|word}} {{trad+|it|parola}}",
    "chose": "{{trad+|ja|事}} {{trad+|ja|物}} {{trad+|en|thing}} {{trad+|it|cosa}}",
    "et": "{{trad+|ja|と}} {{trad+|en|and}} {{trad+|it|e}}",
}


def _fake(monkeypatch):
    async def get(url, params=None, **k):
        page = (params or {}).get("page", "")
        return {"parse": {"wikitext": {"*": FR.get(page, "")}}}, "t", True
    monkeypatch.setattr(tl, "cached_get_json", get)


def test_title_words_are_aligned_from_the_original_language_dictionary(monkeypatch):
    _fake(monkeypatch)
    al = asyncio.run(tl._align("Les Mots et les Choses", "fr", "言葉と物", "ja"))
    assert [(a["orig"], a["lemma"], a["matched"]) for a in al] == [("Mots", "mot", "言葉"), ("et", "et", "と"), ("Choses", "chose", "物")]


def test_a_changed_title_is_shown_as_changed_and_inflections_still_match(monkeypatch):
    _fake(monkeypatch)
    en = asyncio.run(tl._align("Les Mots et les Choses", "fr", "The Order of Things", "en"))
    assert [a["matched"] for a in en] == ["", "", "thing"]          # 英語の題は別の題（chose だけが現れる）
    it = asyncio.run(tl._align("Les Mots et les Choses", "fr", "Le parole e le cose", "it"))
    assert [a["matched"] for a in it] == ["parola", "e", "cosa"]    # 複数形（parole・cose）でも同じ語とみる


def test_okurigana_of_a_dictionary_translation_is_dropped_in_a_title(monkeypatch):
    async def get(url, params=None, **k):
        return {"parse": {"wikitext": {"*": "{{Ü|ja|純粋な}}" if (params or {}).get("page") == "rein" else ""}}}, "t", True
    monkeypatch.setattr(tl, "cached_get_json", get)
    al = asyncio.run(tl._align("reinen", "de", "純粋理性批判", "ja"))
    assert al[0]["lemma"] == "rein" and al[0]["matched"] == "純粋な"


def test_years_and_translators_are_normalised():
    assert tl._year("１９３１") == "1931" and tl._year("昭和23") == "1948" and tl._year("1974-06-05") == "1974"
    ed = {"creators": ["Foucault, Michel, 1926-1984", "渡辺, 一民, 1932-2013", "佐々木, 明, 1934-2010", "ミシェル・フーコー"]}
    assert tl._translators(ed, ["ミシェル・フーコー"]) == ["渡辺一民", "佐々木明"]
    assert tl._translators({"creators": ["マルティーン・ハイデッカー", "寺島実仁"]}, ["マルティン・ハイデッガー"]) == ["寺島実仁"]
