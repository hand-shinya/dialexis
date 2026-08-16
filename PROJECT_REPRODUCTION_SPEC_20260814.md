# Dialexis 現状・完全再現・継続開発仕様書

**スナップショット日時:** 2026-08-14（Asia/Tokyo）
**対象:** /home/handa/dialexis
**目的:** このファイルだけを受け取った、プロジェクトを一度も見たことのない人間またはAIが、Dialexisの目的・画面・データ契約・操作契約・障害時の振る舞い・再現手順・次の改良方針を推測なしで再構築できるようにする。
**現行ブランチ:** main
**HEAD:** 37e05e5 全景クリック契約の是正(半田様2026-08-02・preview)
**ライセンス:** Code = AGPL-3.0 / Documentation = CC-BY-4.0

> この文書は単なるメモではなく、再構築時に優先される受入仕様である。コードとこの文書が矛盾する場合、まず現行コードを実測し、次にこの文書の「未検証」を更新し、その後に設計判断を記録する。既存のユーザー変更を勝手に削除・リセット・本番反映してはならない。

## 0. 結論：現在地と今回の最優先判断

### 0.1 現在地

Dialexisは、哲学的・言語的な問いを、外部の生きた情報源に接地した探索と研究過程へ変えるWebアプリである。現時点の中心画面は /origin（原語による探求）で、次の三つは直近の修正で大きく改善されている。

1. 外部APIや検索源が遅い・空・失敗した時に、処理中のまま画面が止まらない。
2. 画面上のどのメニューを押しても、表示文言から推測した別処理ではなく、共通の ACTIONS → dispatchAction 経路を通る。
3. 成功しなかった時も、元のMap/Contextを壊さず、原因・検索条件・出所・再試行・外部検索・次の探索入口を残す。

今回のキャプチャでは、Karl Marx と吉本隆明の組み合わせ検索が実際に結果を返し、Mapは更新された。一方、次の欠陥は残っている。

- 非有機的肉体が、意味のまとまりより先に 非 / 有 / 機 / 的 / 肉 / 体 の文字列として表示される。
- 文字の字義（例：機 = weaving machine）が、語全体の意味分解であるかのように見える。これは「字義」「形態素」「複合語」「語源」を同じ層に置くUX上の誤解を生む。
- 自動代替が働いたことは表示されるが、主経路・代替源・保証範囲の違いを一目で判断できる情報設計には改善余地がある。
- Contextの右ドロワー、中央Map、浮遊Actionパネル、上部の多数のチップが同時に出るため、知的情報量は多いが、最初に何を読むべきかの優先順位が弱い。

### 0.2 最優先のUI判断

**分解の既定値を「意味のまとまり」へ変更する。文字単位は削除しないが、二次的な展開層へ下げる。**

非有機的肉体の既定表示は次のようにする。

~~~text
意味のまとまり
[ 非 ] ＋ [ 有機的 ] ＋ [ 肉体 ]

形態素・短単位（展開）
[ 非 ] ＋ [ 有機 ] ＋ [ 的 ] ＋ [ 肉体 ]

漢字構成（さらに展開）
[ 非 ] [ 有 ] [ 機 ] [ 的 ] [ 肉 ] [ 体 ]
~~~

ここで 非 / 有機的 / 肉体 は「この語をこの画面で理解するための意味的グルーピング」であり、語源学的な真理として自動断定しない。形態素解析結果、辞書見出し、コーパス基準、編集者の確認、ユーザーの採用をそれぞれ別の証拠層として表示する。

## 1. プロジェクトの同一性

### 1.1 名前と一行定義

**Dialexis（ディアレクシス、διάλεξις＝論究）**は、哲学の答えを配るサイトではなく、利用者の問いを「より深く・根拠あり・反証可能で・共有可能な研究過程」へ変える、反省的哲学研究インフラである。

### 1.2 これは何ではないか

- 哲学版Wikipediaではない。
- 哲学版Google Scholarではない。
- 流暢な回答だけを返すChatGPT置換ではない。
- 特定個人の思考法を唯一の正解として押し付ける個人専用思考OSではない。
- 根拠の薄い美しい思想マップだけを作るサイトではない。
- 内部に百科事典を蓄積して静的に古くなるデータベースではない。

### 1.3 七つの不変原則

| # | 原則 | UI/実装での意味 |
|---:|---|---|
| 1 | 問いの変換 | 情報を読んで終了させず、比較・検証・再探索・研究ノードのいずれかへ接続する。 |
| 2 | 使用即貢献 | 一人の利用者だけでも価値があり、公開を選べば研究痕跡が次の利用者の土台になる。 |
| 3 | レンズ原理 | 知識本体は外部の生きた情報源に置き、内部は来歴・短いキャッシュ・研究痕跡のみ持つ。 |
| 4 | 鮮度の刻印 | 外部情報には出所と取得時刻を付ける。古い情報を無言で現在の事実として表示しない。 |
| 5 | 退化階梯 | 全機能に無料・APIキー不要・決定論的なLevel 0を持たせ、キーは昇格だけに使う。 |
| 6 | AI透明性 | AIが触れた出力はorigin/確度/台帳を持ち、人間の確認までは未確認と表示する。 |
| 7 | 撤退可能性 | 研究はMarkdown、JSON-LD、BibTeX、CSL JSONで持ち出せ、SQLite一ファイルで移動できる。 |

固定の確度語彙:

~~~text
confirmed               確定
high_probability        高蓋然
unverified              未確認
interpretive_hypothesis 解釈仮説
speculation             思弁
~~~

## 2. 再構築時に守るべき定義

### 2.1 再現の三層

新しいAIはどの層を満たしたかを報告する。

1. **思想的同一性:** 七原則、問いを終端にしないこと、出所・時刻・確度を隠さないこと。
2. **機能的同一性:** /origin の言語Map、Context、Menu、Action、組み合わせ検索、外部代替、履歴、研究デスク、Watcher、Exportが同じ契約で動くこと。
3. **視覚的同一性:** 紙色・濃紺・茶・青の配色、右Contextドロワー、中央グラフ、浮遊パネル、チップ群の構成を再現すること。

ピクセル単位の一致は、外部APIの結果、フォント、ブラウザ、取得時刻、画面幅で変わるため受入条件にしない。ただし、外部APIが返した内容を別内容と偽らないことは必須である。

### 2.2 推測禁止

- 画面にないデータをAIの常識で補わない。
- soon/準備中という無作用ボタンを実行可能なボタンと同列に表示しない。
- 成功していない検索を成功したMapで置き換えない。
- 文字の辞書義を語全体の意味と呼ばない。
- 原語・訳語・形態素・語源・文字構成を同一の「意味」として混ぜない。
- Wikipedia全文検索を一般Web全体の代替と表示しない。
- 取得できない場合は捏造せず、現在の状態を保持し、同じ語から再開できる入口を残す。

## 3. 実行環境とリポジトリ

### 3.1 開発環境

~~~text
OS: Linux/WSL2で確認
Python: 3.11以上（現環境は3.12系）
Backend: FastAPI + Uvicorn
Template: Jinja2
Frontend: vanilla JavaScript + CSS（ビルド工程なし）
Database: SQLite
HTTP: httpx
Graph: Canvas自前描画。失敗時は表形式へ退化可能。
~~~

### 3.2 インストールと起動

~~~bash
git clone https://github.com/hand-shinya/dialexis.git
cd dialexis
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
~~~

ブラウザで http://127.0.0.1:8000 を開く。APIキーは不要。

環境変数:

