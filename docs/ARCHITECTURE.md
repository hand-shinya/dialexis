# ARCHITECTURE.md — システム構造設計書

対象読者：本システムを理解・改良しようとする開発者（人間・AI）。上位規範は `GENESIS.md`。

## 1. 全体構成（MVP）

```
ブラウザ (vanilla JS, localStorage にLLM鍵)
   │ fetch JSON
FastAPI (app/main.py)
   ├── pages: Jinja2 templates + i18n (ja/en)
   ├── /api/explore ──► connectors ──► 無料学術API群（ライブ照会＋SQLiteキャッシュ）
   ├── /api/projects… ──► SQLite（研究過程グラフ）
   ├── /api/counter ──► Level0: counter_checklists.json ＋ OpenAlex対立文献検索
   │                    Level2: llm/adapter.py（BYOキー中継・非保存）
   ├── /api/watches… ──► check_watch()（Web UIとharvesterが同一コードを共有）
   └── /api/ledger ──► ai_ledger（AI透明性台帳）
cron / systemd timer ──► app/harvester.py ──► harvester_status.json（不在自体が警報）
```

技術選定の原理：**退屈で再現可能な技術を選ぶ**（GENESIS Part IV 末尾）。ビルド工程なし・フレームワークなし・外部DBなし。理由：月額千円級VPSで動き、初見の人間/AIが依存関係の考古学なしに再構築できること自体が公理7（撤退可能性）の実装である。

## 2. レイヤーと将来対応

GENESIS の6層構想（Source / Concept / Argument / Historical / Research Process / Reflexive）に対する現在の実装状態：

| 層 | MVP実装 | 将来（ROADMAP参照） |
|---|---|---|
| Source 資料層 | connectors（ライブ参照）＋ provenance | TEI/IIIF接続、PhilPapers |
| Concept 概念層 | Wikidata QID をアンカーに使用 | 概念重力ビュー、訳語ノード |
| Argument 論証層 | nodes/edges ＋ arguments/argument_premises（P1..C 標準形・隠れた前提・声・頁ロケータ・妥当性≠健全性の形式分解） | 論証チェイン・PhilPapers 引用チェイン |
| Historical 歴史層 | Wikidata claims（生没・影響） | 受容史・論争再構成ビュー |
| Research Process 研究過程層 | **中核実装済**（projects + nodes + decisions + provenance） | 公開研究痕跡コモンズ |
| Reflexive 反省層 | ai_ledger, origin/confidence 分類 | 研究者立場宣言、偏り検査 |

## 3. データモデル（SQLite・app/db.py が唯一の定義）

```
projects 1─n nodes 1─n provenance（source_name/url/quote/retrieved_at/locator）
              │
              └─n edges（src/dst は nodes.id）
projects 1─n arguments 1─n argument_premises（P1..Pn・seq 順）
              └ conclusion_node_id? / premises.node_id? → nodes.id（ON DELETE SET NULL）
watches 1─n watch_hits
api_cache（URL→JSON、TTL付き）
ai_ledger（AI呼び出しの追記型台帳）
```

- `nodes.type`: question / claim / evidence / counterclaim / uncertainty / interpretation / decision / note / source
- `nodes.confidence`: confirmed / high_probability / unverified / interpretive_hypothesis / speculation（**固定語彙。追加はGENESIS改版を要する**）
- `nodes.origin`: human / ai / external
- `nodes.status`: open / adopted / held / rejected（採用/保留/棄却）
- `edges.rel`: supports / contradicts / answers / refines / derives_from / cites / about / responds_to
- `arguments.validity`: valid / invalid / unassessed／`arguments.soundness`: sound / unsound / unassessed（**新規ドメイン語彙。妥当性と健全性は常に別フィールド。GENESIS 固定の確度語彙とは別物であり D級憲法変更ではない**）
- `argument_premises.voice`: author / commentator / self（**新規ドメイン語彙。`nodes.origin`＝ツール上の作成主体 とは別意味の「哲学的な声」**）／`hidden`: 隠れた前提フラグ（寛容の原理）／`locator`: 標準ロケータ（Stephanus/Bekker/A-B）

Graph DB（Neo4j等）への移行は、公開研究痕跡の横断検索（フェーズ2）で辺数が単一SQLiteの実用限界を超えたときに検討する。エクスポートがJSON-LDである時点で移行コストは限定的。

## 4. コネクタ設計（公理3・4の実装）

すべてのコネクタは `connectors/base.py` の `cached_get_json()` を使い、次の統一封筒で返す：

```json
{"source": "openalex", "retrieved_at": "ISO8601", "cached": false,
 "error": null, "data": …}
```

- 失敗は `error` に文字列で返し、**握りつぶさない**。UIは情報源エラーをバッジで表示する（沈黙する失敗が最悪、という原則）。
- User-Agent は連絡先つき（環境変数 `DIALEXIS_CONTACT`）。丁寧アクセスは無料APIの持続可能性への義務。
- キャッシュTTL：検索系 1h／エンティティ系 24h／新着監視系 10min。

## 5. LLMアダプタ（公理5・6の実装）

- 鍵はブラウザ localStorage のみ。リクエストごとにJSONボディで中継され、サーバーは保存もログもしない（`ai_ledger` に記録されるのは provider/model/task/時刻/入力先頭200字のみ）。
- `adapter.GUARD` が全プロバイダ共通のシステムプロンプトとして、確立した学説/解釈/思弁の分離・一次資料の指名・翻訳リスクの明示を強制する。
- プロバイダ追加は `PROVIDERS` 辞書への1関数追加で完了する。

## 6. Harvester（外部拘束原理）

新着検出の発火点はAIにも人間の記憶にも置かない。cron / systemd timer が `python3 -m app.harvester` を起動し、結果を `data/harvester_status.json` に必ず書く。**このファイルが古い・無いこと自体を異常として監視する**（OPERATIONS.md）。Web UIの「今すぐ照会」と同一の `check_watch()` を共有するため、挙動の乖離が構造的に起きない。

## 7. i18n

`app/i18n/*.json`（UI文字列）＋テンプレート内の言語分岐（長文）。言語追加＝JSONファイル1枚の追加＋`main.py` の `("ja", "en")` タプルへの追記。コンテンツの言語は情報源側の言語がそのまま流れる（Wikidataラベル・Wikipedia要約は `lang` パラメタで解決）。
