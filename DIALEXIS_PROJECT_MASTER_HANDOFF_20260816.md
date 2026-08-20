# Dialexis プロジェクト完全引継ぎ記録

**スナップショット:** 2026-08-19（Asia/Tokyo）更新
**対象:** Dialexis / 反省的哲学研究インフラ
**目的:** 本プロジェクトを全く知らないAIまたは開発者が、この一ファイルと現行リポジトリだけで、目的・背景・画面・コード・データ契約・失敗史・検証・公開運用を理解し、同じ状態を再現して継続開発できるようにする。

本書は、2026-08-14時点のPROJECT_REPRODUCTION_SPEC_20260814.md、2026-08-01時点の
Dialexis_再現継承ガイド、2026-08-11の全景クリック検証資料を基礎に、
現行コード、Git履歴、検証結果、公開反映結果を2026-08-18時点へ統合した
マスター記録である。古い資料と本書が矛盾する場合、設計意図はGENESIS.md、
実装状態は現行コードと実測テスト、公開状態は公開サーバー実測を優先する。

---

## 1. 現在地

### 1.1 正本と公開状態

| 項目 | 現在値 |
|---|---|
| 開発リポジトリ | /home/handa/dialexis |
| GitHub | https://github.com/hand-shinya/dialexis |
| ブランチ | main |
| 前回公開反映済みの製品コードHEAD | 2a418f1（公開コード本体: 7cca756、検証マーカー: 7cca756） |
| 現在のローカルHEAD | `git rev-parse HEAD`で確認。固定値ではなく、直近の検証マーカーを正本とする |
| 現在の検証SHA | `cat deploy/verified_sha.txt`で確認。正規デプロイ対象はこのSHA |
| 今回の公開状態 | 研究台帳実装を公式verifyで検証済み。VPS反映後に公開URLのhealthz/API/UIを再確認する |
| 入口修正（履歴） | 4e96a3b（ホーム・Question Doors・navを /originへ） |
| 公開デプロイ時の検証SHA | 7cca7567d045ffd6b8bc9a0a204faa4b4f9c69eb |
| 本書・回帰E2Eの追加 | `translation_history` 特別モード、台帳、公開E2Eを含む |
| origin/main | 本書更新後のmain。再現時は `git rev-parse HEAD` で確定 |
| 検証マーカー | deploy/verified_sha.txt |
| 公開URL | http://219.94.244.239:8000 |
| 公開アプリ | /opt/dialexis |
| 公開サービス | systemd dialexis.service |
| 作業フォルダー（Windows） | I:\GoogleDriveMirror\MyKnowledgeBase\Main\論考\哲学DESK |
| 作業フォルダー（WSL） | /mnt/i/GoogleDriveMirror/MyKnowledgeBase/Main/論考/哲学DESK |
| ライセンス | Code: AGPL-3.0 / Documentation: CC-BY-4.0 |

7cca756は、未登録語にも辞書・概念・書誌情報を自動抽出する「自動予備台帳」を追加した前回公開製品コードである。
2a418f1はその検証マーカーだけを記録した公開HEADであり、公式verify、VPS側pytest、サービス再起動、公開HTTP検査、
公開実ブラウザ11/11を完了している。現在のGit先端はgit logとgit rev-parseで確認し、公開runtimeの基準は2a418f1とする。
検証SHAはdeploy/verified_sha.txtで確認する。
vps_update.shは、検証SHA以降の差分がマーカーだけであることを確認する。

### 1.2 2026-08-16時点で直った最重要問題

1. 組み合わせ検索が空・遅延・検索源停止になっても、無言で次の提案だけへ
   流れず、条件・演算子・出所・状態・再試行・次Actionを表示する。
2. SearXNGが8秒以内に結果を返さなければ、同じ条件をWikipedia全文検索へ退避する。
   Wikipediaを一般Web全体の代替とは表示しない。
3. 主要メニューはACTION registry → dispatchAction → 正規作用の一本の経路を通る。
4. 未知Action、未宣言effect、非同期例外、空結果、部分JSONでも、
   元のMap/Contextを壊さず、同じ語から実行可能な次Actionを残す。
5. 非有機的肉体は、文字単位を主表示にせず、
   語全体 → 非 / 有機的 / 肉体 → 文字構成の順に表示する。

### 1.3 公開実測

~~~text
healthz: 200
/api/anatomy?q=非有機的肉体&lang=ja:
  semantic units = 非, 有機的, 肉体
  character layer = 補助層、priority 3
/api/combine?a=カール・マルクス&b=吉本隆明&op=and&lang=ja:
  has_results = true, nodes = 13, edges = 12, source = SearXNG
公開実ブラウザの組み合わせUI: 4/4 PASS
GET /api/translation-history?q=共同幻想&domain=philosophy&lang=ja:
  status = discovery, mode = automated_discovery
  term_map = 8, timeline = 9, reception_ledger = 5, sources = 14, next_actions = 3
公開実ブラウザ translation_history.e2e.js: 11/11 PASS
VPS pytest: 93 passed
~~~

公開ブラウザでは、Canvas上の中心語を実マウスクリックし、
「別の語と組み合わせる」→「労働」→「AND」を実行し、
「疎外」を「労働」で絞り込み（AND）の結果Mapへ遷移した。

### 1.4 2026-08-16の人間検証で発見した入口回帰（重要）

2026-08-16 22:56 JST、利用者のスクリーンショット
`F:\download\screenshot_2026-08-16-22_56_26.png` は、グラフと共通Menuが消えたように見える
旧画面を示した。これは実装が消滅した証拠ではなく、公開URLの `/explore` に到達していた。
`/explore` のHTMLはタイトル「資料探索」、`#explore-results`を持ち、旧来の資料カードを表示する。
一方、同じ公開サーバーの `/origin?q=非有機的肉体&lang=ja` は
`#origin-shell`、`#origin-graph`、`#graph-lens`、`graph-play`等を返し、
`/api/origin/graph`も正常にノード・辺を返していた。

原因は、中心機能を `/origin` に移した後も、次の3箇所が旧入口へ向いていたことだった。

1. ホームの検索form: `action="/explore"`
2. Question Doors: `/explore?q=...`
3. 上部の「探索」nav: `/`（そこから検索すると1へ戻る）

したがって、これは利用者の操作ミスではなく、中心機能の実装と入口の接続を完了しないまま
検証済みと扱った統合ミスである。AIによる内部E2Eが `/origin`を直接開いていたため、
人間のホームからの到達経路を検証対象から漏らしていた。

修正 `4e96a3b`:

- ホーム検索、Question Doorsを `/origin` に変更
- ボタン名を実際の遷移先に合わせ「意味Mapを開く」に変更
- 上部navを「原語探求（Map）」と「資料探索」に分離
- `/explore` は補助資料探索として保持し、常時「意味空間の相関図と共通Menu」への復帰導線を表示
- `tests/e2e/entry_routing.e2e.js` でホーム→Map、Canvas/Menu、旧画面→Map復帰を実ブラウザ検査

公開反映後の実測:

~~~text
ホーム検索 action=/origin                         PASS
Question Doors 5件以上が /origin                  PASS
ホーム検索→/origin                                PASS
/origin のshell・Canvas・共通Menu surface          PASS
/explore の資料探索表示                            PASS
/explore→/origin 復帰リンク                        PASS
entry_routing.e2e.js                                10/10 PASS
~~~

今後「グラフが消えた」と報告された場合は、まずブラウザの実URLが `/origin`か `/explore`かを
記録する。`/explore`自体は壊れていないが、意味空間Mapを検証するURLは
`http://219.94.244.239:8000/origin?q=非有機的肉体&lang=ja` である。

---

## 1.5 2026-08-17追加：翻訳・受容史／埋没語追跡の特別モード

2026-08-17、人間検証で示された「単純な文字検索・意味検索では見えない、翻訳で埋没した意味を原典から受容史まで追跡したい」という要求を、通常の `意味`・`解剖`・`埋没`・`外部` とは別のActionとして実装した。

### UI契約

1. `/origin?q=非有機的肉体&lang=ja` を開く。
2. 中心語または語ノードのMenuで `🧭 翻訳・受容史` を選ぶ。
3. 地図の中心・Contextを変えず、Action面に専用研究台帳を表示する。
4. 分野（哲学・思想／文学／科学・化学／芸術・美術）を選び、同じ条件で再調査できる。
5. 結果面に、中心問い、原語・翻訳語対応、保存／欠損／付加、時系列5W1H、受容史人物台帳、最強の反証、出所、次の調査を表示する。
6. `← メニュー`、通常の `この語で続ける` フッター、外部出所リンクを残す。取得条件の不成立時もMapと次の入口を保持する。

このActionは `ACTIONS.translationHistory` → `dispatchAction` → `gTranslationHistoryPanel` の一本の経路で実行する。中心移動・グラフ再構成を行わないため、「調べた結果、別の語へ勝手に移った」という意味の漂流を避ける。

### API・データ契約

- API: `GET /api/translation-history?q=<語>&domain=<哲学等>&lang=ja`
- データ: `app/data/translation_history_seed.json`
- 初期台帳: マルクス「非有機的肉体」問題（`unorganischer Leib`、`unorganischer Körper`、`unorganische Natur`、`Stoffwechsel`、英仏日訳、城塚・田中訳、吉本隆明、受容候補）。
- 返却状態: `ready`（curated台帳）、`discovery`（自動予備台帳）、`not_seeded`（情報源も取得できず調査入口のみ）。未知語・未整備分野には哲学台帳を流用せず、取得できた辞書・概念・書誌の候補と、登録・照合の次Actionを証拠階層つきで返す。
- 証拠階層: `confirmed`（本文・書誌の限定確認）、`bibliography_confirmed`（書誌確認）、`strong`（有力・要照合）、`interpretive`（解釈・再構成）、`candidate`（調査候補）、`unverified`（未確認）。
- 「書誌がある」ことと「該当頁の訳語・引用・影響関係を確認した」ことを分離する。資料の綜合に含まれる未確認主張は画面でも未確認／候補のまま表示する。

