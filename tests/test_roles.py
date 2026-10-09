"""所有者と利用者を取り違えないための関門（2026-10-09）。

半田様の指摘（逐語の要点）:
  半田様がこの system を構築し開発しているのは事実だが、最終的には cloud 上の
  実装を半田様以外の人間が利用者として使う。
  したがって「半田様」という名前と利用者を同一視してはいけない。
  半田様も利用者の1人として使い、試験し、開発をその立場で見ることはするが、
  それと「半田様以外の人間が単なる利用者として利用する」立場は別のものである。

分けるべき3つの役割:
  所有者・開発者（半田様）  設計を決める。採否を決める。撤退を決める。運用の費用を負う
  利用者（誰でも）          自分の文を書く。押す。自分の環境で実行する。自分の判断を記録する
  この system                文を組む。取得する。記録する。送信はしない

この関門が守ること:
  利用者に届く出力（描画されたHTMLと、API が返す本文）に「半田様」が入らないこと。

この関門が守らないこと（公理3）:
  code のコメントや docstring の「半田様の設計」「半田様の決裁」は**帰属の記録**であり、
  利用者と混同していないので、ここでは検査しない。消すと誰が決めたか分からなくなる。
  また、利用者の目的・負担・権利を記した文書がまだ無いことは直せない（台帳 U13）。

なぜ grep ではなく描画と payload を見るか:
  template の Jinja コメント（{# … #}）は描画されない。source を grep すると、
  帰属の記録まで違反として挙がる。**利用者に届くかどうかが基準**である。

外部取得なし。
"""
import pathlib

import pytest
from fastapi.testclient import TestClient

from app import handoff
from app.main import app

ROOT = pathlib.Path(__file__).resolve().parents[1]
OWNER = "半田"

# 利用者が開く画面。描画後の本文を見る。
PAGES = ["/", "/origin", "/explore", "/desk", "/deepsearch", "/word", "/wordspace",
         "/textscan", "/inquiry", "/validation", "/settings", "/donate", "/levels",
         "/about", "/watches", "/ledger"]


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.mark.parametrize("path", PAGES)
def test_no_page_shows_the_owner_name(client, path):
    """利用者が開く画面に所有者の名を出さない。"""
    r = client.get(path)
    if r.status_code != 200:
        pytest.skip("%s は %d を返す（この試験の対象外）" % (path, r.status_code))
    assert OWNER not in r.text, "%s に所有者の名が描画されている" % path


def test_the_handoff_text_never_carries_the_owner_name():
    """持ち出す文は利用者が外部へ貼るものなので、最も害が大きい。"""
    shapes = [
        {"term": "理性"},
        {"term": "理性", "text": "「理性」と「感性」の違いが気になっています。"},
        {"term": "非有機的肉体", "text": "x",
         "receipts": [{"layer": "L", "query_sent": "q", "count": 0,
                       "retrieved_at": "t", "zero_means": "z"}],
         "sources": [{"title": "T", "url": "u", "note": "n", "licence": "CC0"}],
         "records": [{"type": "provisional", "title": "暫定", "body": "本体"},
                     {"type": "memory", "title": "記憶"},
                     {"type": "naming", "title": "命名"}]},
    ]
    for kw in shapes:
        d = handoff.build(**kw)
        assert OWNER not in d["prompt"], kw
        assert OWNER not in d["responsibility"], kw
        assert OWNER not in " ".join(d["contains"]), kw
        assert OWNER not in " ".join(d["omitted"]), kw
        assert OWNER not in d["licence_note"], kw


def test_the_handoff_endpoint_output_carries_no_owner_name(client):
    r = client.post("/api/handoff", json={"term": "理性", "text": "「感性」とは何か。"})
    assert r.status_code == 200
    assert OWNER not in r.text


def test_the_inquiry_output_carries_no_owner_name(client):
    r = client.post("/api/inquiry", json={"text": "「理性」と「感性」の違い。"})
    assert r.status_code == 200
    assert OWNER not in r.text


def test_the_human_record_block_is_attributed_to_whoever_wrote_it():
    """人の判断の欄は、その workspace の利用者のものである（半田様のものではない）。"""
    d = handoff.build(term="x", records=[{"type": "memory", "title": "記憶している"}])
    assert "私自身が書いた判断" in d["prompt"]
    assert "これは私の判断であり" in d["prompt"]
    assert OWNER not in d["prompt"]


def test_the_responsibility_is_addressed_to_the_reader():
    d = handoff.build(term="x", text="y")
    assert "あなたの環境と責任" in d["responsibility"]
    assert "あなたが確かめてください" in d["responsibility"]


def test_the_role_distinction_is_written_down_where_it_is_decided():
    """消えると、次に触る者が同じ取り違えをする。"""
    src = (ROOT / "app" / "handoff.py").read_text(encoding="utf-8")
    assert "役割の区別" in src
    assert "利用者は半田様とは別の人である" in src
    reg = (ROOT / "governance" / "retreat_register.toml").read_text(encoding="utf-8")
    assert "U13" in reg
    assert "役割の混同" in reg


def test_the_unwritten_document_is_declared_not_claimed_done():
    """利用者の目的・負担・権利を記した文書はまだ無い。無いと書く（公理3）。"""
    reg = (ROOT / "governance" / "retreat_register.toml").read_text(encoding="utf-8")
    assert "利用者の目的・負担・権利を記した文書はまだ無い" in reg
