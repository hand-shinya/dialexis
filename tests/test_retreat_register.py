"""撤退台帳の強制（2026-10-09・schema 2）。

なぜ必要か:
  M0 §7.1 は、機構を足すときに期日・観測点・撤退条件の三つを要求する。
  2026-10-08 に関門12本と道具1本が増えたが、どれにも期日が無かった。
  仕様書 §12.12 はそれを欠陥として記述したが、記述は実行ではない（M0 C3）。

初版（schema 1）が破られた経路（2026-10-09 の敵対的検証・すべて実証済み）:
  1. 全欄を無意味な文字列で埋めて12試験すべて通った。
     `retreat = "この機構は削除しない"` が「削除」を含むので通った。
     `how_to_measure` は20字以上という長さだけ、`observation` は非空だけだった。
  2. `deadline = "2099-01-01"` で判定が永久に来なかった（上限が無かった）。
  3. 期日超過の項を、code を残したまま台帳から1行消すだけで通った。
  4. 項を [[correction]] に札替えすると、期日の要求が消えた。
  5. 台帳に書かれた機構が code に在るかは未検査。架空の機構を書いて通った。
  6. code に機構を足して台帳に書かない経路は完全に無強制だった（328 passed）。
  7. この試験file自身を消すと、静かに全部通った（315 passed・rc=0）。
  8. `date.today()` が機械のTZを見るため、同じ台帳が UTC では1日ゆるかった。
  9. `verdict` は「続ける」「.」の1語で通った。根拠も実測値も要求されなかった。
 10. `verdict_date` は 1970 でも 2099 でも通った。

この版が閉じたもの / 閉じていないもの:
  閉じた   上の 1,2,3(git比較),4,5,6(expected_tests),7(expected_tests),8,9,10
  閉じない 台帳の記述が事実かどうか（公理7）。期日前に知らせる経路。
           「機構」の機械的な定義。初回 commit までは git 比較ができない。

外部取得なし・Vaultを触らない。
"""
import datetime
import pathlib
import re
import subprocess
import tomllib
import zoneinfo

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
REL = "governance/retreat_register.toml"
REGISTER = ROOT / REL

REQUIRED_MECH = ("id", "added", "what", "cost", "implemented_by", "deadline",
                 "observation", "observation_threshold", "how_to_measure", "retreat",
                 "status", "observed", "evidence", "verdict", "verdict_date",
                 "retired_at", "retired_commit")
REQUIRED_CORR = ("id", "fixed", "what", "how_fixed", "guarded_by")
STATUSES = ("open", "continued", "retired")

# 「観察を継続する」類は期日でも撤退でもない（M0 §7.1 の逐語）。
NOT_A_RETREAT = ("観察を継続", "観察する", "保留", "様子を見", "無効化して残置",
                 "baseline の取り直し", "baselineの取り初し", "baselineの取り直し",
                 "とりあえず", "当面", "いまのところ", "今のところ")
# 撤退条件に「消す」と書きながら否定するのを拒む。初版は「削除しない」が通った。
REMOVAL_VERBS = ("削除", "除去", "外す", "減らす", "消す")
NEGATED_REMOVAL = re.compile(
    r"(削除|除去|消去)(は)?(しない|せず|されない|しません)"
    r"|(外さない|減らさない|消さない|残置|維持する|そのまま残す)")


