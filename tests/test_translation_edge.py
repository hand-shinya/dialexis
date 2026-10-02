"""訳語辺の固定データ試験（2026-10-02）。

この module は、半田様の指摘を受けて作られた。

    すでにウェブ上に有益な情報源が存在しているのに、それをあえて使わない
    という選択肢を取っていること自体が大問題だ。

実際の失敗は次の2件である。この試験はその再発を機械で止める。

- `love` 本体だけを見て「データ不足」と報告した。下位ページ `love/translations` の
  「strong affection」枠に ja=愛 と grc=ἀγάπη/φιλία/ἔρως/στοργή が揃っていた。
- Wikidata の検索上位（女性名）を採って「日本語ラベルが無い」と報告した。

固定データは 2026-10-02 に en.wiktionary から実取得した応答を縮約したものである。
人物名・枠跨ぎ・引数なし枠の3件は、実際に起きた事故を再現するための合成データである。
外部取得なし・決定論。
"""
import asyncio
import os
import tempfile

os.environ.setdefault("DIALEXIS_DB", os.path.join(tempfile.mkdtemp(), "test.db"))

from app.connectors import translation_edge as te  # noqa: E402

# ── 実取得（2026-10-02・love/translations の「strong affection」枠）を縮約 ──
LOVE_BODY = (
    "* Japanese: {{t+|ja|愛|tr=ai}}, {{t+|ja|愛情|tr=aijō}}, {{t+|ja|愛好|tr=aikō}}\n"
    "* Ancient Greek: {{t|grc|ἀγάπη}}, {{t|grc|φιλία}}, {{t|grc|ἔρως}}, {{t|grc|στοργή}}\n"
    "* Latin: {{t|la|amor}}, {{t|la|cāritās}}\n"
    "* German: {{t+|de|Liebe}}, {{t+|de|Zuneigung}}\n"
)
# 同じ頁の別枠。テニスの0点。ja=ラブ が入るが、枠が違うので混ざってはならない。
LOVE_ZERO_BODY = (
    "* Japanese: {{t+|ja|ラブ|tr=rabu}}, {{t+|ja|零点|tr=reiten}}\n"
    "* Latin: {{t|la|nulli}}\n"
)
LOVE_BODY_PAGE = "{{see translation subpage|Noun}}\n"
LOVE_SUBPAGE = (
    "{{trans-top|strong affection}}\n" + LOVE_BODY + "{{trans-bottom}}\n"
    "{{trans-top|zero}}\n" + LOVE_ZERO_BODY + "{{trans-bottom}}\n"
)

# 枠跨ぎの事故の再現（labour の grc に「出産」枠の τοκετός がある）
LABOUR_PAGE = (
    "{{trans-top|work}}\n"
    "* Japanese: {{t+|ja|労働|tr=rōdō}}\n"
    "* Ancient Greek: {{t|grc|ἔργον}}\n"
    "{{trans-bottom}}\n"
    "{{trans-top|giving birth}}\n"
    "* Ancient Greek: {{t|grc|τοκετός}}\n"
    "{{trans-bottom}}\n"
)

# 引数なし枠の再現（語義が特定できないため採ってはならない）
BARE_PAGE = (
    "{{trans-top}}\n"
    "* Japanese: {{t+|ja|危険語|tr=kiken}}\n"
    "* Ancient Greek: {{t|grc|ΔΑΝΓΕΡ}}\n"
    "{{trans-bottom}}\n"
)


def _install(monkeypatch, pages, pivots_found=None, routes=("insource",)):
    """_wikitext と pivots を固定応答へ差し替える。"""
    async def fake_wikitext(title):
        return pages.get(title, "")

    async def fake_pivots(ja_word, lang="ja"):
        return {"pivots": list(pivots_found or []), "routes_tried": list(routes)}

    monkeypatch.setattr(te, "_wikitext", fake_wikitext)
    monkeypatch.setattr(te, "pivots", fake_pivots)


def test_subpage_is_followed_and_four_greek_terms_are_found(monkeypatch):
    """下位ページを必ず辿る。本体だけで空と判定しない。

    これが 2026-10-02 の「データ不足」誤報の正確な再現防止である。
    """
    _install(monkeypatch,
             {"love": LOVE_BODY_PAGE, "love/translations": LOVE_SUBPAGE},
             ["love"])
    d = asyncio.run(te.collapse("愛"))["data"]
    assert d["matched"] is True
    hit = d["hit"]
    assert hit["page"] == "love/translations"
    assert hit["sense"] == "strong affection"
    grc = [x["term"] for x in hit["originals"] if x["lang"] == "grc"]
    assert grc == ["ἀγάπη", "φιλία", "ἔρως", "στοργή"]
    # 別枠の語が混ざってはならない
    assert "nulli" not in [x["term"] for x in hit["originals"]]
    assert "ラブ" not in hit["japanese_in_sense"]


def test_sense_frames_are_never_crossed(monkeypatch):
    """枠を跨いで原語を集めない。労働←出産の誤りを止める。"""
    _install(monkeypatch, {"labour": LABOUR_PAGE}, ["labour"])
    d = asyncio.run(te.collapse("労働"))["data"]
    assert d["matched"] is True
    terms = [x["term"] for x in d["hit"]["originals"]]
    assert "ἔργον" in terms
    assert "τοκετός" not in terms, "「出産」枠の語を労働の原語として採ってはならない"
    assert "giving birth" in d["hit"]["other_senses"]


def test_bare_trans_top_is_not_used(monkeypatch):
    """語義ラベルの無い枠は採らない。語義が特定できないため。"""
    _install(monkeypatch, {"danger": BARE_PAGE}, ["danger"])
    d = asyncio.run(te.collapse("危険語"))["data"]
    assert d["matched"] is False
    checked = d["headwords_checked"]
    assert checked and checked[0]["bare_blocks"] >= 1, (
        "引数なし枠の件数を記録し、空の理由を見えるようにすること")


def test_unreached_word_records_what_was_tried(monkeypatch):
    """到達できないとき、試した見出し語を残す。空を「無い」と言い換えない。

    権利が `right/translations` に法的権利の語義枠を持たないことが実例である。
    """
    _install(monkeypatch, {"right": "{{trans-top|of direction}}\n"
                                    "* Japanese: {{t+|ja|右|tr=migi}}\n"
                                    "{{trans-bottom}}\n"},
             ["patent", "right", "rightsholder"])
    d = asyncio.run(te.collapse("権利"))["data"]
    assert d["matched"] is False
    tried = [c["headword"] for c in d["headwords_checked"]]
    assert "right" in tried, "試した見出し語が記録されていない"
    assert len(tried) >= 2, "ピボット候補を複数試していない"


def test_headword_variants_absorb_known_mismatches():
    """Wikidata の en label と Wiktionary 見出し語のずれを吸収する。"""
    assert "right" in te.headword_variants("rights")
    assert "normal" in te.headword_variants("normality")
    assert "labour" in te.headword_variants("work")
    assert te.headword_variants("") == []


def test_layer_is_declared_as_general_dictionary(monkeypatch):
    """一般辞書の層であることを必ず宣言する。

    実測で objectification の訳表は Vergegenständlichung を持たない。
    哲学術語の原語として提示すると、過去の「対象化→objectification」と同型の
    誤りになる。層の宣言を落としてはならない。
    """
    _install(monkeypatch,
             {"love": LOVE_BODY_PAGE, "love/translations": LOVE_SUBPAGE},
             ["love"])
    d = asyncio.run(te.collapse("愛"))["data"]
    assert "一般辞書" in d["layer"]
    assert d["evidence"] == "candidate"
