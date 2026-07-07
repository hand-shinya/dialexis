"""Deep-search prompt generator.

半田様の設計 (2026-07-07): Dialexis need not do all the deep/wide searching
itself. Instead it should generate an excellent "deep research" prompt that the
user pastes into whatever powerful service they have (ChatGPT Deep Research,
Gemini, Perplexity, Claude, Elicit…). Crucially, the generated prompt must
embody what makes an LLM different from Google: it instructs the target AI to
(1) uncover the user's TRUE question behind the surface words, (2) trace the
term's genealogy and translation history and RECOVER LOST DISTINCTIONS — the
非有機的肉体 case, where German unorganischer Leib / Körper (two distinct words)
collapsed into one Japanese 非有機的, hiding that the organic/inorganic boundary
was never single — (3) demand primary-source precision, and (4) check the
asker's own possible errors and biases.

Level 0 (this module, keyless, deterministic) emits a complete, ready-to-paste
prompt. Level 2 (with the user's LLM key) refines it conversationally.
"""

SERVICES = [
    {"id": "openai_deep", "label": "ChatGPT (Deep Research / o3)",
     "note_ja": "詳細なブリーフを好む。最初に確認質問をしてくることがある。多段探索・出典引用。",
     "note_en": "Prefers a detailed brief; may ask clarifying questions first; multi-step, cites sources.",
     "free_ja": "有料中心（無料枠は限定的）"},
    {"id": "gemini_deep", "label": "Gemini (Deep Research)",
     "note_ja": "計画を立てて多数のサイトを巡回。長めの構造化ブリーフが有効。",
     "note_en": "Plans then browses many sites; a long structured brief works well.",
     "free_ja": "一部無料枠あり"},
    {"id": "perplexity", "label": "Perplexity",
     "note_ja": "簡潔な問い＋出典指定が有効。各主張に出典リンクを返す。",
     "note_en": "Concise query + source hints; returns per-claim citations.",
     "free_ja": "無料枠あり（回数制限）"},
    {"id": "claude", "label": "Claude (Anthropic)",
     "note_ja": "長い推論・反証・確度分類に強い。詳細な指示を忠実に守る。",
     "note_en": "Strong at long reasoning, refutation, confidence grading; follows detailed instructions.",
     "free_ja": "無料枠あり"},
    {"id": "elicit", "label": "Elicit（実証論文の抽出）",
     "note_ja": "実証系論文の抽出向き。哲学・人文の解釈的問いには不向き（補助扱い）。",
     "note_en": "For empirical paper extraction; weak for interpretive humanities questions.",
     "free_ja": "無料枠あり（機能制限）"},
    {"id": "generic", "label": "汎用（どのAI/検索でも）",
     "note_ja": "特定サービスに依存しない汎用版。",
     "note_en": "Service-agnostic.", "free_ja": "—"},
]
SERVICE_IDS = {s["id"] for s in SERVICES}

# Service-specific opening line appended to steer each engine.
_TUNE_JA = {
    "openai_deep": "あなたはDeep Researchエージェントです。必要なら最初に不明点を確認し、その後、多数の一次・二次資料を巡回して調査してください。",
    "gemini_deep": "あなたはDeep Researchエージェントです。まず調査計画を立て、多数の情報源を巡回し、原語資料にも当たってください。",
    "perplexity": "各主張に必ず出典リンクを付けてください。一次資料・原語文献・専門事典（SEP等）を優先し、内容の薄い二次情報は避けてください。",
    "claude": "腰を据えて多段で推論し、各主張に確度と反証を付けてください。原語と翻訳の差に注意してください。",
    "elicit": "（注意：この問いは解釈的で実証抽出には不向きです。関連する実証研究があれば補助的に抽出し、無ければその旨を述べてください。）",
    "generic": "",
}
_TUNE_EN = {
    "openai_deep": "You are a Deep Research agent. Ask clarifying questions first if needed, then browse many primary and secondary sources.",
    "gemini_deep": "You are a Deep Research agent. Make a research plan, browse many sources, and consult original-language material.",
    "perplexity": "Attach a source link to every claim. Prioritize primary sources, original-language texts and expert encyclopedias (e.g. SEP); avoid thin secondary content.",
    "claude": "Reason in depth across multiple steps; attach a confidence level and the strongest counterargument to each claim; watch original-vs-translation differences.",
    "elicit": "(Note: this is an interpretive question ill-suited to empirical extraction. Extract related empirical studies only as a supplement, or say there are none.)",
    "generic": "",
}


def generate(topic: str, goal: str, service: str, lang: str = "ja") -> str:
    topic = (topic or "").strip()
    goal = (goal or "").strip()
    if service not in SERVICE_IDS:
        service = "generic"
    if lang == "ja":
        return _ja(topic, goal, service)
    return _en(topic, goal, service)