~~~text
DIALEXIS_DB       SQLiteファイルの場所。未指定時はapp/db.pyの既定値。
DIALEXIS_CONTACT  外部無料APIへ送る丁寧なUser-Agent用の連絡先。
SEARX_URL         組み合わせ検索の主検索源。既定値はhttp://127.0.0.1:8888。
DX_CHROMIUM       Playwright E2E用Chromium実行ファイル。
DX_PORT           verify.shが使うポート（既定8099）。
~~~

### 3.3 現在の作業ツリー

HEAD以降の作業は未コミットである。既存変更はユーザーの作業として保存し、ロールバック・reset・cleanを行わない。

~~~text
変更済み:
  app/connectors/wikipedia.py
  app/main.py
  app/static/app.js
  app/static/style.css
  tests/e2e/play.e2e.js
  tests/reach/panorama_check.js
  tests/reach/panorama_live.js
  tests/test_dispatch_single_path.py

新規:
  tests/e2e/combine_resilience.e2e.js
  _backups/ 以下の既存バックアップ群
  本ファイル
~~~

_backups/ は復旧資料であり、削除・編集しない。

### 3.4 ファイル地図

~~~text
GENESIS.md                         最上位憲法。設計根拠と再構築プロンプト。
README.md / README.ja.md           プロジェクト説明と起動。
requirements.txt                   fastapi, uvicorn, httpx, jinja2, multipart。
verify.sh                          Python + E2Eの公式検証入口。

app/main.py                        ページ、API、外部源のオーケストレーション。
app/db.py                          SQLiteスキーマ、固定語彙、接続。
app/static/app.js                  全ページJS、/origin状態機械、Action registry。
app/static/style.css               配色、レイアウト、Menu/Action/Context。
app/templates/                     base/index/explore/origin/desk/project等。
app/i18n/ja.json, en.json          UI文字列。
app/data/                          seed、確度、反証、概念系譜、語彙。
app/connectors/                    Wikidata/Wikipedia/Wiktionary/SEP等の接続。
app/llm/adapter.py                 BYOキーLLMの中継とガード。
app/harvester.py                   cron/systemd用Watcher実行。
docs/                              Architecture、Build、User Guide、運用、検証計画。
deploy/                            VPS、nginx、systemd、Dockerの雛形。
tests/                             Python静的/契約検査。
tests/e2e/                         Playwright実ブラウザ検査。
tests/reach/                       全表示面・全Actionの到達性検査。
~~~

## 4. システム構成

~~~text
Browser
  ├─ Jinja2 pages + static/app.js + static/style.css
  ├─ localStorage: LLM設定、棚、探索経路、レンズ
  └─ fetch JSON
       │
FastAPI app/main.py
  ├─ /api/explore        Wikidata + Wikipedia + SEP + OpenAlex + NDL/CiNii等
  ├─ /api/origin         Wiktionary trace + Wikidata concept + breadth + lineage
  ├─ /api/origin/graph   言語空間の層付きCanvas Map
  ├─ /api/anatomy        原語の語源/構成要素/CJK文字分解
  ├─ /api/combine        SearXNG主経路 + Wikipedia全文検索退避
  ├─ /api/projects...    研究過程グラフとExport
  ├─ /api/counter        Level 0反証チェックリスト + 文献検索、Level 2 LLM
  ├─ /api/watches...     Watcher
  └─ /api/ledger         AI透明性台帳
       │
SQLite
  ├─ 研究データ
  ├─ api_cache
  └─ ai_ledger

systemd timer/cron ── app/harvester.py ── data/harvester_status.json
~~~

外部情報は原則ライブ取得＋TTLキャッシュであり、内部に百科事典を作らない。connectorの戻り値は少なくとも source / retrieved_at / cached / error / data を持つ。

## 5. ページと画面の契約

### 5.1 ページルート

~~~text
/                    問いの入口、検索、Question Doors、七原則
/explore             統合探索結果
/origin              原語による探求。今回の主画面
/desk                研究デスク入口、反証エンジン
/project/{pid}       研究プロセスの編集画面
/watches             新着監視
/levels              7段階の読解
/deepsearch          視点・目的・難易度からプロンプト生成
/settings            LLM設定。キーはブラウザlocalStorageのみ
/donate              公共知とAI計算費用の分離説明
/about               About
/healthz             ヘルスチェック
~~~

ヘッダーに現在表示する主なリンクは「探索 / 深掘り探索プロンプト / 設定 / 支援 / 言語切り替え」。研究デスク・Watcher・読解レベル・Aboutのrouteは残っているが、現在のヘッダーには常設していない。

### 5.2 /originの画面構造

~~~text
ページ上部
  ブランド + nav
  「原語による探求」説明
  q入力 + 原語から問い直す
  新タブ設定

origin-shell（検索語がある限り、グラフ失敗でも残す）
  graph-head: 戻る / 進む / 説明 / 遊ぶ / 棚 / 俯瞰
  graph-lens: 現在の見方、中心語、全体像、中心に据える、組み合わせ、見方、意味、解剖...
  Canvas Map
  graph-note: 出所、重力/関係が推定であること、組み合わせ条件

本文カード
  原語基底、語の意味、語源、人物、論文等

固定Context（右ドロワー、成功時は自動表示）
  その語の概念全景
  取得済みデータから実在する節だけを表示
  目次「この語の見どころ」
  語の来歴 / 原語・思想家・著作 / 翻訳で変わった焦点 /
  関係・対立・運動 / 各言語での表記 / 実際の用法・共起 /
  次にたどれる言葉
  末尾固定の次アクション

浮遊Action
  中央Map上のMenuから選んだ内容。Contextを壊さない。
~~~

### 5.3 surfaceの意味

| surface | 役割 | 成功時 |
|---|---|---|
| menu | 選択した実体の操作一覧 | 押下中は全項目disabled、完了後にActionまたはMenu |
| action | 意味、解剖、組み合わせ、外部、遊び等 | gPanelに本文＋共通継続footer |
| context | 語の概念全景。右側に常設 | Mapと独立して保持し、履歴にも含む |

Contextは #dx-context、Actionは #graph-panel、Menuは #graph-menu。Context最大幅520px、Action最大680px/92vw。Context表示時はbodyに右側の退避幅を付け、画面幅が狭くても交差・画面外・遮蔽を起こさない。

## 6. 全Actionの正規契約

### 6.1 Action registry

ユーザーのクリックは、表示面ごとに処理を書かず、必ず次のregistryを通る。effectは文言ではなく状態遷移の宣言である。

~~~text
center       effect=center       中心語を再構築
meaning      effect=action       この語の意味
multilingual effect=action       多言語での言い方
collapse     effect=action       一訳語に埋没した原語
anatomy      effect=action       語源と構成要素の解剖
contrast     effect=action       訳語/原語を並置
colloc       effect=action       実コーパス共起
lens         effect=action       見方一覧
applyLens    effect=map/center   条件によりMap変更または再中心
combine      effect=action/map   第2語入力/実行
external     effect=action       外部専門情報（新タブリンクを含む）
shelf        effect=store        localStorageの棚へ追加
deepsearch   effect=action       視点・目的・難易度プロンプト
newtab       effect=newpage      新しいoriginタブ
author       effect=action       著者実データ
authorNote   effect=action       系譜メモ
dimension    effect=action       概念固有の探究次元
panorama     effect=context      概念全景Context
focus        effect=map           分岐を中心化
hl           effect=map           経路強調
resetFocus   effect=map           全体へ戻す
~~~

effectの許容値は context / center / map / action / store / newpage の六つだけ。新Actionはregistry、UI_ACTION_IDS、runtime到達性、失敗注入、履歴契約を同時に追加する。

