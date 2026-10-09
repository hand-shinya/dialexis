"""文献空間の現代層の試験（2026-10-05）。

所有者の指摘（10-05）: その語が「どの時代から現代まで」どの分野で誰に
どの文脈で使われたかを示す。NDLのデジタル化資料は著作権の関係で概ね
1940年代までで、現代が空白になる。CiNii と OpenAlex で現代側を埋める。

純関数・外部取得なし・決定論。
"""
from app.main import modern_tally

CINII = [
    {"title": "疎外論の再検討", "creators": ["百木 漠"], "year": "2019-03-01",
     "url": "https://cinii/1", "publisher": "日本哲学会"},
    {"title": "労働疎外とマルクス", "creators": ["水谷 謙治"], "year": "1985",
     "url": "https://cinii/2", "publisher": ""},
    {"title": "年の無い論文", "creators": [], "year": "", "url": "https://cinii/3"},
]
OA = [
    {"title": "Alienation revisited", "year": 2021, "authors": ["A. Smith"],
     "url": "https://doi/1", "cited_by_count": 12, "type": "article"},
    {"title": "Entfremdung und Arbeit", "year": 1999, "authors": ["B. Müller"],
     "url": "https://doi/2", "cited_by_count": 3, "type": "article"},
    {"title": "No year work", "year": None, "authors": [], "url": "https://doi/3",
     "cited_by_count": 0},
]


def test_decades_merge_both_sources():
    t = modern_tally(CINII, OA)
    assert t["by_decade"] == {1980: 1, 1990: 1, 2010: 1, 2020: 1}, t["by_decade"]
    assert t["unknown_year"] == 2


def test_year_strings_are_parsed():
    """CiNiiの年は 2019-03-01 の形で来る。先頭4桁を年として読む。"""
    t = modern_tally(CINII, [])
    assert 2010 in t["by_decade"], t["by_decade"]


def test_works_carry_source_and_people():
    t = modern_tally(CINII, OA)
    by_title = {w["title"]: w for w in t["works"]}
    assert by_title["疎外論の再検討"]["source"] == "CiNii"
    assert by_title["疎外論の再検討"]["people"] == ["百木 漠"]
    assert by_title["Alienation revisited"]["source"] == "OpenAlex"


def test_works_are_newest_first():
    """現代層は新しい順に出す。用例層（古い順）と向きを変える。"""
    years = [w["year"] for w in modern_tally(CINII, OA)["works"] if w["year"]]
    assert years == sorted(years, reverse=True), years


def test_empty_sources_are_not_an_error():
    t = modern_tally([], [])
    assert t["by_decade"] == {} and t["works"] == [] and t["counted"] == 0


def test_people_are_counted_across_sources():
    t = modern_tally(CINII, OA)
    names = dict(t["people"])
    assert names.get("百木 漠") == 1 and names.get("A. Smith") == 1, t["people"]


NOISY = [
    {"title": "", "creators": ["環境省自然環境局"], "year": "2002", "url": "u1"},
    {"title": "   ", "creators": [], "year": "2003", "url": "u2"},
    {"title": "実在する論文", "creators": ["某"], "year": "2004", "url": "u3"},
]


def test_untitled_records_are_dropped():
    """書名の無い記録を一覧に出さない。実測でCiNiiに空題名が返った。"""
    t = modern_tally(NOISY, [])
    assert [w["title"] for w in t["works"]] == ["実在する論文"], t["works"]
    assert t["counted"] == 1


def test_dropped_records_are_counted_not_hidden():
    """落とした件数を出す。黙って消さない。"""
    t = modern_tally(NOISY, [])
    assert t["untitled_dropped"] == 2, t
