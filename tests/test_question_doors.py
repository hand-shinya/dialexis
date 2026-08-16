"""PoC A (question-first entry): a curious person who knows no philosopher's
name still gets a door. Doors are real <a href="/origin?q=SEED"> links (work
without JS = screen-reader friendly), and every seed must be a concept verified
to return a real result — no door may lead to an empty room. Offline Level-0."""
import os
import tempfile

os.environ["DIALEXIS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app, QUESTION_DOORS  # noqa: E402

client = TestClient(app)

# Seeds empirically verified (2026-07-12) to return a real SEP entry; and the
# wrong-sense resolutions that MUST NOT be shipped as doors.
VERIFIED_JA = {"愛", "自由", "正義", "幸福", "真理", "意識", "美"}
VERIFIED_EN = {"love", "happiness", "truth", "consciousness", "beauty"}
KNOWN_BAD = {"時間", "存在", "徳", "justice", "freedom"}


def test_doors_shape():
    for lang in ("ja", "en"):
        assert QUESTION_DOORS[lang], f"{lang} has doors"
        for d in QUESTION_DOORS[lang]:
            assert d["seed"] and d["q"], "each door has a seed and a question"


def test_seeds_are_verified_only():
    for s in [d["seed"] for d in QUESTION_DOORS["ja"]]:
        assert s in VERIFIED_JA and s not in KNOWN_BAD
    for s in [d["seed"] for d in QUESTION_DOORS["en"]]:
        assert s in VERIFIED_EN and s not in KNOWN_BAD


def test_home_renders_real_links_ja():
    html = client.get("/?lang=ja").text
    assert "qdoors" in html
    assert '<form action="/origin"' in html   # primary search opens the Map
    assert "意味Mapを開く" in html              # button names the actual destination
    assert 'href="/origin?q=' in html         # real anchor, not JS-only
    assert 'href="/explore?q=' not in html   # no accidental old-route door
    assert 'href="/origin"' in html          # header has a visible Map route
    assert "愛とは何か" in html                   # a novice-voice question
    assert "名前を知らなくても" in html            # the door title


def test_home_renders_english_doors():
    html = client.get("/?lang=en").text
    assert "What is love?" in html
    assert "href=\"/origin?q=love" in html
    assert "Open meaning map" in html
    assert "No name needed" in html


def test_secondary_explore_explains_and_links_to_origin_map():
    html = client.get("/explore?q=非有機的肉体&lang=ja").text
    assert 'action="/explore"' in html
    assert 'href="/origin?q=' in html
    assert "意味空間の相関図" in html


def test_placeholder_no_longer_presupposes_a_name():
    # the old placeholder led with "Philosopher, work, or concept" — the exact
    # gate that excluded the nameless-curious. It must no longer lead with that.
    html = client.get("/?lang=en").text
    assert "A question, a concept, or a thinker" in html
