# LAUNCH_CHECKLIST.md — 世界公開チェックリスト

## A. 公開前（技術）

- [ ] VPSで https（§7）まで完了（HTTPのままの告知は不可＝鍵入力があるため）
- [ ] `/healthz` 外形監視（UptimeRobot無料枠等）設定
- [ ] GitHub リポジトリ public・README表示確認
- [ ] GENESIS.md / USER_GUIDE 両言語のリンク切れ確認
- [ ] 探索・研究デスク・反証・Watcher・段階的読解を通しで1回操作（スクリーンショット取得＝告知素材）

## B. 公開前（内容）

- [ ] /donate の支援リンク実働 or「準備中」明示
- [ ] 連絡先（GitHub Issues）が全ページfooterから到達可能
- [ ] 既知の限界の明示（TROUBLESHOOTING「英語圏偏り」「Watcherノイズ」）— 誇大表示は信頼を失う

## C. 告知先（順序に意味がある：フィードバック耐性の低い順に小さく始める）

1. **日本語圏・小規模**：Note/Zennで開発経緯記事（思想→実装の物語は日本語圏で強い）、X
2. **哲学系コミュニティ**：Reddit r/philosophy（自己宣伝ルール確認）、r/askphilosophy のリソース紹介経路、PhilPapersフォーラム
3. **技術系**：Hacker News「Show HN: Dialexis – a reflexive philosophy research infrastructure」（AGPL・no-key・provenance-stamped が刺さる層）、Reddit r/selfhosted, r/DigitalHumanities
4. **学術系**：Digital Humanities系メーリングリスト（Humanist）、日本デジタル・ヒューマニティーズ学会、大学図書館系
5. **教育系**：哲学対話・倫理教育コミュニティ（段階的読解が売り）

投稿文例（HN用）：
> Show HN: Dialexis — an open philosophy research desk over live scholarly APIs
> Free and keyless: it unifies Wikidata, OpenAlex, Crossref, OpenCitations, Wikisource and Gutenberg into one provenance-stamped lens, plus a research-process graph (claims/evidence/counterclaims/uncertainties) that exports to Markdown/JSON-LD. Your own LLM key (or local Ollama) elevates a 6-perspective counterargument engine. AGPL-3.0, single SQLite file, no build step. The constitution (GENESIS.md) includes a rebuild prompt any AI can reconstruct it from.

## D. 公開後1週間

- [ ] Issues/フィードバックを研究デスク上のプロジェクトとして記録（IMPROVEMENT_PROTOCOL §0）
- [ ] harvester_status.json とアクセスログでAPI負荷確認
- [ ] 最初の外部コントリビュータへの応答準備（CONTRIBUTING節はREADMEに追記予定）
