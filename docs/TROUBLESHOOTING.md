# TROUBLESHOOTING.md — トラブルシューティング / Troubleshooting

日本語＋English併記。運用者向けの深い障害対応は OPERATIONS.md も参照。

## 利用者側 / For users

| 症状 / Symptom | 原因と対処 / Cause & fix |
|---|---|
| 探索結果に赤い「情報源エラー」バッジ / red source-error badge | その外部API（OpenAlex等）が一時的に不調。他の情報源の結果は正常。数分後に再検索。恒常的なら運用者がCOST_AND_API.mdのレート制限を確認 / That external API is temporarily down; other sources are unaffected. Retry later. |
| AI機能が「APIキーが必要」と出る / "needs an API key" | 正常動作（Level 0）。設定ページで自分の鍵を入れるとLevel 2に昇格。無料で試すならOllama（ローカル）/ Working as designed. Add your own key in Settings, or use local Ollama for free. |
| AI呼び出しが失敗する / LLM call fails | 鍵の誤り・残高不足・モデル名の誤り。エラーメッセージがそのまま表示される。モデル名を空欄（既定値）にして再試行 / Wrong key, no credit, or wrong model name. Try blank model (default). |
| グラフが出ない / graph missing | 表形式に自動退化していれば機能は無事。運用者は vendor/cytoscape.min.js の存在を確認（BUILD_FROM_ZERO.md §5）|
| Watcherの新着に無関係な文献が混ざる / irrelevant watch hits | query型は全文検索のため既知の限界。author型（OpenAlex著者ID紐付け）で登録し直すと適合率が上がる / Known limitation of query-type; re-register as author-type. |
| 検索結果が英語圏に偏る / results skew Anglophone | 既知のバイアス（ROADMAP参照）。lang=ja でWikidata/Wikipediaは日本語化されるが、OpenAlex/Crossrefは英語文献が多い。非西洋情報源の追加はロードマップ最優先課題 |
| データを持ち出したい / want my data out | プロジェクト画面のMarkdown/JSON-LDエクスポート。サーバー全体なら data/dialexis.db を1ファイルコピー（公理7）|

## 運用者側 / For operators

| 症状 | 対処 |
|---|---|
| `/healthz` が落ちている | `systemctl status dialexis` → `journalctl -u dialexis -n 100`。ほぼ確実に (a)ポート競合 (b)DBパス権限 (c)OOM。2GBメモリでOOMは通常起きない（uvicorn1ワーカー約100MB）|
| harvester_status.json が古い | `systemctl list-timers | grep dialexis` でタイマー確認 → 手動実行 `sudo -u dialexis /opt/dialexis/.venv/bin/python -m app.harvester` でエラー本文を取得 |
| 502 Bad Gateway | nginx→uvicorn接続不可。SELinux起因が典型：`setsebool -P httpd_can_network_connect 1`（bootstrap実行済のはず）|
| ディスク逼迫 | `sqlite3 data/dialexis.db "DELETE FROM api_cache; VACUUM;"`（研究データは無傷）|
| HTTPS化したい | ドメイン取得後 DEPLOY_SAKURA_VPS.md §7（certbot）|
| 無料APIから429（レート制限） | `DIALEXIS_CONTACT` に連絡先メールを設定（polite pool）。キャッシュTTLを延長。並列照会数はexplore1回あたり最大7リクエストで設計済 |

## 障害報告の書き方 / Reporting

GitHub Issues に：(1)URL/操作 (2)表示されたエラーバッジ・メッセージの全文 (3)時刻。エラーを隠さない設計のため、画面の赤バッジ全文が最良の診断情報になる。
