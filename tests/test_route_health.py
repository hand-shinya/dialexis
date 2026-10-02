"""route健全性の静的gate（2026-10-02）。

2026-09-28、純関数を `@app.get("/api/origin")` とその関数定義の「間」に挿入した。
FastAPI はその純関数を /api/origin のハンドラとして登録し、api_origin は
decorator を失った。/api/origin は article_title と resolved を必須クエリとして
要求し 422 を返す状態になった。E2E 3スイート（origin_danger・nav_viewstate・
contrast）が落ちた。

この事故を止める試験は、当時どこにも存在しなかった。この file がその穴を塞ぐ。
外部取得なし・決定論。
"""
import os
import re
import tempfile

os.environ.setdefault("DIALEXIS_DB", os.path.join(tempfile.mkdtemp(), "test.db"))

from pathlib import Path  # noqa: E402

from app.main import app  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "app" / "main.py"

DECORATOR_RE = re.compile(r"^@app\.(get|post|put|patch|delete|head|options)\(")
DEF_RE = re.compile(r"^(async\s+)?def\s+")

# 利用者が実際に開く入口。これらが必須クエリを増やした瞬間に 422 になる。
# 「q だけが必須」を固定する。lang などの既定値つき引数は必須ではない。
PUBLIC_API = {
    "/api/origin": "api_origin",
    "/api/canon": "api_canon",
    "/api/translation-history": "api_translation_history",
}


def _decorator_lines():
    """app/main.py の route decorator 行と、その直後の非空行を返す。"""
    lines = MAIN.read_text(encoding="utf-8").split("\n")
    out = []
    for i, line in enumerate(lines):
        if not DECORATOR_RE.match(line):
            continue
        nxt = ""
        nxt_no = i + 1
        for j in range(i + 1, len(lines)):
            s = lines[j]
            # decorator が複数行に渡る場合と、重ねた decorator を飛ばす
            if s.strip() == "" or s.startswith((" ", "\t", ")", "@")):
                continue
            nxt, nxt_no = s, j + 1
            break
        out.append((i + 1, line.strip(), nxt_no, nxt))
    return out


def test_every_route_decorator_is_followed_by_a_function():
    """decorator と関数定義の間に別の定義を挟めないことを固定する。

    これが 2026-09-28 の 422 事故の正確な再現防止である。
    """
    rows = _decorator_lines()
    assert rows, "route decorator が1件も見つからない。検査が空振りしている"
    broken = [(ln, dec, nln, nxt) for ln, dec, nln, nxt in rows
              if not DEF_RE.match(nxt)]
    assert not broken, (
        "route decorator の直後が関数定義ではない（422事故と同型）:\n"
        + "\n".join(f"  app/main.py:{ln} {dec}  →  :{nln} {nxt.strip()[:60]}"
                    for ln, dec, nln, nxt in broken))


def test_public_api_endpoints_are_bound_to_their_handlers():
    """公開入口の path が、意図した関数に結びついていることを固定する。"""
    by_path = {}
    for r in app.routes:
        path = getattr(r, "path", None)
        name = getattr(r, "name", None)
        if path:
            by_path.setdefault(path, set()).add(name)
    for path, want in PUBLIC_API.items():
        assert path in by_path, f"{path} が登録されていない"
        assert want in by_path[path], (
            f"{path} のハンドラが {want} でない: {sorted(by_path[path])}")


def test_public_api_requires_only_the_query_word():
    """公開入口の必須クエリが q だけであることを固定する。

    必須クエリが増えると、利用者の URL がそのまま 422 になる。
    2026-09-28 は article_title と resolved が必須になっていた。
    """
    import inspect

    from app import main as m

    for path, fname in PUBLIC_API.items():
        fn = getattr(m, fname)
        sig = inspect.signature(fn)
        required = [
            n for n, p in sig.parameters.items()
            if p.default is inspect.Parameter.empty
            and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
            and n not in ("self", "request")
        ]
        assert required == ["q"], (
            f"{path} ({fname}) の必須引数が q だけでない: {required}")
