# 実ブラウザE2E（/origin）— 第三者が再現するための手順

`origin.e2e.js` は、`/origin` の重力グラフとメニューを**実Chromiumで実際にクリックして**検証する。
pytest（`tests/`）はネットワーク非依存の純粋関数/parserのみを検査するのに対し、こちらはDOM/canvas/非同期導線を検査する。

## 前提
- Node.js（v22で確認）＋ `npm install playwright-core`
- Chromium バイナリ（Playwrightのキャッシュ）。無ければ `npx playwright install chromium`。
- Linux(WSL)で `libasound.so.2` 等が無い場合、sudo無しで `.deb` を展開し `LD_LIBRARY_PATH` に通す:
  ```
  apt-get download libasound2t64 && dpkg-deb -x libasound2t64_*.deb ext
  export LD_LIBRARY_PATH="$PWD/ext/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH"
  ```

## 実行
```
# 対象を起動（ローカル）: uvicorn app.main:app --port 8000
node origin.e2e.js http://127.0.0.1:8000     # or 本番 http://219.94.244.239:8000
```
先頭の `EXE`（chromiumパス）は環境に合わせて書き換える。

## 現状の検査範囲（23項目）と限界
- 検査: グラフ沈静/自動fit・クリックのジッター耐性・語ノード「深く調べる」で **その語(Entfremdung)に新規再中心**・著者「調べる」で実データ・外部リンク全て新タブ・概念固有次元が概念ごとに異なる 等。
- **限界（第三者へ）**: 普遍性検査は `Entfremdung × 深く調べる` の**1組のみ**。**全ノード種別 × 全階層 × 全メニュー の作用行列は未実装**。各操作後の「検索欄語・API要求語・カード主語・グラフ主語の一致」を全組で検査するよう拡張が必要（下記レビュー文書参照）。
- PASSだけでなく失敗結果・実行コマンド・ブラウザ版・selector・通信ログの保存も未実装。
