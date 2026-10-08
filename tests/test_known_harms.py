"""既知の害を、戻らないように固定する試験（2026-10-09・2巡目の検証を反映）。

なぜ必要か:
  害はいずれも「仕様書に欠陥として書いた」状態で残っていた。
  書くことは直すことではない（M0 C3）。この試験が落ちると verify.sh が落ちる。

1巡目で直したもの:
  H-A /api/anatomy  「非有機的肉体」で 機=weaving machine・的=bright・
        体=alternative form of 笨 が語の構成要素として並んでいた。
  H-B /api/combine  肉体×自然(AND) が 肉体の学校・プロレスラー・精霊 を
        kind="application"（応用）で返し、note が「両方に関わるものだけ」と断定した。
  H-C deepsearch    自動取得のS1材料を「既に判明している手がかり」として他のAIへ渡した。

2巡目の敵対的検証が実証した、1巡目の修理そのものの害（すべて本試験で固定する）:
  F1 矛盾で「矛=spear・盾=shield は語の意味の構成要素ではない」と画面に出していた。
     同じ応答の summary が「韓非子の故事に由来」と言い、tests/e2e/anatomy.e2e.js は
     矛+盾 を正解として守っている。自分の gate が守る情報を画面で否定していた。
     さらに 84語すべてで注記が出ており、識別力が無かった。
  F2 unresolved_unit（機械推定・低確度）を「意味のまとまり」と断定していた
     （越論的・夜城・機的身体 のような非語）。
  F3 NFKC互換漢字（U+F900-FAFF）で印が全て外れ、害が完全に再開していた。
  F4 注記が日本語固定で、英語UIに未翻訳のまま出ていた。
  F5 注記の文の「ありません」が aspect_no_recenter.e2e.js の禁止語に当たり、
     deploy gate が落ちた（実測 3/3 再現）。
  F6 op=semand に断りが無く、この試験の parametrize からも漏れていた。
  F7 /api/gravity が同じ3語を kind="application"・basis なし・断り無しで返していた。
  F8 deepsearch の §4 が、§0 が無いときも「上のSEP論争構造を出発点に」と参照していた。
  F9 /api/translation-history が、印を外した字義を「語源的構成要素」として台帳に入れ、
     低確度の非語を evidence="confirmed"（本文・書誌を確認）で記録していた。

画面に出ているかは、この file では測らない（公理7）:
  1巡目は app.js と style.css を grep していた。敵対的検証で12件の破壊のうち10件が
  全緑のまま通った。とくに「_compNote を潰す」「display:none」「空のspan」の3件は
  画面に何も出なくなるのに緑だった。実描画の検査は tests/e2e/anatomy_note.e2e.js が
  担う（13 assertion・route で /api/anatomy を差し替えるので決定論的）。

外部取得なし（字義の取得だけを差し替える）。
"""
import asyncio
import pathlib

import pytest
from fastapi.testclient import TestClient

from app import deepsearch
from app.connectors import etymology
from app.main import app

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture()
def client():
    return TestClient(app)


# ===========================================================================
# H-A / F1 F2 F3 F4 F5  字義を語義として読ませない
# ===========================================================================

# 実測値（en.wiktionary・2026-10-08）。
# 1巡目の stub は矛と盾を持っておらず、そのせいで「1単位の語には注記を出さない」が
# 偽の緑になっていた（_han_gloss が空を返し comps が空になるため）。
# 対象語の全文字に gloss を返す。
GLOSS = {"非": "not be", "有": "to have", "機": "weaving machine", "的": "bright",
         "肉": "meat", "体": "alternative form of 笨",
         "矛": "spear", "盾": "shield",
         "超": "to jump over", "越": "to pass over", "論": "to discuss",
         "精": "essence", "神": "god"}


def anatomy_of(word, monkeypatch):
    """字義の取得だけを実測値に差し替える（外部へ出ない）。"""
    async def fake_gloss(ch):
        return GLOSS.get(ch, "GLOSS-" + ch)      # 未登録の字も必ず gloss を持つ

    async def fake_extract(term):
        return ""

    monkeypatch.setattr(etymology, "_han_gloss", fake_gloss)
    monkeypatch.setattr(etymology, "_extract", fake_extract)
    return asyncio.run(etymology.anatomy(word, [], "ja"))


def by_part(r):
    return {c["part"]: c for c in r["components"]}


def test_characters_inside_a_unit_are_marked(monkeypatch):
    r = anatomy_of("非有機的肉体", monkeypatch)
    by = by_part(r)
    assert by["機"]["in_unit"] == "有機的"
    assert by["機"]["applies_to_term"] is False
    assert by["機"]["unit_kind"] == "lexical"
    assert by["的"]["in_unit"] == "有機的"
    assert by["体"]["in_unit"] == "肉体"
    assert by["肉"]["in_unit"] == "肉体"