### 対象資料との接続

ユーザー指定の `I:\GoogleDriveMirror\MyKnowledgeBase\Main\論考\非有機的肉体`（WSL: `/mnt/i/GoogleDriveMirror/MyKnowledgeBase/Main/論考/非有機的肉体`）直下にある調査資料から、中心問い、1844年草稿、Grundrisse、Stoffwechsel、岩波訳、吉本隆明、受容史候補、未確認事項を抽出した。主なローカル参照は `compass_artifact_wf-3549...`、`deep-research-report (2).md`、`吉本隆明のマルクス理解：非有機的肉体を中心に.md`、`非有機的肉体とは何か論考計画書 v1.2.md`。これらは研究入力であり、外部原典・NDL・CiNii等での再照合を要する。

### 1.5.1 2026-08-17追加：全語・全窓への一般化

初期実装が「非有機的肉体」の詳細台帳だけを表示する状態だったため、別語・別ノード・別パネルでは
利用者から「反応しない」と見える余地があった。2026-08-17に次を修正した。

1. `ACTIONS.translationHistory` を wordだけでなく、original / language / related / author / work の
   全実体ノードの共通Menu（上部帯・popup）へ移動した。domainなど構造ノードは語ではないため対象外。
2. 全Actionパネルの「この語で続ける」フッターと、空結果・取得保留時の `noMiss` にも
   `🧭 翻訳・受容史` を追加した。どの窓からでも同じdispatcherへ到達する。
3. 台帳未登録の語・分野でも無反応にせず、その語を題名・中心問いにした「新規調査台帳」準備面を返す。
   原語、版、翻訳、受容を順に揃える初回手順と、Wiktionary、NDL、CiNii、Google Booksの
   query-specificな探索入口を表示する。これらは証拠ではなく候補入口である。
4. 既存の「非有機的肉体」台帳は引き続き哲学分野のseedとしてのみ使用し、未知語・文学・科学・芸術へ
   哲学データを流用しない。

### 現時点の検証

~~~text
Python: 93 passed（2026-08-18時点。前版の記録92件は履歴として残す）
翻訳・受容史 Python: 未登録語の調査workspace・query-specific出典候補を含む
translation_history.e2e.js: 11/11 PASS
内容確認: 中心語不変、原語・翻訳語、5W1H、受容史、反証、出所、未整備科学分野、全実体kind、別語、Menu復帰
決定論的UI E2E: 全件PASS
統合 origin: 21/23（従来どおりnetwork依存の情報表示）
検証SHA: deploy/verified_sha.txt に記録された 7cca7567d045ffd6b8bc9a0a204faa4b4f9c69eb
~~~

公開反映後の実測: `http://219.94.244.239:8000/origin?q=非有機的肉体&lang=ja` で、Menu→`翻訳・受容史`→専用API→科学分野の未整備表示→`←メニュー`、さらに人物・著作・原語・言語・関連語の共通Actionと別語「自由」の新規調査台帳を実ブラウザ操作し、11/11 PASS。VPS `pytest 93 passed`、`healthz HTTP:200`。未知語「共同幻想」の自動予備台帳は次節に記録する。人間検証の入口URLはこのURLを使う。

### 1.5.2 2026-08-18追加：未知語の自動予備台帳

前節までの未知語画面は、語専用の調査ワークスペースと情報源リンクを示すだけで、利用者が最初の抽出・整理を自分で行う必要があった。これは「辞書の組み合わせと情報源の連携で、まず現時点の候補を整理して見せてほしい」という要求に対して不十分だった。そこで `7cca756` で、未知語でも取得可能な既存情報を先に台帳化する層を追加した。

#### 自動抽出の流れ

~~~text
GET /api/translation-history
  ├─ curated seed に明示一致 → ready（確定台帳）
  └─ 一致しない語
      ├─ /api/origin       → 辞書義、意味単位、語源連鎖、多言語表記、人物候補
      ├─ /api/anatomy      → 意味のまとまり、語源的構成要素
      └─ /api/explore      → NDL、CiNii、OpenAlex、SEP等の書誌・研究候補
          ↓
      _history_discovery_from_sources が証拠レコードへ正規化
          ↓
      discovery（自動予備台帳）または not_seeded（検索入口へ退避）
~~~

自動予備台帳は、原語・翻訳語候補、保存／欠損／付加、時系列5W1H、受容史人物候補、反証、参照先、次の検証行動を同じ画面に配置する。自動生成したものを「研究史が確定した」とは扱わず、辞書・Wikidataは `candidate`、NDL/CiNiiの書誌は `bibliography_confirmed`、本文のページ・引用・影響関係は未確認として残す。画面上部にも「これは最初の自動整理」と明示し、情報源の選定計画を必ず表示する。

#### 共同幻想の公開実測

2026-08-18、公開VPSのローカルHTTP APIを読み取り確認した結果は次のとおり。

~~~text
query=共同幻想 / domain=philosophy
status=discovery / mode=automated_discovery
term_map=8 / timeline=9 / reception_ledger=5 / sources=14 / next_actions=3
抽出された語形例: 共同幻想、共同、幻想、communal fantasy
人物候補例: カール・マルクス、ウラジーミル・レーニン、ジークムント・フロイト、吉本隆明、岸田秀
書誌候補例: 1966年「禁制論--共同幻想論-1-」、2005年「共同幻想論 : 『文芸』初出」、2016年「吉本隆明と『共同幻想論』」
~~~

上記は「翻訳・受容史の完成結果」ではなく、辞書・概念・書誌の自動初回整理である。とくに人物候補はWikidata上の関連候補、書誌候補はNDL/CiNii/OpenAlexの検索記録であり、実際の引用・影響・訳語対応を意味しない。次に原典本文、版、訳者、該当頁を人間が照合することが正しい運用である。

#### 停止しないための実装

外部情報源が固まったときに `asyncio.wait_for` のキャンセル完了待ちまで画面を止める問題があったため、探索タスクをワーカーへ隔離し、各情報源を8秒で打ち切って取得済み部分だけを正規化する。フロント側の専用API待機は45秒だが、通常は自動台帳または query-specific な調査入口へ退避する。正規化例外も空白画面へせず `not_seeded` に戻す。OpenAlexの哲学レンズとSEP候補は哲学分野でのみ表示し、科学・文学・芸術へ哲学結果を流用しない。

#### 検証・公開

~~~text
公式 verify.sh: Python 93 passed、決定論的E2E全件PASS、translation_history.e2e.js 11/11 PASS
VPS vps_update.sh: pytest 93 passed、healthz 200
公開ブラウザ: http://219.94.244.239:8000 で translation_history.e2e.js 11/11 PASS
製品コード: 7cca756 / 検証マーカー: 2a418f1（markerが指す検証SHAは7cca756）
~~~

### 1.6 2026-08-19追加：研究台帳を独立した再利用資産として実装

利用者との設計確認で、単純な語検索、翻訳・受容史の調査台帳、研究プロジェクトを
同じものとして扱ってはならないことを確定した。特に、ある台帳を複数の研究プロジェクトが
参照する一方、一つの研究プロジェクトが複数台帳を使うという双方向の再利用が必要だった。
この関係を画面だけで模倣せず、SQLiteに永続化した。

#### 役割の分離

~~~text
単純検索
  入力語 → 外部情報源から現在の結果を表示（保存しない）

翻訳・受容史表示
  入力語 + 分野 → curated seed または自動予備台帳を一画面に整理（表示段階）
  「この結果を新しい研究台帳として保存」→ 永続台帳へ昇格

研究台帳（Research Ledger）
  原語、訳語、版、引用、受容、主張、解釈、未解決課題、出典を証拠レベル付きで保持
  一つの台帳を複数プロジェクトから参照可能

研究プロジェクト（Research Project）
  利用者自身の問い、主張、証拠、反証、解釈、判断を研究過程グラフとして保持
  複数台帳を背景・根拠・翻訳比較・反論・方法・文脈として参照可能
~~~

台帳はプロジェクトの親ノートではなく、独立した共有知識資産である。プロジェクトでの
解釈や主張は台帳本体を自動変更しない。必要な記録だけを「このプロジェクトで使う」として
選択し、プロジェクト側に採用関係を記録する。この分離がないと、同じ翻訳上の発見を複数研究で
使うたびに複製・改変され、どれが原記録か分からなくなる。

#### 永続モデルと版

`app/db.py`に追加したテーブルは次のとおり。既存テーブルを削除・再作成しない追加型マイグレーションで、
既存のプロジェクトDBを保持したまま初回起動時に作成される。

~~~text
ledgers                 台帳本体（title, central_question, subject, domain, status, version）
ledger_versions         台帳のスナップショット（台帳の現在状態をJSONで保存）
ledger_entries          台帳内の原語・版・訳語・受容・主張・解釈・課題等の記録
ledger_sources          出典（URL、書誌、取得時刻、locator、引用、役割）
ledger_entry_sources    記録と出典の多対多
ledger_relations        記録間の翻訳・引用・支持・反証等の関係
ledger_tasks            台帳から派生する次の照合課題
project_ledger_links    プロジェクトと台帳の多対多（role, pinned_version）
project_ledger_entries  プロジェクトが採用した台帳記録（relation, adopted_version, use_note）
~~~

固定語彙は`app/db.py`にある。台帳状態は`draft / active / reviewed / archived`、記録種別は
`term / edition / translation / source_text / reception / claim / interpretation / open_question / note`、
証拠レベルは辞書確認・書誌確認・原典本文確認・翻訳本文確認・受容史確認・strong・interpretive・candidate・unverifiedである。
未確認の記録をconfirmedへ格上げする自動処理はない。

台帳を更新するとバージョンを増やし、プロジェクト接続時の`pinned_version`を保存する。
したがって、台帳が後で更新されても、過去のプロジェクトがどの版を参照したかを追跡できる。
必要な場合は`POST /api/ledgers/{id}/fork`で親台帳を残した分岐を作る。

