# BUILD_FROM_ZERO.md — 再現構築書（ゼロからの完全構築手順）

対象読者：**本システムを一度も見たことのない人間またはAI**。本書だけで、空のマシンから動作するDialexisを構築できることを保証目標とする。思想的に同一のシステムを（本リポジトリなしで）再構築する場合は `GENESIS.md` Part IV の Rebuild Prompt を使うこと。

## 0. 前提条件

- OS: Linux / macOS / WSL2（Windowsは WSL2 経由を推奨）
- Python 3.11 以上（`python3 --version` で確認）
- git
- インターネット接続（無料学術APIへの照会に必要。**APIキーは一切不要**）

## 1. 取得と起動（5分）

```bash
git clone https://github.com/hand-shinya/dialexis.git
cd dialexis
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

ブラウザで http://localhost:8000 を開く。トップページ（七つの公理）が表示されれば成功。

## 2. 動作検証（構築のたびに必ず実行）

```bash
# (a) オフラインsmokeテスト（ネットワーク不要の中核機能）
.venv/bin/pip install pytest
.venv/bin/python -m pytest tests/ -q        # → all passed であること

# (b) ライブ検証（無料APIへの実照会）
curl -s "http://127.0.0.1:8000/healthz"
curl -s "http://127.0.0.1:8000/api/explore?q=Karl%20Marx&lang=ja" | head -c 500
#  → entity に retrieved_at（取得時刻）が含まれていること（公理4の検証）

# (c) Watcher end-to-end
curl -s -X POST http://127.0.0.1:8000/api/watches \
  -H 'Content-Type: application/json' \
  -d '{"label":"Karl Marx","kind":"query"}'
curl -s -X POST http://127.0.0.1:8000/api/watches/1/run
#  → {"new_count": N, "errors": []} が返ること
.venv/bin/python -m app.harvester
#  → data/harvester_status.json が生成されること（このファイルの不在＝警報）
```

## 3. ファイル地図（何がどこにあり、なぜあるか）

| パス | 役割 | 対応する公理 |
|---|---|---|
| `GENESIS.md` | 憲法。全設計の導出元 | 全部 |
| `app/main.py` | FastAPI本体・全ルート | 1,4,7 |
| `app/db.py` | SQLiteスキーマの唯一の定義。固定語彙もここ | 7 |
| `app/connectors/` | 無料学術APIコネクタ（統一封筒・鮮度刻印） | 3,4 |
| `app/llm/adapter.py` | LLMスイッチ盤（BYOキー・非保存・GUARD） | 5,6 |
| `app/harvester.py` | cron用新着検出（発火点の外部化） | 4 |
| `app/data/counter_checklists.json` | 反証エンジン Level 0 の6視点 | 5 |
| `app/data/glossary_seed.json` | 段階的読解 Level 0 のseed | 5 |
| `app/i18n/` | UI文字列（ja/en） | — |
| `app/templates/` `app/static/` | 画面。ビルド工程なし | 7 |
| `app/static/vendor/cytoscape.min.js` | グラフ描画（同梱・CDN非依存。無ければ表形式に自動退化） | 5 |
| `tests/test_smoke.py` | オフライン検証 | — |
| `deploy/` | VPS公開一式（bootstrap・systemd・nginx） | — |
| `docs/` | 本書を含む文書一式 | — |

## 4. データの所在とバックアップ単位

- 全データ = `data/dialexis.db`（SQLite 1ファイル）。これをコピーすれば全研究が移動する（公理7）。
- キャッシュと台帳も同ファイル内。消しても研究データは失われない（`api_cache` は再取得される）。
- 環境変数：`DIALEXIS_DB`（DBパス変更）、`DIALEXIS_CONTACT`（丁寧アクセス用連絡先メール。**公開運用では必ず設定**）。

## 5. よくある構築失敗

| 症状 | 原因と対処 |
|---|---|
| `ModuleNotFoundError: fastapi` | venv外で起動している。`.venv/bin/uvicorn` を使う |
| explore が全て source error | ネットワーク遮断環境。プロキシ設定または回線確認。エラーが「表示される」こと自体は正常設計 |
| グラフが表示されない | `app/static/vendor/cytoscape.min.js` 欠落。`curl -L https://unpkg.com/cytoscape@3/dist/cytoscape.min.js -o app/static/vendor/cytoscape.min.js`。なくても表形式で動作する |
| 日本語が文字化け | ロケール未設定。`export LANG=ja_JP.UTF-8`（表示側の問題でありデータはUTF-8で無事） |

## 6. AIによる再構築の受入基準

本書または GENESIS.md Part IV から再構築した場合、次を満たすこと：
1. `pytest` 相当のオフライン検証が全通過する
2. 外部情報の全表示に取得時刻がある（公理4）
3. LLMキーなしで全ページ・全機能が動作する（公理5）
4. AI生成出力に origin=ai の標識と台帳記録がある（公理6）
5. 研究プロジェクトがMarkdownとJSON-LDで完全に書き出せる（公理7）
