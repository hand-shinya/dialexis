"""再開の点検の試験（2026-10-08）。

2026-10-08 の敵対的検証で実証された穴を、1件ずつ固定する。
  R2 消失が「移動」に化け、要約の異常が0件になった（沈黙する失敗・公理1）
  R3 候補の探索がscope内に限られ、Vault自体の移動を検知できなかった
  R4 hash上限超過のfileを、size一致だけで ok と断定した
  R5 記録の形が壊れていると、判断待ちの表示に辿り着く前に落ちた
  R6 記録に無いfileを出所とする命題を無言で見逃した
  R9 `--init "../"` でVAULT_ROOTの外に出られた
外部取得なし・Vaultを触らない。
"""
import json
import pathlib
import subprocess
import sys

TOOL = pathlib.Path(__file__).resolve().parents[1] / "tools" / "resume_check.py"


def run(root, *args):
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True,
                          env={"VAULT_ROOT": str(root), "PATH": "/usr/bin:/bin"})


def make_vault(tmp_path):
    root = tmp_path / "vault"
    (root / "scope").mkdir(parents=True)
    (root / "scope" / "a.md").write_text("alpha\n", encoding="utf-8")
    (root / "scope" / "b.md").write_text("beta\n", encoding="utf-8")
    return root


def doc_for(root, out):
    r = run(root, "--init", "scope", "-o", str(out))
    assert r.returncode == 0, r.stderr
    return json.loads(out.read_text(encoding="utf-8"))


def test_init_records_relative_paths_only(tmp_path):
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc = doc_for(root, out)
    assert [f["path"] for f in doc["files"]] == ["scope/a.md", "scope/b.md"]
    assert str(root) not in out.read_text(encoding="utf-8")


def test_unchanged_is_ok(tmp_path):
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc_for(root, out)
    r = run(root, str(out))
    assert "ok           未 scope/a.md" in r.stdout
    assert "missing 0" in r.stdout


def test_one_byte_change_is_changed(tmp_path):
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc_for(root, out)
    (root / "scope" / "a.md").write_text("alphA\n", encoding="utf-8")
    r = run(root, str(out))
    assert "changed" in r.stdout
    assert run(root, str(out), "--strict").returncode == 1


def test_deletion_is_not_hidden_by_a_copy_elsewhere(tmp_path):
    """R2: 同じ内容が別の場所に在っても、消失は missing のまま残す。"""
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc_for(root, out)
    (root / "elsewhere").mkdir()
    (root / "elsewhere" / "copy.md").write_text("alpha\n", encoding="utf-8")
    (root / "scope" / "a.md").unlink()
    r = run(root, str(out))
    assert "missing" in r.stdout
    assert "missing 1" in r.stdout                 # 要約で消えない
    assert "同じ内容が" in r.stdout                 # 候補は併記する
    assert run(root, str(out), "--strict").returncode == 1


def test_candidates_are_searched_outside_the_scope(tmp_path):
    """R3: scopeの外に移っても候補として見つける。"""
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc_for(root, out)
    (root / "moved_out").mkdir()
    (root / "scope" / "b.md").rename(root / "moved_out" / "b.md")
    r = run(root, str(out))
    assert "moved_out/b.md" in r.stdout


def test_missing_hash_is_unverifiable_not_ok(tmp_path):
    """R4: hashが無ければ、size一致でも ok と言わない。"""
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc = doc_for(root, out)
    doc["files"][0]["sha256"] = ""
    out.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    (root / "scope" / "a.md").write_text("XXXXX\n", encoding="utf-8")   # 同byte数
    r = run(root, str(out))
    assert "unverifiable" in r.stdout
    assert "ok 1" in r.stdout                      # b.md だけが ok


def test_broken_records_do_not_crash_and_reach_the_pending_decision(tmp_path):
    """R5: 壊れた形でも落ちず、判断待ちまで表示する。"""
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc = doc_for(root, out)
    doc["files"].append("これはobjectでない")
    doc["claims"] = "配列でない"
    doc["pending_decision"] = {"question": "次に何をするか", "due": "2026-10-22",
                               "default_path": "資料整理を続ける",
                               "options": ["資料整理", {"label": "精読"}],
                               "forbidden_while_waiting": ["新しい提案"]}
    out.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    r = run(root, str(out))
    assert r.returncode == 0
    assert "invalid" in r.stdout
    assert "判断待ち" in r.stdout and "2026-10-22" in r.stdout
    assert "既定進路" in r.stdout


def test_pending_decision_of_a_broken_shape_is_reported(tmp_path):
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc = doc_for(root, out)
    doc["pending_decision"] = "文字列"
    out.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    r = run(root, str(out))
    assert r.returncode == 0 and "壊れている" in r.stdout


