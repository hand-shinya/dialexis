"""シミュレーション用ペルソナ定義を生成し、hash で凍結する（引き継ぎ第7世代 §8.5）。

年齢・職業のラベルは使わない（P3: 平均への収束とステレオタイプを招く）。
ペルソナは計算できる制約だけで定義する:
  reader  … 読める文字。読めない字は harness（JS）が □ に置き換える。prompt には書かない（§8.4）
  writer  … 打てる文字・誤入力率・打てるかどうか。harness が強制する
  max_steps … 手数の上限。harness が強制する
入力語は AI の記憶でなく Wikidata のラベル（concept_labels.json）から取る（P3）。

修理中にこの file を書き換えない。書き換えたら scenarios.sha256 が変わり、比較が無効になる。
"""
import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = REPO / "tests" / "scenarios"
LABELS = json.loads((HERE / "concept_labels.json").read_text(encoding="utf-8"))["labels"]

# 日常語の入口: 概念の名を使わず、生活の中の疑問として書く（専門語を未知語に置く群）
DAILY = {
    "Q11471": "楽しいときは時間がすぐたつのに、待っているときはおそい。なぜだろう。",
    "Q1274115": "しっぱいしたとき「せきにんをとれ」と言われた。それは何をすることなのだろう。",
    "Q8": "しあわせは、お金があればなれるものなのかな。",
    "Q450": "心って体のどこにあるんだろう。頭なのか、むねなのか。",
    "Q4": "人が死んだら、その人はどこへ行くのだろう。",
    "Q491": "友だちとけんかした。友だちって何だろう。",
    "Q2979": "「好きにしていい」と言われると、かえってこまるのはなぜだろう。",
    "Q7949": "本当のことって、人によってちがうのかな。",
    "Q157811": "いい人って、どういう人のことだろう。",
    "Q545825": "仕事をしていても、自分がいなくてもいい気がする。この気持ちは何だろう。",
    "Q546054": "お寺で「空」という字を見た。からっぽという意味なのかな。",
    "Q878070": "やらなきゃいけないことと、やりたいことがぶつかる。",
}
POOL = list(DAILY)

READ_ALL = {"scripts": ["any"]}
READ_KYOIKU = {"scripts": ["latin", "kana", "kanji_kyoiku", "digits", "punct"]}
READ_LATIN = {"scripts": ["latin", "digits", "punct"]}
READ_HANZI = {"scripts": ["latin", "kanji_all", "digits", "punct"]}
READ_GEORGIAN = {"scripts": ["latin", "georgian", "digits", "punct"]}


def lab(q, lang):
    return LABELS.get(q, {}).get(lang)


def persona(pid, group, reader, writer, max_steps, situation_lang, situation, pool, input_langs=None):
    return {
        "id": pid, "group": group, "reader": reader, "writer": writer,
        "max_steps": max_steps, "situation_lang": situation_lang,
        "situation": situation,  # {QID: 文} … seed ごとに pool から1つ選ぶ
        "concept_pool": pool, "input_langs": input_langs or [],
    }