#### APIと画面導線

~~~text
GET    /api/ledgers
GET    /api/ledgers/{id}
POST   /api/ledgers
PATCH  /api/ledgers/{id}
POST   /api/ledgers/{id}/entries
PATCH  /api/ledger-entries/{id}
POST   /api/ledgers/{id}/fork
POST   /api/ledgers/from-translation-history
GET    /api/projects/{id}/ledgers
POST   /api/projects/{id}/ledgers
DELETE /api/projects/{id}/ledgers/{ledger_id}
POST   /api/projects/{id}/ledger-entries
GET    /api/projects/{id}/ledger-entries
~~~

`/desk`では研究プロジェクト一覧と研究台帳一覧を同時に見られる。台帳画面`/ledger/{id}`では
台帳の問い、版、記録、出典、利用プロジェクトを表示し、同じ台帳を別プロジェクトへ接続できる。
プロジェクト画面`/project/{id}`では参照台帳、役割、固定版、接続解除を表示する。
翻訳・受容史の結果面には保存ボタンと既存台帳への導線があり、保存後に台帳画面へ移動できる。
上部navにも研究デスクへの入口を追加した。

#### 実装で経験した失敗と回帰修正

1. 以前の未登録語画面は、ユーザーが自分で空の調査台帳を作る入口だけを表示していた。辞書・概念・書誌から
   取得できる予備情報まで先に整理してほしいという要求に対し不十分だったため、`discovery`表示と
   「この結果を新しい研究台帳として保存」を追加した。
2. 台帳navを追加した直後、Canvasの実クリックが層1・2だけ成功し、層3・4が前の層2を開いた。
   原因は、実行結果を知らせる固定トーストが新しいヘッダー高さの分だけCanvas上に重なり、クリックを遮っていたことだった。
   通知は表示専用で操作対象ではないため、`#dx-toast { pointer-events: none; }`とし、台帳導線を残したまま
   `canvas_real_click.e2e.js`を13/17から17/17へ回復した。
3. 外部レンズE2Eは`networkidle`待ちで30秒止まることがあり、さらに対象URLが「資本論」ではなく誤った文字列だった。
   正しいUTF-8 URL、`domcontentloaded`、Graph構築完了の明示待機へ修正した。これは外部取得完了を画面遷移の条件にしない
   という本番UX契約にも合う。

#### 検証結果（2026-08-19）

~~~text
Python tests: 96 passed
ledger.e2e.js: 5/5 PASS
translation_history.e2e.js: 11/11 PASS
canvas_real_click.e2e.js: 17/17 PASS
failure_injection.e2e.js: 9/9 PASS
lenses_full.e2e.js: 7/7 PASS
applications_wave.e2e.js: 3/3 PASS
全 verify.sh: 成功（決定論的E2E全件PASS）
統合 origin: 19/23 または外部応答状態により変動（network依存・gate非対象）
~~~

#### 長文入力との境界（未実装）

長文・センテンス入力は価値があるが、今回の台帳実装には混ぜていない。まず単語単位の検索、台帳、
プロジェクト参照関係を安定させることを優先した。将来の文章入口は、入力された原文を`source_text`として
保存し、候補語・前後文脈・関係候補を抽出した後、ユーザーが台帳へ採用する語を確認する別フローにする。
文章から自動抽出した語を即座に研究事実へ格上げしてはならない。現時点で文章入力、文脈抽出、複数語の自動台帳化は
**未実装・未検証**である。

## 2. 目的と背景

### 2.1 一行定義

Dialexis（ディアレクシス、διάλεξις＝論究）は、哲学的な問いを、
より深く、根拠あり、反証可能で、共有可能な研究過程へ変換する
反省的哲学研究インフラである。

一つの答えを返して終わるサイトではない。入力語の意味、原語、
翻訳で失われた差異、関係する人物・著作・言語、比較、反証、
研究デスクの問いへ進む道を残す。

### 2.2 解こうとしている問題

異なるニュアンスを持つ複数の原語が、翻訳で一つの訳語へ集約されると、
元の語の歴史的背景、概念差、使用場面、他概念との接続が見えなくなる。
日本語だけで疎外、弁証法、矛盾などを検索しても、訳語の説明は得られるが、
原語の意味空間、語形成、思想史上の分岐が隠れることがある。

Dialexisは内部に巨大な百科事典を作って解決しない。無料で公開された
外部情報源へ、出所と取得時刻を付けて接続するレンズとして解決する。
内部に保存するのは研究過程、来歴、短期キャッシュ、AI台帳であり、
情報源そのものを所有することではない。

### 2.3 利用の基本連鎖

~~~text
利用者が語を入力
  ↓
一般的意味と原語・多言語・思想家・関連概念を同じ地図に置く
  ↓
ノードを選び、全体像、解剖、並置、多言語、組み合わせ等を選ぶ
  ↓
出所と取得時刻を見ながら意味差や不確実性を把握する
  ↓
別の語、人物、著作、反証、研究デスクへ進む
  ↓
Markdown / JSON-LD / BibTeX / CSL JSONで持ち出す
~~~

### 2.4 これは何ではないか

- 哲学版Wikipediaではない。
- 哲学版Google Scholarではない。
- 出典のない流暢な回答だけを返すChatGPT置換ではない。
- 特定個人の思考法を唯一の正解として押し付けるOSではない。
- 根拠の薄い美しい思想マップだけを作るサイトではない。
- 内部に百科事典を蓄積して古くなる静的DBではない。
- 滞在時間や自動遷移を目的にする娯楽アプリではない。

### 2.5 七公理

GENESIS.mdが最上位の思想的正典である。次の公理を破らない。

| 公理 | 内容 | 実装への翻訳 |
|---|---|---|
| 1 問いの変換 | 情報消費で終わらせず問いを変える | 結果面に次の探索入口 |
| 2 使用即貢献 | 一人でも価値がある | コミュニティを前提にしない |
| 3 レンズ | 外部の生きた知識を見る | connectors + provenance + cache |
| 4 鮮度 | 外部情報に取得時刻を刻む | retrieved_at / queried_at |
| 5 退化階梯 | 無料・鍵不要Level 0を持つ | LLM無しでも探索・反証 |
| 6 AI透明性 | AI由来、確度、台帳を明示 | localStorage、ai_ledger |
| 7 撤退可能性 | 標準形式で持ち出せる | SQLite、Markdown、JSON-LD等 |

固定の確度語彙:

~~~text
confirmed / high_probability / unverified / interpretive_hypothesis / speculation
確定 / 高蓋然 / 未確認 / 解釈仮説 / 思弁
~~~

下位原則として、無中心、中立、breadthをAIで狭めない、
source-grounding、埋没の明示、語と著者の分離、実ブラウザ検証、
作用の普遍性を守る。

---

## 3. 場所と文書の関係

コードのGit正本は /home/handa/dialexis。ユーザーの指示・背景・引継ぎ資料は
I:\GoogleDriveMirror\MyKnowledgeBase\Main\論考\哲学DESK にある。
WSLでは /mnt/i/GoogleDriveMirror/MyKnowledgeBase/Main/論考/哲学DESK。

本書は同じ内容を次の二か所に配置する。

~~~text
/home/handa/dialexis/DIALEXIS_PROJECT_MASTER_HANDOFF_20260816.md
/mnt/i/GoogleDriveMirror/MyKnowledgeBase/Main/論考/哲学DESK/DIALEXIS_PROJECT_MASTER_HANDOFF_20260816.md
~~~

読む順序:

1. 本書。
2. リポジトリのGENESIS.md、README.ja.md。
3. 現行コード、Git履歴、verify.sh。
4. docs/ARCHITECTURE.md、OPERATIONS.md、BUILD_FROM_ZERO.md、
   TROUBLESHOOTING.md、USER_GUIDE.ja.md。
5. 作業フォルダーのAGENTS.md、CLAUDE.md、CONTEXT.md。
6. 過去の個別検証資料。これは現行状態ではなく失敗史として読む。

既存資料の役割:

~~~text
PROJECT_REPRODUCTION_SPEC_20260814.md
  8月14日仕様。全API/UI/DB/意味分解の詳細。ただし時点依存の未deploy記述が残る。
_AI/Dialexis_再現継承ガイド_20260801-155532.md
  8月1日までの背景、失敗史、dispatcher、Panorama。
_AI/アーキテクチャ全体像202707291452.md
  7月29日時点の再構築レベル構造。
_AI/開発台帳.md
  追記型の一次時系列ログ。
継続用_Dialexis全景クリック契約_検証_20260811-1742.md
  全景実クリック検証の方法と、テスト側失敗の分解。
_AI/原理原則.md
  作業フォルダー側P0〜P11。
~~~

AGENTS.mdは指示ファイルであり手動編集禁止なので、新しい記録は本書へ置く。

---

## 4. 技術構成と再現

### 4.1 スタック

~~~text
OS                 Linux / WSL2で確認
Python             現行3.12.3、3.11以上を想定
Backend            FastAPI + Uvicorn + Jinja2
Frontend           vanilla JavaScript + CSS、ビルドなし
描画               Canvas 2D自前force-directed graph
Database           SQLite一ファイル
HTTP               httpx AsyncClient
外部接続           無料・原則APIキー不要の公開源
~~~

requirements.txt:

~~~text
fastapi>=0.110
uvicorn[standard]>=0.29
httpx>=0.27
jinja2>=3.1
python-multipart>=0.0.9
~~~

npm、webpack、React、外部DB、必須LLMキーを追加してはならない。

### 4.2 起動

~~~bash
git clone https://github.com/hand-shinya/dialexis.git
cd dialexis
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
~~~

http://127.0.0.1:8000 を開く。APIキー無しで探索、原語、Map、
組み合わせ、反証Level 0、研究デスクが動く。

### 4.3 環境変数

