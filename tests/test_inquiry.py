"""自由textの問い合わせ層の試験（2026-10-09）。

なぜ在るか:
  入り口が概念語1つである限り、半田様が実際に書いた文が system に入らない。
  非有機的肉体の研究で分岐を作った3つの瞬間は、すべて半田様の発話だった
  （資料0件・AI0件）。

半田様の決裁（2026-10-09）を機械で守る:
  鍵つきの外部AI検索は使わない  → 外部へ出る層の名前を固定し、増えたら落ちる
  外へ投げるのは押したときだけ  → web=False で外部connectorを1本も呼ばない
  投げた文字列を残す            → receipts に query_sent が全件在る

作る途中で実測した自分の欠陥を、戻らないように固定する:
  E1 tetsugaku_jii.lookup は ok() の封筒を返す。封筒を data として読んだため
     哲学字彙1881 が全語で0件になっていた（理性でも0件）。辞書は正常だった。
     今日これと同型の読み違い（0件を欠落と読む）を何度も踏んでいる。
  E2 裸の「って」を接尾辞に入れたため「気になって」から `気にな` が語になった。
  E3 語側が貪欲だったため「非有機的肉体という言葉とは」で語側が標識ごと飲み込み、
     NOT_A_TERM に当たって0語になった。最短一致にして直した。
  D1 語の上限20字で「非有機的肉体という言葉が気にな」が外部6層へ投げられていた。
  D2 順位の根拠が無かった。文の他の語との共起を数えて根拠にする。
  D3 0件の意味が層ごとに違うのに、receipt から読めなかった（沈黙する0件）。

外部取得なし（connector はすべて差し替える）。
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app import inquiry
from app.main import app

# 外部へ出る層。半田様の決裁により、鍵つきの層をここへ増やしてはならない。
KEYLESS_LAYERS = {
    "Wikipedia全文検索", "Wikidata", "SEP（スタンフォード哲学百科）",
    "OpenAlex", "Crossref", "NDLサーチ（作品名で照会）",
}


@pytest.fixture()
def client():
    return TestClient(app)


def run(text, web=False, lang="ja"):
    return asyncio.run(inquiry.gather(text, lang, want_web=web))


# ===========================================================================
# 語の抽出（文の形からだけ取る。意味は判断しない）
# ===========================================================================

CASES = [
    ("「理性」と「感性」の違いが気になっています。非有機的肉体という言葉とはどう関係しますか。",
     ["理性", "感性", "非有機的肉体"]),
    ("ふつうってなんですか。", ["ふつう"]),
    ("疎外とは何かを考えています。", ["疎外"]),
    ("アウラという概念をどう使えばよいか。", ["アウラ"]),
    ("これはただの独り言です。", []),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_terms_come_from_the_shape_of_the_sentence(text, expected):
    got = [t["term"] for t in inquiry.extract_terms(text)]
    for e in expected:
        assert e in got, (text, got)


def test_a_verb_fragment_is_not_a_term():
    """E2: 裸の「って」で「気になって」から `気にな` が語になった。"""
    got = [t["term"] for t in inquiry.extract_terms("非有機的肉体が気になっています。")]
    assert "気にな" not in got, got


def test_the_marker_is_not_swallowed_by_a_greedy_term():
    """E3: 語側が貪欲だと「非有機的肉体という言葉とは」で標識ごと飲み込む。"""
    got = [t["term"] for t in inquiry.extract_terms("非有機的肉体という言葉とはどう関係しますか。")]
    assert "非有機的肉体" in got, got
    assert not any("という" in g for g in got), got


def test_a_clause_is_not_a_term():
    """D1: 上限20字で「非有機的肉体という言葉が気にな」が外部へ投げられていた。"""
    got = [t["term"] for t in inquiry.extract_terms(
        "非有機的肉体という言葉が気になっています。")]
    for g in got:
        assert len(g) <= 12, g
        for bad in inquiry.NOT_A_TERM:
            assert bad not in g, (g, bad)


def test_every_term_says_why_it_was_picked():
    for t in inquiry.extract_terms("「暇」と「退屈」の違い。"):
        assert t["why"]
        assert t["evidence"] == "candidate"


def test_questions_are_split_not_rewritten():
    qs = inquiry.split_questions(
        "肉体と自然の違いを知りたい。吉本隆明は四分類していたと記憶している。")
    assert len(qs) == 2
    assert "肉体と自然の違いを知りたい" in qs[0]
    # 言い換えも補完もしない
    assert all("？" not in q for q in qs)


# ===========================================================================
# 押したときだけ外へ出る（半田様の決裁）
# ===========================================================================

def test_local_only_touches_no_external_connector(monkeypatch):
    """web=False のとき、外部connectorを1本も呼ばない。"""
    called = []

    def boom(name):
        async def f(*a, **k):
            called.append(name)
            raise AssertionError("外部へ出た: " + name)
        return f

    for mod, fn, name in (("wikipedia", "search", "wikipedia"),
                          ("wikidata", "search", "wikidata"),
                          ("sep", "search", "sep"),
                          ("openalex", "search_works", "openalex"),
                          ("crossref", "search_works", "crossref"),
                          ("ndl", "by_title", "ndl")):
        monkeypatch.setattr(getattr(inquiry, mod), fn, boom(name))

    d = run("「理性」と「感性」の違い。", web=False)
    assert called == []
    assert d["web_used"] is False
    assert all(r["layer"] == "哲学字彙1881（local）" for r in d["receipts"])


def test_the_keyless_layer_set_is_fixed(monkeypatch):
    """鍵つきの層が黙って増えないようにする（P5・半田様の決裁）。"""
    d = run_with_stubs(monkeypatch, "「理性」と「感性」の違い。")
    web = {r["layer"] for r in d["receipts"] if r["layer"] != "哲学字彙1881（local）"}
    assert web <= KEYLESS_LAYERS, web - KEYLESS_LAYERS


# ===========================================================================
# 手元の層（封筒の読み違いを戻さない）
# ===========================================================================

def test_the_1881_index_is_actually_readable():
    """E1: 封筒を data として読んだため、理性でも0件になっていた。"""
    assert inquiry._jii_index_alive() is True


def test_the_1881_layer_returns_rows_for_a_known_term():
    d = run("「理性」とは何か。", web=False)
    jii = [r for r in d["receipts"] if r["layer"] == "哲学字彙1881（local）"]
    assert jii and jii[0]["count"] >= 1, jii
    assert jii[0]["index_selftest"] == "ok"
    assert any("Reason" in (s["title"] or "") or "Vernunft" in (s["title"] or "")
               for s in d["sources"]), [s["title"] for s in d["sources"]]


def test_a_broken_index_is_not_reported_as_absence(monkeypatch):
    """索引の故障と、その語が無いことは別である。区別できない0件を作らない。"""
    monkeypatch.setattr(inquiry, "_jii_index_alive", lambda: False)
    d = run("「理性」とは何か。", web=False)
    jii = [r for r in d["receipts"] if r["layer"] == "哲学字彙1881（local）"][0]
    assert jii["index_selftest"] == "broken"
    assert any("索引" in x["why"] for x in d["drops"]), d["drops"]


# ===========================================================================
# 受領証（C5）と 0件の意味（公理1）
# ===========================================================================

STUB = {
    "wikipedia": [{"title": "肉体と自然", "url": "u1", "content": "自然との関係"},
                  {"title": "肉体関係 (隠語)", "url": "u2", "content": ""}],
    "wikidata": [{"label": "体", "url": "u3", "description": "", "qid": "Q1"}],
    "sep": [],
    "openalex": [{"title": "Inorganic body", "url": "u4", "year": 1990, "cited_by_count": 3}],
    "crossref": [],
    "ndl": [],
}


def run_with_stubs(monkeypatch, text, lang="ja"):
    def give(rows):
        async def f(*a, **k):
            return {"source": "stub", "retrieved_at": "2026-10-09T00:00:00Z",
                    "cached": False, "error": None, "data": rows}
        return f

    monkeypatch.setattr(inquiry.wikipedia, "search", give(STUB["wikipedia"]))
    monkeypatch.setattr(inquiry.wikidata, "search", give(STUB["wikidata"]))
    monkeypatch.setattr(inquiry.sep, "search", give(STUB["sep"]))
    monkeypatch.setattr(inquiry.openalex, "search_works", give(STUB["openalex"]))
    monkeypatch.setattr(inquiry.crossref, "search_works", give(STUB["crossref"]))
    monkeypatch.setattr(inquiry.ndl, "by_title", give(STUB["ndl"]))
    return asyncio.run(inquiry.gather(text, lang, want_web=True))


def test_every_receipt_records_the_exact_string_sent(monkeypatch):
    """system は入力をそのまま投げず、取り出した語を投げる。だから投げた文字列を出す。"""
    d = run_with_stubs(monkeypatch, "「肉体」と「自然」の違い。")
    assert d["receipts"]
    for r in d["receipts"]:
        assert r["query_sent"], r
        assert r["query_sent"] in {"肉体", "自然"}, r
        assert r["retrieved_at"]
        assert "count" in r


def test_zero_results_say_what_zero_means(monkeypatch):
    """0 の意味は層ごとに違う。沈黙する0件を作らない。"""
    d = run_with_stubs(monkeypatch, "「肉体」と「自然」の違い。")
    zeros = [r for r in d["receipts"] if r["count"] == 0 and not r.get("error")]
    assert zeros
    for r in zeros:
        assert r.get("zero_means"), r


def test_an_error_is_recorded_as_a_drop(monkeypatch):
    def give_err(*a, **k):
        async def f(*a, **k):
            return {"source": "stub", "retrieved_at": "t", "cached": False,
                    "error": "RuntimeError: 落ちた", "data": None}
        return f

    monkeypatch.setattr(inquiry.wikipedia, "search", give_err())
    monkeypatch.setattr(inquiry.wikidata, "search", give_err())
    monkeypatch.setattr(inquiry.sep, "search", give_err())
    monkeypatch.setattr(inquiry.openalex, "search_works", give_err())
    monkeypatch.setattr(inquiry.crossref, "search_works", give_err())
    monkeypatch.setattr(inquiry.ndl, "by_title", give_err())
    d = asyncio.run(inquiry.gather("「肉体」とは何か。", "ja", want_web=True))
    assert d["drops"], d
    assert d["layers_answered"] < d["layers_asked"]


def test_an_exception_does_not_break_the_payload(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(inquiry.wikipedia, "search", boom)
    monkeypatch.setattr(inquiry.wikidata, "search", boom)
    monkeypatch.setattr(inquiry.sep, "search", boom)
    monkeypatch.setattr(inquiry.openalex, "search_works", boom)
    monkeypatch.setattr(inquiry.crossref, "search_works", boom)
    monkeypatch.setattr(inquiry.ndl, "by_title", boom)
    d = asyncio.run(inquiry.gather("「肉体」とは何か。", "ja", want_web=True))
    assert d["schema_version"] == "dialexis.inquiry.v1"
    assert any("network down" in (r.get("error") or "") for r in d["receipts"])


# ===========================================================================
# 順位の根拠（D2）
# ===========================================================================

def test_context_hits_are_counted_and_used_for_order(monkeypatch):
    """「意味が近い」ではなく「文の他の語と同時に現れた」だけを数える。"""
    d = run_with_stubs(monkeypatch, "「肉体」と「自然」の違い。")
    assert d["sources"]
    for s in d["sources"]:
        assert "context_hits" in s
        assert s["why_ranked"]
    hits = [s["context_hits"] for s in d["sources"]]
    assert hits == sorted(hits, reverse=True), hits
    top = d["sources"][0]
    assert top["context_hits"] >= 1
    assert "自然" in top["context_terms"] or "肉体" in top["context_terms"]


def test_a_zero_hit_source_is_kept_not_dropped(monkeypatch):
    """共起0でも捨てない。捨てると黙って減る（公理1）。"""
    d = run_with_stubs(monkeypatch, "「肉体」と「自然」の違い。")
    assert any(s["context_hits"] == 0 for s in d["sources"])


# ===========================================================================
# 落とし所（M0 C2）
# ===========================================================================

def test_the_payload_names_where_each_finding_can_be_recorded(monkeypatch):
    """取得しただけでは価値にならない。どの欄へ記録できるかを payload が言う。"""
    d = run_with_stubs(monkeypatch, "「肉体」と「自然」の違い。")
    rec = d["record_as"]
    assert rec["question"]["type"] == "provisional"
    assert rec["memory"]["type"] == "memory"
    assert rec["open"]["type"] == "open_question"
    assert "provenance" in rec["source"]["endpoint"]


def test_the_payload_states_what_it_does_not_guarantee(monkeypatch):
    d = run_with_stubs(monkeypatch, "「肉体」と「自然」の違い。")
    assert "保証しない" in d["honesty"]
    assert "主題の判定ではない" in d["honesty"]


# ===========================================================================
# endpoint
# ===========================================================================

def test_endpoint_refuses_empty_text(client):
    assert client.post("/api/inquiry", json={"text": "   "}).status_code == 400
    assert client.post("/api/inquiry", json={}).status_code == 400


def test_endpoint_defaults_to_not_going_outside(client, monkeypatch):
    """web を書かなければ外へ出ない。既定で外へ出る設計にはしない。"""
    async def boom(*a, **k):
        raise AssertionError("既定で外へ出た")

    monkeypatch.setattr(inquiry.wikipedia, "search", boom)
    r = client.post("/api/inquiry", json={"text": "「理性」とは何か。"})
    assert r.status_code == 200
    assert r.json()["web_used"] is False


def test_endpoint_returns_the_contract(client):
    r = client.post("/api/inquiry", json={"text": "「理性」と「感性」の違い。", "web": False})
    d = r.json()
    for k in ("schema_version", "queried_at", "terms", "questions", "sources",
              "receipts", "drops", "layers_asked", "layers_answered", "found",
              "record_as", "honesty", "web_used"):
        assert k in d, k


def test_the_page_is_served_and_says_what_is_sent(client):
    r = client.get("/inquiry")
    assert r.status_code == 200
    body = r.text
    # 押したときだけであること、語だけを送ること、鍵が不要であることを画面に書く
    assert "押したときだけ" in body
    assert "文の全体は送りません" in body
    assert "鍵も料金もありません" in body
