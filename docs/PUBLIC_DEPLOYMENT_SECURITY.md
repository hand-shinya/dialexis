# Public deployment security boundary

更新日: 2026-08-27

## 結論

Dialexis は Level-0 の検索・探索をアカウントなしで公開できる。一方、研究プロジェクト、研究台帳、監視対象、AI 実行記録は、公開設定されていない限り、同じ匿名ブラウザのワークスペースからだけ読書きする。公開設定したプロジェクト／台帳は第三者が閲覧・引用できるが、所有者以外は読取専用である。

これは認証・本人確認ではない。第三者検証用の公開入口と、匿名利用者間の偶然の混線を分離するための過渡的な境界である。Cookie を失った利用者は以前の非公開資産を自動復旧できない。正式なアカウント、共有リンク、権限管理が必要になった時点で、署名 Cookie を認証基盤へ置き換える。

## 起動モード

### ローカル単一利用者（既定）

`DIALEXIS_PUBLIC_INSTANCE` が未設定または真偽値でない場合、全リクエストを `DIALEXIS_LEGACY_WORKSPACE_ID`（既定値 `single-user-local`）へ束ねる。既存 DB の空の `workspace_id` も、このモードでのみ同じ ID へ移行される。従来のローカル利用を壊さないための互換モードである。

### 公開インスタンス

次の 2 つを必須にする。

```text
DIALEXIS_PUBLIC_INSTANCE=1
DIALEXIS_SESSION_SECRET=<十分に長いランダム値>
```

公開モードでは、初回応答で `HttpOnly; SameSite=Lax` の `dialexis_workspace` Cookie を発行する。Cookie はランダムなワークスペース ID と HMAC 署名を含み、署名不正・欠落時は新しいワークスペースを作る。HTTPS は Nginx 等のリバースプロキシで終端し、Cookie の `Secure` 属性が有効になる。

`DIALEXIS_SESSION_SECRET` がない公開起動は、誤って再起動ごとに所有データを失う状態を避けるため、アプリケーション起動時に拒否する。

### 既存VPSを一度だけ公開モードへ切り替える

旧bootstrapで作成したVPSには、リポジトリだけ更新しても `/etc/systemd/system/dialexis.service`
と `/etc/dialexis/dialexis.env` は自動更新されない場合がある。その場合はVPS管理者として、次を
一度だけ実行する。

```bash
sudo /opt/dialexis/deploy/activate_public_instance.sh
```

このスクリプトは、既存のsystemd定義をタイムスタンプ付きで退避し、永続secret、公開用unit、
harvester定義、最小権限sudoersを検証して導入し、daemon-reload・サービス再起動・`healthz`の
公開モード/Cookie確認まで行う。以後の通常更新は、`deploy/vps_deploy.sh`の狭いsudo許可で
継続できる。既存secretが空または短い場合は上書きせず停止する。

## 所有・公開モデル

| 資産 | 既定 | 他ワークスペースからの読取 | 書込み |
|---|---|---|---|
| `projects` | 非公開 | `is_public=1` のみ | 所有ワークスペースのみ |
| `ledgers` | 非公開 | `is_public=1` のみ | 所有ワークスペースのみ |
| `watches` | 非公開固定 | 不可 | 所有ワークスペースのみ |
| `ai_ledger` | 所有ワークスペース | 旧空欄行のみ互換読取 | 所有ワークスペース記録 |

台帳とプロジェクトの関係は所有権とは別である。一つの台帳を複数プロジェクトが参照できる既存の多対多モデルを維持し、公開台帳は別ワークスペースの公開プロジェクトから参照できる。非公開台帳を公開プロジェクトから漏らさないよう、グラフ・台帳詳細・エクスポートの JOIN でも可視性を再確認する。

## ブラウザへ返す能力境界

- API・HTML の所有キー `workspace_id` はブラウザへ返さない。代わりに一覧・詳細の研究資産へ `can_edit: true/false` を付け、UIは公開資産を閲覧・引用・自分のプロジェクトへの参照・台帳の分岐までに制限する。
- 公開プロジェクトでは、ノード、論証、前提、台帳接続などの書込みUIを隠す。公開台帳では本体更新UIを隠し、分岐を案内する。サーバー側の所有者検査が最終防衛線であり、UIの非表示だけを認可とみなさない。
- 公開モードの HTML/API はワークスペースごとに変わるため、静的ファイル以外へ `Cache-Control: no-store` と `Vary: Cookie` を付ける。静的ファイルはハッシュ付きURLでキャッシュ可能とする。

## 実装境界

- `projects.workspace_id`
- `ledgers.workspace_id`, `ledgers.is_public`
- `watches.workspace_id`
- `ai_ledger.workspace_id`
- 既存 SQLite には加算的 migration を適用する。既存の `provenance.locator` migration と同じく、余分な列を旧コードが無視できる形を保つ。
- `/api/` 応答には `Cache-Control: no-store` を付ける。
- 公開モードの非静的応答には `Cache-Control: no-store` と `Vary: Cookie` を付け、ブラウザ／リバースプロキシの匿名ワークスペース混線を防ぐ。
- `X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy`、`Permissions-Policy`、CSP Report-Only、CORP を付ける。
- ブラウザ入力の LLM API キーは `localStorage` から `sessionStorage` へ移し、ブラウザ再起動後まで残さない。サーバ DB にはキーも生プロンプトも保存しない。

## 検証方法

最低限、次を確認する。

1. `DIALEXIS_PUBLIC_INSTANCE=1` かつ秘密値なしで起動が拒否される。
2. 公開モードで Cookie が発行され、同じ Cookie のリクエストだけが非公開台帳・プロジェクトを読める。
3. Cookie を別値にしたリクエストから、非公開プロジェクト、台帳、ノード、論証、エクスポート、監視対象が 404 または空集合になる。
4. `is_public=1` のプロジェクト・台帳は別ワークスペースから読めるが、レスポンスに `workspace_id` がなく `can_edit=false` があり、書込みは 404 になる。
5. 一つの台帳を同じワークスペース内の二つのプロジェクトへリンクできる。
6. 旧 SQLite に列を追加しても、既存データがローカル単一利用者モードで読める。

## 未検証

- `DIALEXIS_SESSION_SECRET` のローテーション時のセッション移行は未実装。
- 署名 Cookie は匿名ブラウザ単位であり、Cookie を共有した利用者の区別、退会、アカウント復旧を保証しない。
- 公開モードの匿名利用に対するIP単位・Cookie単位のレート制限、DoS耐性、外部情報源の総量制御は未実装。広い告知の前に、Nginx／さくら側で `/api/` と高負荷探索エンドポイントへレート制限・接続数制限を設定する。
- CSP は既存テンプレートの inline script を壊さないため Report-Only であり、完全強制ではない。nonce 化は後続課題。
- 既存の公開サイトに本変更を反映した実環境 E2E は未実施。デプロイ前に HTTPS、Nginx、Cookie、二つのブラウザプロファイルで人間検証する。

## ロールバック

コードは Git の差分で戻せる。DB 列は加算的で、旧アプリは余分な列を無視する。ただし新規データの `workspace_id` を旧アプリで表示すると、旧アプリには認可境界がないため、公開サービスで旧コードへ戻す場合はサービスを非公開にしてから行う。DB バックアップを先に取り、旧コードへ戻したまま公開しない。