def load():
    assert REGISTER.exists(), "撤退台帳が無い: " + REL
    return tomllib.loads(REGISTER.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def doc():
    return load()


def as_date(value, where):
    """読める形で落とす。初版は ValueError の生traceback で落ちていた。"""
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError as e:
        pytest.fail("{}: 日付として読めない {!r}（{}）".format(where, value, e))


def today(doc):
    tz = doc.get("timezone") or ""
    assert tz, "timezone が無い。date.today() は機械のTZを見るので、同じ台帳が機械ごとに違う結果になる"
    return datetime.datetime.now(zoneinfo.ZoneInfo(tz)).date()


# ---- 形 -------------------------------------------------------------------

def test_the_register_parses_and_declares_schema_2(doc):
    assert doc.get("schema_version") == 2
    assert str(doc.get("updated") or "").strip()
    as_date(doc["updated"], "updated")


def test_the_timezone_is_fixed_not_inherited_from_the_machine(doc):
    """同じ commit が UTC の機械で1日ゆるくなる穴を塞ぐ。"""
    tz = doc.get("timezone")
    assert tz == "Asia/Tokyo", "時刻帯を固定する（実測: JST 2026-10-09 / UTC 2026-10-08）"
    zoneinfo.ZoneInfo(tz)


def test_there_is_at_least_one_mechanism(doc):
    assert doc.get("mechanism"), "mechanism が0件。機構を足したなら必ず1項を書く"


def test_every_mechanism_has_all_required_fields(doc):
    for m in doc["mechanism"]:
        missing = [k for k in REQUIRED_MECH if k not in m]
        assert not missing, "{}: 欄が足りない {}".format(m.get("id", "?"), missing)
        for k in ("id", "added", "what", "cost", "deadline", "observation",
                  "observation_threshold", "how_to_measure", "retreat", "status"):
            assert str(m[k]).strip(), "{}: {} が空".format(m["id"], k)


def test_status_is_one_of_the_three_values(doc):
    for m in doc["mechanism"]:
        assert m["status"] in STATUSES, \
            "{}: status は {} のいずれか（{!r} ではない）".format(m["id"], STATUSES, m["status"])


def test_ids_are_unique_across_both_sections(doc):
    """初版は項を [[correction]] に札替えすると期日の要求が消えた。"""
    mech = [m["id"] for m in doc["mechanism"]]
    corr = [c["id"] for c in doc.get("correction", [])]
    assert len(mech) == len(set(mech)), "mechanism の id 重複: {}".format(mech)
    assert len(corr) == len(set(corr)), "correction の id 重複: {}".format(corr)
    both = set(mech) & set(corr)
    assert not both, "同じ id が両方の節に在る（札替えの経路）: {}".format(sorted(both))


# ---- 期日 -----------------------------------------------------------------

def test_dates_are_real_and_the_horizon_is_capped(doc):
    """初版は deadline=2099-01-01 で判定が永久に来なかった。"""
    cap = doc.get("max_horizon_days")
    assert isinstance(cap, int) and 0 < cap <= 180, \
        "max_horizon_days を 1〜180 の整数で置く（上限が無いと遠い未来へ逃げられる）"
    for m in doc["mechanism"]:
        added = as_date(m["added"], m["id"] + ".added")
        due = as_date(m["deadline"], m["id"] + ".deadline")
        assert due >= added, "{}: 期日が追加日より前".format(m["id"])
        span = (due - added).days
        assert span <= cap, \
            "{}: 期日が追加日から {}日先（上限 {}日）".format(m["id"], span, cap)


def test_retreat_says_what_is_removed_and_does_not_negate_it(doc):
    """初版は `retreat = "この機構は削除しない"` が通った。"""
    for m in doc["mechanism"]:
        text = str(m["retreat"])
        bad = [w for w in NOT_A_RETREAT if w in text]
        assert not bad, "{}: 撤退条件が撤退になっていない（{}）".format(m["id"], bad)
        assert any(v in text for v in REMOVAL_VERBS), \
            "{}: 撤退条件に、何を消すのかが書かれていない".format(m["id"])
        neg = NEGATED_REMOVAL.search(text)
        assert not neg, \
            "{}: 撤退条件が消すことを否定している（{!r}）".format(m["id"], neg.group(0))


def test_how_to_measure_names_a_command_or_a_path(doc):
    """初版は『あ』20字で通った。長さではなく、走らせられる形を求める。"""
    runnable = ("curl", "python", "pytest", "grep", "git", "ls", "wc", "sqlite3",
                "node", "tools/", "tests/", "governance/", "app/", "/api/")
    for m in doc["mechanism"]:
        how = str(m["how_to_measure"])
        assert any(k in how for k in runnable), \
            "{}: 測り方に、実際に走らせるもの（コマンドかpath）が無い: {!r}".format(m["id"], how)


def test_the_threshold_contains_a_number(doc):
    """『うまくいっているとよい』は観測点ではない。閾値に数を求める。"""
    for m in doc["mechanism"]:
        th = str(m["observation_threshold"])
        assert re.search(r"\d", th), \
            "{}: 観測点の閾値に数が無い: {!r}".format(m["id"], th)


# ---- 台帳と実装の対応 -----------------------------------------------------

def test_every_mechanism_points_at_code_that_exists(doc):
    """初版は架空の機構 quantum-flux-gate を書いて通った。"""
    for m in doc["mechanism"]:
        refs = m["implemented_by"]
        assert isinstance(refs, list) and refs, "{}: implemented_by が空".format(m["id"])
        for ref in refs:
            path, _, symbol = str(ref).partition(":")
            f = ROOT / path
            assert f.exists(), "{}: 実装が存在しない {}".format(m["id"], path)
            if symbol:
                assert symbol in f.read_text(encoding="utf-8"), \
                    "{}: {} に {} が無い".format(m["id"], path, symbol)


def test_the_test_files_on_disk_match_the_register_exactly(doc):
    """二つの穴を同時に塞ぐ。

    (a) 期日に落ちたとき、この試験fileを消して黙らせる経路（初版では 315 passed で通った）
    (b) 機構を足して台帳に書かない経路（初版では完全に無強制だった）
    新しい関門はほぼ必ず新しい試験fileを伴うので、集合の不一致で検出する。
    """
    listed = set(doc.get("expected_tests") or [])
    assert listed, "expected_tests が空"
    on_disk = {str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("test_*.py")}
    only_disk = sorted(on_disk - listed)
    only_list = sorted(listed - on_disk)
    assert not only_disk, (
        "台帳に無い試験fileが在る（機構を足して台帳に書いていない可能性）: "
        + ", ".join(only_disk) + "\nexpected_tests に足すこと")
    assert not only_list, (
        "台帳に在る試験fileがdiskに無い（消して黙らせた可能性）: "
        + ", ".join(only_list) + "\n消したなら expected_tests からも消すこと")


def test_the_register_and_this_test_are_tracked_in_git(doc):
    """未追跡だと、公式配備経路（vps_update.sh の差分検査・VPS側のpytest）に映らない。

    2026-10-09 時点で両fileは未追跡であり、「試験が落ちると deploy が止まる」は
    台帳を持つ手元で verify.sh を走らせた場合に限って成立していた。
    """
    for rel in (REL, "tests/test_retreat_register.py"):
        r = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                           cwd=ROOT, capture_output=True, text=True)
        assert r.returncode == 0, \
            "{} が git に追跡されていない。配備経路がこのfileを知らない".format(rel)


