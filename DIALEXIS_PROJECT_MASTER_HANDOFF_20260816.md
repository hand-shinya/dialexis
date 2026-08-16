# Dialexis プロジェクト完全引継ぎ記録

**スナップショット:** 2026-08-16（Asia/Tokyo）
**対象:** Dialexis / 反省的哲学研究インフラ
**目的:** 本プロジェクトを全く知らないAIまたは開発者が、この一ファイルと現行リポジトリだけで、目的・背景・画面・コード・データ契約・失敗史・検証・公開運用を理解し、同じ状態を再現して継続開発できるようにする。

本書は、2026-08-14時点のPROJECT_REPRODUCTION_SPEC_20260814.md、2026-08-01時点の
Dialexis_再現継承ガイド、2026-08-11の全景クリック検証資料を基礎に、
現行コード、Git履歴、検証結果、公開反映結果を2026-08-16時点へ統合した
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
| 現在のHEAD | 439e367 公開確認後の検証済みSHAを更新 |
| origin/main | 439e367 |
| コードを検証したSHA | 4f0ef9886aa85136c8afa02996f54be74a2bb1d6 |
| 検証マーカー | deploy/verified_sha.txt |
| 公開URL | http://219.94.244.239:8000 |
| 公開アプリ | /opt/dialexis |
| 公開サービス | systemd dialexis.service |
| 作業フォルダー（Windows） | I:\GoogleDriveMirror\MyKnowledgeBase\Main\論考\哲学DESK |
| 作業フォルダー（WSL） | /mnt/i/GoogleDriveMirror/MyKnowledgeBase/Main/論考/哲学DESK |
| ライセンス | Code: AGPL-3.0 / Documentation: CC-BY-4.0 |

439e367は、4f0ef98でコードと公開URL確認を終えた後のマーカー更新である。
したがって、4f0ef...以降に未検証の製品コードが入ったという意味ではない。
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
~~~

公開ブラウザでは、Canvas上の中心語を実マウスクリックし、
「別の語と組み合わせる」→「労働」→「AND」を実行し、
「疎外」を「労働」で絞り込み（AND）の結果Mapへ遷移した。

---

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
/                    問いの入口、Question Doors
/explore             統合探索
/origin              原語探求、言語Map、概念全景
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

### 11.2 2026-08-16の結果

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
既知参照点は1c19fd5（実装）、4f0ef98（検証・公開確認）、
439e367（現在の公開確認済みHEAD）。

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

### 今後

- 上書きで履歴を消さず、日付と理由を追記する。
- 実測していないことは未検証と明記する。
- 決定論gate、network統合、全景掃引を別の証拠として扱う。
- コードと文書が矛盾したら実体を測り、文書を直し、理由を残す。
- 新しい設計判断では、保存・棄却・上位化したものを記録する。