### 6.2 表示面別のAction被覆

~~~text
topbar       gActions（中心語）から動的列挙
popup        gActions（選択node）から動的列挙
edge         hl, focus, combine, deepsearch, center, resetFocus
node         panorama
panelFooter  center, lens, multilingual, external, combine, newtab
nomiss       center, multilingual, external, combine, lens
lensMenu     applyLens
textLink     center
card         dimension, author, external
play         center, combine
shelfPanel   shelf, center, combine
scrollCard   center
contextEnt   panorama
~~~

### 6.3 一操作一transaction

dispatchAction(actionId, target, currentState, surfaceContext)は次の順で動く。

~~~text
1. Action IDをregistryで解決し、effectを検査。
2. targetをterm/label/kind/id/lang/layerへ正規化。
3. NAV.txn=true。中間状態を履歴に積まない。
4. action.runをawait。クリック元の兄弟buttonはbusy/disabled。
5. 例外なら元のPANEL/COMBINE/CONTEXTを復元し、説明面またはMenuを再提示。
6. runResult === falseなら、理由付き結果面があれば保持し、履歴をcommitしない。
7. store/newpage等commits=falseは履歴を変えない。
8. 成功した状態だけnavCommit(currentViewState())を一度実行。
9. NAV.txn=false。_lastDispatchにsuccess/fallback/errorを記録。
~~~

中心語の再構築（初回検索、Mapの語クリック、本文の原語クリック）は originExplore 一本に統合する。成功前に検索欄だけを書き換えたり、空Canvasを表示したりしてはいけない。

### 6.4 失敗時の共通UI

どのActionも最低限、次を表示できる状態にする。

~~~text
処理状態: 読み込み中 / 実行しました / 完了を確認できませんでした
説明: 何を試したか、主経路か代替経路か、元の状態を保持したか
条件: 正確な検索語・演算子・対象term
継続: 同じ語の中心化、見方、多言語、外部、組み合わせ、再試行
~~~

「何も起きなかった」ように見せない。ただし失敗を成功と表示しない。「この機能は使えません」だけで終わらせず、同じ語の別ルートを実行可能なbuttonとして出す。

## 7. バックエンドAPI契約

### 7.1 探索・言語Map

~~~text
GET /api/explore?q=&lang=
  Wikidataでentity解決。
  SEP、Wikipedia、OpenAlex、Gutenberg、NDL、CiNii等を並列照会。
  orientationは知の伝統に応じて変える。

GET /api/origin?q=&lang=ja
  general_meaning / collapse_warning / concept_origin
  originators / associated / relations / named_after
  word_origin / chain / breadth / dimensions
  qid / article_url / wikidata_url / wiktionary_url
  sources[{source,retrieved_at,error}]

GET /api/origin/graph?q=&lang=ja
  nodes[{id,label,kind,layer,weight,q,...}]
  edges[{from,to,strength}]
  note / queried_at / sources

GET /api/anatomy?q=&lang=ja&own=0|1
  term / components[{part,meaning}] / chain[{lang,term,gloss}]
  summary / wiktionary_url / queried_at / own
  own=1は語自身の来歴。概念全景からはown=1を使う。

GET /api/variants?q=&lang=
  labels / qid / retrieved_at / queried_at

GET /api/dimensions?q=&lang=
  Wikipedia節見出しから、その語固有の探究次元を返す。

GET /api/author?name=&lang=
  found / extract / born / died / occupation / works / sources

GET /api/collocations?term=&lang=de
  DWDS Wortprofil。現状はドイツ語以外を空として正直に返す。
~~~

### 7.2 組み合わせ検索

~~~text
GET /api/combine?a=&b=&op=&lang=ja
op = and      両語で絞る
     semand   aの意味近縁をbの文脈で絞る
     not      bを除外
     or       両語の周辺を合わせる
     compare  共通/固有を比較
~~~

正常応答の最低形:

~~~json
{
  "query": "カール・マルクス",
  "nodes": [],
  "edges": [],
  "has_results": true,
  "note": "「カール・マルクス」を「吉本隆明」で絞り込み（AND）。両方に関わるものだけ。出所：Wikipedia全文検索。クリックでその語へ。",
  "queried_at": "ISO-8601"
}
~~~

### 7.3 組み合わせ検索の障害経路

過去の根本原因は、app/connectors/searxng.pyの既定 SEARX_URL=http://127.0.0.1:8888 が応答しない時、例外を空配列として返し、旧 /api/combine が「一般ウェブ検索（SearXNG）は現在準備中」とだけ返し、フロントがnoteを実質表示せずにroot-only Mapを成功に見せていたことである。

現在の経路:

~~~text
1. SearXNGを最大8秒待つ。
2. 空/timeoutなら、同じ語条件をWikipedia MediaWiki全文検索へ渡す。
3. データが返ればnodes/edgesを構築し、noteにWikipedia全文検索と出所を明記。
4. 両方空ならhas_results=false。
5. frontendはMapを置換せず、組み合わせ結果面を開く。
6. 結果面には正確な検索条件、原因、Google/Scholar/Bing/DDG/Wikipedia/OpenAlex等の外部同条件リンク、条件変更して再検索を残す。
~~~

Wikipedia全文検索は一般Web検索の完全な代替ではない。表示上もデータ上も、一般Web全体を検索したと誤認させない。

### 7.4 研究デスクAPI

~~~text
GET    /api/projects
POST   /api/projects
DELETE /api/projects/{pid}
GET    /api/projects/{pid}/graph
POST   /api/projects/{pid}/nodes
PATCH  /api/nodes/{nid}
DELETE /api/nodes/{nid}
POST   /api/projects/{pid}/edges
DELETE /api/edges/{eid}
POST   /api/nodes/{nid}/provenance
GET/POST /api/projects/{pid}/arguments
GET/PATCH/DELETE /api/arguments/{aid}
POST/PATCH/DELETE /api/arguments/{aid}/premises...
GET /api/projects/{pid}/export.md
GET /api/projects/{pid}/export.jsonld
GET /api/projects/{pid}/export.bib
GET /api/projects/{pid}/export.csl.json
~~~

ノード種類は question / claim / evidence / counterclaim / uncertainty / interpretation / decision / source / note。辺種類は supports / contradicts / answers / refines / derives_from / cites / about / responds_to。

### 7.5 その他のAPI

~~~text
GET  /api/applications?q=&lang=
GET  /api/usage?q=&lang=
GET  /api/timeline?q=&lang=
GET  /api/culture?q=&lang=
GET  /api/websearch?q=&lang=
GET  /api/gravity?q=&lang=
GET  /api/citations?doi=
GET  /api/deepsearch/services
POST /api/deepsearch
GET  /api/locator?author=&work=&locator=
POST /api/counter
GET  /api/levels?concept=
POST /api/levels/llm
GET/POST/DELETE /api/watches...
GET  /api/ledger
~~~

## 8. SQLiteデータモデル

app/db.pyのSCHEMAが唯一の定義である。構築AIは次のテーブルをSQLiteに作成する。

~~~sql
projects(
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT DEFAULT '',
 question TEXT DEFAULT '', is_public INTEGER DEFAULT 0,
 created_at TEXT, updated_at TEXT)

nodes(
 id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 type TEXT NOT NULL, title TEXT NOT NULL, body TEXT DEFAULT '',
 confidence TEXT DEFAULT 'unverified', origin TEXT DEFAULT 'human',
 status TEXT DEFAULT 'open', created_at TEXT, updated_at TEXT)

edges(
 id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 src INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
 dst INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
 rel TEXT NOT NULL, created_at TEXT)

