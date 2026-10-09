"""持ち出す文（handoff）— 利用者の環境と責任で実行するための依頼文（2026-10-09）。

役割の区別（2026-10-09 の半田様の指摘）:
  所有者・開発者（半田様）は設計と採否と撤退を決める。
  利用者は半田様とは別の人である。公開instanceでは半田様以外の人間がこれを使う。
  半田様も利用者の1人として使うが、それと「単なる利用者として使う立場」は別である。
  したがって**この層の出力に半田様の名を入れてはならない**。
  以下で「半田様の設計」と書くのは帰属の記録であって、利用者の指示ではない。

なぜ在るか（半田様の設計）:
  利用者が自分の環境で ChatGPT や Google 検索を使うのは自由である。
  この system がそれを提供できないなら、両者を繋ぐのは
  「利用者の環境と責任で実行するための文を、この system が出力すること」である。
  機能と責任を分担する。送信するのは利用者で、この system は送信しない。

既に在ったもの / 足りなかったもの（2026-10-09 の実測）:
  在った  `/deepsearch` の prompt 生成と、`deepsearch` action（視点・目的・難易度を
          選んで `/api/deepsearch` を呼び、textarea とコピーboxを出す）。
          menu の文も「お使いのAI（ChatGPT/Gemini/Claude等）に貼って実行してください」。
  足りない (1) 出る面が3つだけだった（分岐menu・node menu・辺menu）。
              panel footer・card・play・棚・inquiry からは出せなかった。
          (2) 渡していたのは topic と goal だけで、**この system が測ったものを渡していなかった**。
              1881年の訳語対応・取得の受領証・0件の意味・人の判断の欄は渡っていない。
              それらは利用者の手元のAIが知り得ないもので、ここが分担の要である。
          (3) 責任の分担が画面に書かれていなかった。

この文が守ること（公理3）:
  渡すのは、この system が実際に測ったものと、利用者自身が書いたものだけである。
  測っていないことは「未検証」と書く。0件は「0件」と書き、その意味を添える。
  再配布を許さない情報源の本文は載せない。所在（題・URL・locator）と利用条件だけ載せる。
"""
import re

from .connectors import tetsugaku_jii
from .connectors.base import now

MAX_FREE_TEXT = 4000
MAX_RECEIPTS = 24
MAX_SOURCES = 20
MAX_RECORDS = 12

# 本文を載せてよいのは、再配布を許す条件のものだけである。
# 情報源台帳の決裁（2026-10-07）に合わせる。判定できないものは載せない側へ倒す。
QUOTABLE = ("CC0", "PDM", "Public Domain", "CC BY 4.0", "CC BY-SA")


def _quotable(licence: str) -> bool:
    lic = (licence or "").strip()
    if not lic:
        return False
    return any(lic.startswith(x) or x in lic for x in QUOTABLE)


def _clip(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n] + "…"


def _jii_block(terms, lang):
    """1881年『哲学字彙』の訳語対応。CC BY 4.0 なので本文を載せてよい。"""
    rows, asked = [], []
    for t in terms[:4]:
        asked.append(t)
        try:
            env = tetsugaku_jii.lookup(t)
            d = (env or {}).get("data") or {}
        except Exception:
            continue
        for v in (d.get("as_translation") or [])[:4]:
            hw = v.get("headword") or ""
            if hw:
                rows.append("  %s ← %s" % (t, hw))
    if not asked:
        return "", []
    if not rows:
        return ("\n### この system が引いた1881年の訳語対応\n"
                "  照会した語: %s\n"
                "  一致 0 件。意味: 1881年『哲学字彙』にこの語の訳語対応が無い"
                "（索引は既知の語で引けている）。語が無いことと索引の故障は別である。\n"
                % "・".join(asked)), []
    return ("\n### この system が引いた1881年の訳語対応（出所: 『哲学字彙』1881・CC BY 4.0）\n"
            + "\n".join(rows)
            + "\n  これは1881年時点の対応であり、現代の語義ではない。\n"), rows


def _receipt_block(receipts):
    """何を・いつ・どこへ投げ、何件返ったか。手元のAIはこれを知り得ない。"""
    if not receipts:
        return ""
    out = ["\n### この system が実際に取得したこと（受領証・未検証の候補である）"]
    for r in receipts[:MAX_RECEIPTS]:
        if not isinstance(r, dict):
            continue
        line = "  %s / 投げた文字列「%s」 / %s件 / %s" % (
            _clip(r.get("layer"), 40), _clip(r.get("query_sent"), 40),
            r.get("count", "?"), _clip(r.get("retrieved_at"), 32))
        if r.get("error"):
            line += " / 取得の記録: " + _clip(r["error"], 80)
        elif not r.get("count") and r.get("zero_means"):
            line += " / 0件の意味: " + _clip(r["zero_means"], 90)
        out.append(line)
    out.append("  **これらは候補であって、正しさ・関連・網羅を保証しない。**")
    return "\n".join(out) + "\n"


def _source_block(sources):
    """候補の所在。再配布を許さない条件のものは本文を載せず所在だけ載せる。"""
    if not sources:
        return "", []
    quoted, held = [], []
    for s in sources[:MAX_SOURCES]:
        if not isinstance(s, dict):
            continue
        lic = s.get("licence") or ""
        head = "  - %s" % _clip(s.get("title"), 90)
        if s.get("url"):
            head += " <%s>" % s["url"]
        head += " 〔%s〕" % (_clip(lic, 30) or "利用条件 未記入")
        if _quotable(lic) and s.get("note"):
            head += "\n      " + _clip(s["note"], 160)
        elif s.get("note"):
            held.append(_clip(s.get("title"), 40))
        quoted.append(head)
    if not quoted:
        return "", []
    block = ("\n### この system が見つけた候補（所在のみ。確度はすべて「調査候補」）\n"
             + "\n".join(quoted) + "\n")
    if held:
        block += ("  注: 再配布を許す条件が確認できない情報源は、本文を載せず所在だけを載せた"
                  "（%d件）。本文は各情報源で確かめてください。\n" % len(held))
    return block, held


