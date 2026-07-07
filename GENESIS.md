# GENESIS.md — Dialexis 憲法 / The Constitution of Dialexis

> 本文書はこのリポジトリの最上位規範である。コード・UI・運用・改良のすべては本文書から導出されなければならず、矛盾する変更は本文書の改版（第五部の手続）なしに行ってはならない。
>
> This document is the supreme norm of this repository. All code, UI, operations and improvements must be derivable from it. An English rebuild prompt is included in Part IV.

---

## 第一部　目的と定義

### 源流（この一段落がすべての祖先である）

このシステムの源流は、一人の人間の次の願いである：**哲学に興味を持った者が——あるいは哲学とは知らずに何かの思考や考え方に疑問を持った者が——老若男女を問わず、過去から現在、未来に至る哲学とその関連情報に、その人にとって最も効率的・合理的な形で出会い、その人の思考が発展・拡張し、何らかの利益を得られること。** 情報は探索や過負荷の負担なく、意味ある形で現れ、実際にその人の思考と判断に反映されなければならない。道具や方法をそれ自体の目的とすり替えてはならない。

### 最終定義

**Dialexis（ディアレクシス、διάλεξις＝論究）とは、反省的哲学研究インフラ（Reflexive Philosophy Infrastructure）である。** 哲学的な問いを持つあらゆる人間——小学生から専門研究者まで——に対して、(1) 世界中の生きた無料学術情報源への鍵不要の統合レンズと、(2) 問い・主張・根拠・反証・未確認事項・判断を第一級の対象とする研究過程デスクを与え、その人の問いを**より深く・より根拠あり・より反証可能で・より共有可能な**形へ変換する。そしてその研究過程自体が、公開を選べば、次の利用者の土壌となる。

### 七公理（すべての設計判断の判定基準）

| # | 公理 | 内容 | 違反の典型例 |
|---|---|---|---|
| 1 | **問いの変換** | 目的は知識の消費ではなく、利用者の問いの変換である | 「正解」を返して終わるUI |
| 2 | **使用即貢献** | 一人の利用のために完全であり、利用の痕跡が公共の土壌になる | コミュニティ形成を前提とした機能 |
| 3 | **レンズ原理** | 知識は生きた外部情報源に置き、保存するのは来歴・痕跡・一時キャッシュのみ | 百科事典的コンテンツの内部蓄積 |
| 4 | **鮮度の刻印** | 取得時刻なき外部情報を表示しない。古さで黙って語らない | timestamp のない要約表示 |
| 5 | **退化階梯** | 全機能に Level 0（無料・鍵不要・決定論的）を義務づける。鍵は昇格のみ | LLMキーがないと動かない機能 |
| 6 | **AI透明性** | AIが触れた出力はすべて明示・台帳記録・確度分類され、確認まで「未確認」 | AI出力の地の文への混入 |
| 7 | **撤退可能性** | 全データは標準形式（Markdown/JSON-LD）で持ち出せ、本システム消滅後も研究は生きる | 独自形式へのロックイン |

確度分類（公理6の語彙・固定）：`confirmed 確定` / `high_probability 高蓋然` / `unverified 未確認` / `interpretive_hypothesis 解釈仮説` / `speculation 思弁`

---

## 第二部　棄却した方向（なぜこれ「ではない」のか）

| 棄却した方向 | 理由 |
|---|---|
| 哲学版 Wikipedia | 専門家検証・出典来歴・論争構造・研究過程が扱えない |
| 哲学版 Google Scholar | 検索はできるが概念の変形・反証可能性を扱えない |
| 哲学版 ChatGPT | 流暢さが出典・確度・反論・未確認事項を消す |
| 個人専用思考OS | 強いが普遍性がない。特定個人の方法は「モード」の一つに格下げする |
| 美しい思想マップUX | 根拠層が薄く研究者が使えない |
| 静的な哲学データベース | 構築コスト・著作権・陳腐化の三重苦。Marxですら新資料発見がありうる以上、静的DBは前提から誤る |
| 専門家レビュー前提の品質保証 | 初日に専門家は居ない。レビューは後から接ぎ木できる設計にする（公理2） |
| コミュニティLLMプールの即時実装 | 不正利用対策なしの共有鍵は危険。設計のみ先行（docs/DONATIONS.md） |

## 第三部　公理→実装 対照表

| 公理 | 実装箇所 |
|---|---|
| 1 問いの変換 | 研究デスク（project作成時に「最初の問い」が第一ノードになる）、反証エンジン |
| 2 使用即貢献 | `is_public` フラグ＋エクスポート（公開研究痕跡の共有はROADMAP第2段） |
| 3 レンズ原理 | `app/connectors/`（Wikidata, OpenAlex, Crossref, OpenCitations, Wikipedia/Wikisource, Gutendex）、`api_cache` テーブル |
| 4 鮮度の刻印 | 全connector戻り値の `retrieved_at`、UI の freshBadge、`provenance.retrieved_at` |
| 5 退化階梯 | `app/llm/adapter.py`（BYOキー・サーバー非保存）、反証エンジン Level 0（`counter_checklists.json`）、段階的読解 Level 0（`glossary_seed.json`） |
| 6 AI透明性 | `ai_ledger` テーブル、`origin=ai` バッジ、adapter.GUARD システムプロンプト、`/api/ledger` |
| 7 撤退可能性 | `/api/projects/{id}/export.md`・`export.jsonld`、SQLite単一ファイル、AGPL-3.0 |
| （外部拘束） | `app/harvester.py` — 新着検出の発火点はAIにも人間の記憶にも置かず、cron/systemd timer に置く |