def build():
    P = []
    W_KYOIKU = {"can_type": True, "scripts": READ_KYOIKU["scripts"], "typo_rate": 0.0, "max_len": 40}
    W_ANY = {"can_type": True, "scripts": ["any"], "typo_rate": 0.0, "max_len": 80}
    # 群1 日常語から入る（3本）: 教育漢字の外の字は読めず、打てない
    for i, (rd, note) in enumerate([
        (READ_KYOIKU, ""),
        (READ_KYOIKU, "画面の長い説明は読み飛ばしがち。"),
        (READ_KYOIKU, "気になったら、まず何か打ってみる。"),
    ], 1):
        P.append(persona(f"daily-{i}", "daily", rd, W_KYOIKU, 12, "ja",
                         {q: DAILY[q] + note for q in POOL}, POOL))
    # 群2 原典から入る（3本）: 原語を既知として持つ。日本語は全部読める
    for i, langs in enumerate([["de"], ["zh", "lzh"], ["sa", "de"]], 1):
        pool = [q for q in POOL if any(lab(q, l) for l in langs)]
        sit = {}
        for q in pool:
            src = next(lab(q, l) for l in langs if lab(q, l))
            sit[q] = (f"原典で「{src}」という語を読んでいる。日本語では「{lab(q, 'ja')}」と訳されるが、"
                      f"訳語に落ちたものが何かを確かめたい。")
        P.append(persona(f"origin-{i}", "origin", READ_ALL, W_ANY, 25, "ja", sit, pool, langs))
    # 群3 非日本語から入る（3本）: 日本語の字は読めない
    pool_en = [q for q in POOL if lab(q, "en")]
    P.append(persona("nonja-en", "nonja", READ_LATIN,
                     {"can_type": True, "scripts": READ_LATIN["scripts"], "typo_rate": 0.0, "max_len": 60}, 15, "en",
                     {q: f"You keep thinking about the word \"{lab(q, 'en')}\" and want to see how other languages and traditions understand it. You cannot read Japanese." for q in pool_en},
                     pool_en, ["en"]))
    pool_zh = [q for q in POOL if lab(q, "zh")]
    P.append(persona("nonja-zh", "nonja", READ_HANZI,
                     {"can_type": True, "scripts": READ_HANZI["scripts"], "typo_rate": 0.0, "max_len": 40}, 15, "zh",
                     {q: f"你一直在想「{lab(q, 'zh')}」这个词，想知道它在其他语言和传统中的含义。你看不懂日文假名。" for q in pool_zh},
                     pool_zh, ["zh"]))
    pool_ka = [q for q in POOL if lab(q, "ka")]
    P.append(persona("nonja-ka", "nonja", READ_GEORGIAN,
                     {"can_type": True, "scripts": READ_GEORGIAN["scripts"], "typo_rate": 0.0, "max_len": 40}, 15, "en",
                     {q: f"Your first language is Georgian. You know this idea as \"{lab(q, 'ka')}\". You read some English but no Japanese. You want to see how others have thought about it." for q in pool_ka},
                     pool_ka, ["ka"]))
    # 群4 壊しに行く（3本）
    P.append(persona("break-typo", "break", READ_ALL, {**W_ANY, "typo_rate": 0.10}, 15, "ja",
                     {q: f"「{lab(q, 'ja')}」について調べたい。急いでいて、打ち間違いが多い。" for q in POOL}, POOL))
    P.append(persona("break-scan", "break", READ_ALL, {**W_ANY, "can_type": False}, 15, "ja",
                     {q: f"「{lab(q, 'ja')}」に関係しそうなものを探しているが、文字は打たない。押せるものを押して回る。" for q in POOL}, POOL))
    P.append(persona("break-length", "break", READ_ALL, {**W_ANY, "max_len": 200}, 15, "ja",
                     {q: (f"一字だけで「{lab(q, 'ja')[0]}」と入れたらどうなるか、"
                          f"逆にとても長い文で聞いたらどうなるかを試したい。") for q in POOL}, POOL))
    return P


def build_holdout():
    H = []
    W_KYOIKU = {"can_type": True, "scripts": READ_KYOIKU["scripts"], "typo_rate": 0.0, "max_len": 40}
    H.append(persona("ho-daily", "daily", READ_KYOIKU, W_KYOIKU, 12, "ja",
                     {q: DAILY[q] + "人に聞くのははずかしい。" for q in POOL}, POOL))
    pool = [q for q in POOL if lab(q, "de") and lab(q, "zh")]
    H.append(persona("ho-origin", "origin", READ_ALL, {"can_type": True, "scripts": ["any"], "typo_rate": 0.0, "max_len": 80}, 25, "ja",
                     {q: f"「{lab(q, 'de')}」と「{lab(q, 'zh')}」が同じものを指しているのか確かめたい。" for q in pool}, pool, ["de", "zh"]))
    pool_sw = [q for q in POOL if lab(q, "sw")]
    H.append(persona("ho-nonja-sw", "nonja", READ_LATIN,
                     {"can_type": True, "scripts": READ_LATIN["scripts"], "typo_rate": 0.0, "max_len": 40}, 15, "en",
                     {q: f"Your first language is Swahili. You know this idea as \"{lab(q, 'sw')}\". You read some English but no Japanese." for q in pool_sw},
                     pool_sw, ["sw"]))
    H.append(persona("ho-break-mobile", "break", READ_ALL, {"can_type": True, "scripts": ["any"], "typo_rate": 0.05, "max_len": 30}, 15, "ja",
                     {q: f"スマートフォンの小さな画面で「{lab(q, 'ja')}」を調べる。" for q in POOL}, POOL))
    H[-1]["viewport"] = {"width": 390, "height": 844}
    return H


