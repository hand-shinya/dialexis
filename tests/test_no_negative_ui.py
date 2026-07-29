"""原理的普遍化の恒久gate（半田様2026-07-29）: ソース全走査で「〜できません/引けません/見つかりません/
失敗」等の"否定的結末"の表示文が0件であることを毎デプロイで機械保証する。実行時の語×パネル列挙(外延的・
漏れる)でなく、ソース全体(網羅的)で担保＝将来/変種/新規も自動で捕える。行末に `neg-ok` があれば除外。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ["app/static/app.js", "app/main.py"]

BAD = [
    r"できませんでした", r"できません(?!か)", r"でき(ず|ない)[、。」\s]", r"引けま(せん|ない)",
    r"特定でき(ません|ず|ない)", r"見つかりませんでした", r"見つかりません", r"見つから(ない|ず)",
    r"取得でき(ませんでした|ません|ず|ない)", r"出題でき(ません|ない)", r"ありませんでした",
    r"失敗しました", r"失敗(?=[。」\s])",
    r"no data", r"not found", r"no result", r"no usage", r"no series", r"no etymology",
    r"unavailable", r"\bfailed\b",
]
BAD_RE = [re.compile(p, re.IGNORECASE) for p in BAD]


def _strip_js_line_comments(text: str) -> list[str]:
    text = re.sub(r"/\*[\s\S]*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    out = []
    for line in text.split("\n"):
        in_s = None
        esc = False
        cut = line
        for i in range(len(line) - 1):
            c = line[i]
            if esc:
                esc = False
                continue
            if c == "\\":
                esc = True
                continue
            if in_s:
                if c == in_s:
                    in_s = None
                continue
            if c in "\"'`":
                in_s = c
                continue
            if c == "/" and line[i + 1] == "/":
                cut = line[:i]
                break
        out.append(cut)
    return out


def _strip_py_comments(text: str) -> list[str]:
    out = []
    for line in text.split("\n"):
        # 素朴: 文字列外の # 以降を落とす
        in_s = None
        esc = False
        cut = line
        for i, c in enumerate(line):
            if esc:
                esc = False
                continue
            if c == "\\":
                esc = True
                continue
            if in_s:
                if c == in_s:
                    in_s = None
                continue
            if c in "\"'":
                in_s = c
                continue
            if c == "#":
                cut = line[:i]
                break
        out.append(cut)
    return out


def test_no_negative_outcomes_in_source():
    violations = []
    for f in FILES:
        p = ROOT / f
        raw = p.read_text(encoding="utf-8")
        raw_lines = raw.split("\n")
        lines = _strip_js_line_comments(raw) if f.endswith(".js") else _strip_py_comments(raw)
        for i, line in enumerate(lines, 1):
            if "neg-ok" in raw_lines[i - 1]:   # 除外指定は元の行で判定（コメント除去で消えないように）
                continue
            for rx in BAD_RE:
                if rx.search(line):
                    violations.append(f"{f}:{i}  [{rx.pattern}]  {line.strip()[:110]}")
                    break
    assert not violations, (
        "ユーザーに見える否定的結末の表示が残存（0でなければならない・原理的普遍化）:\n"
        + "\n".join(violations)
    )
