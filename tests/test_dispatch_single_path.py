"""3.3 単一Dispatcher強制（静的lint）: 表示面(上部帯/popup/パネルフッター/noMiss/本文リンク/見方一覧)の
クリックハンドラは dispatchAction 単一経路を通す。状態変更関数を表示面のclosureで直接呼ぶ実装が
追加されたら失敗させる。§5.5 の通り本テストは補助lintで、主保証は runtime failure injection と操作同値性E2E。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app/static/app.js").read_text(encoding="utf-8")

# 表示面のクリックハンドラは、その直近ブロックに dispatchAction を含むこと（作用の再実装をしない）。
SURFACE_ANCHORS = [
    ('.tm-chip").forEach', "上部帯"),
    ('closest(".gm-item")', "ノードpopup"),
    ('.gp-cont-b").forEach', "パネルフッター"),
    ('closest(".nomiss-b")', "noMiss"),
    ('.lens-row").forEach', "見方一覧"),
    ('closest(".ext-term")', "本文語リンク"),
]

# 表示面が直接呼んではいけない状態変更関数
FORBIDDEN = ["originRecenter(", "gWordAspect(", "applyLensBuild(", "applyLensFor(",
             "gFocusSubtree(", "gAnatomyPanel(", "gContrastPanel(", "gExtPanel(",
             "gColloc(", "gCombinePanel(", "gPerspectivePanel(", "gLensMenu(", "shelfAdd("]


def _block_after(anchor: str, span: int) -> str:
    i = JS.find(anchor)
    assert i >= 0, f"anchor not found: {anchor}"
    return JS[i:i + span]


def test_surfaces_route_through_dispatch():
    problems = []
    for anchor, name in SURFACE_ANCHORS:
        # dispatchAction 到達は広めに、禁止関数は「ハンドラ本体だけ」（最初のdispatchActionまで）で検査。
        wide = _block_after(anchor, 420)
        if "dispatchAction" not in wide:
            problems.append(f"{name}: dispatchAction を通っていない（anchor={anchor}）")
        body = wide.split("dispatchAction", 1)[0]   # 表示面ハンドラ本体（dispatchより前）に直接作用が無いこと
        for f in FORBIDDEN:
            if f in body:
                problems.append(f"{name}: 状態変更関数を表示面で直接呼んでいる → {f}")
    assert not problems, "単一Dispatcher違反:\n" + "\n".join(problems)


def test_no_per_item_closures():
    # 各項目に fn closure を持たせて作用を再実装する旧構造が復活していないこと
    assert "it.fn" not in JS and "c.fn ?" not in JS, "項目closure(it.fn)が復活＝作用の再実装（Dispatcher単一化違反）"


def test_actions_registry_covers_core_ids():
    for aid in ["center", "meaning", "anatomy", "contrast", "multilingual", "combine",
                "external", "shelf", "deepsearch", "newtab", "focus", "resetFocus", "lens"]:
        assert re.search(r"\b" + aid + r":\s*\{", JS), f"ACTIONS registry に {aid} が無い"