def test_a_real_prefix_still_applies_to_the_term(monkeypatch):
    """全部を『語義でない』にすると、本当の接頭辞まで隠れる。非 は語に効く。"""
    by = by_part(anatomy_of("非有機的肉体", monkeypatch))
    assert by["非"]["in_unit"] == ""
    assert by["非"]["applies_to_term"] is True


def test_the_note_counts_the_characters_and_names_the_units(monkeypatch):
    r = anatomy_of("非有機的肉体", monkeypatch)
    note = r["components_note"]
    assert "5 字" in note
    assert "有機的" in note and "肉体" in note
    parts = r["components_note_parts"]
    assert parts["inside_count"] == 5
    assert parts["lexical_units"] == ["有機的", "肉体"]
    assert parts["unresolved_units"] == []
    assert parts["whole_is_one_unit"] is False


def test_the_character_glosses_are_not_deleted(monkeypatch):
    """削ると沈黙する欠落になる（公理1）。印を付けるだけで、消さない。"""
    r = anatomy_of("非有機的肉体", monkeypatch)
    assert len(r["components"]) == 6
    assert any(c["meaning"] == "weaving machine" for c in r["components"])


# ---- F1 語そのものが1単位のとき ------------------------------------------

def test_a_word_that_is_one_unit_gets_no_mark_and_no_note(monkeypatch):
    """矛盾は1単位。矛=spear・盾=shield は語の由来そのものである。

    1巡目は「矛と盾は語の意味の構成要素ではない」と画面に出していた。
    同じ応答の summary が韓非子の故事を述べ、tests/e2e/anatomy.e2e.js は
    「矛盾→矛(spear)+盾(shield)に分解される」を PASS として守っている。
    """
    r = anatomy_of("矛盾", monkeypatch)
    assert r["components_note"] == ""
    assert r["components_note_parts"]["whole_is_one_unit"] is True
    for c in r["components"]:
        assert c["in_unit"] == "", c
        assert c["applies_to_term"] is True, c
    assert {c["meaning"] for c in r["components"]} == {"spear", "shield"}


@pytest.mark.parametrize("w", ["矛盾", "疎外", "肉体", "有機的"])
def test_single_unit_words_stay_silent(monkeypatch, w):
    """1巡目は 84語すべてで注記が出ており、識別力がゼロだった。"""
    assert anatomy_of(w, monkeypatch)["components_note"] == "", w


# ---- F2 未解決の残りを語と断定しない --------------------------------------

@pytest.mark.parametrize("word,remainder", [("超越論的", "越論的"), ("不夜城", "夜城")])
def test_an_unsegmented_remainder_is_not_called_a_meaning_unit(monkeypatch, word, remainder):
    """「越論的」「夜城」は語ではない。実装自身が low / unresolved_unit と記録している。"""
    r = anatomy_of(word, monkeypatch)
    note = r["components_note"]
    assert "切り分けられていない" in note, note
    assert "機械推定" in note, note
    assert "「{}」という意味のまとまり".format(remainder) not in note, note
    assert r["components_note_parts"]["unresolved_units"] == [remainder]
    assert r["components_note_parts"]["lexical_units"] == []
    inside = [c for c in r["components"] if c["applies_to_term"] is False]
    assert inside and all(c["unit_kind"] == "unresolved" for c in inside)


# ---- F3 互換漢字 ----------------------------------------------------------

def test_compatibility_ideographs_do_not_reopen_the_harm(monkeypatch):
    """U+FA1D U+FA19（精神）は NFKC で U+7CBE U+795E になる。

    1巡目は cjk を正規化前の原文字から作っていたため、unit_of の鍵と一致せず、
    全字が applies_to_term=True・注記なしになっていた（害が完全に再開していた）。
    互換漢字は OCR・NDL本文・古い組版から日常的に入る。
    """
    plain = anatomy_of("精神", monkeypatch)
    compat = anatomy_of("精神", monkeypatch)
    assert compat["term"] == "精神"
    assert compat["components_note"] == plain["components_note"]
    assert compat["components_note_parts"] == plain["components_note_parts"]
    assert [c["part"] for c in compat["components"]] == [c["part"] for c in plain["components"]]


# ---- F5 画面に出る文に禁止語を使わない ------------------------------------

@pytest.mark.parametrize("w", ["非有機的肉体", "超越論的", "矛盾", "不夜城"])
def test_the_note_avoids_the_forbidden_expressions(monkeypatch, w):
    """aspect_no_recenter.e2e.js の禁止語に当たって deploy gate が落ちた（実測）。"""
    note = anatomy_of(w, monkeypatch)["components_note"]
    for bad in ("できません", "引けません", "特定でき", "見つかり", "失敗",
                "ありません", "unavailable", "not found"):
        assert bad not in note, (w, bad, note)


