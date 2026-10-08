"""人の判断の記録を、黙って書き換えられないようにする試験（2026-10-08）。

なぜ必要か（半田様の「非有機的肉体」研究の復元から）:
  研究を実際に進めた3つの動きが、systemに1つも無かった。
    S2 暫定定義を自分で書き、そこから何が落ちたかを自分で言う（provisional）
    S6 自分の記憶を、出典なしの独立した枝として立てる（memory）
    S9 命名を保留したまま、問いを言い換えて進む（naming）
  「知り得なかったことに到達した」3つの瞬間の引き金は、すべて人の動きだった
  （資料0件・AI0件）。誤る権利は人の側にあり、守るべきはその記録が消えないことである。

何を保証し、何を保証しないか（公理3）:
  保証する   一度記録した人の判断は、追記のみで、黙って書き換え・削除できない
  保証しない 発信者が人であること。`origin` はclientの自己申告である

  当初は `origin != human` を入口で拒む設計だったが、2026-10-08 の敵対的検証で
  13件の抜け道が実証された。originを省けば既定でhumanになり、型を後から
  付け替えれば確度もstatusも迂回でき、人が書いた欄も3往復で洗えた。
  宣言が実装の実力を超えていたため、関門そのものを「追記のみ」へ替えた。
  この試験は、その置き換えが実際に効いていることと、
  敵対的検証で生き残った4つの変異（検査されていなかった実装行）を固定する。
"""
import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def pid(client):
    r = client.post("/api/projects", json={"title": "人の判断の欄の試験"})
    assert r.status_code == 200
    return r.json()["id"]


def make(client, pid, **kw):
    body = {"origin": "human", **kw}
    return client.post(f"/api/projects/{pid}/nodes", json=body)


def node_of(client, pid, nid):
    g = client.get(f"/api/projects/{pid}/graph").json()
    return [n for n in g["nodes"] if n["id"] == nid][0]


# ---- 型と宣言 -------------------------------------------------------------

def test_the_three_types_exist():
    assert set(db.HUMAN_ONLY_TYPES) == {"provisional", "memory", "naming"}
    for t in db.HUMAN_ONLY_TYPES:
        assert t in db.NODE_TYPES


def test_the_limit_of_the_guarantee_is_written_down():
    """originが自己申告であることを、codeの側に書き残す（公理3）。"""
    assert "自己申告" in db.ORIGIN_IS_SELF_DECLARED


# ---- 作成時 ---------------------------------------------------------------

@pytest.mark.parametrize("t", ["provisional", "memory", "naming"])
def test_declaring_ai_is_refused(client, pid, t):
    r = make(client, pid, type=t, title="AIが名乗って書いた", origin="ai")
    assert r.status_code == 403
    assert "自己申告" in r.json()["detail"]


def test_human_keeps_both_halves(client, pid):
    """暫定定義（title）と、そこから落ちた契機（body）を1つのnodeに持つ。"""
    r = make(client, pid, type="provisional",
             title="非有機的肉体とは、人間の外部にある自然のことである",
             body="この説明では足りない。「自己の一部である」という契機が落ちる")
    assert r.status_code == 200
    assert "落ちる" in node_of(client, pid, r.json()["id"])["body"]


def test_memory_confidence_is_pinned_at_creation(client, pid):
    r = make(client, pid, type="memory", confidence="confirmed",
             title="吉本は非有機的肉体を四分類していたと記憶している")
    assert node_of(client, pid, r.json()["id"])["confidence"] == "unverified"


def test_naming_starts_held(client, pid):
    r = make(client, pid, type="naming", status="adopted",
             title="LLMを『知的非有機的器官』と呼ぶ",
             body="問いを『疎外化と呼びうる過程が成立しているか』へ書き換えた")
    assert node_of(client, pid, r.json()["id"])["status"] == "held"


def test_empty_is_allowed_and_not_filled_by_default(client, pid):
    r = make(client, pid, type="provisional", title="暫定定義だけ書いた")
    assert node_of(client, pid, r.json()["id"])["body"] == ""


