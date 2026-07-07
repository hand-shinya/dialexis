# Dialexis — 反省的哲学研究インフラ

*あなたの問いを、より深く・根拠あり・反証可能で・共有可能に。*
[English README](README.md) · **[GENESIS.md — 憲法](GENESIS.md)**

Dialexisは、哲学的な問いを持つあらゆる人——小学生から専門研究者まで——のためのオープン（AGPL-3.0）な研究インフラです。哲学版Wikipediaでも、論文検索エンジンでも、チャットボットでもありません。提供するのは：

1. **レンズ** — 世界中の生きた無料学術情報源（Wikidata・OpenAlex・Crossref・OpenCitations・Wikipedia/Wikisource・Project Gutenberg）への鍵不要の統合窓口。すべての情報に情報源と取得時刻を刻印。百科事典的な内容は一切内部に溜め込みません。
2. **研究デスク** — 問い・主張・根拠・反証・未確認事項・判断を第一級の対象とする研究過程グラフ。ノードごとの来歴、固定の確度分類（確定/高蓋然/未確認/解釈仮説/思弁）、Markdown / JSON-LD への完全エクスポート。
3. **反証エンジン** — 任意の主張を6つの専門的視点（文献学・翻訳/概念史・分析哲学・思想史・科学技術・社会/制度）が尋問します。無料・鍵不要（Level 0）。自分のLLM APIキーを設定すると反証の自動生成に昇格（Level 2）。
4. **新着監視（Watcher）** — cron駆動のハーベスタが、追跡対象の新しい著作・論文・引用を機械的に検出。Karl Marxのような古典的著者でも新資料は発見されうる、という前提に立ちます。
5. **段階的読解** — 同じ概念を小学生から専門家まで7段階の深さで。
6. **AI透明性** — AIが触れた出力はすべて明示・台帳記録され、人間が出典を確認するまで「未確認」。

## クイックスタート

```bash
git clone https://github.com/hand-shinya/dialexis.git
cd dialexis
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000
# http://localhost:8000 を開く
```

APIキー不要・外部DB不要・ビルド工程なし。LLMキー（Anthropic / OpenAI / Gemini / ローカルOllama）は任意で、ブラウザ内にのみ保存されます。

## 文書一覧

READMEの英語版の表を参照してください。日本語利用者向けには特に：
[GENESIS.md（憲法）](GENESIS.md) / [使用手順書](docs/USER_GUIDE.ja.md) / [さくらVPS公開手順](docs/DEPLOY_SAKURA_VPS.md) / [運用手順書](docs/OPERATIONS.md) / [改良手順書](docs/IMPROVEMENT_PROTOCOL.md)

## ライセンス

コード：AGPL-3.0／文書：CC-BY-4.0。公共知は囲い込めません。
