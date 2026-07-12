"""C' — SEP-guided concept disambiguation. Bare polysemous CJK nouns rank a
unit/name sense first in Wikidata (時間→'hour', 存在→'Entity'), losing the
philosophical entry. _pick_resolution re-chooses conservatively: it only moves
off [0] when [0] is a concept with no relevant SEP entry AND a sibling has one.
Fixtures below are the REAL candidate/SEP outcomes captured 2026-07-12.
Offline / pure-function (no network)."""
import os
import tempfile

os.environ["DIALEXIS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from app.main import _pick_resolution, _has_latin, _sep_relevant  # noqa: E402


def test_jikan_picks_time_not_hour():
    # 時間: [0] Q25235 'Hour'(unit) → SEP irrelevant; [1] Q11471 'Time' → SEP 'Time'
    scored = [
        {"qid": "Q25235", "is_person": False, "anchor": "Hour", "sep_ok": False},
        {"qid": "Q11471", "is_person": False, "anchor": "Time", "sep_ok": True},
    ]
    assert _pick_resolution(scored) == "Q11471"


def test_sonzai_picks_first_existence_not_entity():
    # 存在: [0] 'Entity' fails; first sibling with SEP is 'Existence' (Q468777),
    # even though 'Being'(Q203872) also passes — lowest order wins.
    scored = [
        {"qid": "Q35120", "is_person": False, "anchor": "Entity", "sep_ok": False},
        {"qid": "Q468777", "is_person": False, "anchor": "Existence", "sep_ok": True},
        {"qid": "Q203872", "is_person": False, "anchor": "Being", "sep_ok": True},
        {"qid": "Q24255051", "is_person": False, "anchor": "Something", "sep_ok": False},
    ]
    assert _pick_resolution(scored) == "Q468777"


def test_person_top_is_never_reranked():
    # a person query (Kant) must keep [0] even if a later sibling has a SEP entry
    scored = [
        {"qid": "Q9312", "is_person": True, "anchor": "Immanuel Kant", "sep_ok": False},
        {"qid": "Q999", "is_person": False, "anchor": "Ethics", "sep_ok": True},
    ]
    assert _pick_resolution(scored) == "Q9312"


def test_good_top_is_untouched():
    # 愛→Love already resolves to a relevant SEP entry → no rerank (no regression)
    scored = [
        {"qid": "Q316", "is_person": False, "anchor": "Love", "sep_ok": True},
        {"qid": "Q000", "is_person": False, "anchor": "Other", "sep_ok": True},
    ]
    assert _pick_resolution(scored) == "Q316"


def test_all_names_fall_back_to_top():
    # 徳: every candidate is a name / has no SEP sense → keep [0] (can't be saved
    # by reranking; documented residual needing a different term e.g. 美徳)
    scored = [
        {"qid": "Q94627855", "is_person": False, "anchor": None, "sep_ok": False},
        {"qid": "Q65926113", "is_person": False, "anchor": None, "sep_ok": False},
    ]
    assert _pick_resolution(scored) == "Q94627855"


def test_person_sibling_is_not_chosen():
    # a concept [0] with no SEP must not jump to a PERSON sibling that has a SEP
    # page under their name — persons are excluded from the rerank target set.
    scored = [
        {"qid": "Q0", "is_person": False, "anchor": "Foo", "sep_ok": False},
        {"qid": "Qp", "is_person": True, "anchor": "Some Philosopher", "sep_ok": True},
    ]
    assert _pick_resolution(scored) == "Q0"


def test_empty_is_safe():
    assert _pick_resolution([]) is None


def test_helpers_unchanged():
    assert _has_latin("Time") and not _has_latin("時間")
    assert _sep_relevant("Time", "Time") and not _sep_relevant("Infinite Regress", "Hour")