def test_no_mechanism_disappears_without_being_retired(doc):
    """初版は、期日超過の項を code を残したまま1行消すだけで通った。

    git の HEAD 版と id 集合を比べる。消えた id が在れば、
    その id は HEAD 側で status=retired になっていなければならない。
    台帳が HEAD に無い間（初回 commit まで）は比較できない。そこは未強制である。
    """
    r = subprocess.run(["git", "show", "HEAD:" + REL],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("台帳が HEAD に無い（初回 commit 前）。この経路は未強制である")
    prev = tomllib.loads(r.stdout)
    prev_mech = {m["id"]: m for m in prev.get("mechanism", [])}
    now_ids = {m["id"] for m in doc["mechanism"]}
    gone = [i for i in prev_mech if i not in now_ids]
    bad = [i for i in gone if str(prev_mech[i].get("status", "")) != "retired"]
    assert not bad, (
        "撤退していない機構が台帳から消えている: " + ", ".join(sorted(bad))
        + "\n撤退したなら status=\"retired\" と retired_at を書いた行を残すこと")


# ---- 判定 -----------------------------------------------------------------

def test_an_expired_mechanism_must_be_retired_or_continued_with_evidence(doc):
    """これがこの試験の本体である。

    期日を過ぎた機構は、次のどちらかでなければ落ちる。
      retired   その機構を消し、retired_at を書く（行は残す）
      continued observed（実測値）・evidence（出所）・verdict（根拠）・verdict_date を書く
    初版は verdict に「続ける」「.」と1語書けば通った。ここを閉じる。
    """
    td = today(doc)
    problems = []
    for m in doc["mechanism"]:
        due = as_date(m["deadline"], m["id"] + ".deadline")
        if td <= due:
            continue
        over = (td - due).days
        st = m["status"]
        if st == "open":
            problems.append("{}（期日 {}・{}日超過・status=open）".format(m["id"], m["deadline"], over))
        elif st == "retired":
            if not str(m.get("retired_at", "")).strip():
                problems.append("{}: retired なのに retired_at が空".format(m["id"]))
        elif st == "continued":
            for k in ("observed", "evidence", "verdict", "verdict_date"):
                if not str(m.get(k, "")).strip():
                    problems.append("{}: continued なのに {} が空".format(m["id"], k))
            if len(str(m.get("verdict", "")).strip()) < 20:
                problems.append("{}: 続ける根拠が20字未満（1語では通らない）".format(m["id"]))
    assert not problems, (
        "期日の処理が済んでいない: " + " / ".join(problems)
        + "\n直し方: (a) 機構を消して status=\"retired\" と retired_at を書く"
          " (b) status=\"continued\" にして observed・evidence・verdict・verdict_date を書く。"
          "『観察を継続する』『保留』『とりあえず置く』は (b) ではない（M0 §7.1）。")


def test_a_verdict_is_dated_within_a_sane_range(doc):
    """初版は verdict_date が 1970 でも 2099 でも通った。"""
    td = today(doc)
    for m in doc["mechanism"]:
        if not str(m.get("verdict", "")).strip():
            continue
        added = as_date(m["added"], m["id"] + ".added")
        vd_raw = str(m.get("verdict_date", "")).strip()
        assert vd_raw, "{}: 判定が在るのに日付が無い".format(m["id"])
        vd = as_date(vd_raw, m["id"] + ".verdict_date")
        assert added <= vd <= td, \
            "{}: 判定日が範囲外（{} ≦ {} ≦ {} でない）".format(m["id"], added, vd, td)
        bad = [w for w in NOT_A_RETREAT if w in str(m["verdict"])]
        assert not bad, "{}: 判定が判定になっていない（{}）".format(m["id"], bad)


def test_a_retired_mechanism_is_dated_and_keeps_its_row(doc):
    td = today(doc)
    for m in doc["mechanism"]:
        if m["status"] != "retired":
            continue
        added = as_date(m["added"], m["id"] + ".added")
        ra = as_date(m["retired_at"], m["id"] + ".retired_at")
        assert added <= ra <= td, "{}: 撤退日が範囲外".format(m["id"])


# ---- 訂正 -----------------------------------------------------------------

def test_every_correction_names_a_test_that_actually_has_tests(doc):
    """初版は guarded_by が `app/db.py` でも `.` でも通った。"""
    for c in doc.get("correction", []):
        missing = [k for k in REQUIRED_CORR if k not in c]
        assert not missing, "{}: 欄が足りない {}".format(c.get("id", "?"), missing)
        as_date(c["fixed"], c["id"] + ".fixed")
        guard = str(c["guarded_by"])
        assert re.fullmatch(r"tests/test_[A-Za-z0-9_]+\.py", guard), \
            "{}: guarded_by は tests/test_*.py でなければならない（{!r}）".format(c["id"], guard)
        f = ROOT / guard
        assert f.exists(), "{}: 守る試験が存在しない {}".format(c["id"], guard)
        body = f.read_text(encoding="utf-8")
        assert body.count("def test_") >= 1, \
            "{}: {} に試験関数が無い".format(c["id"], guard)
        assert guard in (doc.get("expected_tests") or []), \
            "{}: {} が expected_tests に無い（消しても気づけない）".format(c["id"], guard)


# ---- 自己適用 -------------------------------------------------------------

def test_the_register_applies_to_itself(doc):
    """自分に適用しない規範は、他に適用する資格を持たない（M0 §7.1 の自己適用）。"""
    ids = [m["id"] for m in doc["mechanism"]]
    assert "retreat-register" in ids, \
        "台帳自身が台帳に載っていない。この試験もまた撤退の対象である"
    me = [m for m in doc["mechanism"] if m["id"] == "retreat-register"][0]
    # 自己検証の輪を避ける: 自分の観測点を「判定が書かれたこと」にすると、
    # 1語書くだけで自分を延命できる。実際に撤退が起きたことに限る。
    assert "retired" in str(me["observation"]), \
        "台帳自身の観測点は『実際に撤退が起きたこと』でなければ、自分を延命する輪になる"


def test_the_unclosed_holes_are_written_down(doc):
    """塞げていない穴を書かないことは、塞いだと言うことと同じ害を持つ（公理3）。

    初版のこの試験は「閉じていない穴」という語の存在だけを見ていた。
    冒頭の説明文にも同じ語が在るので、節ごと消しても通った（2026-10-09 に実証）。
    穴の番号を要求する形に替える。
    """
    text = REGISTER.read_text(encoding="utf-8")
    assert "# 閉じていない穴" in text, "塞げていない穴の節が無い"
    for tag in ("U1", "U2", "U3", "U4"):
        assert tag in text, "塞げていない穴 {} の記述が無い".format(tag)
    assert "足場" in text, "この機構は §7.1 の外部強制そのものではない。そう名乗らないこと"
