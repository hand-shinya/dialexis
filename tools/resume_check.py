#!/usr/bin/env python3
"""中断から壊れずに再開するための点検。

なぜ必要か（2026-10-08 に実地で確認した事実）:
  半田様の「非有機的肉体」研究の再開guide（2026-05-03 作成）は
  `/mnt/g/マイドライブ/MyKnowledgeBase/...` を絶対pathで指していた。
  Vaultが `/mnt/i/GoogleDriveMirror/MyKnowledgeBase/...` へ移った時点で、
  **再開の手段ごと壊れた**。4か月後の第2世代はWSL pathとWindows pathを併記したが、
  それは修正ではなく保守の負担を2倍にしただけだった。

この道具がやること:
  - path を root からの**相対**で持つ。root は環境変数 `VAULT_ROOT` が与える。
  - 各fileの `bytes` と `sha256` を記録し、次の起動時に照合する。
  - 結果を5状態で印字する。`ok` / `changed` / `missing` / `unverifiable` /
    `invalid`（記録の形が壊れている）。
    **`missing` を他の状態に隠さない。** 同じ内容のfileが別の場所に在る場合は、
    `missing` のまま候補を併記する（2026-10-08 の検証で、消失が移動に化けて
    要約の異常が0件になる沈黙が実証されたため）。
  - 未読を算出する。手で保守するlistは腐る（第2世代の未読listは4か月更新されず、
    載っていた9本のうち6本が未読のまま残った）。
    読了の定義は「そのfileを出所とする命題が1件以上あること」である。

やらないこと:
  - 止めない。欠落や未読が在っても exit 0 を返す（`--strict` のときだけ 1）。
    止める設計は、守られて本体が4か月進まなかった前例がある。
  - 人に入力を求めない。`_resume.json` を作るのもこの道具である（`--init`）。
  - 絶対pathを出さない。rootは `$VAULT_ROOT` と表示する。

使い方:
    VAULT_ROOT=/path/to/vault python3 tools/resume_check.py --init "Main/論考/X" -o _resume.json
    VAULT_ROOT=/path/to/vault python3 tools/resume_check.py _resume.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
import time

SCHEMA = "dialexis.resume.v1"
STATES = ("ok", "changed", "missing", "unverifiable", "invalid")
CANDIDATE_LIMIT = 5
DEFAULT_MAX_HASH_BYTES = 32 * 1024 * 1024


def die(msg: str) -> None:
    """絶対pathを出さずに止める。"""
    sys.stderr.write(msg + "\n")
    raise SystemExit(2)


def vault_root() -> pathlib.Path:
    root = os.environ.get("VAULT_ROOT")
    if not root:
        die("VAULT_ROOT が設定されていない。root を環境変数で与えること"
            "（fileに絶対pathを書かないため）")
    p = pathlib.Path(root)
    if not p.is_dir():
        die("VAULT_ROOT が存在しない（値はfileに書かない）")
    return p.resolve()


def safe_join(root: pathlib.Path, rel: str):
    """rootの外へ出るpathを拒む。絶対path・`..`・symlink脱出を止める。"""
    if not isinstance(rel, str) or not rel or rel.startswith(("/", "\\")):
        return None
    if pathlib.PurePosixPath(rel).is_absolute() or ".." in pathlib.PurePosixPath(rel).parts:
        return None
    try:
        p = (root / rel)
        resolved = p.resolve()
    except (OSError, ValueError):
        # NUL入りのpathは resolve が ValueError を投げる（2026-10-08 実測）。
        return None
    if root not in resolved.parents and resolved != root:
        return None
    return p


def sha256_of(path: pathlib.Path):
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def init(root: pathlib.Path, rel_dir: str, max_bytes: int) -> dict:
    base = safe_join(root, rel_dir)
    if base is None or not base.is_dir():
        die("対象folderが無い、またはVAULT_ROOTの外を指している")
    files, skipped = [], 0
    for p in sorted(base.rglob("*")):
        if p.is_symlink():
            skipped += 1
            continue
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        size = p.stat().st_size
        entry = {"path": rel, "bytes": size}
        if size <= max_bytes:
            entry["sha256"] = sha256_of(p) or ""
        else:
            entry["sha256"] = ""
            entry["hash_skipped_bytes"] = max_bytes
        files.append(entry)
    return {"schema": SCHEMA, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "scope": rel_dir, "files": files, "claims": [],
            "symlinks_skipped": skipped,
            "pending_decision": None,
            "note": "pathはVAULT_ROOTからの相対である。絶対pathを書かないこと。"}


def _hash_index(root: pathlib.Path, max_bytes: int) -> dict:
    """VAULT_ROOT全体から同じ内容のfileを探す索引。

    scope内だけを見ると、この道具が作られた理由（Vault自体やfolderの移動）を
    検知できない。全体を見るが、hashを取る上限は呼び出し側と同じ値を使う。
    """
    out = {}
    for p in root.rglob("*"):
        if not p.is_file() or p.is_symlink():
            continue
        try:
            if p.stat().st_size > max_bytes:
                continue
        except OSError:
            continue
        h = sha256_of(p)
        if h:
            out.setdefault(h, []).append(p.relative_to(root).as_posix())
    return out


def check(root: pathlib.Path, doc, max_bytes: int) -> dict:
    if not isinstance(doc, dict):
        return {"fatal": "記録の最上位がobjectでない"}
    raw_files = doc.get("files")
    if not isinstance(raw_files, list):
        return {"fatal": "files が配列でない"}
    raw_claims = doc.get("claims")
    claims = [c for c in raw_claims if isinstance(c, dict)] \
        if isinstance(raw_claims, list) else []
    known = set()
    rows, hash_index = [], None
    for f in raw_files:
        if not isinstance(f, dict) or not isinstance(f.get("path"), str):
            rows.append({"path": "(記録が壊れている)", "bytes": 0, "state": "invalid"})
            continue
        rel = f["path"]
        known.add(rel)
        size_rec = f.get("bytes")
        hash_rec = f.get("sha256") if isinstance(f.get("sha256"), str) else ""
        p = safe_join(root, rel)
        row = {"path": rel, "bytes": size_rec if isinstance(size_rec, int) else 0}
        if p is None:
            row["state"] = "invalid"
            row["note"] = "VAULT_ROOTの外を指している"
            rows.append(row)
            continue
        if not p.is_file():
            row["state"] = "missing"
            if hash_rec:
                if hash_index is None:
                    hash_index = _hash_index(root, max_bytes)
                cand = [x for x in hash_index.get(hash_rec, []) if x != rel]
                if cand:
                    # missing のまま候補を併記する。状態を上書きしない。
                    row["same_hash_elsewhere"] = cand[:CANDIDATE_LIMIT]
            rows.append(row)
            continue
        size_now = p.stat().st_size
        if not hash_rec:
            # hashが無ければ、一致は主張できない。sizeだけでokと言わない。
            row["state"] = "unverifiable"
            row["note"] = ("hashが記録されていない（上限超過か記録漏れ）。"
                           "size {} -> {}".format(size_rec, size_now))
            rows.append(row)
            continue
        got = sha256_of(p)
        if got is None:
            row["state"] = "unverifiable"
            row["note"] = "fileを読めないため照合できていない"
        else:
            row["state"] = "ok" if got == hash_rec else "changed"
        rows.append(row)

    for r in rows:
        r["claims"] = sum(1 for c in claims if c.get("source") == r["path"])
        r["read"] = r["claims"] > 0
    dangling = sorted({str(c.get("source") or "") for c in claims
                       if str(c.get("source") or "") not in known
                       and c.get("source")})
    unread = [r for r in rows if not r["read"]]
    return {"rows": rows, "unread": unread, "dangling_claims": dangling,
            "unread_bytes": sum(r.get("bytes") or 0 for r in unread)}


def show_pending(doc) -> None:
    pend = doc.get("pending_decision") if isinstance(doc, dict) else None
    if pend is None:
        return
    if not isinstance(pend, dict):
        print("--- 判断待ち: 記録の形が壊れている（objectでない）")
        return
    due = pend.get("due") or "期日なし"
    print(f"--- 判断待ち: {pend.get('question', '')}（期日 {due}）")
    print(f"    既定進路: {pend.get('default_path', '（無い）')}"
          f" / 既定で進んだか: {pend.get('taken_by_default', False)}")
    opts = pend.get("options")
    if isinstance(opts, list):
        for i, opt in enumerate(opts, 1):
            if isinstance(opt, dict):
                print(f"    {i}. {opt.get('label', '')}"
                      f"／開く: {opt.get('opens', '')}／閉じる: {opt.get('closes', '')}")
            else:
                print(f"    {i}. {opt}")
    elif opts is not None:
        print("    選択肢の記録が壊れている（配列でない）")
    forb = pend.get("forbidden_while_waiting")
    if isinstance(forb, list) and forb:
        print(f"    待機中の禁止: {'、'.join(str(x) for x in forb)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("doc", nargs="?", help="_resume.json")
    ap.add_argument("--init", metavar="REL_DIR", help="この相対folderから作る")
    ap.add_argument("-o", "--out", help="--init の出力先")
    ap.add_argument("--max-hash-bytes", type=int, default=DEFAULT_MAX_HASH_BYTES)
    ap.add_argument("--strict", action="store_true",
                    help="missing / changed / invalid が1件でもあれば exit 1")
    a = ap.parse_args()
    root = vault_root()

    if a.init:
        doc = init(root, a.init, a.max_hash_bytes)
        text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
        if a.out:
            try:
                pathlib.Path(a.out).write_text(text, encoding="utf-8")
            except OSError as e:
                die(f"出力先に書けない: {type(e).__name__}（pathは表示しない）")
            print(f"{len(doc['files'])} file -> {pathlib.Path(a.out).name}")
            if doc.get("symlinks_skipped"):
                print(f"（symlink {doc['symlinks_skipped']} 件は記録していない）")
        else:
            print(text)
        return 0

    if not a.doc:
        ap.error("doc か --init のどちらかが必要")
    try:
        doc = json.loads(pathlib.Path(a.doc).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        die(f"記録を読めない: {type(e).__name__}")
    res = check(root, doc, a.max_hash_bytes)
    if res.get("fatal"):
        print(f"invalid  記録の形が壊れている: {res['fatal']}")
        return 1 if a.strict else 0
    for r in res["rows"]:
        # 印字で落ちないようにする（不正なUTF-8のfile名があった）。
        r["path"] = r["path"].encode("utf-8", "replace").decode("utf-8")
    width = max((len(r["path"]) for r in res["rows"]), default=10)
    for r in res["rows"]:
        mark = "読" if r.get("read") else "未"
        extra = ""
        if r.get("same_hash_elsewhere"):
            extra = "（同じ内容が $VAULT_ROOT/" \
                    + "、$VAULT_ROOT/".join(r["same_hash_elsewhere"]) + " に在る）"
        if r.get("note"):
            extra += f" {r['note']}"
        print(f"{r['state']:12s} {mark} {r['path']:<{width}}"
              f" {r.get('bytes', 0):>10,} B{extra}")
    counts = {s: sum(1 for r in res["rows"] if r["state"] == s) for s in STATES}
    print("\n--- {} file / ".format(len(res["rows"]))
          + " / ".join(f"{s} {counts[s]}" for s in STATES))
    print(f"--- 未読 {len(res['unread'])} file / {res['unread_bytes']:,} B"
          f"（読了の定義: そのfileを出所とする命題が1件以上あること）")
    if res["dangling_claims"]:
        print(f"--- 記録に無いfileを出所とする命題が {len(res['dangling_claims'])} 件: "
              + "、".join(res["dangling_claims"][:5]))
    show_pending(doc)
    # unverifiable も「一致を主張できない」状態である。strict の対象に入れる。
    bad = (counts["missing"] + counts["changed"] + counts["invalid"]
           + counts["unverifiable"])
    return 1 if (a.strict and bad) else 0


if __name__ == "__main__":
    sys.exit(main())
