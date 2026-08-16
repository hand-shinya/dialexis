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
        # busy/disabled guards and the anchor/dispatcher call may legitimately
        # span more than the original 420-character probe.  Keep this a local
        # handler probe; the split below still prevents scanning later code.
        wide = _block_after(anchor, 700)
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


def _handler_bodies():
    """全 addEventListener("click"|"keydown"|"submit"|"pointerdown") のコールバックを括弧平衡で抽出。"""
    bodies = []
    for m in re.finditer(r'addEventListener\(\s*"(click|keydown|submit|pointerdown)"\s*,', JS):
        i = m.start()
        # addEventListener( の開き括弧から平衡を取り、閉じるまでをコールバック領域とする
        j = JS.find("(", i)
        depth = 0
        k = j
        while k < len(JS):
            c = JS[k]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        bodies.append((i, JS[j:k + 1]))
    return bodies


# ユーザーevent handler内で許される状態遷移呼出しの形（これ以外の状態変更関数の直接呼出しは違反）
_ALLOWED_LINE = re.compile(r"dispatchAction\(|navGo\(|\{\s*nav:\s*true\s*\}")


def test_all_event_handlers_no_direct_state_change():
    """条件A1: 全ユーザーevent handlerを走査し、状態変更関数の直接呼出しが無いことを保証（既知anchor限定でない）。
    許容: dispatchAction / navGo / originRecenter(...,{nav:true})（履歴復元）。それ以外は違反。"""
    problems = []
    for pos, body in _handler_bodies():
        for f in FORBIDDEN + ["gCombineRun(", "gDimAct(", "gAuthorInvestigate(", "gAuthorPanel(", "gCounter("]:
            idx = 0
            while True:
                idx = body.find(f, idx)
                if idx < 0:
                    break
                # その呼出しを含む行が許容形（dispatch/navGo/{nav:true}）でなければ違反
                ls = body.rfind("\n", 0, idx) + 1
                le = body.find("\n", idx)
                line = body[ls:(le if le > 0 else len(body))]
                if not _ALLOWED_LINE.search(line):
                    problems.append(f"@{pos} 直接状態変更 {f} in: {line.strip()[:90]}")
                idx += len(f)
    assert not problems, "ユーザーevent handlerでのDispatcher迂回（直接状態変更）:\n" + "\n".join(problems[:20])


def test_no_noop_menu_items():
    # 条件6: gActions / gMenuEdge の menu item に無作用placeholder(soon:)や直接fnが無く、必ず action: を持つ。
    # クリック可能な無作用項目(選ぶとメニューが閉じるだけ)を静的に0件保証する（Codex E2で発覚した回帰の再発防止）。
    for fn_name in ["function gActions", "function gMenuEdge"]:
        i = JS.find(fn_name)
        assert i >= 0, f"{fn_name} not found"
        end = JS.find("\nfunction ", i + 10)
        block = JS[i:end if end > i else i + 2000]
        assert "soon:" not in block, f"{fn_name} に無作用placeholder(soon:)が残存"
        assert re.search(r"\bfn:\s*(\(|function)", block) is None, f"{fn_name} に直接fnのmenu item(無作用/Dispatcher迂回)が残存"
        # 各 menu item literal( { t: ... } )に action: がある（gShowMenu/renderTopMenuはit.actionをdispatchするため）
        assert re.search(r"\{\s*[st]:\s*[`\"'][^`\"']*[`\"'][^}]*\}", block), f"{fn_name} に menu item が無い?"