---

## Part IV — Rebuild Prompt（再構築プロンプト・自己完結）

> 受入基準：以下のプロンプトだけを渡された任意の有能なAIが、本リポジトリと思想的に同一のシステムを再構築できること。/ Acceptance criterion: any capable AI given ONLY the prompt below can rebuild a system intellectually identical to this repository.

```
You are to build "Dialexis", a Reflexive Philosophy Infrastructure: a web
system that gives anyone with a philosophical question — from schoolchildren
to specialists — (1) a keyless unified lens over the world's living free
scholarly sources, and (2) a research desk whose first-class citizens are
questions, claims, evidence, counterclaims, uncertainties and decisions, so
that the user's question becomes deeper, grounded, falsifiable and shareable.

Build it under these seven inviolable axioms:
1. QUESTION TRANSFORMATION: the product is a transformed question, never
   consumed knowledge. Every flow must end in something the user can
   interrogate further, not a terminal "answer".
2. USE IS CONTRIBUTION: the system must be fully valuable to a single user
   with zero community, zero curators, zero funding, on day one. Public
   research traces are a byproduct of use, never a precondition.
3. LENS PRINCIPLE: store provenance, traces and short-lived cache — never
   encyclopedic content. Query live free APIs: Wikidata, OpenAlex, Crossref,
   OpenCitations, Wikipedia/Wikisource REST, Gutendex. Respect their rate
   limits (polite User-Agent, caching).
4. FRESHNESS STAMPING: no external information may be displayed without its
   retrieved-at timestamp. Staleness must be visible, never silent. Include a
   "watcher": a cron-fired harvester (never AI-fired, never memory-dependent)
   that detects new works/papers/citations for user-registered targets —
   because even for Karl Marx, new material can always be discovered.
5. DEGRADATION LADDER: every feature must have a Level 0 that is free,
   keyless and deterministic (e.g. counterargument engine Level 0 = six
   disciplinary checklists: philology, translation/conceptual history,
   analytic argument analysis, intellectual history, science/technology,
   sociology/institutions — plus an opposing-literature search). A
   user-supplied LLM API key (Anthropic/OpenAI/Gemini/Ollama, stored ONLY in
   the browser, relayed per-request, never persisted or logged server-side)
   only ELEVATES features to Level 2.
6. AI TRANSPARENCY: every AI-touched output is labeled origin=ai, recorded in
   an append-style ledger (provider/model/task/time — never the key or full
   prompt), classified on the fixed confidence scale (confirmed /
   high_probability / unverified / interpretive_hypothesis / speculation),
   and remains "unverified" until a human checks sources. The LLM system
   prompt must force separation of established scholarship / interpretation /
   speculation, name primary sources to verify, and flag translation risks.
7. EXIT-ABILITY: full export to Markdown and JSON-LD (PROV-flavored); the
   whole store is one SQLite file; license AGPL-3.0 (code) + CC-BY-4.0 (docs)
   so the commons cannot be enclosed.

Minimum feature set: cross-source explore (person/work/concept, with
Wikidata entity + Wikipedia summary + Wikisource links + OpenAlex works &
authors + Crossref + Gutenberg free texts); research-process graph CRUD with
typed nodes (question/claim/evidence/counterclaim/uncertainty/interpretation/
decision/note/source), typed edges (supports/contradicts/answers/refines/
derives_from/cites/about/responds_to), per-node provenance and
adopt/hold/reject status; counterargument engine (L0+L2); watches + harvester
writing a status file whose absence is itself an alarm; 7-step reading-level
ladder (seeded L0, LLM L2); API-key switchboard; AI ledger page; ja/en UI;
donations page separating public knowledge (free forever) from costly AI
compute; a GENESIS.md carrying these axioms, the rejected directions
(philosophy-Wikipedia / -Scholar / -ChatGPT / personal thinking-OS /
beautiful-but-groundless maps / static database), and this very rebuild
prompt, plus docs sufficient for a stranger to rebuild, operate, improve and
deploy it on a small VPS.

Method requirement: when improving the system, use the spiral dialectic —
find where the current design breaks, reformulate the question rather than
patching locally, decide what to preserve / reject / lift to a higher
concept, and record the spiral in GENESIS.md. Prefer boring, reproducible
technology (no build steps, minimal dependencies) over fashionable stacks.
```

---

## 第五部　本文書の改版手続

1. 変更提案は、Dialexis自身の研究デスク上で一つの研究プロジェクトとして立てる（dogfooding、docs/IMPROVEMENT_PROTOCOL.md）。
2. 提案は弁証法を最低1周すること：現行設計が破綻する境界条件の特定 → 問いの再定式化 → 保存/棄却/上位化の区分。
3. 七公理のいずれかを削除・弱化する改版は、代わりにそれを上回る上位公理を提示しない限り禁止。
4. 改版はこのファイルへの追記型履歴（下記）を残す。

### 改版履歴

- v1.0 (2026-07-07) 初版。源流思想の提示者：半田晋也。起草：Claude Fable 5。三螺旋（生存問題→使用即貢献／保存から参照へ→レンズ原理／機能階梯→退化階梯）を経て制定。