| 変数 | 用途 | 現行既定 |
|---|---|---|
| DIALEXIS_DB | SQLiteの場所 | data/dialexis.db |
| DIALEXIS_CONTACT | 外部API用User-Agent連絡先 | 空 |
| SEARXNG_URL | 組み合わせの主検索源 | http://127.0.0.1:8888 |
| DX_PORT | verify/run_localのポート | verify=8099、run_local=8815 |
| DX_CHROMIUM | Chromium実体 | /home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome |
| NODE_PATH | playwright-coreの解決先 | 現環境のnpxキャッシュ |
| LD_LIBRARY_PATH | Chromium補助ライブラリ | 現環境のalsa展開先 |

古い資料のSEARX_URLではなく、現行コードはSEARXNG_URLを読む。

### 4.4 E2E環境

製品自体はNode不要だが、E2Eはplaywright-coreとChromiumが必要。

~~~bash
cd /home/handa/dialexis
export DX_CHROMIUM=/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome
export NODE_PATH=/home/handa/.npm/_npx/e41f203b7505f1fb/node_modules
export LD_LIBRARY_PATH=/home/handa/.claude/jobs/b4518c70/tmp/alsa_ext/ext/usr/lib/x86_64-linux-gnu
node tests/e2e/run_local.js tests/e2e/semantic_units.e2e.js
~~~

新しいマシンでplaywright-coreやlibasoundが無い時は、
E2E環境の不足と製品不具合を分けて診断する。
run_local.jsはUvicornを子プロセスとして起動し、一時SQLite、
healthz待ち、指定Chromiumテスト、終了処理を一つにする。

---

## 5. リポジトリ地図とデータ経路

