"""持ち出す文の試験（2026-10-09）。

なぜ在るか（半田様の設計）:
  半田様が自分の環境で ChatGPT や Google 検索を使うのは自由である。
  この system がそれを提供できないなら、両者を繋ぐのは
  「半田様の環境と責任で実行するための文」を出すことである。送信はこの system がしない。

既に在ったもの（実測して確かめた・重複を作らないため）:
  `/deepsearch` の prompt 生成と `deepsearch` action（視点・目的・難易度を選ぶ面）。
  menu の文も「お使いのAI（ChatGPT/Gemini/Claude等）に貼って実行してください」。
  足りなかったのは次の3つで、本試験はそこを守る。
    (1) 出る面が3つだけだった（分岐menu・node menu・辺menu）
    (2) 渡していたのは topic と goal だけで、この system が測ったものを渡していなかった
    (3) 責任の分担が画面に書かれていなかった

外部取得なし（この層は取得しない。1881年の辞書は手元のfile）。
"""
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from app import handoff
from app.main import app

ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")

RECEIPTS = [
    {"layer": "Wikipedia全文検索", "query_sent": "理性", "count": 5,
     "retrieved_at": "2026-10-09T11:00:00Z", "licence": "CC BY-SA 4.0"},
    {"layer": "NDLサーチ（作品名で照会）", "query_sent": "理性", "count": 0,
     "retrieved_at": "2026-10-09T11:00:00Z",
     "zero_means": "作品名として照会したので、概念語では0件になりやすい"},
    {"layer": "SEP", "query_sent": "理性", "count": 0,
     "retrieved_at": "2026-10-09T11:00:00Z", "error": "TimeoutError: upstream"},
]
SOURCES = [
    {"title": "理性", "url": "https://ja.wikipedia.org/wiki/理性",
     "note": "哲学の概念", "licence": "CC BY-SA 4.0"},
    {"title": "禁転載の資料", "url": "https://ctext.org/x",
     "note": "ここが本文である", "licence": "保存禁止"},
    {"title": "条件未記入の資料", "url": "https://example.org/y",
     "note": "ここも本文である", "licence": ""},
]


@pytest.fixture()
def client():
    return TestClient(app)


def build(**kw):
    kw.setdefault("term", "非有機的肉体")
    return handoff.build(**kw)


# ===========================================================================
# 責任の分担（半田様の設計の中心）
# ===========================================================================

def test_the_text_says_who_executes_it():
    d = build(text="「理性」と「感性」の違いが気になっています。")
    assert "半田様の環境と責任" in d["responsibility"]
    assert "送信しません" in d["responsibility"]
    assert "実行はあなたの環境で行ってください" in d["prompt"]


def test_the_system_does_not_send_anything():
    """この層は取得しない。connector を呼ぶ経路が無いことを source で確かめる。"""
    src = (ROOT / "app" / "handoff.py").read_text(encoding="utf-8")
    for bad in ("httpx", "requests", "cached_get_json", "searxng", "wikipedia",
                "wikidata", "openalex", "crossref", "sep"):
        assert bad not in src, bad


def test_the_ui_states_the_division_on_the_inquiry_page(client):
    body = client.get("/inquiry").text
    assert "この system は送信しません" in body
    assert "半田様の環境と責任で行ってください" in body


# ===========================================================================
# 何を渡し、何を渡さないか（公理3）
# ===========================================================================

def test_the_users_own_sentence_is_passed_verbatim():
    text = "「理性」と「感性」の違いが気になっています。"
    d = build(text=text)
    assert text in d["prompt"]
    assert "私が書いた文（原文のまま）" in d["prompt"]


def test_measured_receipts_are_passed_with_the_exact_query():
    """手元のAIが知り得ないのはここである。分担の要。"""
    d = build(text="x", receipts=RECEIPTS)
    p = d["prompt"]
    assert "投げた文字列「理性」" in p
    assert "2026-10-09T11:00:00Z" in p
    assert "未検証の候補" in p


def test_zero_results_carry_their_meaning():
    d = build(text="x", receipts=RECEIPTS)
    assert "0件の意味: 作品名として照会したので" in d["prompt"]


def test_a_failed_layer_is_not_hidden():
    d = build(text="x", receipts=RECEIPTS)
    assert "TimeoutError: upstream" in d["prompt"]


def test_the_1881_dictionary_is_quoted_with_its_licence():
    d = build(term="理性")
    assert "理性 ← Reason" in d["prompt"]
    assert "CC BY 4.0" in d["prompt"]
    assert "1881年時点の対応であり、現代の語義ではない" in d["prompt"]


def test_a_term_absent_from_1881_says_what_zero_means():
    d = build(term="非有機的肉体")
    assert "一致 0 件" in d["prompt"]
    assert "索引の故障は別" in d["prompt"]


# ===========================================================================
# 利用条件（再配布を許さない情報源の本文を載せない）
# ===========================================================================

def test_content_is_quoted_only_when_redistribution_is_allowed():
    d = build(text="x", sources=SOURCES)
    p = d["prompt"]
    # CC BY-SA は載せる
    assert "哲学の概念" in p
    # 保存禁止・条件未記入は本文を載せず所在だけ
    assert "ここが本文である" not in p
    assert "ここも本文である" not in p
    assert "https://ctext.org/x" in p
    assert "https://example.org/y" in p


def test_the_omission_is_declared_not_silent():
    d = build(text="x", sources=SOURCES)
    assert any("再配布を許す条件が確認できない" in x for x in d["omitted"]), d["omitted"]
    assert "所在だけを載せた（2件）" in d["prompt"]


