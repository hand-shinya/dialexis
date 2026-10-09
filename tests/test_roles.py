"""所有者の名前が利用者に届かないことの関門（2026-10-09）。

所有者の指示（逐語の要点）:
  最も重要なのは、実装されたときに所有者の名が一切出ないこと。
  利用者から見て所有者の名が見えてはいけない。知ってはいけない。
  将来許可した場合に出す可能性はあるが、現時点では一切ない。

なぜ「コメントだから無害」が誤りだったか:
  `app/static/app.js` は StaticFiles で browser へ**そのまま配信される**。
  利用者が `/static/app.js` を開けば、JSのコメントを全部読める（実測40箇所）。
  `app/static/style.css` も同じ（2箇所）。
  さらに endpoint の docstring は FastAPI が `/openapi.json` と `/docs` に出す
  （`app/main.py` に11箇所）。
  2026-10-09 に「40件は全てコメントなので描画されない」と報告したのは誤りだった。
  基準は描画の有無ではなく**配信の有無**である。

この試験が名前そのものを持たない理由:
  「名前が無いこと」を検査する試験が名前を literal で持つと、
  その試験fileが名前を repository へ持ち込む（この file も公開repoに入る）。
  したがって符号位置から組み立て、source に読める形で置かない。

分けるべき3つの役割:
  所有者・開発者  設計を決める。採否を決める。撤退を決める。運用の費用を負う
  利用者（誰でも） 自分の文を書く。押す。自分の環境で実行する。自分の判断を記録する
  この system      文を組む。取得する。記録する。送信はしない

この関門が守らないこと（公理3）:
  git の履歴とcommitの文には名前が残っている。書き換えには履歴の改変が要る。
  公開repoのURL（owner名を含む）と、AGPL-3.0 が要求する source の提示も残る。
  いずれも所有者の決裁が要るので、ここでは検査しない（台帳 U14）。

外部取得なし。
"""
import pathlib

import pytest
from fastapi.testclient import TestClient

from app import handoff
from app.main import app

ROOT = pathlib.Path(__file__).resolve().parents[1]

# 符号位置から組む。source に読める形で名前を置かない。
NAME = chr(0x534A) + chr(0x7530)                       # 姓
GIVEN = chr(0x4FE1) + chr(0x5F25)                      # 名の表記候補
FORBIDDEN = (NAME, NAME + chr(0x6A23), GIVEN)

# 利用者が browser で取得できるもの。配信されるなら中身は全部読める。
SERVED = ["/static/app.js", "/static/style.css", "/static/favicon.svg",
          "/openapi.json", "/docs"]

PAGES = ["/", "/origin", "/explore", "/desk", "/deepsearch", "/word", "/wordspace",
         "/textscan", "/inquiry", "/validation", "/settings", "/donate", "/levels",
         "/about", "/watches", "/source"]

# 名前が docstring 経由で openapi へ漏れる。source も検査の対象に入れる。
SOURCE_DIRS = ["app", "tools", "tests", "governance", "deploy", "docs"]


@pytest.fixture()
def client():
    return TestClient(app)


def hits(text):
    return [f for f in FORBIDDEN if f in text]


# ===========================================================================
# 配信されるもの
# ===========================================================================

@pytest.mark.parametrize("path", SERVED)
def test_nothing_served_to_the_browser_contains_the_name(client, path):
    """配信されるなら、コメントも含めて利用者が読める。"""
    r = client.get(path)
    if r.status_code != 200:
        pytest.skip("%s は %d を返す" % (path, r.status_code))
    assert not hits(r.text), "%s に名前が入っている" % path


@pytest.mark.parametrize("path", PAGES)
def test_no_page_contains_the_name(client, path):
    r = client.get(path)
    if r.status_code != 200:
        pytest.skip("%s は %d を返す" % (path, r.status_code))
    assert not hits(r.text), "%s に名前が入っている" % path


def test_the_openapi_description_does_not_leak_docstrings_with_the_name(client):
    """endpoint の docstring は /openapi.json の description に出る。"""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert not hits(r.text)


# ===========================================================================
# API が返す本文
# ===========================================================================

def test_the_handoff_text_never_carries_the_name():
    """持ち出す文は利用者が外部のAIへ貼るものなので、最も害が大きい。"""
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
        for field in ("prompt", "responsibility", "licence_note"):
            assert not hits(d[field]), (field, kw)
        assert not hits(" ".join(d["contains"])), kw
        assert not hits(" ".join(d["omitted"])), kw


@pytest.mark.parametrize("path,body", [
    ("/api/handoff", {"term": "理性", "text": "「感性」とは何か。"}),
    ("/api/inquiry", {"text": "「理性」と「感性」の違い。"}),
])
def test_api_responses_do_not_carry_the_name(client, path, body):
    r = client.post(path, json=body)
    assert r.status_code == 200
    assert not hits(r.text)


