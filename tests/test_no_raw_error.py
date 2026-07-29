"""条件8（生エラー遮断）恒久gate: 例外/APIエラー文字列を、そのままユーザー向けDOMへ入れる経路が
ソースに残っていないことをソース全走査で機械保証する（Codex E2: source.error を title に格納 等の再発防止）。
title/innerHTML/return 文字列テンプレに esc(e.message)/esc(s.error)/level2.error 等が現れたら失敗。
行末 raw-ok で除外（診断はconsole.errorへ）。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app/static/app.js").read_text(encoding="utf-8").split("\n")

# 生エラーを DOM 文字列へ差し込む典型パターン（テンプレートリテラル内の ${...esc(<error>)...}）
BAD = [
    re.compile(r"esc\(\s*(String\()?\s*e\.message"),
    re.compile(r"esc\(\s*String\(\s*e\s*\)"),
    re.compile(r"esc\(\s*[^)]*\.error\b"),          # esc(d.error/res.error/d.level2.error/s.error…) 非貪欲に捕捉
    re.compile(r"esc\(\s*[^)]*\.errors\b"),         # r.errors.join(...) 等
    re.compile(r'title="\$\{esc\([^}]*error'),
]


def test_no_raw_error_to_dom():
    violations = []
    for i, line in enumerate(JS, 1):
        if "raw-ok" in line:
            continue
        # console.error(...) はユーザーDOMでないので許可（診断ログ）
        stripped = re.sub(r"console\.error\([^)]*\)", "", line)
        for rx in BAD:
            if rx.search(stripped):
                violations.append(f"app/static/app.js:{i}  [{rx.pattern}]  {line.strip()[:110]}")
                break
    assert not violations, (
        "生エラーをユーザー向けDOMへ入れる経路が残存（0でなければならない・条件8）:\n" + "\n".join(violations)
    )
