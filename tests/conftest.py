"""testごとにDBを分ける。

2026-10-08 の敵対的検証で、新しいtestが本番用の `data/dialexis.db` に
直接書いていることが指摘された。後片付けも分離も無く、試験の残骸が
実データに混ざる。`DIALEXIS_DB` は `app/db.py` が読む環境変数なので、
import より前に差し替える。
"""
import os
import pathlib
import tempfile

_TMP = pathlib.Path(tempfile.mkdtemp(prefix="dialexis-tests-"))
os.environ.setdefault("DIALEXIS_DB_TEST_DIR", str(_TMP))
# 既に本番pathが入っている場合も、test実行中は差し替える。
os.environ["DIALEXIS_DB"] = str(_TMP / "test.db")