~~~text
GENESIS.md                         憲法・七公理・再構築プロンプト
README.md / README.ja.md           概要・起動
requirements.txt                   Python依存
verify.sh                          公式検証とverified_sha生成
app/main.py                        ページ、API、外部源オーケストレーション
app/db.py                          SQLiteスキーマ
app/static/app.js                  全UI、Graph、Action、ViewState
app/static/style.css               レイアウト・面・配色
app/templates/                     Jinja2ページ
app/i18n/                          ja/en
app/data/                          seed、反証、原語クラスタ、思想家系譜
app/connectors/                    外部APIごとの取得・整形
app/llm/adapter.py                 BYOキーLLMの中継とガード
app/harvester.py                   Watcherのsystemd/cron本体
tests/test_*.py                    Python機能・静的gate
tests/e2e/*.e2e.js                 実Chromium・実DOM検証
tests/reach/*                      gate外の到達効果・Panorama
deploy/vps_update.sh               pull、SHA gate、pytest
deploy/vps_deploy.sh               更新、systemd再起動、healthz
deploy/verified_sha.txt            検証済みコードSHA
deploy/systemd/                    dialexisとharvesterのunit/timer
docs/                              構造・運用・構築・改善・費用
_backups/                          復旧資料。削除禁止
~~~

データ経路:

~~~text
Browser
  → Jinja2 + app.js + style.css
  → fetch JSON
  → FastAPI app/main.py
  → connectors
  → 外部無料API + SQLite api_cache

研究デスク → SQLite projects/nodes/edges/provenance/arguments
Watcher timer → app/harvester.py → harvester_status.json
LLM設定 → browser localStorage → 一時中継 → ai_ledger（キーは保存しない）
~~~

connectors/base.pyの共通封筒:

~~~text
成功: source, retrieved_at, cached, error=null, data
失敗: source, retrieved_at, cached=false, error, data=null
キャッシュ: api_cache、既定TTL 3600秒
HTTP: User-Agent、timeout 25秒
429/503: 最大3回、Retry-After尊重、待機最大5秒
~~~

失敗を黙って成功に変えない。UI側で生例外を隠し、
原因と次Actionを人間に説明する。

---

## 6. 画面・Menu・Actionの契約

### 6.1 ページ

~~~text
/                    問いの入口、Question Doors。検索とDoorは /origin へ送る
/explore             資料・文献の補助横断探索。Map復帰導線を常設
/origin              主入口。原語探求、言語Map、概念全景、共通Menu
/desk                研究デスクと反証
/project/{pid}       研究過程編集
/watches             新着監視
/levels              7段階読解
/deepsearch          深掘り探索プロンプト
/settings            LLM設定
/donate              公共知とAI計算費用
/about               About
/healthz             ヘルスチェック
~~~

### 6.1.1 入口の遷移契約

通常利用者の主経路は次でなければならない。

~~~text
ホーム入力語 ─┐
Question Door ─┼─> /origin?q=... ─> origin-shell + Canvas + graph-lens + Menu
上部「原語探求」┘

上部「資料探索」 ─> /explore?q=... ─> 資料結果 + 「原語探求（Map）」復帰リンク
~~~

`/explore`を中心Mapの代替と説明してはならない。`/explore`が表示された場合は、
資料横断検索を意図した場合を除き、表示中のMap復帰リンクを使う。

### 6.2 /origin

~~~text
上部: ブランド、nav、検索語、原語から問い直す、新タブ設定
shell: 戻る、進む、説明、遊ぶ、棚、俯瞰、今の見方badge
Map: Canvas 2D、層付きノード・エッジ
Context: 右ドロワー、概念全景、目次、出所、次にたどれる実体語
Action: Menu選択の結果、成功・空・失敗の説明と次Action
~~~

実体語・人物・著作はterm、kind、stable idを持つ。
domain、件数、カテゴリ見出し、q無し構造ノードは実体語として扱わない。
Graphがrootだけ、空、外部失敗でもshellは消さない。

### 6.3 レンズ

~~~text
all          俯瞰（すべて）
thinkers     思想家と著作
original     原語と語源
languages    世界の言語
relations    類語・対義（星座）
domains      意味の領域
spheres      文化圏
applications 応用・波及
usage        使用例・引用
timeline     時代・変遷
~~~

意味、多言語、埋没は中心を変えずPanelを開く。
中心を変えるのは「中心に据える」と、必要時に別語へ適用する見方だけ。

### 6.4 共通MenuとAction ID

~~~text
panorama     全体像を見る
center       中心に据える
combine      組み合わせ
lens         見方
meaning      意味
anatomy      解剖
contrast     並置
collapse     埋没
multilingual 多言語
colloc       共起
external     外部で調べる
shelf        棚
deepsearch   深掘り
newtab       新タブ
author       著者を調べる
authorNote   系譜メモ
dimension    探究の次元
focus        この分岐を中心に
hl           経路を強調
resetFocus   全体に戻す
~~~

人物・著作はauthor/authorNoteを使い、語源エンジンへ流さない。
domainはfocus/resetFocus/hl/deepsearchを使う。
エッジの比較・説明もAction IDを持つ。soonやfn closureだけの
無作用項目は許さない。

### 6.5 組み合わせ

~~~text
and     aをbで絞る
not     aからbを除外
or      aとbの周辺を合わせる
compare aとbを共有/固有に並べる
semand  aの意味アンカーをbの文脈で絞る
~~~

成功なら結果Map。空・退避・失敗なら元Mapを結果と偽らず、
条件、演算子、出所、状態、再試行、同条件外部検索、次Actionを表示する。

---

## 7. API・意味単位・SQLite

### 7.1 主なAPI

~~~text
GET /api/explore?q=&lang=
GET /api/origin?q=&lang=
GET /api/origin/graph?q=&lang=
GET /api/anatomy?q=&lang=&own=0|1
GET /api/variants?q=&lang=
GET /api/dimensions?q=&lang=
GET /api/author?name=&lang=
GET /api/collocations?term=&lang=de
GET /api/applications?q=&lang=
GET /api/usage?q=&lang=
GET /api/timeline?q=&lang=
GET /api/culture?q=&lang=
GET /api/websearch?q=&lang=
GET /api/gravity?q=&lang=
GET /api/combine?a=&b=&op=&lang=
GET/POST /api/projects...
GET/POST /api/counter
GET /api/levels、POST /api/levels/llm
GET/POST /api/watches...
GET /api/ledger
~~~

/api/originはgeneral_meaning、concept_origin、originators、word_origin、
chain、breadth、relations、associated、sources、queried_at等を返す。
表示sourceはsources、wiktionary_url、wikidata_url、article_url等から
確定できるものだけにする。

### 7.2 /api/anatomyのsegment_layers

既存のcomponents/chainは後方互換で残し、segment_layersを正規表示契約とする。

~~~json
{
  "term": "非有機的肉体",
  "segment_layers": [
    {
      "level": "whole",
      "label": "語全体",
      "priority": 0,
      "units": [
        {
          "text": "非有機的肉体",
          "role": "whole_term",
          "children": ["非","有","機","的","肉","体"],
          "source": "user-term",
          "confidence": "high"
        }
      ]
    },
    {
      "level": "semantic",
      "label": "意味のまとまり",
      "priority": 1,
      "units": [
        {"text":"非","role":"prefix","children":["非"],"confidence":"high"},
        {"text":"有機的","role":"lexical_unit","children":["有","機","的"],"confidence":"high"},
        {"text":"肉体","role":"lexical_unit","children":["肉","体"],"confidence":"high"}
      ]
    },
    {
      "level": "character",
      "label": "文字構成（補助）",
      "priority": 3,
      "units": [
        {"text":"非","role":"character"},
        {"text":"有","role":"character"},
        {"text":"機","role":"character"},
        {"text":"的","role":"character"},
        {"text":"肉","role":"character"},
        {"text":"体","role":"character"}
      ]
    }
  ],
  "queried_at": "取得時刻"
}
~~~

意味層は語源学的唯一解ではない。既知の境界を先に採用し、
未知の残りを無根拠に一文字へ分割せず、まとまりとして保持する。
アルファベット語でcomponentsがある場合はmorphology層を使う。
文字辞書義は語全体の意味ではない。

中心コード:

~~~text
app/connectors/etymology.py
  _semantic_cjk_units
  _semantic_layers
  semantic_layers
  _cjk_anatomy
  _deepen_chain
  _is_langname
  anatomy
app/static/app.js
  segmentLayersHtml
  gAnatomyPanel
  gContrastPanel
~~~

### 7.3 /api/combineの退避

~~~text
SearXNGをdrop_commercial=trueで試す
  結果あり → source=SearXNG
  空または8秒timeout → Wikipedia全文検索を同じ条件で試す
  それも空/失敗 → has_results=false、source状態をnoteへ
~~~

Wikipediaを一般Webと偽らない。結果にはnodes、edges、note、
has_results、queried_atを含める。

### 7.4 SQLite

~~~text
projects
nodes: question, claim, evidence, counterclaim, uncertainty,
       interpretation, decision, note, source
edges: supports, contradicts, answers, refines, derives_from,
       cites, about, responds_to
provenance: source_name, source_url, retrieved_at, quote, locator, note
watches / watch_hits
api_cache
ai_ledger
arguments / argument_premises
~~~

確度、origin、人間/AI/外部、status、argument validity/soundnessは
app/db.pyの固定語彙を使う。研究データはMarkdown、JSON-LD、BibTeX、
CSL JSONへexportできる。

LLMキーはlocalStorageのdialexis_provider、dialexis_model、
dialexis_keyだけに置き、サーバーDB・ログ・台帳へキーや完全プロンプトを保存しない。

---

## 8. 単一Dispatcherと失敗安全

### 8.1 正規対象とeffect

すべての対象を次へ正規化する。

~~~text
{ term, label, kind, lang, id, surface, layer }
~~~

effect:

~~~text
context  Contextを置換
center   Map中心とContextを変更
map      Mapを描き替えContextを保持
action   Action面を置換
store    保存だけ
newpage  元画面を変えず新規ページ
~~~

### 8.2 dispatchActionの契約

~~~text
1. Action IDとeffectの存在を確認
2. targetを正規化
3. 前のPanel/Combine/Contextを保存
4. NAV.txn=true
5. ACTIONS[action].runをawait
6. 例外なら前状態へrollbackし、元Map/Contextを保持
7. run=falseなら説明付きfallbackを残し、架空の成功履歴を積まない
8. commits=false以外は確定後navCommitを一回だけ行う
9. Toastと次Actionを表示
~~~

表示面がgWordAspect、gAnatomyPanel、gCombineRun、originRecenter等を
直接呼ばない。上部帯、popup、edge、Panel footer、noMiss、本文リンク、
見方一覧、遊ぶ、棚をすべてdispatchActionへ通す。

### 8.3 ViewState

~~~json
{
  "q": "中心語",
  "lens": "all",
  "focus": "stable-id",
  "context": {"term": "選択語"},
  "panel": {"action": "anatomy", "term": "語"},
  "combine": {"a": "語A", "b": "語B", "op": "and"}
}
~~~

hover、loading、txn中の一時状態は履歴へ入れない。
1ユーザー操作＝1commit。復元失敗時はindexを元へ戻す。
focusはstable IDを優先し、表示labelだけで復元しない。

### 8.4 共通失敗面

noMiss、softLine、_dispatchRecoveryは、失敗を空白で終わらせない。
ユーザーには、Action名、追加確認対象、元Map/Context保持、
同じ語から実行可能な次Action、可能なら出所・取得時刻・再試行を表示する。

生のJavaScript例外、API内部trace、推測source、押しても何も起きない
soonボタンを表示しない。

---

## 9. 実際の失敗体験と修正

### 9.1 カール・マルクス AND 吉本隆明

**症状:** ユーザーがカール・マルクスを選び、「別の語と組み合わせる」、
吉本隆明、ANDを実行した。一般検索なら普通にできる操作なのに、
結果が確定したのか、空だったのか、検索が中止されたのかが説明されず、
AIのコメントもないまま次の提案だけが出た。

**原因:** SearXNGは空・timeout・停止を返しうる。旧UIは専用のcombine
outcome面を持たず、一般的なnoMissへ流れた。次Actionの存在と、
直前Actionの説明を混同していた。

**修正:** SearXNGを8秒で切り上げ、Wikipedia全文検索へ同条件退避。
APIにhas_results、note、source、queried_atを残し、成功時は結果Map、
空/失敗時は条件・演算子・出所・再試行・同条件外部検索・次Actionを表示。

**検証:** combine_resilience 6/6、公開combine_ui 4/4、
公開AND API nodes 13、edges 12。

### 9.2 Menuが無反応・不安定

初期原因はpointerdownでMenuを閉じ、後続clickが届かなかったこと、
数pxのマウス移動を即ドラッグと判定したことだった。
後の回帰ではgMenuEdgeがsoon/fnだけでAction IDを持たず、
クリックして閉じるだけの項目を作った。

ドラッグ閾値、pointerup選択、Action ID、単一Dispatcher、
test_no_noop_menu_items、実DOM/実マウスで是正した。
「たまに動かない」はAPIだけでなくイベント順序、座標、面の重なり、
状態所有、Action IDを分解して再現する。

### 9.3 停止・古い語の混入・二重履歴

非同期応答の競合、要求ID不足、複数状態源、途中commitで、
前の語のContextが次の語へ流れ、loadingが止まり、遅い応答が新操作を
上書きした。async Actionのreturn忘れで1操作二commitも起きた。

要求token、stale破棄、NAV.txn、Context/Panel/Combine rollback、
成功後一回commit、asyncのawaitを実装した。

### 9.4 一文字分解

非有機的肉体が非/有/機/的/肉/体となり、機の辞書義が語全体の
意味分析に見えた。文字構成、形態素、語源構成、意味グループを
同じ層に置いたことが原因である。

segment_layersを導入し、語全体、意味層、語源構成、文字補助を分離した。
意味層は非/有機的/肉体。未知の残りは一文字へ分割しない。

### 9.5 代替の意味契約違反

別endpointへ移るだけのfallbackは、元の問いに答える保証がなかった。
埋没を語源で埋める、共起を翻訳語一覧で埋める等が発生した。
anatomy、contrast、collapse、colloc、multilingualの意味契約を分け、
同じ契約を満たす実取得だけを代替とする。

提供元不明時にWiktionaryを推測表示した時期もあった。
現在はsourcesと確定URL、応答のretrieved_at/queried_atだけを根拠とする。

### 9.6 否定文字列の漏れ

「できません」「見つかりません」を列挙置換しても、
「引けません」「no data」が漏れた。列挙でなくapp.js/main.py全走査の
静的gateへ転換した。gateの否定語彙自体の完全性は未検証として残す。

### 9.7 Panoramaテストの誤検出

1920幅browser closed、外部popupのunclickable、txn中の早すぎるsettled、
details再オープン漏れ、stale面クリックは、テスト側が原因だった。
viewportごとにbrowser再生成、クリック前popup待受、txn/loading/Action/nav
安定判定、details復元、stable signature再解決へ改めた。

全Panorama BFSは4時間で完走せず、L3 2459/21484で打ち切り。
これは製品全件PASSではなく、未検証のまま引き継ぐ。

### 9.8 sandbox pytest停止

同期TestClientがAnyIO blocking portalで止まる現象が最小FastAPIでも再現した。
httpx2を一時的に試したがrequirementsは変更しなかった。
ASGITransport、Uvicorn、実ブラウザ、sandbox外の公式検証は動作した。
テストランナー環境の失敗と製品機能を分ける。

2026-08-16の入口修正では、sandbox内のTestClient停止を製品成功と混同せず、
実環境権限で `./verify.sh` を再実行した。結果はPython 86 passed、
決定論E2E全通過、組み合わせUI 4/4、Play 5/5、思想家Graph 4/4、
思想家再照会 6/6、`origin` 21/23（network依存情報表示）だった。
さらに公開URLへ `entry_routing.e2e.js` を実行し10/10 PASSした。

---

## 10. 開発時系列

### 2026-07-07〜07-12: MVP

f778d28でMVP。SEP案内、NDL邦訳、論証再構成、引用/export、深掘りプロンプト。
f052084でcold load 60秒超を並列化して約5秒へ。
ee40951で429/503とRetry-Afterへ対応。外部APIは落ちる前提が確定した。

### 2026-07-17〜07-24: 原語基底

3c96bef、4a922df、532bdd2、9051933で原語探求へ転回。
0412e4eで哲学を上位に固定することをやめ、一般理解と原語を並置。
fcac255で無中心原点、1ce341dで概念-翻訳-原点、多言語fan、
a3a1225で埋没警告を実装。

### 2026-07-24〜07-26: Graphと普遍性

7c9c18e、d80895dでCanvas重力グラフ。
196c738、a4e52c8、1db26e0でMenuの不安定・用語・クリックを是正。
bbf8296、11485b1で著者を語源から分離。
241c6edでP11、どの語・どのMenuもその語から始める契約を確立。

### 2026-07-27〜07-28: レンズと組み合わせ

9990069、5abefc、31df143でレンズ。
6341a9fで思想家Graph、88bbda9でSearXNGと重力分布。
ba3417d、5ee5130でAND/意味AND/NOT/OR/比較。
77b75d0で画面内の語をクリックして探索へ戻れる生命線を作った。

### 2026-07-29: 行き止まりゼロから共通基盤

791bfd8でGraph失敗でもshell保持、9ff80b6で全Panel footer、
822e3deでCJK語源解剖、dfb3843で普遍性掃引。
9325deeでnoMiss、1796b54で否定静的gate。
3f63211でExplorationTarget、ACTIONS、dispatchAction、ViewState。
cf23808で無作用Menu/raw error/実クリック/SHA gate。
6e11043で自動代替、履歴rollback、Canvas実マウス。
71865f0で言語名を語源語に誤接続するバグをguard。

### 2026-07-30〜08-02: 概念全景

f2e086b、9ba0575で代替の意味契約、提供元、async commitを是正。
0a97205で概念全景ドロワー。
06b086e、9536a6d、c20b794で目次、空節、過剰推論、英語gloss、
Context、共起節、activeを是正。
37e05e5で全景クリックを実体語、構造ノード、外部出典、
開閉へ分類し、stable ID/data属性駆動へ移行。

### 2026-08-11〜08-16: テスト・意味単位・公開

8月11日はPanorama大規模検証の資源・待受・stale面・details問題を分解。
8月14日はユーザーキャプチャから検索説明不足と意味単位優先を明文化。
1c19fd5で意味単位、失敗安全、combine fallback、部分応答耐性を実装。
fa6478d、4f0ef98、439e367で検証マーカー、公開確認、最終反映を記録。

---

## 11. テストと検証

### 11.1 公式コマンド

~~~bash
cd /home/handa/dialexis
./verify.sh
~~~

verify.shはpytest、Uvicorn、healthz、決定論E2E、network依存統合E2Eを実行し、
gateが全成功した時だけHEADをdeploy/verified_sha.txtへ記録する。

### 11.2 2026-08-16の結果（履歴）

~~~text
Python: 85 passed

主要な決定論E2E:
anatomy 6/6
applications_wave 3/3
aspect_no_recenter 8/8
auto_fallback 6/6
canvas_real_click 17/17
combine_resilience 6/6
contrast 4/4
dim_no_stop 6/6
extterm 3/3
failure_injection 9/9
graph_ux 4/4
history_model 3/3
lens 7/7
lenses_full 7/7
menu_resilience 10/10
nav_viewstate 7/7
no_negative 2/2
op_equivalence 6/6
origin_danger 10/10
perspective 5/5
real_click 3/3
relations_lens 6/6
resolve 5/5
semantic_units 9/9
shelf 6/6
state_consistency 5/5
universal_menu 13/13
universality_sweep 3/3

gate外のnetwork依存:
combine_ui 4/4
play 5/5
thinkers_graph 4/4
thinkers_recall 6/6
origin 21/23 PASS（外部ネットワーク依存）
~~~

originの21/23は決定論gateとは別の情報表示である。
network flakeを隠さず、しかし全機能失敗とも誤診しない。

### 11.2.1 2026-08-18の最新結果

~~~text
Python: 93 passed
決定論的E2E: 全件PASS
translation_history.e2e.js: 11/11 PASS（自動予備台帳、科学分野退避、別語、全実体kindを含む）
VPS pytest: 93 passed
公開healthz: 200
公開API共同幻想: discovery / automated_discovery、term_map 8、timeline 9、人物5、sources 14
統合origin: 21/23 PASS（network依存・gate外。結果は実行時の外部応答で変動）
~~

公式verifyの `deploy/verified_sha.txt` は7cca756を指し、マーカーコミット2a418f1を含むmainが公開VPSへ反映済みである。

### 2026-08-16: 人間入口の回帰を修正

利用者スクリーンショットで、ホームから旧 `/explore` に入り、Map・共通Menuが
「消えた」ように見える回帰を発見。内部の `/origin`機能と公開APIは生きていたため、
原因を入口routingの不整合と特定した。`4e96a3b`でホーム検索、Question Doors、
上部navを `/origin`中心へ変更し、旧 `/explore`には説明付きの復帰リンクを追加。
`11c49b0`としてSHA gate、VPS pytest、サービス再起動、公開HTTP検査を完了した。
続いて `entry_routing.e2e.js` を追加し、公開ブラウザで10/10 PASSを確認した。

### 11.3 静的確認

~~~bash
git diff --check
node --check app/static/app.js
.venv/bin/python -m compileall -q app
.venv/bin/python -m pytest -q
~~~

### 11.4 対象別E2E

~~~bash
node tests/e2e/run_local.js tests/e2e/semantic_units.e2e.js
node tests/e2e/run_local.js tests/e2e/combine_resilience.e2e.js
node tests/e2e/run_local.js tests/e2e/failure_injection.e2e.js
node tests/e2e/run_local.js tests/e2e/state_consistency.e2e.js
node tests/e2e/run_local.js tests/e2e/graph_ux.e2e.js
~~~

実クリックの原則:

- __dx.dispatchを呼ぶだけでは実クリックではない。
- fixed sleepだけでsettledと判定しない。
- detailsを列挙時の前提へ戻す。
- popupはクリック前にwaitForEvent。
- Canvas対象を可視領域へパンしてから実マウス。
- node実行、EC=$?保存、EXIT表示の順で終了コードを捕まえる。

---

## 12. 公開運用と切り戻し

### 12.1 正規デプロイ

~~~bash
ssh -i /home/handa/.ssh/dialexis_vps ubuntu@219.94.244.239 \
  /opt/dialexis/deploy/vps_deploy.sh
~~~

vps_deploy.shは、dialexisユーザーとしてvps_update.shを実行し、
systemd dialexis.serviceを再起動してlocalhost:8000/healthzを確認する。
vps_update.shはgit pull --ff-only、SHA gate、pip install、pytestを行う。

SHA gateが保証するのは正規デプロイ経路が検証SHA以後の未検証コード差分を
拒否することだけであり、全手動経路を物理封鎖するものではない。

### 12.2 公開後

~~~bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://219.94.244.239:8000/healthz
curl -s 'http://219.94.244.239:8000/api/anatomy?q=非有機的肉体&lang=ja'
curl -s 'http://219.94.244.239:8000/api/combine?a=カール・マルクス&b=吉本隆明&op=and&lang=ja'
~~~

app/main.pyの_asset_versionがapp.js/style.cssのhashをstatic URLへ付ける。
新APIと古いJSの組み合わせによる偽の空表示を防ぐ。

### 12.3 DB・バックアップ

公開DBはdata/dialexis.dbのSQLite一ファイル。更新前に日時付きコピーを作る。
api_cacheは再取得可能だが、projects/nodes/provenance/ai_ledgerは研究状態。
コードからDBを自動初期化・削除しない。_backups/とnode_modules/は
現在Git管理外で、削除・clean対象ではない。

### 12.4 安全な切り戻し

~~~text
1. status、HEAD、verified_sha、healthzを記録
2. 公開DBをバックアップ
3. 問題commitをgit revertで新commitとして戻す
4. ./verify.sh
5. verified_shaのmarker commit
6. push
7. vps_deploy.sh
8. healthz、対象API、実ブラウザを確認
~~~

reset --hard、checkout --、git clean、広範なrmを使わない。
上記の古いSHAは過去の切り戻し・失敗史参照点である。現在の公開確認済み参照点は
7cca756（製品コード）、2a418f1（検証マーカー）である。

---

## 13. UX・言語・好奇心の設計根拠

単語を一文字ずつに分けることは情報を持つが、第一表示単位として常に
最適ではない。意味を担うまとまり、形態素、文字構成、語源連鎖を別層にする。
UniDic、BCCWJの短単位語・長単位語の議論は、形態解析とUI意味グループを
区別する補助根拠である。解析器の出力を唯一の意味へ格上げしない。

情報ギャップ理論、自己決定理論、認知負荷、段階的開示をUX判断に使う。

- 未知と既知の差を空白でなく根拠付きの問いとして示す。
- 利用者が次Actionを自分で選ぶ自律性を残す。
- 成功条件と失敗状態を表示し、有能感を壊さない。
- 目次、折りたたみ、Panelで情報量を制御する。
- 推薦の目的は滞在時間ではなく、問いの深まりである。

参照資料:

~~~text
NINJAL UniDic / BCCWJ Morphological Information
Loewenstein, The Psychology of Curiosity
Curiosity in Classrooms Framework
Ryan & Deci, Self-Determination Theory
Cognitive Theory of Multimedia Learning
Stanford Encyclopedia of Philosophy: Concepts
Stanford Encyclopedia of Philosophy: Hermeneutics
Stanford Encyclopedia of Philosophy: Conceptions of Analysis
~~~

研究から直接導けない効果、たとえば知的好奇心が必ず高まることを断定しない。

---

## 14. 継続開発の規律

### 14.1 着手前

~~~text
1. 本書、GENESIS.md、原理原則を読む
2. git status --short
3. git log -10 --oneline --decorate
4. deploy/verified_sha.txtとHEADを比較
5. 公開healthzと対象APIを読み取り確認
6. 対象ファイルを日時付きでバックアップ
7. 目的、失敗条件、受入テストを先に定義
~~~

### 14.2 実装

- 目的と手段を混同しない。
- 外部APIは遅い・空・壊れる前提でtimeout、cache、fallbackを作る。
- fallbackは同じ意味契約を満たす実取得だけ。
- UIから状態変更関数を直接呼ばない。
- async Actionは必ずreturn/awaitし、一操作一commit。
- 成功していない結果でMapを上書きしない。
- source、時刻、確度を推測で埋めない。
- 別カテゴリのデータで空欄を偽装しない。
- 新Menuはregistry、UI action map、実クリック、failure injectionへ接続。
- 文字列テストだけでなく、実DOM、実座標、履歴、Context、sourceを確認。

### 14.3 変更後

~~~text
1. git diff --check
2. node --check app/static/app.js
3. python compileall
4. 対象pytest
5. 対象E2Eをrun_local
6. failure injection / state consistency / no negative
7. ./verify.sh
8. verified_shaのmarker commit
9. push
10. vps_deploy.sh
11. healthz、対象API、公開実ブラウザ
12. 本書・開発台帳へ時系列と未検証を追記
~~~

### 14.4 してはいけないこと

- git reset --hard、git checkout --、git clean、広範な削除。
- _backups/の削除・上書き。
- 本番DB初期化で問題を隠す。
- 空の外部結果をAIの常識で埋める。
- 取得していないsourceや時刻を表示する。
- soon/準備中の無作用ボタン。
- 固定sleepだけのPASS。
- __dx直呼びだけを実クリックと報告する。
- network依存の部分成功を全件PASSと報告する。

### 14.5 次の候補

1. 意味単位の語彙・境界ルールを任意のUniDic/MeCab補助層として検討。
2. SearXNG/Wikipediaのcache、rate limit、timeoutを改善。
3. CJK文字glossの日本語出所を増やす。
4. 語源連鎖の仏語・伊語等を実取得の範囲で深化する。
5. Panorama全景掃引を範囲分割・永続seen・完走時間記録で改善する。
6. 重力代理指標を引用・コーパス・意味関係の出所付き信号へ分解する。
7. 著者×著作×一次テキストを接地する。
8. 文化圏・情報源の偏りを測定する。
9. 問いの深まりへの到達効果をプライバシーを侵害せず評価する。

---

## 15. 未検証・既知の限界

1. **未検証:** 外部APIが将来も同じ内容、応答時間、レート制限を保つこと。
2. **未検証:** 公開SearXNGが常時応答すること。
3. **未検証:** Wikipedia全文検索が一般Web検索と同等であること。
4. **未検証:** 非 / 有機的 / 肉体が全辞書・全文脈の唯一正しい分解であること。
5. **未検証:** semantic boundary辞書が未知の日本語を十分にカバーすること。
6. **未検証:** 全Panorama BFS、両viewport、全L3の一括完走PASS。
   2026-08-11の全BFSは4時間で打ち切られた。
7. **未検証:** origin統合E2Eのnetwork依存2件が常時成功すること。
8. **未検証:** Panoramaが知的好奇心や研究継続を定量的に高めること。
9. **既知の限界:** CJK文字glossはWiktionary抽出で、語全体の意味ではない。
10. **既知の限界:** 共起はDWDS中心で、言語によって空になる。
11. **既知の限界:** 重力の一部は代理指標で、物理的な概念引力ではない。
12. **既知の限界:** LLM Level 2出力は人間確認まで未確認。
13. **既知の限界:** SHA gateは正規経路の規律であり全手動経路を封鎖しない。

---

## 15.5 2026-08-20 操作レビュー：前編／後編の境界と帰路の共通化

### この時点での最終目的との位置

Dialexis の前編は「人類の知識を網羅する検索機」ではない。中心命題は、
**翻訳・検索によって失われる差異を、出典と反証可能性を保った研究過程へ変換すること**である。
したがって、検索結果・辞書の語義・Wikidata の多言語ラベル・書誌レコード・原典本文・受容者の解釈を、
同じ「答え」として混ぜない。現行UIの境界宣言は次の三点を明示する。

- 人類の知を網羅する装置ではない。
- 自動抽出は証拠ではなく候補である。
- グラフは真理の地図ではなく、出典へ進む探索レンズである。

### 前編と後編

前編（現在の実装範囲）は、語・短い句・原語・翻訳語・訳語の保存／欠損／追加、受容史、
出典、研究台帳である。後編（入口だけ先に設計）は、文・段落・引用・まとまった文章、原典全文、
版比較、用例、翻訳アラインメント、論証再構成である。

この分割は機能を弱めるためではない。単語から入った予備探索と、文章全体の文脈を解釈する研究を
同じ画面で混同しないための境界である。`/origin` には後編用の入力単位（文／段落／引用／文章）、
注目語、著者、著作、版・刊年、翻訳者、標準ロケータの入口を置いた。現時点では注目語を前編の探索へ
接続するだけで、本文解析・保存・翻訳アラインメントは未実装である。

将来の接続契約は次の形を崩さない。

~~~text
research_target = {
  subject_type: term | text | excerpt | research_question,
  body: 文・段落・引用そのもの,
  anchor_terms: 前編で調べる語の集合,
  author, work, edition, translator, year, locator,
  evidence_status: candidate | confirmed | disputed | unverified
}
~~~

### 研究台帳と研究プロジェクトの関係

研究台帳は一つのプロジェクトの下書きではなく、翻訳・原典・受容・書誌の再利用可能な研究資産である。
一つの台帳を複数プロジェクトが参照でき、逆に一つのプロジェクトが複数台帳を参照できる。
実装上も `ledgers`、`ledger_entries`、`projects`、`project_ledger_links`、`project_ledger_entries` を分離し、
「台帳をプロジェクトへ採用した」ことと「台帳に書かれた候補が真である」ことを分けている。
台帳詳細画面では、この再利用性を明示し、プロジェクト接続、個別記録の採用、分岐を別の操作として扱う。

### 原典・版・訳者・ロケータを第一級にする理由

`ledger_entries` には `source_term`、`target_term`、`source_language`、`target_language`、`author`、
`translator`、`work`、`edition`、`year`、`locator`、`original_quote`、`translated_quote`、
`preserved_meaning`、`lost_meaning`、`added_meaning` を持たせている。2026-08-20 のUI修正では、
これらを台帳詳細の記録カードへ実際に表示し、原文引用と翻訳引用、保存／欠損／追加の差を別欄にした。
単なる「原語→日本語」の一覧に戻してはならない。出典がレコードに存在することと、その本文が該当箇所を
証明することも別であり、証拠階層を維持する。

### 画面の共通状態機械と、今回の失敗から得た修正

Menu、Action、Context は `SURF` が一元管理する。共通規則は次の通り。

1. Menu と Action は同時に積層しない。
2. Action から別の Action へ進んだ場合、直前のAction面を履歴に保持し、閉じると親面へ戻す。
3. Menu のタイトル全体、Action のヘッダ全体（ボタン・リンク等の操作部品を除く）をドラッグ面にする。
4. 面の座標は viewport と Context の占有領域内にクランプし、`ViewState.panel_position` に保存する。
5. 面を閉じる、別ページへ移る、台帳を保存して開く、台帳一覧／詳細／プロジェクトを往復する場合も、
   画面ごとの個別復帰処理を増やさず、共通 `routeHrefWithReturn` と `restoreViewState` を使う。

失敗体験として、保存後の「保存しました。台帳を開く」が二重のクリック処理を持ち、同一クリックで二度の
遷移を起こしてブラウザ側の待機が中断された。原因は保存後に `onclick` を動的追加した一方、初期の
`addEventListener` も残ったことだった。保存後はボタンを再有効化し、同一のイベントハンドラが保存済みIDを
検査して一度だけ遷移する形へ直した。この失敗は、UIの「一つの操作」をイベント登録数ではなく、実際のDOM操作と
遷移結果で検証しなければならないことを示す。

もう一つの回帰は、境界宣言と後編入口をMapより上へ追加したことで、検索直後のMapがviewport外に残ったことだった。
実DOM測定ではcanvas上端がviewport下端を越え、実マウス座標が画面外になっていた。これはテストの座標を誤魔化すのではなく、
検索でMapが構築された時点に `originRevealMap()` を共通実行し、作業面をviewportへ自動表示することで直した。これにより、
人間が検索後にさらに探してスクロールしなくても、Mapのノード、Menu、次のActionへ直ちに進める。境界説明を追加する場合も、
説明の存在が操作面を押し下げて実作業を隠さないことを受入条件にする。

### 人間による効果検証の受入条件

自動テストは「壊れない」「例外で空白にならない」「同じActionが同じDispatcherを通る」ことを示せるが、
利用者の理解が深まったことは示せない。人間検証では最低限、次を同じ語で実演する。

- 語を検索し、Context、Menu、Action を開き、Actionを移動してから閉じる。閉じた後に親面へ戻るか。
- 翻訳・受容史を開き、候補／書誌／本文・書誌を確認のうえ台帳へ保存する。保存後にボタンが停止せず、台帳を開き、元の語・見方・Context・Action・面位置へ戻れるか。
- 台帳一覧、台帳詳細、プロジェクトを相互に移動する。戻ったときに初期画面へリセットされないか。
- AND検索、空結果、外部情報源の遅延・失敗を試す。条件、原因、出所、再試行または次のActionが残るか。
- 画面を見た人が、どれが候補でどれが証拠でどれが解釈か、そして次に何を確認すべきかを説明できるか。

公開反映確認済み: `69de8a1` を正規経路でVPSへ反映し、VPS側の `vps_update.sh` でSHA gate、pytest
`96 passed`、サービス再起動後の `healthz 200` を確認した。VPS上の対象APIも `/api/anatomy`、
`/api/combine` が `200`、`/origin` に境界宣言・長文入口が存在することを確認した。
未検証: 公開サイトを人間が操作して「理解が深まった」と判断する効果検証。未検証: 長文本文の解析・
翻訳アラインメント・文章からの複数語抽出。公開後も決定論的テスト、実DOMブラウザテスト、healthz／
対象API／主要UI確認を別々の証拠として扱う。

2026-08-20のローカル公式ゲートは、Python `96 passed`、決定論的E2E全件PASS（`canvas_real_click 17/17`、
`combine_resilience 6/6`、`route_return_surface 10/10`、`translation_history 11/11` を含む）だった。
統合系は `origin 21/23`、`thinkers_graph 4/4`、`thinkers_recall 6/6` で、originの未通過2件は
network依存・gate非対象として扱う。公開VPS上では対象APIと入口HTMLの到達性を別途確認した。

### 2026-08-21 人物名・人物間比較を翻訳受容史から分離

人間検証で、`カールマルクス`、`Karl Marx`、`Karl Marx AND 吉本隆明` に対する表示が、人物・著作・思想の
調査ではなく、一般語の語源・翻訳検索へ落ちていた。この結果はメニュー名「翻訳・受容史を追跡」が最低限
約束する内容を満たさず、人物名の表記差と概念の翻訳史を混同していた。特に固有名詞には、一般語と同じ
「原語の語義」を当てはめるべきではない。人物名でまず必要なのは、人物同定、異表記、著作の原題・翻訳題、
思想上の概念、受容者と引用・影響の検証を別レイヤーで示すことである。

このため `app/data/person_profiles.json` を追加し、現在はKarl Marx、吉本隆明、その二者関係を curated seed として
登録した。データの目的は「知識を網羅した人物百科」ではなく、同一人物判定と研究入口を安定させることにある。
プロフィールには次の境界を明記する。

- `name_forms`: カタカナ、中黒有無、ラテン文字、フルネーム、必要に応じた別言語表記。これは名前の翻訳史ではなく表記・同定の候補である。
- `works`: 原題、代表的な日本語題、年、役割。作品タイトルの翻訳・版比較は人物名とは別に追跡する。
- `concepts`: 人物に関係する思想語。人物の発言そのもの、後世の受容者の再構成、サイトの仮説を混同しない。
- `timeline` / `reception` / `counterchecks`: 年代、受容者、反証・照合課題。引用・影響関係は候補から本文確認へ進める。

API契約も一般語と分けた。`/api/translation-history?q=Karl%20Marx` は `subject_kind: person`、`dossier.mode: person` を返し、
人物カードでは氏名の表記候補、著作と翻訳題、概念、時系列、受容、保存／移動／追加、出所、次の確認を表示する。
`/api/translation-history/pair?a=Karl%20Marx&b=吉本隆明` は `subject_kind: person_pair`、`dossier.mode: person_pair` を返し、
「二人の名前を翻訳対応させる」のではなく、二人の著作・共通概念・相互受容・比較軸・反証課題を表示する。
`/api/combine` の既知人物同士の `and`、`compare`、`semand` も同じ人物間契約へ早期分岐するため、一般検索のノイズだけを
「研究結果」として表示しない。未登録人物については、ラテン文字または人物名らしい入力だけを慎重に候補照会し、
通常の漢字概念を勝手に人物化しない。

UIで確認できる失敗原因と修正は次の通り。

- AND検索の二語目入力欄が前回のUI変更で消え、表示上は組み合わせ操作があっても実際には二語目を入力できなかった。
  `gCombinePanel` に二語目欄 `#cmb-b` を復元し、人物二人なら比較モードへ送る。
- 翻訳受容史の人物表示が一般語の「語源」カードだった。人物カード、著作・版カード、思想語カードを分離し、人物名の
  翻訳対応ではないことを画面上でも説明する。
- 台帳保存後に元の画面へ戻れない経路では、戻り先トークンを常に `/origin` のものへ上書きしていた。
  `routeReturnInit` は `/origin` 入口だけが新しい探索復帰トークンを作り、台帳一覧→台帳詳細→プロジェクトの親経路を上書きしない。
  `restoreViewState` は `kind` と `pair` も復元し、閉じる／戻る／フッターからの次Actionでも人物モードを維持する。
- 多言語候補は全件を常時並べず、代表8件を先に表示し、残りは「すべて表示」、言語選択、表記検索で展開する。
  これにより情報量を隠さず、初期画面の縦長化と主要Actionの埋没を防ぐ。

台帳保存は `/api/ledgers/from-translation-history` が `subject_kind` を読み、人物は `subject_type: person`、人物間比較は
`subject_type: research_question` として作る。人物・二人比較が「単語台帳」として保存されないことを、DB上の型でも保証する。
一つの台帳を複数プロジェクトが参照できる既存の多対多設計は維持し、人物の予備台帳も研究プロジェクトへ接続可能な再利用資産とする。

実装検証（ローカル）: `python -m py_compile`、JSON検証、`node --check app/static/app.js`、`git diff --check`、
翻訳受容史・人物・人物間・Action registry等の対象テストを通過した。`tests/test_translation_history.py` には、
日本語／英語人物名の同一人物契約と、人物間ANDの比較契約を追加した。
未検証: この実行環境ではFastAPI TestClientが単純なhealthzでも停止し、Chromium子プロセス間のlocalhost接続も分離されるため、
今回のブラウザ実DOM操作とTestClient経由の台帳POSTはローカルサンドボックスで再実行できていない。公開反映後はVPS上のpytest、healthz、
人物API、人物間API、実ブラウザで同じ受入手順を確認し、未検証を成功扱いしない。

### 優先順位

3D化や情報源数の追加は後順位とする。現在の心臓部は、(a) 操作が途中で停止しない、(b) Menuの命令が
実行される、(c) 失敗時も説明と次Actionが残る、(d) 候補・証拠・解釈・判断が混ざらない、(e) 台帳と
プロジェクトが再利用可能な関係を持つ、の五点である。

## 16. 次のAIの最初の操作

細かな承認を連続要求して作業を止めない。ただし破壊的・不可逆な操作、
秘密情報、外部への新規権限付与は別途扱う。通常の読み取り、テスト、
バックアップ、可逆的なコード修正、検証済みデプロイはこの引継ぎの範囲で進める。

~~~bash
cd /home/handa/dialexis
git status --short
git log -5 --oneline --decorate
cat deploy/verified_sha.txt
git diff --check
node --check app/static/app.js
.venv/bin/python -m compileall -q app
curl -s 'http://219.94.244.239:8000/api/anatomy?q=非有機的肉体&lang=ja'
curl -s 'http://219.94.244.239:8000/api/combine?a=カール・マルクス&b=吉本隆明&op=and&lang=ja'
~~~

製品コードを変更する前に、目的、反例、受入テストを定義する。
変更後は本書の現在地、検証、未検証、時系列を更新する。

---

## 17. 受入チェックリスト

~~~text
[ ] /originで日本語、CJK、アルファベット、人物を入力できる
[ ] ホーム検索・Question Doors・上部Map navが /originへ到達する
[ ] /exploreは資料探索と明示され、Map復帰リンクを持つ
[ ] Graphがroot-only、空、外部失敗でもshellと次Actionを失わない
[ ] Canvas、Context、Menu、Actionが画面幅で破綻しない
[ ] 語、人物、著作、構造ノードでActionが変わる
[ ] 表示面がACTIONS registryとdispatchActionを通る
[ ] 1操作の履歴commitが1回だけ
[ ] 失敗でMap/Contextを成功結果として上書きしない
[ ] 生例外、推測source、無作用soonがDOMにない
[ ] 非有機的肉体の意味層が非/有機的/肉体
[ ] character層が補助で、語全体の意味と誤認させない
[ ] AND/NOT/OR/compare/semandの結果契約がある
[ ] SearXNG空/timeoutからWikipedia同条件検索へ退避する
[ ] 空/失敗でも条件、出所、次Action、再試行が残る
[ ] 実DOM/実マウスE2Eがある
[ ] verify.shを実行できる
[ ] verified_sha gate後だけ公開更新する
[ ] 公開後healthz、対象API、主要UIを確認する
[ ] Markdown/JSON-LD/BibTeX/CSL JSONへ持ち出せる
[ ] 未検証事項を成功として報告しない
~~~

---

## 18. 改訂履歴

### 2026-08-16

- 本マスター引継ぎ文書を作成。
- 2026-07-07から2026-08-16までの主要な開発転換と失敗体験を統合。
- 意味単位、dispatcher、combine fallback、部分応答耐性を現行実装として記録。
- API、SQLite、connector、E2E、SHA gate、VPS運用を統合。
- 公開healthz、意味単位API、AND API、実ブラウザ操作を記録。
- 旧資料に残る時点依存の未deploy・未検証記述を現在の公開実測と分離。

### 2026-08-16 23時台追記

- 人間スクリーンショットで発見した `/explore` 迷入の原因と責任範囲を記録。
- ホーム→`/origin`入口修正、公開反映、公開ブラウザ10/10 E2Eを追記。
- AI内部テストが直接 `/origin`だけを開き、人間の入口経路を漏らした失敗を明記。

### 2026-08-17追記

- 翻訳・受容史／埋没語追跡を通常検索から分離した特別Actionとして実装。
- 原語・翻訳語、保存／欠損／付加、時系列5W1H、受容史人物台帳、反証、出所、次の調査を `translation_history_seed.json` に記録。
- 未知語・文学・科学・芸術の未整備状態で哲学データを流用しないAPI契約を追加。
- `tests/test_translation_history.py` と `tests/e2e/translation_history.e2e.js` を追加。
- 公式verify（Python 91 passed、決定論的UI E2E全件PASS）とVPS pytest（91 passed）を通過し、公開URLの実ブラウザ8/8、healthz 200を確認。
- `db993a8`（製品コード）と `213f709`（検証マーカー・公開HEAD）を記録。

### 2026-08-17 一般化追記

- 翻訳・受容史Actionを全実体ノードと全Actionパネルへ一般化。
- 未登録語に対しても語専用の調査台帳準備面、初回調査手順、語を埋め込んだ出典候補リンクを表示。
- 公式verifyを再実行し、Python 92 passed、翻訳・受容史11/11、全決定論的E2Eを確認。
- `5696a64`（一般化実装）、`efc7d5d`（検証マーカー・公開HEAD）、VPS pytest 92 passed、healthz 200を記録。

### 2026-08-18 自動予備台帳追記

- 未登録語で利用者が空の台帳を手作業で作るだけだった不足を修正し、`/api/origin`、`/api/anatomy`、`/api/explore` の既存情報を証拠階層つきの `discovery` 台帳へ正規化。
- `共同幻想` の公開APIで `term_map=8`、`timeline=9`、`reception_ledger=5`、`sources=14`、`next_actions=3` を実測。吉本隆明を含む人物・書誌候補を表示するが、引用・影響・訳語対応は未確認のまま残す。
- 外部情報源のキャンセル待ちで画面が止まる経路をワーカー隔離・期限退避へ変更。取得失敗時は `not_seeded` の語専用調査入口へ戻す。
- 科学・文学・芸術で哲学レンズのOpenAlex/SEP結果を表示しない分野ゲートを追加。
- 公式verifyはPython 93 passed、決定論的E2E全件PASS、翻訳・受容史11/11。VPS pytest 93 passed、healthz 200、公開実ブラウザ11/11を確認。
- `7cca756`（自動予備台帳製品コード）、`2a418f1`（検証マーカー・公開HEAD）を記録。

### 今後

- 上書きで履歴を消さず、日付と理由を追記する。
- 実測していないことは未検証と明記する。
- 決定論gate、network統合、全景掃引を別の証拠として扱う。
- コードと文書が矛盾したら実体を測り、文書を直し、理由を残す。
- 新しい設計判断では、保存・棄却・上位化したものを記録する。