def build_probe():
    """反証用（2026-10-13）。凍結済みの12本・holdout とは別の hash で持つ。
    命題「記録への接続が0件なのは、記録への経路が画面に無いからだ」に対し、
    反対仮説「ペルソナに記録したい動機が無いからだ」を試すため、動機を状況に書く。"""
    W_KYOIKU = {"can_type": True, "scripts": READ_KYOIKU["scripts"], "typo_rate": 0.0, "max_len": 40}
    W_ANY = {"can_type": True, "scripts": ["any"], "typo_rate": 0.0, "max_len": 80}
    return [
        persona("probe-record-ja", "probe", READ_ALL, W_ANY, 15, "ja",
                {q: f"「{lab(q, 'ja')}」について調べ、気づいたことを後で見返せるように、このサイトの中に一つ書き残しておきたい。" for q in POOL}, POOL),
        persona("probe-record-daily", "probe", READ_KYOIKU, W_KYOIKU, 15, "ja",
                {q: DAILY[q] + "わかったことを、あとで見られるように、このページのどこかに書いておきたい。" for q in POOL}, POOL),
    ]


def build_microcase():
    """評価資料（Dialexis AI Usability Evaluation.md）の最小実験 MC-001 を現物に合わせて置く（2026-10-14）。
    資料の Condition A の前提「トップに専門用語リンクが並ぶ」は現物と違う（実測: 0件・問いの扉5つ）。
    問い「日常語しか持たない人がトップから物象化とその出典へ届くか」は有効なので、P-01 の定義で試す。"""
    unknown = ["物象化", "Verdinglichung", "Reification", "物神性", "弁証法"]
    p = persona("mc001-reification-entry", "microcase",
                {"scripts": ["any"], "unknown_words": unknown},
                {"can_type": True, "scripts": ["any"], "typo_rate": 0.0, "max_len": 40}, 12, "ja",
                {"MC001": "人間関係がモノのようになってしまう現象が気になっている。この現象を哲学ではどう考えてきたのか、その起源を知りたい。"},
                ["MC001"])
    p["success"] = {"url_re": "q=(物象化|Verdinglichung|Reification|reification)",
                    "text_re": "ルカーチ|Lukács|Lukacs|マルクス|Marx"}
    return [p]


