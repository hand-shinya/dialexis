#!/usr/bin/env python3
"""言語の橋の探針（2026-10-14）。撤退台帳 `language-bridge` の観測点を測る。

画面の言語を固定して、いろいろな言語の語を /api/origin に入れ、どの概念（Wikidata QID）に
着いたかを数える。期待の QID は、en.wiktionary の語義（各語の第一義が freedom / liberty）と、
Wikidata Q2979（日本語ラベル「自由」）に基づく。2026-10-14 に取得した資料で確かめた語だけを置く。

使い方:
  python3 tools/pivot_probe.py http://127.0.0.1:8097 ja
  python3 tools/pivot_probe.py http://219.94.244.239:8000 ja
出力の最終行: `landed n/m`（期待の QID に着いた語の数）。
"""
import json
import sys
import urllib.parse
import urllib.request

# 語 → 期待の QID（Q2979＝自由）
EXPECT = {
    "kalayaan": "Q2979",    # タガログ語
    "kebebasan": "Q2979",   # インドネシア語
    "tự do": "Q2979",       # ベトナム語
    "özgürlük": "Q2979",    # トルコ語
    "ነፃነት": "Q2979",       # アムハラ語
    "حرية": "Q2979",        # アラビア語
    "자유": "Q2979",         # 朝鮮語
    "เสรีภาพ": "Q2979",     # タイ語
    "vapaus": "Q2979",      # フィンランド語
    "libereco": "Q2979",    # エスペラント
    "آزادی": "Q2979",       # ペルシア語
    "Freiheit": "Q2979",    # ドイツ語
    "freedom": "Q2979",     # 英語
    "uhuru": "Q2979",       # スワヒリ語
    "自由": "Q2979",         # 日本語（既存の解決を保つことの確認）
}


def main(base: str, lang: str) -> int:
    landed = 0
    for w, want in EXPECT.items():
        url = f"{base}/api/origin?q={urllib.parse.quote(w)}&lang={lang}"
        try:
            d = json.load(urllib.request.urlopen(url, timeout=180))
            got = d.get("qid")
            br = d.get("language_bridge") or {}
        except Exception as e:  # 失敗は失敗として数える（沈黙しない）
            d, got, br = {}, f"ERR {type(e).__name__}", {}
        ok = got == want
        landed += ok
        print(f"{'OK ' if ok else 'NG '}\t{w}\t{got}\t{d.get('resolved_to')}"
              f"\tbridge={br.get('applied')}\tinput={br.get('input_lang')}\tconfirmed={br.get('confirmed')}")
    print(f"landed {landed}/{len(EXPECT)}")
    return 0 if landed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8097",
                  sys.argv[2] if len(sys.argv) > 2 else "ja"))