# ---- 追記のみ（敵対的検証で破られた経路） ---------------------------------

@pytest.mark.parametrize("t", ["provisional", "memory", "naming"])
def test_an_existing_human_record_cannot_be_patched_at_all(client, pid, t):
    """originを書かずにPATCHする経路（H2・H5）を閉じる。変異4を殺す。"""
    nid = make(client, pid, type=t, title="人が書いた記録").json()["id"]
    for body in ({"title": "書き換え"}, {"body": "差し替え"},
                 {"confidence": "confirmed"}, {"status": "adopted"},
                 {"type": "note"}, {"origin": "human", "title": "人を名乗る"}):
        r = client.patch(f"/api/nodes/{nid}", json=body)
        assert r.status_code == 409, (t, body, r.status_code)
        assert "追記のみ" in r.json()["detail"]


@pytest.mark.parametrize("t", ["provisional", "memory", "naming"])
def test_an_ordinary_node_cannot_be_converted(client, pid, t):
    """型を後から付け替える経路（H3・H4）を閉じる。"""
    nid = make(client, pid, type="note", title="ふつうの覚書",
               origin="ai", confidence="confirmed", status="adopted").json()["id"]
    r = client.patch(f"/api/nodes/{nid}", json={"type": t})
    assert r.status_code == 409
    assert "新しく作る形" in r.json()["detail"]
    assert node_of(client, pid, nid)["type"] == "note"


@pytest.mark.parametrize("t", ["provisional", "memory", "naming"])
def test_a_human_record_cannot_be_deleted(client, pid, t):
    """却下した定義も、誤っていた記憶も、研究を動かした記録である。"""
    nid = make(client, pid, type=t, title="消させない記録").json()["id"]
    r = client.delete(f"/api/nodes/{nid}")
    assert r.status_code == 409
    assert node_of(client, pid, nid)["title"] == "消させない記録"


def test_memory_cannot_be_given_a_source(client, pid):
    """H6: memory に出典を付けられた。出典が在るなら evidence を別に立てる。"""
    nid = make(client, pid, type="memory", title="記憶").json()["id"]
    r = client.post(f"/api/nodes/{nid}/provenance",
                    json={"source_name": "吉本隆明", "locator": "p.123"})
    assert r.status_code == 409
    assert "evidence" in r.json()["detail"]


def test_adoption_is_expressed_by_a_new_node_not_a_rewrite(client, pid):
    """命名の採用は、naming を書き換えるのではなく decision を足して表す。"""
    nid = make(client, pid, type="naming", title="『知的非有機的器官』と呼ぶ").json()["id"]
    dec = make(client, pid, type="decision", title="この命名を採用する",
               body="2026-10-08 に採用", status="adopted")
    assert dec.status_code == 200
    e = client.post(f"/api/projects/{pid}/edges",
                    json={"src": dec.json()["id"], "dst": nid, "rel": "answers"})
    assert e.status_code == 200
    assert node_of(client, pid, nid)["status"] == "held"   # 元の記録は保留のまま


# ---- 検査されていなかった実装行（変異1〜3を殺す） -------------------------

def test_unknown_type_is_refused_on_create(client, pid):
    r = make(client, pid, type="随筆", title="x")
    assert r.status_code == 400


def test_empty_title_is_refused_on_create(client, pid):
    for t in ("", "   ", "　"):
        assert make(client, pid, type="note", title=t).status_code == 400


def test_title_is_stripped_on_create(client, pid):
    nid = make(client, pid, type="note", title="  前後に空白  ").json()["id"]
    assert node_of(client, pid, nid)["title"] == "前後に空白"


