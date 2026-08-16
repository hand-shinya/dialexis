"""全メニューのAction IDが単一registryとUI面宣言に接続されているかを検査する。"""

import re
from pathlib import Path


JS = (Path(__file__).resolve().parents[1] / "app/static/app.js").read_text(encoding="utf-8")


def _block(start, end):
    i = JS.index(start)
    j = JS.index(end, i)
    return JS[i:j]


def test_every_action_has_effect_and_run():
    block = _block("const ACTIONS = {", "// 各表示面が使う Action ID")
    entries = re.findall(r"^\s{2}([A-Za-z][A-Za-z0-9]*):\s*\{([\s\S]*?)(?=^\s{2}[A-Za-z][A-Za-z0-9]*:\s*\{|\Z)", block, re.MULTILINE)
    assert entries
    assert all(re.search(r"\beffect\s*:", body) for _, body in entries)
    assert all(re.search(r"\brun\s*:", body) for _, body in entries)
    effects = set(re.findall(r"const EFFECTS = \[([^]]+)\]", JS)[0].replace('"', "").split(", "))
    declared = {m.group(1) for m in re.finditer(r"\beffect\s*:\s*\"([^\"]+)\"", block)}
    assert declared <= effects


def test_gactions_and_edge_menu_only_emit_registered_ids():
    registry = set(re.findall(r"^\s{2}([A-Za-z][A-Za-z0-9]*):\s*\{", _block("const ACTIONS = {", "// 各表示面が使う Action ID"), re.MULTILINE))
    for fn, end in (("function gActions", "function gLensMenu"), ("function gMenuEdge", "// メニューの中身")):
        block = _block(fn, end)
        emitted = set(re.findall(r"\baction:\s*\"([^\"]+)\"", block))
        assert emitted, fn
        assert emitted <= registry, f"{fn}: {sorted(emitted - registry)}"


def test_ui_action_maps_reference_registry_ids():
    registry = set(re.findall(r"^\s{2}([A-Za-z][A-Za-z0-9]*):\s*\{", _block("const ACTIONS = {", "// 各表示面が使う Action ID"), re.MULTILINE))
    block = _block("const UI_ACTION_MAP = {", "const UI_ACTION_IDS = {")
    mapped = set(re.findall(r":\s*\"([A-Za-z][A-Za-z0-9]*)\"", block))
    assert mapped <= registry


def test_all_registry_ids_are_exposed_to_runtime_probe():
    block = _block("const UI_ACTION_IDS = {", "function _activeTerm")
    # The runtime probe must enumerate the registry, not maintain a second hidden list.
    assert "actions() { return Object.keys(ACTIONS); }" in JS
    assert "registry()" in JS
    assert "uiActions()" in JS
    assert "topbar" in block and "popup" in block