provenance(
 id INTEGER PRIMARY KEY, node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
 source_name TEXT DEFAULT '', source_url TEXT DEFAULT '', retrieved_at TEXT DEFAULT '',
 quote TEXT DEFAULT '', note TEXT DEFAULT '')

watches(
 id INTEGER PRIMARY KEY, label TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'query',
 openalex_id TEXT DEFAULT '', query TEXT DEFAULT '', created_at TEXT, last_checked TEXT DEFAULT '')

watch_hits(
 id INTEGER PRIMARY KEY, watch_id INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
 external_id TEXT, title TEXT, year TEXT DEFAULT '', url TEXT DEFAULT '', source TEXT DEFAULT '',
 found_at TEXT, seen INTEGER DEFAULT 0, UNIQUE(watch_id, external_id))

api_cache(url TEXT PRIMARY KEY, fetched_at TEXT, body TEXT)

ai_ledger(
 id INTEGER PRIMARY KEY, ts TEXT, provider TEXT, model TEXT, task TEXT,
 project_id INTEGER, summary TEXT)

arguments(
 id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 title TEXT NOT NULL, conclusion TEXT DEFAULT '', conclusion_node_id INTEGER REFERENCES nodes(id) ON DELETE SET NULL,
 validity TEXT DEFAULT 'unassessed', soundness TEXT DEFAULT 'unassessed', note TEXT DEFAULT '',
 created_at TEXT, updated_at TEXT)

argument_premises(
 id INTEGER PRIMARY KEY, argument_id INTEGER NOT NULL REFERENCES arguments(id) ON DELETE CASCADE,
 seq INTEGER NOT NULL DEFAULT 0, text TEXT DEFAULT '', hidden INTEGER DEFAULT 0,
 voice TEXT DEFAULT 'author', node_id INTEGER REFERENCES nodes(id) ON DELETE SET NULL,
 locator TEXT DEFAULT '', source_name TEXT DEFAULT '', source_url TEXT DEFAULT '',
 quote TEXT DEFAULT '', retrieved_at TEXT DEFAULT '')
~~~

nodes.origin（human/ai/external）と論証前提のvoice（author/commentator/self）は別概念である。validityとsoundnessも別フィールドであり、妥当性と健全性を混同しない。

## 9. 外部情報源

| Connector | 役割 | 失敗時 |
|---|---|---|
| Wikidata | entity/QID/labels/claims/人物・著作・関係 | error封筒、UIは赤badgeまたは次入口 |
| Wikipedia | summary、節、全文検索退避 | source/errorを表示 |
| Wiktionary | 語義、語源trace、字/語の構成 | 語の来歴と文字構成を混同しない |
| SEP | 英語圏の哲学オリエンテーション | 関連性gate、無関係項目を出さない |
| OpenAlex | 論文・著者・引用・Watcher | relevance filter |
| Crossref | 書誌 | error封筒 |
| OpenCitations | citation | error封筒 |
| Project Gutenberg/Gutendex | 無料原典 | error封筒 |
| NDL | 邦訳・日本語圏書誌 | orientation planで日本語圏を補完 |
| CiNii | 日本語研究 | orientation planで日本語圏を補完 |
| DWDS | ドイツ語共起 | 現在は独語中心、他言語は空を正直に返す |
| SearXNG | 組み合わせ検索主経路 | 8秒でWikipedia全文検索へ |

すべての外部表示には原則 source と retrieved_at を付ける。Connectorは連絡先付きUser-AgentとキャッシュTTLを使用する。

## 10. 2026-08-14キャプチャの実測記録

全画像は1920px幅。前半8枚の多くは高さ911px、13_58_28と13_58_53は高さ1504pxである。Windows側の指定パスは、WSL/共有環境では /mnt/f/download/ に対応する。

| 時刻 | ファイル | 画面状態・確認内容 | UX課題 |
|---|---|---|---|
| 13:53 | screenshot_2026-08-14-13_53_01.png | Karl Marx + 吉本隆明のAND結果Map。左Mapは13ノード級の結果、右Contextは元の弁証法を保持。 | Mapが更新されたこととContextを保持したことを、利用者にもっと明確に伝えられる。 |
| 13:54 | screenshot_2026-08-14-13_54_30.png | 吉本隆明の中の梧谷行人を選択したContext。次にたどれる語と共通footerが表示。 | 文脈は正しいが、何が現在の主題で何が親MapのContextかを視覚的に強調できる。 |
| 13:55 | screenshot_2026-08-14-13_55_28.png | 共同幻想のMapと概念全景。人物・関係・多言語の枝を表示。 | 複数のチップが一列に密集し、読む順序が弱い。 |
| 13:55 | screenshot_2026-08-14-13_55_55.png | 共同幻想の「この語の意味」Action。Wiktionaryへ自動代替したこと、字単位のglossを表示。 | 自動代替の理由は出るが、検索源の保証範囲と元の主経路との差が小さい。 |
| 13:56 | screenshot_2026-08-14-13_56_20.png | 共同幻想の多言語Action。日本語/英語の表記。 | 表記と意味差を混同しない注意書きはある。次に何を比較するかの提案を理由付きにできる。 |
| 13:57 | screenshot_2026-08-14-13_57_04.png | 吉本隆明の著者Action。経歴、生没、職業、外部専門情報、言語別リンク。 | 実データと外部リンクが豊富。情報源/取得時刻のバッジを人物表にも揃えると一貫する。 |
| 13:58 | screenshot_2026-08-14-13_58_28.png | 非有機的肉体のContext。「この語で見落としやすいこと」にLeib/Körperが表示。MapにもLeib/Körper。 | 重要な概念差は良いが、右の「語の来歴」が一文字分解で始まる。意味単位優先が必要。 |
| 13:58 | screenshot_2026-08-14-13_58_53.png | 埋没した原語Action。Leib/Körperが、訳語に埋没した複数原語として表示。 | この層は適切。文字分解ではなく、訳語の意味上の分岐と区別して配置すべき。 |
| 13:59 | screenshot_2026-08-14-13_59_20.png | 訳語/原語の並置。右側に非=not be、有=to haveなどが列挙。 | これは文字の辞書義であり、非有機的肉体の語義ではない。見出しと階層を直す必要がある。 |
| 14:02 | screenshot_2026-08-14-14_02_25.png | 非有機的肉体の意味Action。自動代替と取得時刻を表示。 | fallbackの透明性は改善。ただし「語全体の意味」「文字の字義」「原語Leib/Körper」を一画面で分離する必要がある。 |

添付画像の原本:

~~~text
/mnt/f/download/screenshot_2026-08-14-13_53_01.png
/mnt/f/download/screenshot_2026-08-14-13_54_30.png
/mnt/f/download/screenshot_2026-08-14-13_55_28.png
/mnt/f/download/screenshot_2026-08-14-13_55_55.png
/mnt/f/download/screenshot_2026-08-14-13_56_20.png
/mnt/f/download/screenshot_2026-08-14-13_57_04.png
/mnt/f/download/screenshot_2026-08-14-13_58_28.png
/mnt/f/download/screenshot_2026-08-14-13_58_53.png
/mnt/f/download/screenshot_2026-08-14-13_59_20.png
/mnt/f/download/screenshot_2026-08-14-14_02_25.png
~~~

## 11. 意味のまとまりを優先する分解仕様

### 11.1 問題の定義

現在の app/connectors/etymology.py は、アルファベット語では語源連鎖とprefix/rootを抽出し、CJK語では _cjk_anatomy で漢字を一文字ずつ取り出す。これは「漢字一字にも意味がある」という問いには答えるが、次の五つを区別しない。