def test_patch_validates_vocabulary_and_title(client, pid):
    """H7: PATCHが title を無検査で空に戻せた。"""
    nid = make(client, pid, type="note", title="x").json()["id"]
    for bad in ({"status": "採用"}, {"confidence": "たぶん"},
                {"origin": "AI"}, {"type": "随筆"}, {"title": "   "}):
        assert client.patch(f"/api/nodes/{nid}", json=bad).status_code == 400


def test_create_validates_status(client, pid):
    assert make(client, pid, type="note", title="x", status="保留").status_code == 400


# ---- 2巡目の敵対的検証（N1〜N8）で破られた経路 ----------------------------

def test_project_deletion_does_not_silently_cascade(client, pid):
    """N1: 企画を消すとFK CASCADEで人の記録が黙って消えた。"""
    for t in ("provisional", "memory", "naming"):
        assert make(client, pid, type=t, title=f"{t} の記録").status_code == 200
    r = client.delete(f"/api/projects/{pid}")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["human_records"] == 3
    assert "confirm_human_records=3" in detail["message"]
    # 件数が合わないrequestも通さない
    assert client.delete(f"/api/projects/{pid}?confirm_human_records=1").status_code == 409
    assert len(client.get(f"/api/projects/{pid}/graph").json()["nodes"]) == 3
    # 件数を明示すれば通る（消すこと自体は人の判断である）
    assert client.delete(f"/api/projects/{pid}?confirm_human_records=3").status_code == 200


def test_export_md_shows_the_three_types(client, pid):
    """N2: 人が読む export.md からだけ3型が黙って落ちていた。"""
    for t in ("provisional", "memory", "naming"):
        make(client, pid, type=t, title=f"MARK-{t}")
    md = client.get(f"/api/projects/{pid}/export.md").text
    for t in ("provisional", "memory", "naming"):
        assert f"MARK-{t}" in md, t


def test_supersedes_edge_actually_exists(client, pid):
    """N3: 409が指示する supersedes が語彙に無く400だった（公理3違反）。"""
    assert "supersedes" in db.RELATIONS
    old = make(client, pid, type="provisional", title="古い暫定定義").json()["id"]
    new = make(client, pid, type="provisional", title="新しい暫定定義").json()["id"]
    r = client.post(f"/api/projects/{pid}/edges",
                    json={"src": new, "dst": old, "rel": "supersedes"})
    assert r.status_code == 200


def test_memory_cannot_get_a_source_at_creation_either(client, pid):
    """N4: create時の provenance 配列は検査されていなかった。"""
    r = make(client, pid, type="memory", title="記憶",
             provenance=[{"source_name": "AIが同時に付けた出典"}])
    assert r.status_code == 409


def test_edges_touching_a_human_record_cannot_be_deleted(client, pid):
    """N5: 辺を消すと、記録は残っても「どの問いに答えていたか」が消える。"""
    q = make(client, pid, type="question", title="暇と退屈はどう違うのか").json()["id"]
    m = make(client, pid, type="memory", title="四分類していたと記憶している").json()["id"]
    e = client.post(f"/api/projects/{pid}/edges",
                    json={"src": m, "dst": q, "rel": "responds_to"}).json()["id"]
    r = client.delete(f"/api/edges/{e}")
    assert r.status_code == 409
    assert "contradicts" in r.json()["detail"]


@pytest.mark.parametrize("t", ["provisional", "memory"])
def test_human_records_start_open_not_adopted(client, pid, t):
    """N7: 最初から adopted で置くと、後から直せない記録が生まれる。"""
    nid = make(client, pid, type=t, title="置いてみる", status="adopted").json()["id"]
    assert node_of(client, pid, nid)["status"] == "open"


def test_non_string_fields_are_refused_not_crashed(client, pid):
    """N8: title/body が str でないと500になっていた。"""
    for bad in ({"type": "note", "title": 1}, {"type": "note", "title": None},
                {"type": "note", "title": {"a": 1}},
                {"type": "note", "title": "x", "body": ["list"]},
                {"type": "note", "title": "x", "body": 3}):
        r = make(client, pid, **bad)
        assert r.status_code == 400, bad
