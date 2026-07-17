"""C' — SEP-guided concept disambiguation. Bare polysemous CJK nouns rank a
unit/name sense first in Wikidata (時間→'hour', 存在→'Entity'), losing the
philosophical entry. _pick_resolution re-chooses conservatively: it only moves
off [0] when [0] is a concept with no relevant SEP entry AND a sibling has one.
Fixtures below are the REAL candidate/SEP outcomes captured 2026-07-12.
Offline / pure-function (no network)."""
import os
import tempfile

os.environ["DIALEXIS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from app.main import (_pick_resolution, _has_latin, _sep_relevant,  # noqa: E402
                      _nonconcept, _sep_anchor_match)


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
    # when every candidate is a name / has no SEP sense → keep [0] (conservative)
    scored = [
        {"qid": "Q94627855", "is_person": False, "anchor": None, "sep_ok": False},
        {"qid": "Q65926113", "is_person": False, "anchor": None, "sep_ok": False},
    ]
    assert _pick_resolution(scored) == "Q94627855"


# ---- C'' (2026-07-17): non-concept senses & the widened sibling window ------
# freedom/en: [0] 'Freedom (Beyoncé song)' defeated the token-overlap gate
# (shares 'freedom' with SEP's 'Divine Freedom') and self-certified. _nonconcept
# (Wikidata P31) forces its sep_ok to False so [1] liberty wins. P31 fixtures
# below are the REAL API values captured 2026-07-17.

def _ent(p31):
    return {"error": None, "data": {"instance_of": p31}}


def test_nonconcept_song_and_names_true():
    assert _nonconcept(_ent(["Q105543609"]))          # Beyoncé single (freedom)
    assert _nonconcept(_ent(["Q202444", "Q22809413"]))  # given name 'De' (徳)


def test_concept_senses_are_not_nonconcept():
    assert not _nonconcept(_ent(["Q840396", "Q1207505", "Q129510955", "Q151885"]))  # liberty
    assert not _nonconcept(_ent(["Q151885", "Q2515887", "Q129510955"]))             # virtue
    assert not _nonconcept({"error": "boom", "data": None})  # error ent is safe
    assert not _nonconcept(None)


def test_freedom_picks_liberty_over_song():
    # song's sep_ok is forced False upstream by _nonconcept → liberty (sep_ok
    # via SEP 'Positive and Negative Liberty') is the first qualifying sibling.
    scored = [
        {"qid": "Q24198308", "is_person": False, "anchor": "Freedom (Beyoncé song)", "sep_ok": False},
        {"qid": "Q2979", "is_person": False, "anchor": "Liberty", "sep_ok": True},
    ]
    assert _pick_resolution(scored) == "Q2979"


def test_toku_reaches_virtue_at_index_11():
    # 徳: virtue (Q157811, SEP 'Virtue Ethics') sits at Wikidata index 11 —
    # inside the widened window (search limit 20, sibling scan n=12).
    # [0] is the NON-person given name 'De' (a person [0] would rightly stop
    # the rerank); the tail mixes persons (Chikurin-in…) and SEP-less concepts.
    noise = [{"qid": f"Q{i}", "is_person": i > 0 and i % 2 == 0, "anchor": None,
              "sep_ok": False} for i in range(11)]
    scored = noise + [{"qid": "Q157811", "is_person": False, "anchor": "Virtue", "sep_ok": True}]
    assert _pick_resolution(scored) == "Q157811"


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


def test_sep_anchor_match_is_strict():
    # the rerank probe demands ALL significant tokens (len>=3) in the title —
    # 'Edo period' must NOT self-certify via the generic token 'period'
    # (real false positive: SEP top was "Plato's Middle Period Metaphysics…").
    assert not _sep_anchor_match("Plato’s Middle Period Metaphysics and Epistemology".lower(), "Edo period")
    assert _sep_anchor_match("Positive and Negative Liberty", "Liberty")
    assert _sep_anchor_match("Virtue Ethics", "Virtue")
    assert _sep_anchor_match("Time", "Time")
    assert not _sep_anchor_match("Divine Freedom", "Freedom (Beyoncé song)")  # 'song' absent
    assert not _sep_anchor_match("Anything", "時間")  # CJK anchor never matches