~~~text
語全体の意味                 非有機的肉体
意味のある複合・句単位        非 / 有機的 / 肉体
形態素・短単位                非 / 有機 / 的 / 肉体
漢字・文字の構成              非 / 有 / 機 / 的 / 肉 / 体
語源上の原語                  Leib / Körper 等
~~~

文字の辞書義を結合しても、語全体の意味にはならない。機=weaving machineという文字義から有機的の哲学的意味を導くことはできない。文字の表示自体をやめるのではなく、**親子関係と証拠層を持つ木構造**に変更する。

### 11.2 表示階層

~~~text
L0 語全体            非有機的肉体
L1 意味のまとまり    非 | 有機的 | 肉体       ← 初期表示
L2 形態素/短単位      非 | 有機 | 的 | 肉体
L3 文字構成          非 | 有 | 機 | 的 | 肉 | 体
L4 原語・語源        Leib / Körper / ...
~~~

L1はsemantic grouping、L2は辞書/形態素基準、L3は漢字構成、L4は語源・訳語対応である。L1をL2やL4と偽らない。

### 11.3 NINJALの根拠と実装への翻訳

国立国語研究所のUniDicはShort Unit Word（短単位）を形態解析用の単位とし、BCCWJは短単位を「意味を担う最小の語彙項目」、Long Unit Wordを複合・合成語の単位として扱う。UIでは次のように使う。

~~~text
形態解析候補      UniDic/MeCabのSUW/LUW（実装可能なら）
意味グルーピング  LUW・辞書見出し・品詞/接辞・コーパス境界を根拠に構成
ユーザー確認      「この分け方を採用」または「分割を変更」
文字分解          文字辞書義。ただし「語義ではない」と明示
~~~

外部辞書・形態解析器を導入できない環境では、決定論的fallbackとして以下を使う。

1. 既知の複合語・辞書見出しを最長一致で検出する。
2. 接頭辞・接尾辞候補（非、無、的等）を単独の意味候補として切り出す。
3. 残りの連続文字列を単語候補として残す。
4. 推定であること、使用辞書、取得時刻を表示する。
5. ユーザーが修正・採用するまでunverifiedにする。

fallbackは、常識だけで新しい意味区切りを断定してはならない。

### 11.4 APIの推奨拡張

既存の /api/anatomy を壊さず、レスポンスに segment_layers を追加するか、将来的に /api/segments を追加する。

~~~json
{
  "term": "非有機的肉体",
  "segment_layers": [
    {
      "id": "semantic-0",
      "label": "意味のまとまり",
      "policy": "semantic_grouping",
      "confidence": "high_probability",
      "source": "UniDic/辞書/決定論的ルール",
      "retrieved_at": "ISO-8601",
      "segments": [
        {
          "id": "s0",
          "text": "非",
          "role": "prefix",
          "gloss": "否定・非〜",
          "children": ["m0"]
        },
        {
          "id": "s1",
          "text": "有機的",
          "role": "modifier",
          "gloss": "有機体に関する",
          "children": ["m1", "m2"]
        },
        {
          "id": "s2",
          "text": "肉体",
          "role": "noun",
          "gloss": "身体・物体的な身体",
          "children": ["m3"]
        }
      ]
    },
    {
      "id": "morph-0",
      "label": "形態素・短単位",
      "policy": "morphological",
      "confidence": "unverified",
      "segments": []
    },
    {
      "id": "char-0",
      "label": "漢字構成",
      "policy": "character",
      "confidence": "high_probability",
      "warning": "字義は語全体の語義ではありません",
      "segments": []
    }
  ],
  "sources": []
}
~~~

componentsは後方互換のため残してよいが、UIの初期表示は segment_layers の semantic_grouping を使う。componentsだけを見て新しいUIを描画してはならない。

### 11.5 UIの完成形

Contextまたは「語源と構成要素を解剖する」Actionは次の順にする。

~~~text
語の構成
  この語を読むための意味のまとまり
  [非] [有機的] [肉体]
  ※意味グルーピング。出所・確度を表示。

  形態素・短単位を表示（折りたたみ）
  [非] [有機] [的] [肉体]

  漢字構成を表示（折りたたみ）
  [非] [有] [機] [的] [肉] [体]
  ※字義は語全体の語義ではない。

語の来歴
  原語/語源/訳語差。Leib/Körperはここではなく、
  「翻訳で変わった焦点」または「埋没した原語」に置く。
~~~

各チップを押した時も、直接APIを呼ばず dispatchAction("center", ...) へ渡す。親の意味単位を選択した場合は親語を中心にし、文字を選択した場合は文字の辞書/語源を別語として開く。ただし、文字を押しただけで親語の意味が文字義に置換されてはならない。

### 11.6 受入テスト

~~~text
非有機的肉体:
  初期表示の最上位が 非 / 有機的 / 肉体 である。
  一文字列挙は既定で閉じている。
  「字義は語全体の語義ではない」が表示される。
  Leib/Körperは文字分解と同じ列に置かれない。
  各層にsource/retrieved_at/confidenceがある。

共同幻想、弁証法、矛盾、疎外、身体:
  意味単位が空でも、文字分解へ黙って降格せず、理由付きの次入口を残す。
  文字分解が可能でも、語源や訳語差と同一事実として重複表示しない。

アルファベット語:
  dia + legein等の語源構成を、形態素/文字分解と混同しない。
~~~

## 12. 組み合わせ検索・全メニューのUX仕様

### 12.1 組み合わせ検索の期待フロー

~~~text
1. Map上で「カール・マルクス」を選択。
2. 「別の語と組み合わせる」を押す。
3. 入力欄に「吉本隆明」を入力。
4. ANDを押す。
5. 実際の検索を行う（SearXNG、空/遅延ならWikipedia全文検索）。
6. 成功なら、新Map、演算子、2語、出所、取得時刻を表示。
7. 失敗/空なら元Mapを維持し、ANDを実行した事実、結果がない/主経路が応答しない事実、正確なquery、外部同条件リンク、再試行を表示。
8. どちらの場合もContextの「次にたどれる言葉」と共通footerを残す。
~~~

### 12.2 全メニューの機械的検査

~~~text
node kind: word / original / related / opposite / author / work /
            application / concept / language / domain
layer:      1 / 2 / 3 / 4 / 5
surface:    topbar / popup / edge / node / card / footer / nomiss / Context
action:     全registry ID
state:      success / empty / timeout / HTTP error / popup blocked / stale response
viewport:   1128x900 / 1920x1000 / 狭幅モバイル相当
~~~

各ケースで判定する。

~~~text
A. 押下可能か（実マウス/実pointerで押せるか）
B. 意図したAction IDか
C. effectに応じた状態が遷移したか
D. 途中で空画面/無限busy/未説明の停止がないか
E. 失敗時に元Map/Contextを保持したか
F. 次の操作が少なくとも一つ以上実在するか
G. 1ユーザー操作=1履歴commitか（transient除外）
H. 外部リンクが新タブで現在画面を壊さないか
~~~

### 12.3 Actionごとの失敗時期待

