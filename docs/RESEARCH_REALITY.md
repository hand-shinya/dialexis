# RESEARCH_REALITY.md — 実際の哲学研究の作業風景（設計の再土台）

本書は「道具を作る前に、実際の研究者が何をしているかを把握せよ」という要請に応えるための、現地調査に基づく作業風景の記述である。以降の Dialexis の全設計は、GENESIS.md の七公理に加えて、本書に接地しなければならない。初版 Dialexis が「使い物にならなかった」根本原因は、本書の内容を知らずにキーワード検索を土台にしたことにある。

出典は各節末尾に付す（大学の研究ガイド、現役哲学者の手記、PhilPapers/SEP 自身の解説、書誌計量の実証研究、哲学者コミュニティの実際の議論）。

## 0. 一行で言うと

**哲学研究は「検索」ではなく「論争への定位（オリエンテーション）」から始まり、論証の再構成を中心成果物とし、標準ロケータと校訂版と原語を基盤とする。** 道具の正しい形は、あらゆる方法に共通して「証拠を提示し、解釈判断は人間が確定する（proposer-of-evidence, human-ratified verdict）」ものであり、解釈を自動で確定してはならない。

## 1. 文献探索の実際の経路（初版が最も外していた点）

研究者はキーワードを学術索引に投げることから**始めない**。実際の順序は：

1. **SEP（スタンフォード哲学百科）で当該項目を読む** — ほぼ全員の入口。各節の見出しが「論争の地図（主要な立場と応酬）」になっている。
2. **SEP の書誌を PhilPapers 経由で採掘する** — SEP 書誌は各項目が PhilPapers レコードにリンクする。ここが主力動作。
3. **PhilPapers を分野固有の索引として使う**（3,000超の人手分類体系。各葉カテゴリ＝その問題の精選書誌）。
4. **引用チェイン（双方向）** — 後方：鍵論文の脚注をたどる。前方：それを引用した論文（Google Scholar / Scite）。
5. **指導教員・専門家に訊く**（最も関連性の高い最新・未公刊はしばしば人的助言が勝る）。

決定的事実：**哲学の文献探索は網羅的・系統的ではなく、論証駆動で目的的**。「ヘーゲル研究の全体」ではなく「自分の論点に至る系譜だけ」を地図化する。

> 設計含意：Dialexis の探索は「SEP項目＝論争の地図＋検証済み書誌」を主役に据える（実装済 v0.2）。学術検索は補助に格下げする。