def test_error_messages_do_not_carry_the_name(client):
    for path, body in (("/api/handoff", {}), ("/api/inquiry", {"text": " "})):
        r = client.post(path, json=body)
        assert r.status_code == 400
        assert not hits(r.text)


# ===========================================================================
# source（docstring が openapi へ出るので、ここも対象にする）
# ===========================================================================

@pytest.mark.parametrize("d", SOURCE_DIRS)
def test_no_source_file_contains_the_name(d):
    base = ROOT / d
    if not base.exists():
        pytest.skip("%s が無い" % d)
    bad = []
    for p in base.rglob("*"):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if hits(t):
            bad.append(str(p.relative_to(ROOT)))
    assert not bad, "名前が残っている: " + ", ".join(sorted(bad))


def test_the_repository_root_files_do_not_contain_the_name():
    bad = []
    for p in ROOT.glob("*"):
        if not p.is_file() or p.name.startswith("ans"):
            continue        # ans*.md は所有者への報告で、git 未追跡である
        try:
            t = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if hits(t):
            bad.append(p.name)
    assert not bad, "名前が残っている: " + ", ".join(sorted(bad))


# ===========================================================================
# 役割の区別そのもの（名前を消しても、区別が消えてはいけない）
# ===========================================================================

# ===========================================================================
# UIから名前へ到達する経路（配信される中身に名前が無いだけでは足りない）
# ===========================================================================

@pytest.mark.parametrize("path", PAGES)
def test_no_page_links_to_the_public_repository(client, path):
    """公開repoのURLには所有者のaccount名が含まれ、辿れば履歴から名前に着く。

    2026-10-09 の実測で、footer が repo へ link しており、account名に
    名の romaji 表記が入っていた。1click で名前に到達できた。
    """
    r = client.get(path)
    if r.status_code != 200:
        pytest.skip("%s は %d を返す" % (path, r.status_code))
    for host in ("github.com", "gitlab.com", "bitbucket.org"):
        assert host not in r.text, "%s が %s へ link している" % (path, host)


def test_the_source_is_still_offered(client):
    """AGPL-3.0 は network 越しの利用者へ source の提示を要求する。

    link を外した代わりに、ここから配る。提示そのものを外してはならない。
    """
    assert client.get("/source").status_code == 200
    r = client.get("/source/dialexis-source.tar.gz")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/gzip"
    assert len(r.content) > 100_000


def test_the_archive_carries_no_name_and_no_history(client):
    """配る snapshot に名前も履歴も入っていないことを、中身を開いて確かめる。"""
    import io
    import tarfile
    r = client.get("/source/dialexis-source.tar.gz")
    assert r.status_code == 200
    tf = tarfile.open(fileobj=io.BytesIO(r.content))
    names = tf.getnames()
    assert names
    assert not any("/.git/" in n for n in names), "履歴が入っている"
    assert any(n.endswith("LICENSE") or "COPYING" in n for n in names), "licence が無い"
    bad = []
    for m in tf.getmembers():
        if not m.isfile() or m.size > 2_000_000:
            continue
        f = tf.extractfile(m)
        if f is None:
            continue
        try:
            t = f.read().decode("utf-8")
        except UnicodeDecodeError:
            continue
        if hits(t):
            bad.append(m.name)
    assert not bad, "配る snapshot に名前が残っている: " + ", ".join(sorted(bad)[:5])


def test_the_responsibility_is_addressed_to_the_reader():
    d = handoff.build(term="x", text="y")
    assert "あなたの環境と責任" in d["responsibility"]
    assert "あなたが確かめてください" in d["responsibility"]
    assert "送信しません" in d["responsibility"]


def test_the_human_record_block_is_attributed_to_whoever_wrote_it():
    """人の判断の欄は、その workspace の利用者のものである。"""
    d = handoff.build(term="x", records=[{"type": "memory", "title": "記憶している"}])
    assert "私自身が書いた判断" in d["prompt"]
    assert "これは私の判断であり" in d["prompt"]


def test_the_role_distinction_survives_the_name_removal():
    """名前を消した結果、誰と誰を分けるのかが読めなくなっては意味が無い。"""
    src = (ROOT / "app" / "handoff.py").read_text(encoding="utf-8")
    assert "役割の区別" in src
    assert "利用者は所有者とは別の人である" in src
    reg = (ROOT / "governance" / "retreat_register.toml").read_text(encoding="utf-8")
    assert "U13" in reg and "役割の混同" in reg


def test_what_cannot_be_removed_here_is_written_down():
    """git 履歴・公開repoのURL・AGPL の source 提示は、この関門では直せない。"""
    reg = (ROOT / "governance" / "retreat_register.toml").read_text(encoding="utf-8")
    assert "U14" in reg
    assert "git の履歴" in reg
    assert "AGPL" in reg