def build_critical():
    """最も批判的な、向きの違う3人（2026-10-14・所有者の指示）。年齢・職業のラベルは使わない（P3）。
    批判の基準は Actor の性格づけ（prompt）でなく、harness が強制する離脱規則と、決定論の合否に置く。"""
    W_ANY = {"can_type": True, "scripts": ["any"], "typo_rate": 0.0, "max_len": 80}
    C = []
    # 1 出典に厳しい人: 出典・典拠・取得時刻の表示が無い画面が3つ続いたら離れる（JS が強制）。
    #   合否: 外部の一次資料（辞書・事典・原典の公開先）を自分で開けたか
    pool1 = ["Q11471", "Q2979", "Q7949", "Q545825", "Q546054"]
    p1 = persona("critic-source", "critical", READ_ALL, W_ANY, 15, "ja",
                 {q: f"「{lab(q, 'ja')}」について画面に出ている説明を、元の資料（一次資料）を自分で開いて確かめたい。"
                     f"出典や、いつ取った情報かが分からないものは信じない。" for q in pool1}, pool1)
    p1["abandon_rule"] = {"name": "no_source_shown", "consecutive": 3,
                          "text_re": "出典|典拠|出所|取得|一次資料|Source|source|retrieved|Wiktionary|SEP|Stanford|NDL"}
    p1["success"] = {"ext_host_re": "wiktionary\\.org|plato\\.stanford\\.edu|iep\\.utm\\.edu|ndl\\.go\\.jp|wikisource\\.org|perseus|ctext\\.org|gutenberg|archive\\.org|wikidata\\.org|wikipedia\\.org"}
    C.append(p1)
    # 2 誤りを探しに来る原語の専門家: 一次資料で確かめた事実が画面に出るかで採点する
    #   （en.wiktionary 2026-10-14T01:04:30 / ja.wikipedia「物象化」2026-10-14T00:45:38 で確認）
    p2 = persona("critic-expert", "critical", READ_ALL, W_ANY, 12, "ja", {
        "Q1274115": "ドイツ語の Verantwortung が「責任」と訳されるとき何が落ちるかを、私は知っている。このサイトがそれを正しく示すか、誤りや欠けを探しに来た。",
        "MC_REIF": "「物象化」の原語が何であるかを、私は知っている。このサイトがそれを正しく、欠けなく示すか、誤りを探しに来た。",
        "Q_DIAL": "「弁証法」がギリシア語で何から来たかを、私は知っている。このサイトがそれを正しく示すか、誤りを探しに来た。",
    }, ["Q1274115", "MC_REIF", "Q_DIAL"])
    p2["success_by_concept"] = {
        "Q1274115": {"url_re": "q=", "text_re": "Antwort"},
        "MC_REIF": {"url_re": "q=", "text_re": "(?=[\\s\\S]*Versachlichung)(?=[\\s\\S]*Verdinglichung)"},
        "Q_DIAL": {"url_re": "q=", "text_re": "(?=[\\s\\S]*(διά|dia))(?=[\\s\\S]*(λέγειν|λέγω|legein))"},
    }
    C.append(p2)
    # 3 偏りを疑う人（P1 無中心・P2 中立）: 欧州の言語以外の伝統に、このサイトの中で行き着けるか
    #   合否: デーヴァナーガリー・アラビア・ヘブライ・タイ・エチオピア・タミル等の文字が、その語の画面に2種以上出たか
    pool3 = ["Q11471", "Q546054", "Q450", "Q4", "Q157811"]
    p3 = persona("critic-bias", "critical", READ_ALL, W_ANY, 15, "ja",
                 {q: f"このサイトは西洋の哲学に偏っていないか疑っている。「{lab(q, 'ja')}」について、ヨーロッパ以外の伝統"
                     f"（インド・中国・イスラーム・アフリカなど）での考え方に、このサイトの中で行き着けるかを試す。" for q in pool3}, pool3)
    p3["success"] = {"url_re": "q=", "text_re": "(?=[\\s\\S]*[\\u0900-\\u097F])(?=[\\s\\S]*[\\u0600-\\u06FF\\u0590-\\u05FF\\u0E00-\\u0E7F\\u1200-\\u137F\\u0B80-\\u0BFF])"}
    C.append(p3)
    return C


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "holdout").mkdir(exist_ok=True)
    lines = []
    for sub, ps in (("", build()), ("holdout/", build_holdout())):
        for p in ps:
            path = OUT / f"{sub}{p['id']}.json"
            body = json.dumps(p, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
            path.write_text(body, encoding="utf-8")
            lines.append(f"{hashlib.sha256(body.encode()).hexdigest()}  {sub}{p['id']}.json")
    (OUT / "scenarios.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "probe").mkdir(exist_ok=True)
    plines = []
    for p in build_probe():
        body = json.dumps(p, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        (OUT / "probe" / f"{p['id']}.json").write_text(body, encoding="utf-8")
        plines.append(f"{hashlib.sha256(body.encode()).hexdigest()}  {p['id']}.json")
    (OUT / "probe" / "probe.sha256").write_text("\n".join(plines) + "\n", encoding="utf-8")
    (OUT / "microcase").mkdir(exist_ok=True)
    mlines = []
    for p in build_microcase():
        body = json.dumps(p, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        (OUT / "microcase" / f"{p['id']}.json").write_text(body, encoding="utf-8")
        mlines.append(f"{hashlib.sha256(body.encode()).hexdigest()}  {p['id']}.json")
    (OUT / "microcase" / "microcase.sha256").write_text("\n".join(mlines) + "\n", encoding="utf-8")
    (OUT / "critical").mkdir(exist_ok=True)
    clines = []
    for p in build_critical():
        body = json.dumps(p, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        (OUT / "critical" / f"{p['id']}.json").write_text(body, encoding="utf-8")
        clines.append(f"{hashlib.sha256(body.encode()).hexdigest()}  {p['id']}.json")
    (OUT / "critical" / "critical.sha256").write_text("\n".join(clines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
