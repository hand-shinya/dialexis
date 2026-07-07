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
import re

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


def generate(topic: str, goal: str, service: str, lang: str = "ja", ctx: dict | None = None) -> str:
    """Generate a deep-search prompt ADAPTED to the specific term.

    ctx (from the system's own Wikidata + SEP resolution) makes the prompt
    concrete rather than a fill-in-the-blank template: it names the actual
    original-language term(s), the actual adjacent concepts / figures, the
    actual debate structure, and turns the user's stated goal into targeted
    sub-questions. Without ctx it degrades to the generic (weaker) form.
    """
    topic = (topic or "").strip()
    goal = (goal or "").strip()
    if service not in SERVICE_IDS:
        service = "generic"
    ctx = ctx or {}
    return (_ja if lang == "ja" else _en)(topic, goal, service, ctx)


def _sub_questions(goal: str) -> list:
    """Split the user's free-text goal into discrete research asks. Purely
    mechanical (punctuation split) — no interpretation, so it never invents."""
    if not goal:
        return []
    parts = re.split(r"[。\n！？・、,;]|そして|また|および", goal)
    return [p.strip() for p in parts if len(p.strip()) >= 6]


def _orig_line(ctx: dict, jp: bool) -> str:
    labels = ctx.get("orig_labels") or {}
    names = {"en": "英", "de": "独", "fr": "仏", "el": "希", "grc": "古希",
             "la": "羅", "it": "伊"} if jp else {}
    if not labels:
        return ""
    pairs = [f"{v}（{names.get(k, k)}）" if jp else f"{v} ({k})"
             for k, v in labels.items()]
    return " / ".join(pairs)


def _ja(topic: str, goal: str, service: str, ctx: dict) -> str:
    tune = _TUNE_JA.get(service, "")
    orig = _orig_line(ctx, True)
    desc = (ctx.get("description") or "").strip()
    related = ctx.get("related") or []
    influences = ctx.get("influences") or []
    debate = ctx.get("debate") or []
    sep_title = ctx.get("sep_title") or ""
    subs = _sub_questions(goal)

    # Term-specific header grounding the request in real, resolved facts.
    grounded = []
    if desc:
        grounded.append(f"- この語の位置づけ（Wikidata要約）: {desc}")
    if orig:
        grounded.append(f"- 確認された原語候補: **{orig}** ／ これらが同一の日本語「{topic}」に"
                        f"潰れていないか、原語間の意味差を必ず検査してください。")
    if sep_title:
        grounded.append(f"- 専門事典の該当項目: SEP『{sep_title}』（一次の定位に使用）")
    if debate:
        grounded.append("- この主題の論争構造（SEPの節見出し＝主要な立場・論点）:\n    "
                        + "\n    ".join(f"・{d}" for d in debate[:8]))
    if related:
        grounded.append(f"- 隣接概念（必ず関係を検討）: {', '.join(related[:10])}")
    if influences:
        grounded.append(f"- 系譜上の関連人物: {', '.join(influences[:8])}")
    grounded_block = ("\n\n## 0. 既に判明している手がかり（これを踏まえて深掘りせよ）\n"
                      + "\n".join(grounded)) if grounded else ""

    if subs:
        sub_block = ("\n\n## あなた（依頼者）の具体的な問い（各々に個別に答えよ）\n"
                     + "\n".join(f"{i+1}. {s}" for i, s in enumerate(subs)))
    else:
        sub_block = f"\n- 私の目的・文脈: {goal}" if goal else ""

    # The lost-distinction instruction is now anchored on the ACTUAL original
    # term, with Leib/Körper demoted to a one-line illustration of the pattern.
    if orig:
        lost = (f"- 上記の原語（{orig}）のそれぞれについて、**日本語で同じ「{topic}」に"
                f"訳される近縁の別語が存在しないか**を検査してください。原語間で意味・"
                f"含意・使用文脈がどう違い、翻訳でどの区別が消えたかを、原文の該当箇所"
                f"とともに示してください。")
    else:
        lost = ("- 「{t}」が翻訳語であれば原語を特定し、**原語では別語だったものが日本語で"
                "一語に潰れていないか**を検査してください。").format(t=topic)
    lost_illus = ("（この種の「失われた区別」の一例：マルクスの「非有機的肉体」は独語で "
                  "unorganischer Leib と Körper の2語がありうるが日本語では「非有機的」一語に潰れる。）")

    return f"""{tune}

# 調査依頼: 「{topic}」{('（' + orig + '）') if orig else ''}

私は上記について、表面的な要約ではなく、資料に接地した精密な理解を求めています。上記の「既に判明している手がかり」は出発点にすぎません。ここから一次・二次資料を巡回し、深掘りしてください。{grounded_block}{sub_block}

## 1. 私の本当の問いを先に言語化する
- 私が「{topic}」で本当に知りたいことを、複数の解釈候補として明示してください（上の具体的な問いも踏まえて）。
- 私の問いの立て方に、誤解・思い込み・自己バイアス（用語の混同、時代錯誤、特定立場の暗黙の前提）があれば、遠慮なく指摘してください。

## 2. 語の系譜・翻訳史・失われた区別（最重要）
{lost}
- 各語の初出・時代・提唱者を特定し、どの一次文献のどの箇所に現れるかを原文とともに示してください。
{lost_illus}

## 3. 一次資料の精密性
- 一次資料を校訂版（例：Marx=MEGA, Kant=アカデミー版, Husserl=Husserliana）と標準ロケータで特定してください。
- 邦訳は**訳者・版・出版社・年**を併記し、訳語選択が解釈に与える差異を指摘してください。
- 二次文献は「研究史上の位置」（主要説・対立説）とともに挙げてください。

## 4. 立場の対立と反証
- 主要な立場とその対立点・反論を整理してください（上のSEP論争構造を出発点に）。
- 私の想定への最も強い反証を、専門分野別に提示してください。

## 5. 出力の規律
各主張に確度分類（**確定／高蓋然／未確認／解釈仮説／思弁**）を付け、学術的に確立したこと・解釈・思弁を分けてください。出典を各主張に付け、確認できないものは「未確認」と明記し捏造しないこと。最後に「次に当たるべき一次資料」を3〜5点、理由付きで挙げてください。

## 範囲外
流暢な一般論・出典なき要約・通俗的紹介は不要。資料に接地しない断定は避けてください。
""".strip()