# ---- 契約 -----------------------------------------------------------------

@pytest.mark.parametrize("w", ["非有機的肉体", "矛盾", "あ", "", "   ", "dialectic"])
def test_the_contract_keys_exist_on_every_path(monkeypatch, w):
    r = anatomy_of(w, monkeypatch)
    assert "components_note" in r, w
    assert "components_note_parts" in r, w
    assert isinstance(r["components_note_parts"], dict), w


def test_the_browser_assertions_live_in_their_own_suite():
    """画面に出ているかは実描画で測る。この file の grep では測らない（公理7）。

    1巡目は app.js / style.css を grep しており、「_compNote を潰す」
    「.anat-compnote を display:none」「印を空のspanにする」のいずれでも緑だった。
    """
    e2e = ROOT / "tests" / "e2e" / "anatomy_note.e2e.js"
    assert e2e.exists(), "実描画の検査が無い"
    body = e2e.read_text(encoding="utf-8")
    assert "offsetHeight > 0" in body, "見えているかを測っていない（display:none を捕まえられない）"
    assert "lang=en" in body or "\"en\"" in body, "英語UIを測っていない"


# ===========================================================================
# H-B / F6 F7  検索一致を「応用」と名乗らない
# ===========================================================================

HITS = [{"title": "肉体の学校", "content": "自然主義文学の影響", "url": "u1"},
        {"title": "自然治癒力", "content": "肉体の回復", "url": "u2"},
        {"title": "プロレスラー", "content": "肉体と自然", "url": "u3"}]


@pytest.fixture()
def stub_web(monkeypatch):
    from app import main as m

    async def fake(a, lang, extra="", n=20):
        return HITS, "試験用スタブ"

    monkeypatch.setattr(m, "_combine_web_search", fake)


@pytest.fixture()
def stub_gravity(monkeypatch):
    """SearXNG と Wikidata を止める。/api/gravity は両方を使う。"""
    from app import main as m

    async def fake_search(q, lang, n=20, extra="", drop_commercial=True):
        return HITS

    async def fake_node(q, lang):
        return {"error": None, "data": {"originators": [], "associated": [],
                                        "relations": {"near": [], "opposite": []}}}

    monkeypatch.setattr(m.searxng, "search", fake_search)
    monkeypatch.setattr(m.concept, "node", fake_node)


def combine(client, a="肉体", b="自然", op="and"):
    r = client.get("/api/combine", params={"a": a, "b": b, "op": op, "lang": "ja"})
    assert r.status_code == 200, r.text
    return r.json()


# F6: semand を含める。1巡目はここから漏れていた。
ALL_OPS = ["and", "not", "or", "compare", "semand"]


@pytest.mark.parametrize("op", ALL_OPS)
def test_search_hits_are_never_called_application(client, stub_web, op):
    d = combine(client, op=op)
    kinds = {n.get("kind") for n in d["nodes"]}
    assert "application" not in kinds, (op, kinds)


@pytest.mark.parametrize("op", ALL_OPS)
def test_every_op_declares_the_relation_unverified(client, stub_web, op):
    d = combine(client, op=op)
    assert "概念としての関係は未検証です" in d["note"], (op, d["note"])
    assert "両方に関わるものだけ" not in d["note"]
    assert "両方に関わる概念" not in d["note"]


@pytest.mark.parametrize("op", ["and", "or", "compare"])
def test_search_hits_carry_the_cooccurrence_kind_and_a_basis(client, stub_web, op):
    d = combine(client, op=op)
    hits = [n for n in d["nodes"] if n.get("kind") == "cooccurrence"]
    assert hits, op
    for n in hits:
        assert n.get("basis"), n


def test_the_shared_group_is_named_by_what_was_measured(client, stub_web):
    d = combine(client, op="compare")
    labels = [n["label"] for n in d["nodes"]]
    assert "両方の検索結果に現れた語" in labels
    assert "共有（両方に関わる）" not in labels


def test_semand_keeps_neighbours_as_neighbours(client, stub_web):
    """Wikidataの近縁で文脈に出なかったものは、近縁のままである（応用ではない）。"""
    d = combine(client, op="semand")
    for n in d["nodes"]:
        if n.get("kind") == "related":
            assert n.get("basis") == "wikidata-neighbour", n
            assert "context_match" in n, n


