"""NDL次世代デジタルライブラリーから「用例層」を取る試験（2026-10-05）。

なぜ必要か（2026-10-04 実測）:
  辞書層は関係の型を与えるが、その語が実際にいつ・誰に・どの分野で使われたかを
  言わない。Book API は年・著者・訳者・NDC・出現箇所を返す。
  「権理」は1870-80年代に集中し1900年代以降ほぼ消え、「権利」は1880年代から
  続く。語の交代が解釈でなく件数の分布として出る。

この試験は実取得（10-04）を縮約した固定値で、集計だけを検証する。
外部取得なし・決定論。
"""
from app.connectors import ndl_fulltext as nf

ITEMS = [
    {"id": "798457", "title": "權理提綱", "publishyear": 1877, "ndc": "360",
     "responsibility": "斯辺銷 (ハルバルト・スペンサー) 著||尾崎行雄 訳",
     "highlights": ["生命並ニ自由之<em>權理</em>&#x2F;1p  (0005.jp2)"]},
    {"id": "798458", "title": "權理提綱", "publishyear": 1882, "ndc": "360",
     "responsibility": "斯辺銷 (ハルバルト・スペンサー) 著||尾崎行雄 訳", "highlights": []},
    {"id": "901", "title": "社会平権論", "publishyear": 1884, "ndc": "360",
     "responsibility": "ハーバート・スペンサー 著||松島剛 訳", "highlights": []},
    {"id": "902", "title": "権利質論", "publishyear": 1912, "ndc": "324",
     "responsibility": "神戸寅次郎 著", "highlights": []},
    {"id": "903", "title": "年不明の書", "publishyear": 0, "ndc": None,
     "responsibility": "", "highlights": []},
]


def test_decade_tally_excludes_unknown_year():
    """年が0の資料を1900年代などに入れない。不明は不明として数える。"""
    t = nf.tally(ITEMS)
    assert t["by_decade"] == {1870: 1, 1880: 2, 1910: 1}, t["by_decade"]
    assert t["unknown_year"] == 1


def test_authors_and_translators_are_separated():
    """著者と訳者を分けて数える。訳者が誰かは訳語史の核である。"""
    t = nf.tally(ITEMS)
    assert ("尾崎行雄", 2) in t["translators"], t["translators"]
    assert ("松島剛", 1) in t["translators"]
    names = dict(t["authors"])
    assert names.get("神戸寅次郎") == 1, t["authors"]


def test_ndc_tally_and_unknown():
    t = nf.tally(ITEMS)
    assert t["by_ndc"]["360"] == 3 and t["by_ndc"]["324"] == 1
    assert t["unknown_ndc"] == 1


def test_works_are_deduplicated_by_title_and_keep_earliest_year():
    """同じ書名の版を1件に畳み、最も早い年を残す。"""
    t = nf.tally(ITEMS)
    kenri = [w for w in t["works"] if w["title"] == "權理提綱"]
    assert len(kenri) == 1, t["works"]
    assert kenri[0]["year"] == 1877 and kenri[0]["editions"] == 2


def test_highlight_markup_is_cleaned_but_marks_the_term():
    """強調記法を落とし、出現箇所を読める形にする。"""
    t = nf.tally(ITEMS)
    loc = [w for w in t["works"] if w["title"] == "權理提綱"][0]["locators"]
    assert loc and "<em>" not in loc[0] and "&#x2F;" not in loc[0], loc
    assert "權理" in loc[0]


def test_variant_survey_declares_what_was_tried():
    """字体ごとの件数と、試した表記を必ず残す。空を「無い」と言わない。"""
    merged = nf.merge_variants({
        "権理": {"hit": 6756, "items": ITEMS[:1]},
        "權理": {"hit": 6756, "items": ITEMS[1:3]},
    })
    assert merged["variants_tried"] == ["権理", "權理"]
    assert merged["hit_by_variant"]["權理"] == 6756
    assert merged["sampled"] == 3