| Action群 | 成功 | 空/失敗 |
|---|---|---|
| center | 検索欄、Map、Contextを同じtermへ更新 | 旧Map/Context維持、対象termのMenu再表示、Toastで説明 |
| meaning/multilingual/anatomy/contrast/colloc | Actionパネルにデータと出所 | パネル内に理由＋同語の継続入口。空パネル禁止 |
| combine | 条件付きMapへ置換 | 元Map維持、条件・検索源・再試行・外部同条件リンク |
| applyLens/focus/hl/resetFocus | Mapの表示状態だけ更新 | 旧Map維持、レンズ/分岐の代替入口 |
| external | 外部資源一覧 | パネルを残し、別資源を出す。外部タブが開けない場合はMenu再表示 |
| newtab | 新タブ、現在画面を保持 | popup blockerをToast、Menu再表示 |
| shelf | localStorageへ保存、Toast | 現在Mapを変えず保存失敗を隠さない |
| author | Wikipedia/Wikidata実データ | 別表記/外部検索/継続入口 |
| dimension | 該当節へ進み、または組み合わせ検索等へ | 「準備中」だけで終えずAction結果面 |
| panorama | 右Contextを開く | Contextを保持し、同語の次入口・外部資源 |
| deepsearch/play | 実行可能なprompt/ゲーム | 同語の研究・外部・組合せ入口 |

## 13. 知的好奇心・教育・哲学と言語の設計原則

### 13.1 情報ギャップは空白ではなく扱える差分として出す

好奇心研究の情報ギャップ理論では、知っていることと知りたいことの差が注意を引き、情報探索を促す。ただし、巨大すぎる未知は圧倒し、小さすぎる差は退屈になり得る。

~~~text
悪い例: 「詳しくは外部サイトへ」だけ
良い例: 「日本語では一語だが、ドイツ語ではLeib/Körperという焦点差がある」
        → 「生きられた身体」と「物体的身体」を比較する
        → 原典/思想家/用例へ進む
~~~

「この語で見落としやすいこと」は、出典接地した対比が成立した時だけ表示する。差分が推測の場合は、見出しごと出さないか、明確に解釈仮説とする。

### 13.2 自律性・有能感・関係性をUIへ変換する

~~~text
自律性  ユーザーが「意味/形態素/文字/語源/比較」を選べる。推薦は理由を明示し、強制しない。
有能感  いまのterm、Map、Context、処理状態、出所、次の一手が常に見える。
関係性  思想家・著作・原典・異なる言語・反対概念へ接続し、孤立した定義で終わらない。
~~~

「次のおすすめ」は一つに決めつけず、少なくとも異なる種類の入口（根拠を読む、言語差を見る、反対概念を見る、組み合わせる）を出す。

### 13.3 認知負荷と段階的開示

情報を一つの長い連続表示に詰め込まず、ユーザーが自分のペースで意味単位を開く。Map、Context、Actionの役割を分離し、本文の節と目次を一致させる。最初は「この語の意味」「意味のまとまり」「次に何を見るか」を優先し、語源の深い連鎖・字義・原典の詳細は展開層へ置く。

### 13.4 解釈学：意味を単一の答えに潰さない

~~~text
この場所での意味        現在のMap/文脈
語の来歴                語自身の形成・語源
原語・思想家・著作       概念を担った人物・テキスト
翻訳で変わった焦点       出典のある訳語差、Leib/Körper等
関係・対立・運動         近縁/対立/影響
各言語での表記           表記の広がり。意味差を断定しない
実際の用法・共起         実コーパスで取得できる時だけ
次にたどれる言葉        行き止まり防止
~~~

### 13.5 概念分析から概念設計へ

~~~text
問い: 「非有機的肉体」を非 / 有機的 / 肉体として読む根拠は何か。
仮説: 日本語の意味まとまりとしては上記の三分割が読みやすい。
根拠: 形態解析、辞書見出し、原典のLeib/Körper、訳文の用法。
未確認: すべての版・訳者で同じ分割が妥当か。
判断: この研究ではsemantic_groupingを採用する。
~~~

## 14. 今後のUX改良案（優先順位付き）

### P0：意味分解の階層是正

1. segment_layersをAPIに追加。
2. gAnatomyPanelとContextの「語の来歴」にL1を既定表示。
3. L2/L3はdetailsまたはタブで展開。
4. Leib/Körperは「翻訳で変わった焦点」「埋没した原語」へ分離。
5. 文字glossに「字義」のラベルを付け、語義として再利用しない。
6. 非有機的肉体、共同幻想、弁証法、矛盾、疎外のfixtureと実データで検証。

### P1：操作結果の可視性

1. Graph noteを「実行した操作 / Mapの状態 / Contextの状態 / 出所」の4項に分ける。
2. 組み合わせ成功時に、Map上部に AND: カール・マルクス × 吉本隆明 を固定表示。
3. 代替検索時に、主経路: SearXNG、代替: Wikipedia全文検索、保証範囲: Wikipedia内全文を表示。
4. 失敗時のToastだけに頼らず、画面に残るstatus panelを使う。

### P1：Contextの情報設計

1. Context先頭に現在の語、親文脈、取得時刻を表示。
2. 節の長さと重要度に応じた折りたたみ。ただし「次にたどれる言葉」は常時見える。
3. 目次activeと本文見出しの一致を維持。
4. 同じ事実を「語源」「比較」「埋没原語」に重複表示しない。

### P2：知的好奇心を研究へ変換

1. 「この語で見落としやすいこと」に、出典付きの小さな対比カードを出す。
2. 各対比カードに「なぜ次にこの語を提案するのか」を一行表示。
3. 「次の提案」を、根拠・言語差・反対・応用の4種に分ける。
4. 推薦をクリックせず、自分で選ぶ。自動遷移・無限スクロール・点数化はしない。

### P2：研究痕跡との接続

1. 意味単位の採用・修正を研究デスクのnote/decisionへ送る。
2. segmentのsource/confidence/retrieved_atをExportに含める。
3. 「この表示を研究ノードに保存」をAction footerへ追加する場合もregistry/dispatcher経由にする。

## 15. 検証結果と検証コマンド

### 15.1 生成直前に実行した静的検査

2026-08-14のこの作業中に次を実行し、すべて終了コード0だった。

~~~text
node --check app/static/app.js
.venv/bin/python -m compileall -q app
git diff --check
.venv/bin/python -m pytest -q tests/test_dispatch_single_path.py
~~~

最後の結果は 5 passed。

### 15.2 このセッションで直近確認済みのUI検査

コード生成前の現行変更に対し、次の結果を確認済みである。数値は再実行時に外部API・ブラウザの状態で変動し得る。

~~~text
panorama_check.js             138/138 PASS
combine_resilience.e2e.js       6/6 PASS
no_negative.e2e.js              2/2 PASS
play.e2e.js                     5/5 PASS
shelf.e2e.js                    6/6 PASS
perspective.e2e.js              5/5 PASS
test_dispatch_single_path.py    5 passed
~~~

panorama_checkの内訳は、1128px/1920pxの各viewportで全Action列挙、実クリック、target mismatch 0、effect transition mismatch 0、history commit mismatch 0、Menu/Actionの交差・遮蔽0、未分類0を含む。

### 15.3 E2Eの再実行

~~~bash
export DX_PORT=8099
export DX_CHROMIUM=/home/handa/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome
.venv/bin/python -m pytest -q
./verify.sh
~~~

verify.shは内部でサーバーを起動する。統合系（SearXNG/Wikidata/外部ランダム結果に依存）と決定論的gateを区別する。失敗した状態で本番deployしない。

### 15.4 組み合わせのライブ確認

直近の実測値（ポート8145の一時DB使用時）:

~~~text
GET /api/combine?a=カール・マルクス&b=吉本隆明&op=and&lang=ja
HTTP 200
所要約8.89秒
nodes=13, edges=12, has_results=true
source=Wikipedia全文検索
~~~

**未検証:** この仕様書生成直後のプロセスでポート8145を常駐させたままにしていること。新しいライブ確認が必要な場合は、一時DBで起動する。