def _ja(topic: str, goal: str, service: str) -> str:
    tune = _TUNE_JA.get(service, "")
    goal_line = f"\n- 私の目的・文脈: {goal}" if goal else ""
    return f"""{tune}

# 調査依頼: 「{topic}」

私は上記について、表面的な要約ではなく、資料に接地した精密な理解を求めています。{goal_line}

以下の手順で、テキストベースで徹底的に調査し、報告してください。

## 1. 私の本当の問いを先に言語化する
- 私が「{topic}」という言葉で本当に知りたいことは何か、複数の解釈候補を挙げて明示してください。
- 私がこの問いの立て方において、誤解・思い込み・自己バイアスに陥っている可能性があれば、遠慮なく指摘してください（例：用語の混同、時代錯誤、特定の立場の暗黙の前提）。

## 2. 語の系譜・翻訳史・失われた区別を復元する（最重要）
- 「{topic}」に含まれる鍵概念について、初出・原語・時代を特定してください。日本語の場合、それが翻訳語なら**原語は何か**を必ず示してください。
- **原語では元々複数の異なる語であったものが、翻訳で一語に潰れていないか**を検査してください。
  （典型例：マルクスの「非有機的肉体」は独語で unorganischer **Leib** と unorganischer **Körper** の2語がありうるが、日本語ではどちらも「非有機的（肉体/身体）」に潰れ、区別が消えている。このように、境目が元々1つではなかった、という失われた区別を探してください。）
- 各語がどの一次文献のどの箇所に現れるか、原文（該当言語）とともに示してください。

## 3. 一次資料の精密性
- 一次資料（原著・書簡・草稿・講義録）を、校訂版（例：Marx=MEGA, Kant=アカデミー版）と標準ロケータで特定してください。
- 邦訳がある場合は**訳者・版・出版社・年**を併記し、訳語選択が解釈に与える差異を指摘してください。
- 二次文献は「研究史上の位置」（主要説・対立説）とともに挙げてください。

## 4. 立場の対立と反証
- この主題をめぐる主要な立場と、それらの対立点・反論を整理してください。
- 私の想定に対する最も強い反証を、専門分野別（文献学／哲学史／該当分野）に提示してください。

## 5. 出力の規律
各主張に次の確度分類を付けてください：**確定／高蓋然／未確認／解釈仮説／思弁**。
- 「学術的に確立していること」「解釈にとどまること」「思弁にすぎないこと」を必ず分けてください。
- 出典（原文の該当箇所・書誌）を各主張に付けてください。出典を確認できないものは「未確認」と明記し、捏造しないでください。
- 最後に「私が次に当たるべき一次資料」を3〜5点、理由付きで挙げてください。

## 範囲外
流暢な一般論・出典なき要約・通俗的な紹介は不要です。資料に接地しない断定は避けてください。
""".strip()


def _en(topic: str, goal: str, service: str) -> str:
    tune = _TUNE_EN.get(service, "")
    goal_line = f"\n- My aim / context: {goal}" if goal else ""
    return f"""{tune}

# Research request: "{topic}"

I want a source-grounded, precise understanding — not a fluent summary.{goal_line}

Work through the following, text-based and thoroughly.

## 1. First, articulate my real question
- State several candidate readings of what I actually want to know by "{topic}".
- If my framing shows a likely misunderstanding, assumption, or self-bias, say so plainly (e.g. conflated terms, anachronism, an unstated commitment to one position).

## 2. Recover the term's genealogy, translation history, and LOST DISTINCTIONS (most important)
- For each key concept in "{topic}", identify its first appearance, original language, and period. If a term is a translation, state the ORIGINAL-language word.
- Check whether SEVERAL distinct original words were collapsed into one in translation. (Paradigm: Marx's "inorganic body" can be unorganischer **Leib** vs **Körper** in German — two words — flattened into one in other languages, hiding that the organic/inorganic boundary was never single. Hunt for exactly this kind of lost distinction.)
- Show which primary text and passage each word appears in, with the original-language wording.

## 3. Primary-source precision
- Identify primary sources (works, letters, drafts, lectures) by their critical edition (e.g. Marx=MEGA, Kant=Akademie) and standard locator.
- Where translations exist, give translator/edition/publisher/year and note how translation choices change the interpretation.
- List secondary literature with its place in the history of scholarship (main vs rival readings).

## 4. Positions and counterarguments
- Map the main positions and their points of disagreement.
- Give the strongest counterargument to my assumption, per discipline (philology / history of philosophy / the relevant field).

## 5. Output discipline
Tag each claim: **confirmed / highly-probable / unverified / interpretive-hypothesis / speculation**.
- Separate established scholarship from interpretation from speculation.
- Attach a source to each claim; mark anything you cannot verify as "unverified" and do not fabricate citations.
- End with 3–5 primary sources I should read next, with reasons.

## Out of scope
No fluent generalities, no source-less summaries, no popular overviews.
""".strip()
