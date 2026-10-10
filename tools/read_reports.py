#!/usr/bin/env python3
"""匿名報告を所有者が読む道具（2026-10-10）。

なぜ endpoint ではないのか:
  この system には認証機構が無い（公開instanceは署名cookieのworkspace分離だけ）。
  一覧を返す endpoint を作ると、**他の利用者が書いた文が読める面**が生まれる。
  所有者は VPS 上でこの script を使う。面を増やさないことが保証になる。

使い方（VPS 上で）:
  python3 tools/read_reports.py                 open のものを古い順に出す
  python3 tools/read_reports.py --all           すべて出す
  python3 tools/read_reports.py --read CODE     状態を read にする
  python3 tools/read_reports.py --close CODE    状態を closed にする
  python3 tools/read_reports.py --count         状態ごとの件数だけ出す

この script が保証しないこと（公理3）:
  報告の内容が正しいこと。報告が本物の利用者から来たこと。
  連絡先を持たないので、返信はできない。番号を知る人が状態を見られるだけである。
"""
import argparse
import os
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = os.environ.get("DIALEXIS_DB") or str(ROOT / "data" / "dialexis.db")
STATUSES = ("open", "read", "closed")


def conn():
    p = pathlib.Path(DB)
    if not p.exists():
        print("DBが見つかりません: %s" % DB, file=sys.stderr)
        print("DIALEXIS_DB を指定するか、VPS 上で実行してください", file=sys.stderr)
        sys.exit(2)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def has_table(c):
    r = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reports'")
    return r.fetchone() is not None


def show(rows):
    if not rows:
        print("該当する報告はまだありません。")
        return
    for r in rows:
        print("─" * 72)
        print("%s  [%s]  %s  %s" % (r["code"], r["status"], r["kind"], r["ts"]))
        if r["page"]:
            print("  画面: %s" % r["page"])
        if r["handled_at"]:
            print("  処理: %s" % r["handled_at"])
        print()
        for line in (r["body"] or "").split("\n"):
            print("  " + line)
        if r["context"]:
            print()
            print("  添付（利用者が自分で選んだもの・%d字）" % len(r["context"]))
            print("  " + r["context"][:600] + ("…" if len(r["context"]) > 600 else ""))
        print()
    print("─" * 72)
    print("%d 件" % len(rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="状態を問わず出す")
    ap.add_argument("--count", action="store_true", help="状態ごとの件数だけ出す")
    ap.add_argument("--read", metavar="CODE", help="状態を read にする")
    ap.add_argument("--close", metavar="CODE", help="状態を closed にする")
    a = ap.parse_args()

    c = conn()
    if not has_table(c):
        print("reports table がまだありません（1件も報告が来ていない版のDBです）。")
        return 0

    if a.read or a.close:
        code = (a.read or a.close).strip().upper()
        new = "read" if a.read else "closed"
        import datetime
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        try:
            n = c.execute("UPDATE reports SET status=?, handled_at=? WHERE code=?",
                          (new, ts, code)).rowcount
            c.commit()
        except sqlite3.OperationalError as e:
            # VPS では DB が app の実行user所有である。読みは通るが書きは通らない。
            # 生のtracebackを出さず、何が要るかを言う（公理1: 沈黙も混乱もさせない）。
            print("状態を書き換えられませんでした: %s" % e, file=sys.stderr)
            print("DBは app の実行userが所有しています。そのuserで実行してください:",
                  file=sys.stderr)
            print("  sudo -u dialexis DIALEXIS_DB=%s \\" % DB, file=sys.stderr)
            print("    /opt/dialexis/.venv/bin/python tools/read_reports.py %s %s"
                  % ("--read" if a.read else "--close", code), file=sys.stderr)
            print("sudo の許可は意図的に2命令（vps_update.sh と systemctl restart）"
                  "だけなので、この命令を通すには1行足す決裁が要ります。", file=sys.stderr)
            return 3
        print("%s を %s にしました（%d 件）" % (code, new, n) if n
              else "%s に一致する報告は 0 件です" % code)
        return 0 if n else 1

    if a.count:
        for s in STATUSES:
            n = c.execute("SELECT COUNT(*) FROM reports WHERE status=?", (s,)).fetchone()[0]
            print("%-8s %d" % (s, n))
        return 0

    q = "SELECT * FROM reports ORDER BY id"
    rows = list(c.execute(q) if a.all else
                c.execute("SELECT * FROM reports WHERE status='open' ORDER BY id"))
    show(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