~~~bash
DIALEXIS_DB=/tmp/dx-live-check.db \
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8145
~~~

## 16. 空のマシンからの再構築手順

この節とこのファイルだけを渡されたAIは、次の順番で実装する。外部APIの現在の仕様は実行時に公式ドキュメントで確認し、返却データは必ずこの文書の封筒へ正規化する。

### Step 1：骨格

1. Python仮想環境とrequirementsを用意。
2. FastAPI app.main:appを作る。
3. Jinja2でbase.htmlとindex.htmlを作る。
4. /healthzを実装し、SQLite初期化をimport時にidempotent実行。
5. /static/app.js、style.cssはビルドなしで配信。

### Step 2：外部source封筒

1. cached_get_jsonを実装。
2. source/retrieved_at/cached/error/dataを全connectorで返す。
3. timeout・HTTP errorを空の成功と区別する。
4. DIALEXIS_CONTACTをUser-Agentに含める。

### Step 3：/origin

1. Wiktionary traceとWikidata conceptを並列取得。
2. /api/origin/graphはroot(layer1)、domain(layer2)、real entity(layer3+)を作る。
3. domainはqを持たない構造ノードとして扱う。
4. real entityだけがクリック可能で、stable id、term、kindを持つ。
5. Canvas Mapとfallback表を描画。
6. originInit → originExplore → originResolveGraph → originRun → Contextの順を固定。

### Step 4：surface/dispatcher

1. Menu、Action、Contextをsurface managerで管理。
2. 21 Action registryをそのまま実装。
3. 表示面に直接gWordAspect等を呼ばせない。
4. dispatchActionのeffectによりMap/center/context/action/store/newpageを区別。
5. async操作は必ずawaitし、成功後だけ履歴をcommit。

### Step 5：意味分解

1. まずsegment_layersのデータ型を追加。
2. semantic groupingを既定表示。
3. morphological/character/etymonを子層へ。
4. 字義を語義として扱わないテストを追加。

### Step 6：組み合わせとfailure-safe

1. SearXNGを8秒で切り上げる。
2. Wikipedia全文検索を同一条件の退避にする。
3. has_results=falseを明示。
4. 空/timeout/errorに対する説明面を実装。
5. 元Mapを上書きしない。

### Step 7：研究デスク、Watcher、Export

1. SQL schemaを作る。
2. node/edge/provenance CRUD。
3. argument/premise、validity/soundness。
4. Markdown/JSON-LD/BibTeX/CSL JSON。
5. cron/systemdからharvesterを起動し、harvester_status.jsonの不在・古さ自体を異常にする。

### Step 8：受入

1. 静的構文。
2. pytest。
3. 実Chromiumで全表示面を実クリック。
4. 失敗注入で無限busy・空パネル・誤履歴を検査。
5. 1128pxと1920pxで配置を検査。

## 17. 運用・デプロイ・ロールバック

### 17.1 ローカルデータ

研究データはSQLite一ファイル。キャッシュは削除して再取得できる。公開運用では data/dialexis.db を安全にバックアップする。

### 17.2 VPS

deploy/bootstrap_vps.sh、deploy/vps_update.sh、deploy/systemd/、deploy/nginx-dialexis.confが既存資料である。更新は次の順番に限定する。

~~~text
git pull
requirements更新
pytest
verify.sh / 対象E2E
verified_sha確認
systemd restart
healthz確認
harvester_status確認
~~~

本仕様書生成では本番deploy、push、commitを行っていない。

### 17.3 安全規則

- git reset --hard、git checkout --、広範な削除を行わない。
- _backups/を消さない。
- DBをコードから自動削除しない。
- 外部APIキーをログ/SQLiteへ保存しない。
- 失敗時に古いMapを新検索の結果と偽らない。

## 18. 未検証・既知の限界

1. **未検証:** この文書だけで、現行リポジトリなしにピクセル完全なサイトを再現できること。外部API、フォント、ブラウザ、時間依存のため機能的同一性を受入とする。
2. **未検証:** UniDic/MeCabを本番VPSへ追加した場合のRAM・ライセンス・応答時間。まずAPIデータ型とfallbackを実装し、導入を別判断にする。
3. **未検証:** 非有機的肉体の 非 / 有機的 / 肉体 が、全辞書・全訳・全文脈で唯一の正解であること。これは今回のUX既定案であり、確定した語源学的主張ではない。
4. **未検証:** SearXNGが公開運用で常時応答すること。Wikipedia全文検索は一般Webの代用品ではない。
5. **未検証:** すべての外部sourceのレート制限が将来も同じであること。
6. **未検証:** 現在の全E2Eを仕様書生成直後にネットワーク込みで再実行した結果。直近結果は15.2に保存。
7. **既知の限界:** 現在のCJK解剖は一文字分解が中心であり、意味単位階層はこの文書の次の実装課題。
8. **既知の限界:** 実コーパス共起は現在ドイツ語DWDS中心で、他言語は正直な空結果として扱う。
9. **既知の限界:** AIを使うLevel 2の内容は人間が出典確認するまで未確認である。

## 19. 次のAIへの作業指示

このファイルを受け取ったAIは、最初に以下だけを行う。

~~~text
1. このファイルを読み、0、6、11、12、18を受入基準として固定。
2. git statusを確認し、既存変更を保存。
3. 現行の非有機的肉体を実ブラウザで確認。
4. segment_layersのfixtureを作る。
5. 文字分解を既定表示から子層へ移す。
6. 全Actionのdispatcher契約を壊さない。
7. 静的検査→対象E2E→全E2Eの順に実行。
8. 画面キャプチャと検証結果をこのファイルの改訂履歴へ追記。
~~~

知的好奇心を理由に、ユーザーを自動遷移・無限スクロール・報酬点数へ誘導してはならない。推薦の目的は滞在時間ではなく、問いの深まりである。

## 20. Web研究根拠（2026-08-14照合）

### 言語単位・形態解析