def test_a_source_without_a_licence_is_marked_as_unrecorded():
    d = build(text="x", sources=[SOURCES[2]])
    assert "利用条件 未記入" in d["prompt"]


@pytest.mark.parametrize("lic,quotable", [
    ("CC0 1.0", True), ("PDM 1.0", True), ("CC BY 4.0", True),
    ("CC BY-SA 4.0", True), ("CC BY-NC-SA 3.0", False),
    ("保存禁止", False), ("", False), ("内部利用のみ", False),
])
def test_the_licence_gate_decides_per_tier(lic, quotable):
    assert handoff._quotable(lic) is quotable


# ===========================================================================
# 人の判断の欄（半田様自身が書いたもの）
# ===========================================================================

def test_human_records_are_passed_as_the_users_own():
    d = build(text="x", records=[
        {"type": "provisional", "title": "非有機的肉体とは外部にある自然である",
         "body": "この説明では足りない"},
        {"type": "memory", "title": "吉本は四分類していたと記憶している"},
        {"type": "naming", "title": "『知的非有機的器官』と呼ぶ"}])
    p = d["prompt"]
    assert "半田様自身が書いた判断" in p
    assert "暫定定義" in p and "記憶" in p and "命名" in p
    assert "この system が生成したものではない" in p


def test_the_endpoint_includes_human_records_of_a_project(client):
    pid = client.post("/api/projects", json={"title": "持ち出しの試験"}).json()["id"]
    for t, title in (("provisional", "暫定の定義"), ("memory", "記憶している"),
                     ("naming", "こう呼ぶ")):
        r = client.post("/api/projects/%d/nodes" % pid,
                        json={"type": t, "title": title, "origin": "human"})
        assert r.status_code == 200, r.text
    d = client.post("/api/handoff", json={"term": "非有機的肉体",
                                          "project_id": pid}).json()
    for title in ("暫定の定義", "記憶している", "こう呼ぶ"):
        assert title in d["prompt"], title
    assert any("人の判断の欄 3 件" in x for x in d["contains"]), d["contains"]


def test_without_a_project_the_absence_is_declared(client):
    d = client.post("/api/handoff", json={"term": "理性"}).json()
    assert any("人の判断の欄" in x for x in d["omitted"]), d["omitted"]


# ===========================================================================
# 契約と endpoint
# ===========================================================================

def test_the_payload_lists_what_it_contains_and_omits():
    d = build(text="x", receipts=RECEIPTS, sources=SOURCES)
    assert d["schema_version"] == "dialexis.handoff.v1"
    assert d["contains"] and d["omitted"]
    assert d["chars"] == len(d["prompt"])
    assert "鍵・API・内部path（渡さない）" in " ".join(d["omitted"])


def test_endpoint_refuses_an_empty_request(client):
    assert client.post("/api/handoff", json={}).status_code == 400
    assert client.post("/api/handoff", json={"term": "  ", "text": " "}).status_code == 400


def test_endpoint_accepts_text_alone(client):
    r = client.post("/api/handoff", json={"text": "「理性」とは何か。"})
    assert r.status_code == 200
    assert "理性" in r.json()["prompt"]


def test_an_unknown_project_is_refused_not_silently_dropped(client):
    assert client.post("/api/handoff",
                       json={"term": "理性", "project_id": 999999}).status_code == 404


# ===========================================================================
# どの場面からでも出せること（半田様の「どんな時でも」）
# ===========================================================================

def _block(start, end):
    i = JS.index(start)
    return JS[i:JS.index(end, i)]


def test_handoff_is_a_registered_action():
    block = _block("const ACTIONS = {", "// 各表示面が使う Action ID")
    assert re.search(r"^\s{2}handoff:\s*\{", block, re.MULTILINE), "registry に無い"
    assert "gHandoffPanel" in JS


def test_handoff_does_not_change_the_map():
    """持ち出しは探索ではない。地図の中心や履歴を動かさない。"""
    block = _block("  handoff:", "  newtab:")
    assert "transient: true" in block
    assert "commits: false" in block
    assert "changesCenter" not in block


def test_handoff_appears_on_every_surface_that_has_a_subject():
    """1つの面にだけ在ると、その場面でしか持ち出せない。"""
    ids = _block("const UI_ACTION_IDS = {", "function _activeTerm")
    for surface in ("edge", "node", "card", "play", "shelfPanel",
                    "scrollCard", "contextEnt", "textLink"):
        line = re.search(r"^\s{2}%s:\s*(\[[^\]]*\])" % surface, ids, re.MULTILINE)
        assert line, surface
        assert "handoff" in line.group(1), surface


def test_handoff_is_in_the_panel_footer():
    m = _block("const UI_ACTION_MAP = {", "const UI_ACTION_IDS = {")
    assert m.count("handoff") >= 2, "panelFooter と nomiss の両方に要る"
    # 実際のボタン列にも在ること（map に在ってボタンが無いと押せない）
    assert '["handoff", "📤 "' in JS


def test_the_node_and_domain_menus_offer_it():
    assert JS.count('action: "handoff"') >= 2


def test_the_existing_deepsearch_action_is_not_removed():
    """既に在る面を置き換えない。重複の自由text入口を増やしたくない。"""
    assert "gPerspectivePanel" in JS
    block = _block("const ACTIONS = {", "// 各表示面が使う Action ID")
    assert re.search(r"^\s{2}deepsearch:\s*\{", block, re.MULTILINE)
