"""ja.wiktionary から辞書層の辺を取る試験（2026-10-05）。

なぜ必要か（2026-10-04 実測）:
  我々は en.wiktionary だけを引いていた。ja.wiktionary の「自然」には
  呉音「じねん」と語義「あるがまま…無為」が、「理性」には類義語
  「ロゴス・論理・知性」と対義語「感性」が、構造化されて入っていた。
  28歳UIデザイナーと35歳看護師が求めた層は、引いていない辞書に在った。

この試験は実取得した wikitext を縮約した固定値で、解析だけを検証する。
外部取得なし・決定論。
"""
from app.connectors import ja_wiktionary as jw

SHIZEN = """{{kana-DEFAULTSORT|しぜん}}
=={{L|ja}}==
{{ja-kanjitab|し|ぜん|yomi=kanon}}
{{ja-kanjitab|じ|ねん|yomi=goon}}
==={{noun}}・{{adjectivenoun}}===
{{ja-noun|[[しぜん]]}}（古:[[じねん]]）
#[[あるがまま]]であること。人の[[意思]]を[[もつ|持っ]]た[[行為]]により、[[変化]]が[[くわえる|加え]]られていないこと。[[無為]]。
#ある物事の[[因果]]やある人の[[行動]]に、[[不思議]]さがないこと。
===={{syn}}====
語義1
*[[天然]]
*[[ネイチャー]]
語義2
*[[当然]]
===={{ant}}====
語義1
*[[人為]]
*[[人工]]
語義2
*[[不自然]]
"""

RISEI = """=={{L|ja}}==
==={{noun}}===
#[[物事]]を[[論理的]]に[[考える]][[能力]]。
===={{syn}}====
*[[ロゴス]]
*[[論理]]
*[[知性]]
===={{ant}}====
*[[感性]]
"""

KENRI = """=={{L|ja}}==
===={{ant}}====
*[[義務]]
===={{rel}}====
*[[人権]]、[[生存権]]
*[[物権]]、[[所有権]]、[[債権]]
"""


def test_goon_reading_is_recovered():
    """呉音「じねん」を落とさない。漢音だけを読みとしない。"""
    r = jw.readings(SHIZEN)
    pairs = {(x["kana"], x["yomi"]) for x in r}
    assert ("じねん", "goon") in pairs, r
    assert ("しぜん", "kanon") in pairs, r


def test_senses_are_extracted_in_order():
    """語義を順序どおりに取る。「無為」を含む第一義を落とさない。"""
    s = jw.senses(SHIZEN)
    assert len(s) == 2, s
    assert "無為" in s[0], s[0]
    assert "あるがまま" in s[0]


def test_relations_keep_sense_grouping():
    """語義別の類義・対義を、語義の別として保つ。混ぜない。"""
    rel = jw.relations(SHIZEN)
    syn = {(e["term"], e["sense"]) for e in rel if e["kind"] == "synonym"}
    assert ("天然", "語義1") in syn, syn
    assert ("当然", "語義2") in syn, syn
    ant = {(e["term"], e["sense"]) for e in rel if e["kind"] == "antonym"}
    assert ("人為", "語義1") in ant and ("不自然", "語義2") in ant, ant


def test_relations_without_grouping():
    """語義の見出しが無い語でも取れる。sense は空にする。"""
    rel = jw.relations(RISEI)
    syn = {e["term"] for e in rel if e["kind"] == "synonym"}
    assert syn == {"ロゴス", "論理", "知性"}, syn
    assert [e["sense"] for e in rel if e["kind"] == "synonym"] == ["", "", ""]
    assert {e["term"] for e in rel if e["kind"] == "antonym"} == {"感性"}


def test_comma_separated_related_terms_split():
    """読点で並んだ関連語を1語ずつに割る。1行を1語にしない。"""
    rel = jw.relations(KENRI)
    related = {e["term"] for e in rel if e["kind"] == "related"}
    assert {"人権", "生存権", "物権", "所有権", "債権"} <= related, related


def test_empty_sections_yield_no_edges():
    """節が無い語で辺を捏造しない。"""
    assert jw.relations("=={{L|ja}}==\n#意味だけ。\n") == []
    assert jw.readings("=={{L|ja}}==\n") == []


def test_parse_bundles_everything_with_layer_declared():
    """まとめて返す形が、層の宣言と出所を必ず持つ。"""
    d = jw.parse(SHIZEN)
    assert d["readings"] and d["senses"] and d["relations"]
    assert "ja.wiktionary" in d["source"]
    assert d["layer"], "層の宣言が無い"


RISEI_NOISE = """=={{L|ja}}==
==={{noun}}===
#[[物事]]を[[論理的]]に[[かんがえる|考える]][[能力]]。
===={{ant}}====
*[[感性]]
[[Category:{{yue}}]]
[[Category:{{nan}}_{{noun}}]]
"""


def test_piped_link_shows_display_text():
    """[[もつ|持っ]] は表示側を採る。語義文を読める形にする。"""
    s = jw.senses(RISEI_NOISE)
    assert "考える" in s[0], s[0]
    assert "かんがえる" not in s[0], s[0]


def test_category_lines_are_not_edges():
    """分類用のリンクを関係語にしない。実測で理性の対義語に混入していた。"""
    ant = [e["term"] for e in jw.relations(RISEI_NOISE) if e["kind"] == "antonym"]
    assert ant == ["感性"], ant


MULTILANG = """=={{L|ja}}==
==={{noun}}===
# [[体力]]を{{おくりがな2|使|つか|っ|つかう}}て{{おくりがな2|働|はたら|く|はたらく}}こと。
#{{タグ|ja|法律}} [[労働者]]が{{ふりがな|労務|ろうむ}}を[[提供]]すること。{{w|労働基準法}}に定義は無い。
===={{syn}}====
*[[労務]]
===={{ant}}====
*[[余暇]]
=={{L|yue}}==
==={{noun}}===
# 粵語の語義。
===={{ant}}====
*lei5sing3
*li2seng3
"""


def test_only_the_japanese_section_is_parsed():
    """他言語節の関係語を混ぜない。実測で粵語の発音が対義語に入っていた。"""
    ant = [e["term"] for e in jw.relations(MULTILANG) if e["kind"] == "antonym"]
    assert ant == ["余暇"], ant
    assert len(jw.senses(MULTILANG)) == 2, jw.senses(MULTILANG)


def test_okurigana_template_keeps_the_word():
    """{{おくりがな2}} を消さない。実測で「体力をてこと」に壊れていた。"""
    s = jw.senses(MULTILANG)[0]
    assert "使って働く" in s, s


def test_furigana_and_wikilink_templates_render():
    """{{ふりがな}} と {{w}} は中身を残す。"""
    s = jw.senses(MULTILANG)[1]
    assert "労務" in s and "労働基準法" in s, s


def test_field_tag_is_kept_as_a_label():
    """{{タグ|ja|法律}} は分野の標識として残す。黙って捨てない。"""
    assert "法律" in jw.senses(MULTILANG)[1]