- [NINJAL UniDic: What is UniDic?](https://clrd.ninjal.ac.jp/unidic/en/about_unidic_en.html) — UniDicのShort Unit WordとMeCab形態解析辞書の説明。
- [NINJAL BCCWJ: Morphological Information](https://clrd.ninjal.ac.jp/bccwj/en/morphology.html) — Short Unit Wordを意味を担う最小語彙項目として説明し、Long Unit Wordと対比する。非/有機/的/肉体を形態単位候補、非/有機的/肉体をUIの意味グルーピング候補として分ける根拠にした。
- [NINJAL Corpus of Spontaneous Japanese data](https://clrd.ninjal.ac.jp/csj/en/data-index.html) — SUWとLUWの区別。

### 好奇心・教育心理

- [Loewenstein, The Psychology of Curiosity, DOI](https://doi.org/10.1037/0033-2909.116.1.75) — 情報ギャップ理論の基礎文献。
- [Markey & Loewenstein, Curiosity, Carnegie Mellon University](https://www.cmu.edu/dietrich/sds/docs/loewenstein/Curiosity_IntlHandbookEmotEduc.pdf) — 教育文脈で、ギャップの重要性・顕著性・意外性を扱うレビュー。
- [Curiosity in Classrooms Framework, PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9022842/) — 好奇心を未知・不確実性・情報探索として教育設計へ操作化する研究。
- [Ryan & Deci, Self-Determination Theory](https://selfdeterminationtheory.org/about-the-theory/) — 自律性・有能感・関係性を支える環境が、持続・創造性・高品質な動機づけを促すという設計根拠。

### 認知負荷・段階的開示

- [Cognitive Theory of Multimedia Learning, PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9762622/) — segmenting principle、短くユーザーが制御できる単位、限定されたワーキングメモリに関する整理。
- [Mayer, Educational Psychology Review / ERIC](https://eric.ed.gov/?id=EJ1407410) — active processing、limited capacity、dual channelの整理。

### 言語・意味・哲学

- [Stanford Encyclopedia of Philosophy: Concepts](https://plato.stanford.edu/archives/fall2022/entries/concepts/index.html) — 概念が分類・推論・記憶・学習・意思決定の構成要素であり、言語と概念の優先関係に争いがあること。
- [Stanford Encyclopedia of Philosophy: Hermeneutics, 2025](https://plato.stanford.edu/archives/sum2025/entries/hermeneutics/) — 解釈を文法的構造、著者/歴史、存在・知・言語の問題と結びつける根拠。
- [Stanford Encyclopedia of Philosophy: Conceptions of Analysis, Conceptual Engineering](https://plato.stanford.edu/entries/analysis/s6.html) — 既存概念を明確化・改善する概念設計の議論。利用者が意味単位を採用・比較できるUIの哲学的背景。

## 2026-08-16 実装更新・検証追補

この追補は、上記の「次の実装課題」「既知の限界」のうち、2026-08-16時点で実装・検証が完了した項目を上書きする。再構築するAIは、本文の設計意図を保ちつつ、この追補の現行コード対応と検証結果を優先する。

### 実装済み

- `app/connectors/etymology.py` に意味単位層を実装した。`非有機的肉体` は既定の主表示を `非 / 有機的 / 肉体` とし、文字単位 `非 / 有 / 機 / 的 / 肉 / 体` は character 層の補助情報へ下げた。意味単位は推定ルールによる構造であり、全訳・全辞書に対する唯一の語源学的正解とは扱わない。
- `/api/anatomy` と `/api/origin` に `segment_layers` を追加した。各層には `level`、`priority`、`units`、`source`、`confidence`、`retrieved_at` を持たせ、既存の `components` と `chain` は後方互換のため残した。
- `app/static/app.js` の意味・解剖・並置・Context表示は、語全体 → 意味のまとまり → 文字/語源の補助層の順で描画する。文字辞書義には「語全体の意味ではない」と明示し、初期表示では折りたたむ。
- dispatcher は未知Action、未宣言effect、非同期例外、空結果を復旧経路へ送る。復旧面には、何を実行したか、外部情報・入力条件・画面構築のどこを確認すべきか、元Map/Contextを保持したこと、同じ語から選べる次の操作を表示する。
- 組み合わせ検索の結果面は、実行した演算子を動的に表示する。AND成功時は結果Mapへ進み、空/失敗時は元Mapを保持して、条件・結果の説明・外部同条件リンク・再試行・次の入口を残す。
- 部分的な外部応答（`term`だけ返り、`components`/`chain`が欠落する場合）でも、配列欠落をJavaScript例外にせず、画面を継続構築する。

### 実ブラウザ検証済み

以下は `tests/e2e/run_local.js` でUvicornとChromiumを同一のローカル実行系に起動して確認した結果である。Chromiumの実行には環境上の補助ライブラリを `LD_LIBRARY_PATH` で指定する。各テストは一時DBを使用し、既存研究DBを変更しない。

~~~text
semantic_units.e2e.js       7/7 PASS
combine_resilience.e2e.js   6/6 PASS
menu_resilience.e2e.js     10/10 PASS
failure_injection.e2e.js    9/9 PASS
auto_fallback.e2e.js        6/6 PASS
dim_no_stop.e2e.js          6/6 PASS
universal_menu.e2e.js      13/13 PASS
universality_sweep.e2e.js   3/3 PASS
~~~

`universality_sweep.e2e.js` は、6パネル × 5語種 = 30通りの続行フッター、階層2/3/4の共通メニュー、CJK・アルファベット語を含む5語の解剖を掃引した。これは「全ての語・全てのmenuが数学的に無条件で成功する」ことではなく、失敗・空・部分応答でも未説明の行き止まりを残さない契約を決定論的に検証した結果である。

実行例:

~~~bash
LD_LIBRARY_PATH=/home/handa/pwlibs/usr/lib/x86_64-linux-gnu \
  node tests/e2e/run_local.js tests/e2e/universality_sweep.e2e.js
~~~

### 公開URLでの反映確認（2026-08-16）

VPS反映後の `http://219.94.244.239:8000` を読み取り・実ブラウザで確認した。

~~~text
healthz                         200
/api/anatomy?非有機的肉体       semantic_units=[非, 有機的, 肉体], character priority=3
/api/combine?カール・マルクス×吉本隆明&op=and
                                has_results=true, nodes=13, edges=12, source=SearXNG
公開 combine_ui.e2e.js          4/4 PASS
~~~

公開ブラウザでは、canvasを可視領域へ移動し、語ノード → 「別の語と組み合わせる」 → `労働` → `AND` の順に実操作し、`「疎外」を「労働」で絞り込み（AND）` の結果Mapへ遷移した。公開URL上のテストは外部APIの初回キャッシュ状態により時間が変動するため、同一操作を再試行できる構成にしている。

### 残る未検証・限界の更新

- **未検証:** 公開本番サイトへのdeploy後に、同じ変更が実際の公開URLへ反映されていること。この作業ではcommit/push/deployは行っていない。
- **未検証:** 外部APIが将来も同じ内容・レート制限・応答時間を保つこと。実ブラウザ検証は主要APIをfixture/ローカル実装で固定し、失敗注入を併用した。
- **未検証:** `pytest -q` 全体をこの追補直後に完走した結果。対象の意味単位・dispatcher・UI gate・実ブラウザ検証は個別に通過している。現環境では、6つのTestClient依存テストを含む全85件を実行すると、最初の同期TestClient呼び出しがアプリに到達する前にAnyIOのblocking portalで待機し、180秒上限で終了した。最小FastAPIアプリでも再現し、ASGITransportとUvicorn実ブラウザ経路は正常だったため、現時点ではアプリの機能失敗ではなくテストランナー依存の環境制約として扱う。
- **未検証:** `非 / 有機的 / 肉体` が全辞書・全訳・全文脈で唯一の分解であること。現行UIの既定表示であり、採用・修正可能な意味グルーピングとして扱う。
- **既知の限界:** 形態素解析器（UniDic/MeCab）を本番依存にせず、現在は決定論的fallbackを使用している。将来導入する場合も、semantic層・character層・出所表示の契約を壊さない。

## 改訂履歴

### 2026-08-14

- 現行HEAD、未コミット変更、実行方法、全ページ/API/DB/Action契約を統合。
- 2026-08-14提供の10キャプチャを確認し、画面状態とUX課題を記録。
- SearXNG→Wikipedia全文検索退避、組み合わせ検索のhas_results、失敗時の説明面を記録。
- 非有機的肉体の一文字優先分解を、意味まとまり優先の階層仕様へ再定義。
- NINJAL、好奇心研究、自己決定理論、認知負荷、SEPの根拠を参照し、改良方針へ反映。
- 本ファイル生成自体以外のコード変更・commit・deployは行っていない。

### 2026-08-16

- 意味単位優先のAPI/UI実装、dispatcher復旧面、組み合わせ結果面の動的演算子表示を反映。
- 部分応答の配列欠落に対する画面構築の防御を追加。
- 失敗注入・自動代替・探究次元・共通メニュー・普遍性掃引を実ブラウザで再検証し、上記の結果を記録。
- VPS公式デプロイ後のhealthz、意味単位API、AND API、公開ブラウザ組み合わせ操作を確認。