def test_empty_result_is_not_an_error():
    """0件は誤りではない。0件と取得失敗を区別する。"""
    t = nf.tally([])
    assert t["by_decade"] == {} and t["works"] == [] and t["sampled"] == 0


DUP = {
    "権理": {"hit": 6756, "items": [ITEMS[0], ITEMS[2]]},
    "權理": {"hit": 6756, "items": [ITEMS[0], ITEMS[3]]},
}


def test_same_record_is_counted_once_across_variants():
    """字体を変えて引くとAPIが同じ資料を返す。idで畳んで二重に数えない。"""
    m = nf.merge_variants(DUP)
    assert m["sampled"] == 3, m["sampled"]
    assert sum(m["by_decade"].values()) == 3, m["by_decade"]


def test_author_suffixes_beyond_cho():
    """稿・講述・講義も著者とみなす。実測で「西村茂樹 稿」が落ちていた。"""
    a, t = nf._people("西村茂樹 稿")
    assert a == ["西村茂樹"] and t == [], (a, t)
    a, t = nf._people("志田[コウ]太郎 講述")
    assert a == ["志田[コウ]太郎"], a


def test_multiple_names_in_one_part_are_split():
    """「山田俊蔵, 大角豊次郎 共」を2人に割る。1人として数えない。"""
    a, _ = nf._people("山田俊蔵, 大角豊次郎 共")
    assert a == ["山田俊蔵", "大角豊次郎"], a


def test_translator_pair_is_split():
    a, t = nf._people("木村鋭一, 立花俊吉 訳")
    assert t == ["木村鋭一", "立花俊吉"], t


BAD_YEARS = [
    {"id": "a", "title": "西暦1000年の書", "publishyear": 1000, "ndc": "100",
     "responsibility": "某 著", "highlights": []},
    {"id": "b", "title": "1800年の書", "publishyear": 1800, "ndc": "100",
     "responsibility": "某 著", "highlights": []},
    {"id": "c", "title": "正しい年の書", "publishyear": 1877, "ndc": "100",
     "responsibility": "某 著", "highlights": []},
    {"id": "d", "title": "未来の書", "publishyear": 2999, "ndc": "100",
     "responsibility": "某 著", "highlights": []},
]


def test_impossible_years_are_treated_as_unknown():
    """刊年として成立しない値は不明に寄せる。

    実測（10-05 本番）: 「理性」で西暦1000年が11件出た。近代の資料である。
    1500年より前と、今年より後は刊年として採らない。
    """
    t = nf.tally(BAD_YEARS)
    assert 1000 not in t["by_decade"] and 2990 not in t["by_decade"], t["by_decade"]
    assert t["unknown_year"] == 2, t["unknown_year"]


def test_placeholder_year_is_flagged_not_deleted():
    """1800年は実在しうる刊年である。消さずに疑わしい値として数える。

    実測で明治の『言論叢』『商法通論』に1800が入っていた。NDL側の代入値と
    思われるが、我々には判定できない。黙って捨てず、件数を出して利用者に委ねる。
    """
    t = nf.tally(BAD_YEARS)
    assert t["by_decade"].get(1800) == 1, t["by_decade"]
    assert t["suspect_years"].get(1800) == 1, t["suspect_years"]


def test_impossible_year_still_keeps_the_work():
    """年が使えなくても資料そのものは捨てない。年不明として残す。"""
    t = nf.tally(BAD_YEARS)
    titles = {w["title"] for w in t["works"]}
    assert "西暦1000年の書" in titles, titles
    bad = [w for w in t["works"] if w["title"] == "西暦1000年の書"][0]
    assert bad["year"] == 0


def test_role_suffix_is_stripped_from_each_split_name():
    """分割した各名から役割語を落とす。実測で訳者に「斎田功太郎 編」が入った。"""
    a, t = nf._people("原野彦太郎 訳||斎田功太郎 編")
    assert t == ["原野彦太郎"], t
    assert a == ["斎田功太郎"], a
    _, t2 = nf._people("木村鋭一, 立花俊吉 編 訳")
    assert t2 == ["木村鋭一", "立花俊吉"], t2
