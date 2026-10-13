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
    print("\n".join(lines))


if __name__ == "__main__":
    main()
