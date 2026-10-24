"""所有者の写し（2026-10-24 10:49・資本論）: 最初に語を入れて Enter を押しただけでは地図が出ず、
「原語から問い直す」を押して初めて出た。初めての語は、意味・語源などの取得と同時に走るため、地図の
組み立てが画面側の打ち切り（20秒）を超えていた（本番ログ: 最初の読み込みに地図の応答の記録が無い）。
地図の取得だけは長く待ち、1回取り直すことを、画面の source で守る。
"""
import re
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / "app" / "static" / "app.js").read_text(encoding="utf-8")


def test_graph_fetch_waits_longer_than_the_default_timeout():
    m = re.search(r"const GRAPH_TIMEOUT_MS = (\d+);", JS)
    d = re.search(r"const API_TIMEOUT_MS = (\d+);", JS)
    assert m and d and int(m.group(1)) >= 60000 > int(d.group(1))
    body = JS[JS.index("async function originResolveGraph"):JS.index("async function originExplore")]
    assert "timeout: GRAPH_TIMEOUT_MS" in body


def test_graph_fetch_is_retried_once():
    body = JS[JS.index("async function originResolveGraph"):JS.index("async function originExplore")]
    assert re.search(r"for \(let attempt = 0; attempt < 2 && !d; attempt\+\+\)", body)
