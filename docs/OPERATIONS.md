# OPERATIONS.md — 運用手順書

対象読者：本番環境（VPS）でDialexisを運用する管理者。初回構築は `DEPLOY_SAKURA_VPS.md`。

## 1. 日常運用は「無い」ことが正常

本システムの運用は外部実行系（systemd）に委譲されており、平常時に人間の作業は発生しない。確認すべきは以下の2点のみ（週1回程度）：

```bash
curl -s https://<ホスト>/healthz          # {"status":"ok",…} であること
ssh <VPS> cat /opt/dialexis/data/harvester_status.json | head -5
# last_run が24時間以内であること。古い/無い = 異常（それ自体が警報）
```

## 2. サービス管理（systemd）

```bash
systemctl status dialexis            # アプリ本体（uvicorn）
systemctl status dialexis-harvester.timer   # 新着監視タイマー（日次）
journalctl -u dialexis -n 100        # アプリログ
journalctl -u dialexis-harvester -n 50      # ハーベスタログ
systemctl restart dialexis           # 再起動（数秒で完了・データ影響なし）
```

## 3. バックアップ

全データは `/opt/dialexis/data/dialexis.db` の1ファイル。日次バックアップは bootstrap が cron に登録済み：

```bash
# /etc/cron.d/dialexis-backup が実行する内容（sqlite3の安全なオンラインバックアップ）
sqlite3 /opt/dialexis/data/dialexis.db ".backup /var/backups/dialexis/dialexis-$(date +%a).db"
# 曜日ローテーション7世代。リストア = ファイルを戻して systemctl restart dialexis
```

## 4. 更新（新バージョンの適用）

```bash
cd /opt/dialexis
sudo -u dialexis git pull
sudo -u dialexis .venv/bin/pip install -r requirements.txt
sudo -u dialexis .venv/bin/python -m pytest tests/ -q   # 全通過を確認してから
sudo systemctl restart dialexis
```

ロールバック：`sudo -u dialexis git checkout <直前タグ>` → restart。DBスキーマは追記的にのみ変更する方針（IMPROVEMENT_PROTOCOL.md 参照）のため、コード巻き戻しでデータは壊れない。

## 5. 監視と警報（沈黙する失敗を許さない）

| 監視対象 | 正常条件 | 異常時 |
|---|---|---|
| `/healthz` | HTTP 200 | systemctl status / journalctl で原因特定 |
| `harvester_status.json` | last_run < 26h | `systemctl list-timers`、手動実行 `python3 -m app.harvester` |
| ディスク | `df -h` 80%未満 | api_cache の削除で即応：`sqlite3 data/dialexis.db "DELETE FROM api_cache"` |
| 無料APIのエラー率 | explore結果のerrorバッジが常態化しない | COST_AND_API.md のレート制限を確認。TTL延長で対応 |

外形監視は UptimeRobot 等の無料枠で `/healthz` を5分間隔監視し、メール通知を設定することを推奨（人間の記憶に依存させない）。

## 6. セキュリティ運用

- サーバーにはいかなるユーザーAPIキーも保存されない（設計上）。漏洩リスクの中心はOS層 → `dnf -y update` を月次、または `dnf-automatic` で自動化
- アプリは非rootユーザー `dialexis` で稼働、nginx が80/443を終端
- `ai_ledger` と `watch_hits` は追記型で肥大しうる → 年1回 `DELETE FROM ai_ledger WHERE ts < date('now','-1 year')`

## 7. 費用の現況確認

さくらVPS 2Gプラン月額1,848円（契約時価格）＋ドメイン代（任意）が全費用。LLM費用は利用者のBYOキーに帰属しゼロ。費用が発生する変更を加える際は DONATIONS.md の区分（公共知識/AI処理/レビュー）に従い、無料閲覧の恒久性を侵さないこと。
