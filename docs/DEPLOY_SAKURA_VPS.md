# DEPLOY_SAKURA_VPS.md — さくらVPS公開手順書

対象環境：**さくらのVPS v5・2Gプラン・Ubuntu Server**（本プロジェクトの実際の契約環境。IPv4: 219.94.244.239 / ホスト名: os3-284-31735.vs.sakura.ne.jp）。bootstrap は Ubuntu（apt）と Rocky/RHEL（dnf）の両方を自動判別して対応する。

所要時間：初回約20分（うちコマンド実行は数分）。

## 1. 事前準備（さくらのコントロールパネル）

1. https://secure.sakura.ad.jp/vps/ にログイン → 対象サーバー
2. **OS確認**：Ubuntu Server がインストール済みであること（OS再インストール時に管理ユーザー（既定 `ubuntu`）のパスワード／公開鍵を設定する）
3. **パケットフィルター**：「設定」→ パケットフィルター →
   - SSH（22）: 許可（既定）
   - **Web（80/443）: 許可を追加** ← これを忘れるとnginxが動いていても外から見えない
4. サーバーが「稼働中」であることを確認

## 2. SSH接続

```
ssh ubuntu@219.94.244.239
```

（ユーザー名はOSインストール時に設定したもの。さくらのUbuntuイメージの既定は `ubuntu`）。初回接続でホスト鍵の確認が出たら yes。パスワードはOSインストール時に設定したもの。

## 3. 一括構築（bootstrap）

```bash
export DIALEXIS_CONTACT="あなたのメールアドレス"   # 無料API群への丁寧アクセス用（推奨）
curl -sL https://raw.githubusercontent.com/hand-shinya/dialexis/main/deploy/bootstrap_vps.sh | sudo -E bash
```

bootstrap は次を自動実行する（再実行しても安全）：
パッケージ導入 → 専用ユーザー作成 → git clone → venv → **オフラインテスト全通過の確認** → systemd（アプリ＋ハーベスタtimer）→ nginx＋SELinux → firewalld（http/https開放）→ 日次DBバックアップのcron登録 → healthz確認。

最後に `OK: Dialexis is live on port 80 via nginx.` が出れば完了。

## 4. 公開確認

ブラウザで次を開く：

```
http://219.94.244.239/
```

トップページ（七つの公理）が表示され、`Karl Marx` の探索で取得時刻バッジつきの結果が返れば公開成功。

## 5. 動作しないとき

| 症状 | 確認 |
|---|---|
| ブラウザから見えない | §1-3 パケットフィルターでWeb許可を追加したか（最頻出） |
| curlでlocalhostは見えるが外から見えない | 同上＋ `firewall-cmd --list-services` に http があるか |
| 502 | `journalctl -u dialexis -n 50` でアプリ状態確認。Rocky/RHEL系のみ `setsebool -P httpd_can_network_connect 1`（bootstrapが実施済のはず） |
| nginxが起動しない（Ubuntu） | 既定サイトとの競合。`rm -f /etc/nginx/sites-enabled/default && nginx -t && systemctl reload nginx`（bootstrapが実施済のはず） |
| bootstrapがテストで停止 | 正しい挙動（壊れた状態で公開しない）。エラー全文をGitHub Issueへ |

## 6. 独自ドメイン（任意）

1. ドメイン取得（さくら・Cloudflare等。年2,000円前後）
2. DNSのAレコード：`dialexis.example.com → 219.94.244.239`
3. `/etc/nginx/conf.d/dialexis.conf` の `server_name _;` を `server_name dialexis.example.com;` へ変更 → `systemctl reload nginx`

## 7. HTTPS化（ドメイン取得後に必ず実施）

```bash
sudo apt-get install -y certbot python3-certbot-nginx   # Ubuntu
# Rocky/RHEL: sudo dnf -y install certbot python3-certbot-nginx
sudo certbot --nginx -d dialexis.example.com --agree-tos -m あなたのメール
# 自動更新タイマーは certbot が登録する。確認: systemctl list-timers | grep certbot
```

HTTPS化まではAPIキー（LLM）の入力を控えるよう /settings の説明にも注記がある。平文HTTP区間では鍵が傍受されうるため。

## 8. 更新・バックアップ・監視

OPERATIONS.md 参照（更新は `git pull` → テスト → restart の3手）。