def test_dangling_claims_are_surfaced(tmp_path):
    """R6: 記録に無いfileを出所とする命題を黙って見逃さない。"""
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc = doc_for(root, out)
    doc["claims"] = [{"text": "p", "source": "scope/zzz.md"}]
    out.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    r = run(root, str(out))
    assert "記録に無いfileを出所とする命題" in r.stdout


def test_read_is_computed_from_claims(tmp_path):
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc = doc_for(root, out)
    doc["claims"] = [{"text": "p", "source": "scope/a.md"}]
    out.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    r = run(root, str(out))
    assert "読 scope/a.md" in r.stdout
    assert "未読 1 file" in r.stdout


def test_init_cannot_escape_the_root(tmp_path):
    """R9: `../` でVAULT_ROOTの外に出られない。"""
    root = make_vault(tmp_path)
    (tmp_path / "outside.txt").write_text("x", encoding="utf-8")
    r = run(root, "--init", "../", "-o", str(tmp_path / "x.json"))
    assert r.returncode == 2
    assert "VAULT_ROOT" in r.stderr


def test_absolute_path_in_the_record_is_invalid(tmp_path):
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc = doc_for(root, out)
    doc["files"].append({"path": "/etc/hostname", "bytes": 1, "sha256": "x" * 64})
    out.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    r = run(root, str(out))
    assert "invalid" in r.stdout and "VAULT_ROOTの外" in r.stdout


def test_missing_vault_root_stops_without_printing_a_path(tmp_path):
    r = subprocess.run([sys.executable, str(TOOL), "--init", "scope"],
                       capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin"})
    assert r.returncode == 2
    assert "VAULT_ROOT" in r.stderr
    assert "/mnt/" not in r.stderr


# ---- 2巡目の検証（R1・R4・R7・R8）---------------------------------------

def test_nul_in_a_path_does_not_crash(tmp_path):
    """R1(d): NUL入りのpathで resolve が ValueError を投げ、1行も出さず落ちた。"""
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc = doc_for(root, out)
    doc["files"].append({"path": "scope/a\x00b.md", "bytes": 1, "sha256": "a" * 64})
    out.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    r = run(root, str(out))
    assert r.returncode == 0, r.stderr
    assert "VAULT_ROOTの外" in r.stdout
    assert "ok" in r.stdout


def test_unverifiable_counts_as_strict_failure(tmp_path):
    """R4: hashが無いまま ok と言わない以上、--strict でも素通りさせない。"""
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc = doc_for(root, out)
    doc["files"][0]["sha256"] = ""
    out.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    assert run(root, str(out)).returncode == 0
    assert run(root, str(out), "--strict").returncode == 1


def test_unreadable_file_is_unverifiable_not_changed(tmp_path):
    """R7: 読めないfileを changed と断定していた（実際は照合できていない）。"""
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc_for(root, out)
    target = root / "scope" / "a.md"
    target.chmod(0o000)
    try:
        r = run(root, str(out))
    finally:
        target.chmod(0o644)
    assert "unverifiable" in r.stdout
    assert "読めない" in r.stdout


def test_skipped_symlinks_are_counted(tmp_path):
    """R8: symlink を黙って飛ばしていた。件数を出す。"""
    root = make_vault(tmp_path)
    (root / "scope" / "link.md").symlink_to(root / "scope" / "a.md")
    out = tmp_path / "_resume.json"
    r = run(root, "--init", "scope", "-o", str(out))
    assert "symlink 1 件" in r.stdout
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["symlinks_skipped"] == 1


def test_unwritable_output_does_not_print_a_path(tmp_path):
    """R1(b): -o の書き込み失敗で絶対path入りのtracebackが出た。"""
    root = make_vault(tmp_path)
    r = run(root, "--init", "scope", "-o", str(tmp_path / "no" / "such" / "x.json"))
    assert r.returncode == 2
    assert "Traceback" not in r.stderr
    assert str(tmp_path) not in r.stderr


def test_the_record_path_is_echoed_for_dangling_claims(tmp_path):
    """同語反復の指摘への対応。見出しの語だけでなくpathを確かめる。"""
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc = doc_for(root, out)
    doc["claims"] = [{"text": "p", "source": "scope/zzz.md"}]
    out.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    r = run(root, str(out))
    assert "scope/zzz.md" in r.stdout


def test_broken_entry_is_printed_as_invalid_not_ok(tmp_path):
    """同語反復の指摘への対応。要約の `invalid 0` ではなく行とcountを見る。"""
    root = make_vault(tmp_path)
    out = tmp_path / "_resume.json"
    doc = doc_for(root, out)
    doc["files"].append("objectでない")
    out.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    r = run(root, str(out))
    assert "invalid      未 (記録が壊れている)" in r.stdout
    assert "invalid 1" in r.stdout
    assert run(root, str(out), "--strict").returncode == 1
