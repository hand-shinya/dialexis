#!/usr/bin/env python3
"""撤退台帳の最小検査を、pytest の外側で行う（2026-10-09）。

なぜ pytest の中ではないか:
  2026-10-09 の敵対的検証で、`tests/test_retreat_register.py` を消すと
  全体が静かに通ることが実証された（315 passed・rc=0）。
  試験fileの実在を検査する試験が、その試験file自身の中に在るからである。
  自分の存在を自分で守れない。

そこで検査を runner（verify.sh）の側へ出す。
このfileが消えたときは `python tools/check_register_files.py` が
非ゼロで落ち、verify.sh が fail=1 を立てる（沈黙しない・公理1）。

検査するのは3つだけである。
  1. 台帳が在り、TOML として読めること
  2. 台帳の expected_tests と tests/test_*.py の集合が厳密に一致すること
  3. 台帳と、台帳を強制する試験が git に追跡されていること

有効性や内容の正しさは検査しない（公理7）。それは pytest 側と半田様が見る。
"""
import pathlib
import subprocess
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
REL = "governance/retreat_register.toml"
REGISTER = ROOT / REL
MUST_BE_TRACKED = (REL, "tests/test_retreat_register.py", "tools/check_register_files.py")

problems = []

if not REGISTER.exists():
    print("撤退台帳が無い: " + REL, file=sys.stderr)
    sys.exit(2)

try:
    doc = tomllib.loads(REGISTER.read_text(encoding="utf-8"))
except Exception as e:
    print("撤退台帳が読めない: {}: {}".format(type(e).__name__, e), file=sys.stderr)
    sys.exit(2)

listed = doc.get("expected_tests")
if not isinstance(listed, list) or not listed:
    # TOML の落とし穴: 裸のkeyを [[table]] の後ろに置くと、そのtableの中に入る。
    # 2026-10-09 に実際に踏んだ。見た目では独立した節に見える。
    problems.append("expected_tests が list として読めない（[[mechanism]] より前に置くこと）")
    listed = []

on_disk = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("test_*.py"))
only_disk = sorted(set(on_disk) - set(listed))
only_list = sorted(set(listed) - set(on_disk))
if only_disk:
    problems.append("台帳に無い試験fileが在る（機構を足して台帳に書いていない可能性）: "
                    + ", ".join(only_disk))
if only_list:
    problems.append("台帳に在る試験fileがdiskに無い（消して黙らせた可能性）: "
                    + ", ".join(only_list))

for rel in MUST_BE_TRACKED:
    if not (ROOT / rel).exists():
        problems.append("在るべきfileが無い: " + rel)
        continue
    r = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        problems.append("git に追跡されていない（配備経路がこのfileを知らない）: " + rel)

if problems:
    print("撤退台帳の検査に失敗:", file=sys.stderr)
    for p in problems:
        print("  - " + p, file=sys.stderr)
    sys.exit(1)

print("撤退台帳 ok（試験file {} 本が台帳と一致・追跡 {} 件）".format(len(on_disk), len(MUST_BE_TRACKED)))
