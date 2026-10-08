"""読み落ちた節・語義IDの一意性・原語pivot・0件の原因の試験（2026-10-08）。

なぜ必要か（10人の模擬の分析）:
  1. `{{comp}}{{drv}}{{prov}}{{idiom}}` は正規表現に一致せず、10語のうち9語で
     未読の節が在った。自然の複合語10件は消え、労働の15件は無名の related で残った。
  2. 自然は品詞blockが2つあり、どちらにも「語義1」が在る。番号だけで解決すると
     黙って別の本文を指す（14/14が名を持つと報告した語で、2本が別語義だった）。
  3. `{{trans}}` 節は語義ごとに外国語lemmaを並べる。これを1本も読んでいなかった。
     英語の行は3形あり、私の正規表現は3回取りこぼした（0→2→5→7件）。
  4. 0件には4つの原因がある。同じ空白として出すと、資料の欠落と読み落ちが混ざる。

外部取得なし・決定論。
"""
from app.connectors import ja_wiktionary as jw
from app.main import _coverage, _pivot_edges

# 品詞blockが2つあり、どちらにも語義1が在る形（自然の構造を縮約した）
TWO_BLOCKS = """=={{L|ja}}==
==={{noun}}===
{{ja-kanjitab|し|ぜん|yomi=kanon}}
# あるがままであること。無為。
# 人の手が加わらないこと。
==={{syn}}===
* 語義1: [[天然]]
==={{comp}}===
* [[自然界]]
* [[大自然]]
==={{adjectivenoun}}===
# 作りものでない様子。
==={{ant}}===
* 語義1: [[人為]]
==={{trans}}===
{{trans-top|名詞}}
*{{T|en}}: [[nature]]
{{trans-bottom}}
{{trans-top|形容表現}}
*{{T|en}}: {{t|en|natural}}
{{trans-bottom}}
"""

# 英語の行の第3形（コメントつき）と {{top}} 区切り
THIRD_FORM = """=={{L|ja}}==
==={{noun}}===
# 単調で嫌になる様子。
==={{trans}}===
{{top}}
*[[{{en}}]]<!--*English-->:{{t+|en|bore}}, {{t+|en|boredom}}
{{bottom}}
"""

# 別pageへの転送（愛 → 愛情）
SEE_FORM = """=={{L|ja}}==
==={{noun}}===
# 慈しむ気持ち。
==={{trans}}===
{{trans-see|語義1|愛情}}
"""


def test_unread_sections_are_now_read():
    s = jw.sections(TWO_BLOCKS)
    assert "comp" in s["read"] and "syn" in s["read"] and "ant" in s["read"]
    assert s["unread"] == []
    assert "trans" in s["read_elsewhere"]
    assert "noun" in s["not_relation"]


def test_compound_section_becomes_edges():
    """自然の複合語が消えていた。節を読めば辺になる。"""
    rel = jw.relations(TWO_BLOCKS)
    comp = [e["term"] for e in rel if e["kind"] == "compound"]
    assert comp == ["自然界", "大自然"]
    assert all(e["note"] for e in rel)          # 押す前の説明を必ず持つ


def test_sense_ids_are_unique_across_pos_blocks():
    """語義1が2つあっても、別のidになる。"""
    sm = jw.sense_map(TWO_BLOCKS)
    ids = [s["sense_id"] for s in sm]
    assert len(ids) == len(set(ids))
    labels = [s["label"] for s in sm]
    assert labels.count("語義1") == 2          # labelは重複する。idは重複しない


def test_relation_sense_resolves_within_its_own_block():
    """同じ『語義1』でも、節が属するblockの語義に結びつく。"""
    rel = jw.relations(TWO_BLOCKS)
    syn = [e for e in rel if e["kind"] == "synonym"][0]
    ant = [e for e in rel if e["kind"] == "antonym"][0]
    assert syn["sense"] == ant["sense"] == "語義1"
    assert syn["sense_id"] != ant["sense_id"]
    assert "無為" in syn["sense_text"]
    assert "作りもの" in ant["sense_text"]


def test_translations_keep_the_sense_label():
    tr = jw.translations(TWO_BLOCKS)
    assert tr["has_section"] is True
    got = {r["sense_label"]: r["en"] for r in tr["rows"]}
    assert got == {"名詞": ["nature"], "形容表現": ["natural"]}


def test_third_english_form_is_read():
    """*[[{{en}}]]<!--*English-->: の形も読む。3回取りこぼした形である。"""
    tr = jw.translations(THIRD_FORM)
    assert tr["rows"] and tr["rows"][0]["en"] == ["bore", "boredom"]


def test_trans_see_is_recorded():
    tr = jw.translations(SEE_FORM)
    assert tr["rows"] == []
    assert tr["see"] == [{"sense_label": "語義1", "page": "愛情"}]


def test_pivot_names_the_edge_and_drops_the_query_itself():
    dic = {"word": "正義", "translations": {"rows": [
        {"sense_label": "語義指定なし", "en": ["justice"]}]}}
    edges = _pivot_edges(dic)
    assert all(e["term"] != "正義" for e in edges)   # 自分自身は辺にしない
    dic2 = {"word": "労働", "translations": {"rows": [
        {"sense_label": "語義指定なし", "en": ["labor"]}]}}
    e2 = _pivot_edges(dic2)
    assert [x["term"] for x in e2] == ["工作"]
    assert e2[0]["evidence"] == "pivot"
    assert "Labor の訳語（1881年）" in e2[0]["sense"]
    assert e2[0]["why"]


def test_coverage_separates_the_causes():
    empty = {"missing": False, "relations": [], "senses": ["道理にかなって正しいこと。"],
             "sections": {"found": ["trans"], "read": [], "unread": []},
             "translations": {"rows": []}}
    c = _coverage(empty, {"missing": True}, [])
    causes = [b["cause"] for b in c["blanks"]]
    assert "entry_but_empty_relations" in causes and "in_gloss_only" in causes

    no_entry = {"missing": True, "relations": [], "senses": [],
                "sections": {"found": [], "read": [], "unread": []},
                "translations": {"rows": []}}
    assert "no_entry" in [b["cause"] for b in _coverage(no_entry, {"missing": True}, [])["blanks"]]

    other_side = {"missing": False, "relations": [{"kind": "related", "term": "x"}],
                  "senses": ["a"], "sections": {"found": ["rel"], "read": ["rel"], "unread": []},
                  "translations": {"rows": [{"sense_label": "", "en": ["labor"]}]}}
    got = _coverage(other_side, {"missing": True}, [{"term": "工作"}])
    assert "key_on_other_side" in [b["cause"] for b in got["blanks"]]
    none_hit = _coverage(other_side, {"missing": True}, [])
    assert "key_on_other_side_unmatched" in [b["cause"] for b in none_hit["blanks"]]


def test_coverage_reports_both_found_and_read():
    """資料に無いのか、我々が読んでいないのかを分ける唯一の欄である。"""
    c = _coverage({"missing": False, "relations": [{"kind": "related", "term": "x"}],
                   "senses": ["a"], "sections": jw.sections(TWO_BLOCKS),
                   "translations": {"rows": []}}, {"missing": False}, [])
    assert c["sections_found"] and c["sections_read"]
    assert c["sections_unread"] == []