def _en(topic: str, goal: str, service: str, ctx: dict) -> str:
    tune = _TUNE_EN.get(service, "")
    orig = _orig_line(ctx, False)
    desc = (ctx.get("description") or "").strip()
    related = ctx.get("related") or []
    debate = ctx.get("debate") or []
    sep_title = ctx.get("sep_title") or ""
    subs = _sub_questions(goal)

    grounded = []
    if desc:
        grounded.append(f"- What this term is (Wikidata): {desc}")
    if orig:
        grounded.append(f"- Confirmed original-language term(s): **{orig}** — check whether these collapse into one word and how their senses differ.")
    if sep_title:
        grounded.append(f"- Encyclopedia entry: SEP '{sep_title}'.")
    if debate:
        grounded.append("- Debate structure (SEP section headings = positions):\n    "
                        + "\n    ".join(f"- {d}" for d in debate[:8]))
    if related:
        grounded.append(f"- Adjacent concepts to examine: {', '.join(related[:10])}")
    grounded_block = ("\n\n## 0. Leads already found (build on these)\n" + "\n".join(grounded)) if grounded else ""
    sub_block = ("\n\n## My specific questions (answer each)\n"
                 + "\n".join(f"{i+1}. {s}" for i, s in enumerate(subs))) if subs else (
                 f"\n- Aim/context: {goal}" if goal else "")

    if orig:
        lost = (f"- For each original term ({orig}), check whether a NEAR-SYNONYM is "
                f"collapsed into the same word in translation; show how their senses/uses differ and which distinction was lost, with source passages.")
    else:
        lost = f'- If "{topic}" is a translation, identify the original word and check whether several distinct originals collapsed into one.'

    return f"""{tune}

# Research request: "{topic}"{(' (' + orig + ')') if orig else ''}

I want a source-grounded, precise understanding — not a fluent summary. The leads below are only a starting point; browse primary and secondary sources from here.{grounded_block}{sub_block}

## 1. First, articulate my real question
- Give several candidate readings of what I actually want (using my specific questions above).
- Flag any misunderstanding, assumption, or self-bias in my framing.

## 2. Genealogy, translation history, LOST DISTINCTIONS (most important)
{lost}
- Identify each term's first appearance, period, and coiner, with the primary passage in the original language.
(Example of a lost distinction: Marx's "inorganic body" is Leib vs Körper in German, flattened into one word elsewhere.)

## 3. Primary-source precision
- Identify primary sources by critical edition (Marx=MEGA, Kant=Akademie, Husserl=Husserliana) and standard locator.
- For translations, give translator/edition/publisher/year and how the choice changes interpretation.
- Place secondary literature in the history of scholarship (main vs rival).

## 4. Positions and counterarguments
- Map the main positions and disagreements (start from the SEP structure above); give the strongest counterargument to my assumption, per discipline.

## 5. Output discipline
Tag each claim (confirmed / highly-probable / unverified / interpretive-hypothesis / speculation); separate scholarship from interpretation from speculation; cite each claim; mark unverifiable as "unverified"; never fabricate. End with 3–5 primary sources to read next, with reasons.

## Out of scope
No fluent generalities, no source-less summaries.
""".strip()