def _record_block(records):
    """人の判断の欄。その workspace の利用者自身が書いたものなので、そのまま渡す。

    公開instanceでは workspace ごとに別の利用者である（§2.6）。
    半田様の判断ではなく、その欄を書いた利用者の判断である。
    """
    if not records:
        return ""
    JA = {"provisional": "暫定定義（自分で書き、自分で却下しうるもの）",
          "memory": "記憶（出典を持たない独立した枝）",
          "naming": "命名（保留のまま進めているもの）"}
    out = ["\n### 私自身が書いた判断（この system の人の判断の欄・追記のみ）"]
    for r in records[:MAX_RECORDS]:
        if not isinstance(r, dict):
            continue
        out.append("  [%s] %s" % (JA.get(r.get("type"), r.get("type") or "?"),
                                  _clip(r.get("title"), 120)))
        if r.get("body"):
            out.append("      " + _clip(r["body"], 200))
    out.append("  これは私の判断であり、この system が生成したものではない。"
               "誤っていれば指摘してください。")
    return "\n".join(out) + "\n"


def build(term: str = "", text: str = "", receipts=None, sources=None,
          records=None, lang: str = "ja", purpose: str = "") -> dict:
    """持ち出す文を組む。外部へは一切出ない（この関数は取得しない）。

    返すのは文そのものと、何を入れ何を入れなかったかである。
    入れなかったものを言わないと、受け取った側は在ると思って探す。
    """
    term = _clip(term, 80)
    text = str(text or "")[:MAX_FREE_TEXT].strip()
    terms = [term] if term else []
    for m in re.finditer(r"[『「“\"]([^』」”\"]{1,20})[』」”\"]", text):
        g = m.group(1).strip()
        if g and g not in terms:
            terms.append(g)

    jii, jii_rows = _jii_block(terms, lang)
    rcp = _receipt_block(receipts or [])
    src, held = _source_block(sources or [])
    rec = _record_block(records or [])

    head = ["# 調査の依頼（Dialexis が組んだ文です。実行はあなたの環境で行ってください）", ""]
    if term:
        head.append("## 主題: %s" % term)
    if purpose:
        head.append("## 目的: %s" % _clip(purpose, 200))
    if text:
        head += ["", "## 私が書いた文（原文のまま）", "```", text, "```"]

    body = [jii, rcp, src, rec]

    ask = """
## お願いしたいこと

1. 上の「私が書いた文」から、私が本当に知りたいことを複数の解釈候補として言語化してください。
2. 私の問いの立て方に、誤解・思い込み・時代錯誤・用語の混同があれば、遠慮なく指摘してください。
3. 「この system が取得したこと」は**未検証の候補**です。誤りがあれば、まずそれを指摘し、
   訂正した上で進めてください。これに反する一次資料があれば、一次資料を採ってください。
4. 一次資料は校訂版と標準locatorで特定してください。邦訳は訳者・版・出版社・年を併記し、
   訳語の選択が解釈をどう変えるかを示してください。
5. 各主張に確度（確定／高蓋然／未確認／解釈仮説／思弁）を付け、
   確認できないものは「未確認」と明記し、捏造しないでください。
6. 最後に「次に当たるべき一次資料」を3〜5点、理由付きで挙げてください。

## 範囲外
流暢な一般論・出典のない要約・資料に接地しない断定は不要です。
"""

    prompt = "\n".join(head) + "\n" + "".join(b for b in body if b) + ask

    contains = []
    if term:
        contains.append("主題の語")
    if text:
        contains.append("あなたが書いた文（原文のまま）")
    if jii_rows:
        contains.append("1881年の訳語対応 %d 件（本文つき・CC BY 4.0）" % len(jii_rows))
    elif jii:
        contains.append("1881年の訳語対応 0 件（0件の意味つき）")
    if receipts:
        contains.append("取得の受領証 %d 件（投げた文字列・時刻・件数）" % min(len(receipts), MAX_RECEIPTS))
    if sources:
        contains.append("候補の所在 %d 件" % min(len(sources), MAX_SOURCES))
    if records:
        contains.append("人の判断の欄 %d 件" % min(len(records), MAX_RECORDS))

    omitted = ["この system の鍵・API・内部path（渡さない）"]
    if held:
        omitted.append("再配布を許す条件が確認できない情報源の本文 %d 件（所在のみ渡した）" % len(held))
    if not receipts:
        omitted.append("取得の受領証（この場面では取得していない）")
    if not records:
        omitted.append("人の判断の欄（企画を指定していない、または0件）")

    return {
        "schema_version": "dialexis.handoff.v1",
        "built_at": now(),
        "prompt": prompt,
        "chars": len(prompt),
        "contains": contains,
        "omitted": omitted,
        # 利用者は半田様とは別の人である（2026-10-09 の指摘）。
        # 公開instanceでは、この文を読むのは半田様以外の利用者である。
        "responsibility": ("この文を実行するのは、あなたの環境と責任です。"
                           "この system は送信しません。鍵も料金も使いません。"
                           "貼り付け先の利用規約と、情報源の利用条件は、あなたが確かめてください。"),
        "licence_note": ("再配布を許す条件（CC0・PD・CC BY・CC BY-SA）が確認できたものだけ"
                         "本文を載せました。それ以外は所在だけです。"),
    }