出典: [PhilPapers/SEP linked bibliographies](https://philpapers.org/sep/) · [Jeff Maynes, How to Do Research in Philosophy](https://jeffmaynes.com/researching-philosophy/) · [Cambridge: Researching a Topic](https://libguides.cam.ac.uk/philosophy/research-topic)

## 2. なぜ引用グラフ（OpenAlex/Crossref）は哲学で構造的に機能しないか

初版の「関連論文」は、哲学で失敗することが実証済みのSTEM前提の薄いデータに乗っていた：

- **哲学の産出と被引用は論文でなく書籍中心**。人文学の産出の70%超が論文以外（書籍・章）で、引用索引はこれを構造的に取りこぼす。
- **引用が20年より古い文献に偏る**（古典が現役の対話相手）。新しさ・被引用速度で並べるSTEM型ランキングは、まさに重要なものを埋める。
- **引用行為が賛否の表明**（「XはYを見落とす」）であり、中立な知識累積の引用とは別物。類似度・共引用の指標は哲学を誤モデル化する。

> 設計含意：引用グラフを中核に据えない。書籍・SEP・古典を含み、新しさでなく正典性で扱う。OpenAlex は「最近の論文の補助」に限定（哲学subfieldフィルタ適用済）。

出典: [A&HCI: humanities >70% non-article output](https://arxiv.org/pdf/1102.1934) · [Citation characteristics of philosophy monographs](https://www.sciencedirect.com/science/article/abs/pii/S0740818898900056) · [Aaron Tay, What Academic Deep Research Is Really For](https://aarontay.substack.com/p/what-academic-deep-research-is-really)

## 3. 中心成果物：論証の再構成（P1…C）

哲学の note は要約ではなく**論証の標準形**。実際の artifact が含むもの：

- **前提と結論を分けて番号化**（P1, P2 … ∴C）。結論は本文の最後の文とは限らない。
- **隠れた前提（enthymeme）の補填** — 推論の飛躍を、寛容の原理で最も無理のない前提により埋める（攻撃の前に）。規範的結論には規範的前提が要る。
- **声の区別（voice codes）** — 著者の主張と自分の注釈を恒久マーカーで区別（数ヶ月後の混同・剽窃を防ぐ）。
- **精密な頁ロケータ**（Newman式 10.1/10.5/10.9）— 「どこかで読んだが探せない」問題への対処。ノートを取る主目的は引用箇所を再発見できること。
- **引用符の規律**（直接引用は必ず引用符。後で下書きに貼る際の無自覚剽窃を防ぐ）。

> 設計含意：研究デスクを「汎用ノードグラフ」から「論証再構成」に形を寄せる。ノード型 claim/evidence/counterclaim は方向として正しいが、(a) 隠れた前提フラグ、(b) 声の区別、(c) 頁ロケータ、を第一級フィールドにすべき（ROADMAP フェーズ1）。

出典: [Peter Suber, Taking Notes on Philosophical Texts](https://legacy.earlham.edu/~peters/courses/notes.htm) · [Jim Pryor, Guidelines on Reading/Writing Philosophy](https://www.jimpryor.net/teaching/guidelines/reading.html)

## 4. 標準ロケータ＝参照の原子単位（初版が完全に欠いていた）

哲学の参照単位は DOI でも PDF 頁でもなく、版に依存しない**標準ロケータ**：

- Plato → **Stephanus** 番号（例: Republic 514a）
- Aristotle → **Bekker** 番号（例: Nicomachean Ethics 1094a1）
- Kant → **A/B** ページ付け（Critique of Pure Reason A51/B75）
- Wittgenstein → 命題番号、Aquinas → 部/問/項

これらは全ての校訂版・翻訳の欄外に印刷され、あらゆる版・言語で同じ一節を指す。これを扱えない道具は、哲学者の引用・参照の仕方を支えられない。

> 設計含意：標準ロケータの解決＋原典への deep-link を実装（`/api/locator`、v0.2 で Plato/Aristotle を Perseus へ、Kant は引用規約を案内）。Oxford Scholarly Editions が有償で行うことの無料版。

出典: [Bekker numbering](https://en.wikipedia.org/wiki/Bekker_numbering) · [Citing Plato & Aristotle: Stephanus & Bekker](https://proofed.com/writing-tips/citing-plato-and-aristotle-stephanus-and-bekker-numbers/) · [Oxford Scholarly Editions, Bekker deep-linking](https://www.oxfordscholarlyeditions.com/classics/newsitem/221/using-bekker-numbers-to-navigate-the-works-of-aristotle)

## 5. 精読・翻訳分析：語ではなく lemma、単訳を信じない

精読は「一節＋版＋原語＋複数訳の対照＋lemma 単位の用例収集＋校訂異文」。翻訳分析は「用例×訳者のアラインメント行列」で、各訳が何を保存し何を落とすかを判定する（logos→Word/Reason、Dasein、ousia/substantia が典型）。

**設計上の失敗モード（全出典が独立に警告）**：多義の lemma を単一の「意味」に潰す文字列検索は、自信ありげな無意味を生む（εἶδος を全て「Form」に潰すと corpus の半分を誤訳する）。

> 設計含意：Translation Distortion View は「用例×訳者行列＋原語 lemma＋落ちた含意」を実装すべき本命機能（現状スタブ）。Perseus（原語＋形態素解析＋対訳）が無料基盤。ROADMAP フェーズ2。

出典: [Cassin, Dictionary of Untranslatables (review)](https://www.theoryculturesociety.org/blog/review-barbara-cassin-et-al-dictionary-of-untranslatables) · [Perseus/Republic 596a](http://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.01.0168:book%3D10:section%3D596a)

## 6. 道具の普遍的な正しい形（五方法すべてに共通）

論証再構成・精読・歴史的文脈(Cambridge学派)・概念史(Koselleck)・翻訳分析——五つの方法はすべて同じ形を持つ：

- **機械化できる中核**（全方法でほぼ同一）：日付・帰属つきコーパスの構築、lemma 単位の全用例抽出、共有アンカー（節番号・Stephanus番号）での対訳アライン、差分・基準・頻度曲線・相互参照の提示、来歴の管理。ここが手作業では潰れるほど退屈で誤りやすい。
- **代替不能な人間の層**（同じく共通）：「ここで生きている意味・読みはどれか」「寛容な・帰結的な判定」「時代区分・文脈の境界」「著者が何を*していた*か」。頻度や埋め込みのシフトは**信号であって判定ではない**。
- **設計すべき失敗モード**：平坦化（多義語の単一化、埋め込みシフトを意味判定と誤認、「著者はXを意図した」の自動出力）。道具は**証拠の提示者**であり、人間が判定を確定する。

> これは GENESIS 公理6（AI透明性・人間が確認するまで未確認）と同一概念である。初版は思想は正しかったが、機能が実際の作業に接地していなかった。

出典: [Skinner, Meaning and Understanding (要約)](https://cluelesspoliticalscientist.wordpress.com/2017/01/09/meaning-and-understanding-in-the-history-of-ideas-by-quentin-skinner-a-summary/) · [Koselleck, Begriffsgeschichte and Social History](https://germanhistory-intersections.org/en/knowledge-and-education/ghis:document-129)

## 7. 研究者の実際の痛点（道具が狙うべき所）

- **「どこかで読んだが探せない」** — 個人ライブラリを横断した一節単位の再発見。
- **声の分離**（著者/自分）— 剽窃防止・論証帰属。
- **「決定的な反論を見落としたのでは」** という慢性的不安（目的的探索の副作用）。
- **翻訳の対照**（単訳を信じられない）。
- **書く・直す・出典付けの分離**（同時にやると生産性が死ぬ）。
- **Zotero への書き出し・安定した citekey・Obsidian/Markdown 連携**（既存ワークフローに乗らない道具は捨てられる）。

## 8. 既存メニューの正直な再評価と是正方針

| メニュー | 初版の問題 | 是正 |
|---|---|---|
| 探索 | キーワード×OpenAlex（哲学で機能しない土台） | **SEP項目＝論争地図＋検証済み書誌を主役に**（v0.2実装）。学術検索は補助。標準ロケータ解決を追加 |
| 研究デスク | 汎用ノードグラフ | 論証再構成に形を寄せる：隠れ前提・声の区別・頁ロケータを第一級に（フェーズ1） |
| 反証エンジン | 対立文献がOpenAlex頼み | 6視点チェックリストは方向として妥当。対立文献はSEP書誌＋PhilPapers由来へ |
| 段階的読解 | 一般向けで研究者中核ではない | 使命の一部として維持（老若男女）。研究者機能とは分離 |
| Watcher | 二次的 | 「決定的反論の見落とし不安」に効く。PhilPaticcategory監視へ発展 |
| 翻訳歪みView | スタブ | 本命機能。用例×訳者行列＋原語lemma（フェーズ2） |

## 9. まだ足りていないと正直に認めること

- **PhilPapers API 未接続**（非商用キー申請中の想定）。現状はSEP書誌で代替。
- **論証再構成の第一級化は未実装**（研究デスクは汎用ノードのまま）。
- **翻訳歪みViewの本実装は未着手**。
- **Zotero/Obsidian連携・標準citekey出力は未実装**（採用の要）。
- SEPは英語のみ。日本語利用者にはWikidataの英語ラベルで橋渡ししている（自由→freedom→SEP）。日本語圏の情報源（CiNii/NDL）接続は未了。

これらは ROADMAP に優先度つきで登録する。本書は「作業風景を把握してから改良する」ための最初の接地であり、以後の改良は本書との差分で測る。