def test_gravity_does_not_call_a_search_hit_an_application(client, stub_gravity):
    """F7: 同じ3語が /api/gravity では今も「応用」として出ていた。"""
    r = client.get("/api/gravity", params={"q": "肉体", "lang": "ja"})
    assert r.status_code == 200, r.text
    d = r.json()
    kinds = {n.get("kind") for n in d["nodes"]}
    assert "application" not in kinds, kinds
    leaves = [n for n in d["nodes"] if n.get("layer") == 3]
    if leaves:
        for n in leaves:
            assert n.get("basis") in {"search-hit", "wikidata-anchor"}, n
    assert "概念としての関係は未検証です" in (d.get("note") or "")


# ===========================================================================
# H-C / F8  自動取得を確定事実として渡さない
# ===========================================================================

CTX = {"description": "人間が自然を自己の身体の延長として用いること",
       "orig_labels": {"de": "unorganischer Leib", "en": "inorganic body"},
       "sep_title": "Marx", "debate": ["疎外論", "物質代謝"],
       "related": ["疎外", "自然"], "influences": ["ヘーゲル"]}


@pytest.mark.parametrize("lang", ["ja", "en"])
def test_the_retrieved_block_is_declared_unverified(lang):
    p = deepsearch.generate("非有機的肉体", "肉体と自然の境界を知りたい", "claude", lang, CTX)
    if lang == "ja":
        assert "機械が取得した手がかり" in p
        assert "未検証" in p
        assert "既に判明している手がかり" not in p
    else:
        assert "UNVERIFIED" in p
        assert "Leads already found" not in p


def test_other_language_labels_are_not_called_confirmed_originals():
    ja = deepsearch.generate("非有機的肉体", "", "claude", "ja", CTX)
    en = deepsearch.generate("inorganic body", "", "claude", "en", CTX)
    assert "確認された原語候補" not in ja
    assert "原語の確認ではない" in ja
    assert "Confirmed original-language term" not in en
    assert "NOT a confirmed original term" in en


def test_the_prompt_tells_the_reader_to_correct_the_block():
    ja = deepsearch.generate("非有機的肉体", "", "claude", "ja", CTX)
    assert "まずそれを指摘し" in ja
    assert "一次資料を採ってください" in ja


def test_the_lost_distinction_example_is_on_the_body_side():
    """埋没しているのは「肉体」の側である。例示が区別を取り違えていた。"""
    ja = deepsearch.generate("非有機的肉体", "", "claude", "ja", CTX)
    assert "埋没しているのは「肉体」の側である" in ja
    assert "「非有機的」一語に埋没する" not in ja
    en = deepsearch.generate("inorganic body", "", "claude", "en", CTX)
    assert 'collapse is on the "body" side' in en


def test_without_ctx_the_block_is_absent_and_said_to_be_absent():
    """節が無いのに本文が節を参照すると、受け取った側が在ると思って探す。"""
    ja = deepsearch.generate("非有機的肉体", "", "claude", "ja", {})
    assert "## 0. 機械が取得した手がかり" not in ja
    assert "上記の「機械が取得した手がかり」" not in ja
    assert "この依頼には機械が取得した手がかりを付けていません" in ja
    en = deepsearch.generate("inorganic body", "", "claude", "en", {})
    assert "## 0. Machine-retrieved leads" not in en
    assert "The leads below" not in en
    assert "No machine-retrieved leads are attached" in en


@pytest.mark.parametrize("lang", ["ja", "en"])
def test_section_four_does_not_reference_a_debate_structure_that_is_absent(lang):
    """F8: §0 を出さないのに §4 が「上のSEP論争構造を出発点に」と書いていた。

    受け取った AI は存在しない節を探し、無ければ補完して書く。
    それはもう自動取得でもない内容が「SEPの論争構造」として下流に入ることである。
    """
    with_ctx = deepsearch.generate("非有機的肉体", "", "claude", lang, CTX)
    without = deepsearch.generate("非有機的肉体", "", "claude", lang, {})
    if lang == "ja":
        assert "論争構造" in with_ctx
        assert "論争構造" not in without, without[without.find("## 4"):][:200]
    else:
        assert "debate structure" in with_ctx
        assert "debate structure" not in without


# ===========================================================================
# F9  台帳へ印と確度を引き継ぐ
# ===========================================================================

def test_the_ledger_does_not_stamp_confirmed_on_a_machine_guess():
    """seed の "confirmed" のラベルは「本文・書誌を確認」である。

    1巡目は、機械が切り出した非語（機的身体）を confirmed で台帳に入れていた。
    説明は「引用された本文か典拠目録が直接支持する」であり、当たらない。
    """
    src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    i = src.index("def _history_discovery_from_sources")
    seg = src[i:i + 6000]
    assert '"confirmed", [dict_source], "意味のまとまりとして抽出"' not in seg
    assert '"unverified" if unresolved else "candidate"' in seg
    assert '"unverified" if inside else "candidate"' in seg
    assert "字の辞書義（補助）" in seg
