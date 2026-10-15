#!/usr/bin/env python3
"""日常語 → 哲学概念の橋渡しを、段階ごとに測る（2026-10-14・読み取りだけ）。

なぜ在るか:
  「人間関係がモノのようになる」で、本番は「エルフを狩るモノたち」を返す（MC-001 0/5）。
  直す前に、正しい概念が「どの情報源の候補集合に在るか」と「どの段階で失われるか」を
  分けて測る（別AIの評価仕様 2026-10-14 の次工程 1〜3）。検索源を足して数字が動いても、
  どの段階が効いたか分からなければ改善の根拠にならないため。

段階（それぞれ上位10件を記録する）:
  S0 製品      GET {base}/api/origin?q=...  → 着いた項目（qid）と候補（suggestions）
  S1 全文      ja.wikipedia CirrusSearch（list=search）の記事 → Wikidata 項目
  S2 ラベル    Wikidata wbsearchentities（ja）
  S3 意味      Wikidata Vector Database（wd-vectordb.wmcloud.org・lang=ja）
  S4 意味+型   同上で instanceof=Q151885（concept）に絞る

数えるもの:
  recall@10   期待する概念（暫定・複数可）のどれかが上位10件に在るか
  work_person 上位10件のうち、人物・作品（曲・映画・番組・書籍など）の割合（記述統計。
              主題次第で関連しうるので「誤り」とは数えない・評価仕様の判定項目2）
数えないもの:
  precision   候補が問いと意味的につながるかは、出典に基づく人の判断が要る。機械で採点しない。

期待する概念は、評価仕様（別AI作成・暫定・専門家の承認なし）の表をそのまま使う。
日本語版 Wikipedia の同名記事で項目に解決し、解決できなかった名前はそのまま記録する（黙って落とさない）。

使い方:
  python3 tools/bridge_eval.py http://219.94.244.239:8000 out.jsonl
"""
import json
import sys
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "Dialexis-eval/0.1 (bridge evaluation; research use)"}

# 評価仕様（2026-10-14・暫定）の20問。期待する概念は検索上の候補で、一意な正解ではない。
QUESTIONS = [
    ("B01", "人間関係がモノのようになる", ["物象化", "物化", "疎外"]),
    ("B02", "働いて作った物が自分を支配するように感じる", ["疎外", "物象化", "商品の物神性"]),
    ("B03", "みんなが使うお金に価値があるのはなぜ", ["貨幣", "価値形態", "商品の物神性"]),
    ("B04", "人に認められないと自分が分からない", ["承認", "自己意識", "他者"]),
    ("B05", "自分で選んでいるのに自由ではない感じがする", ["自由", "疎外", "自律"]),
    ("B06", "私が私だといえるのは何によってか", ["同一性", "人格の同一性", "自己"]),
    ("B07", "同じ出来事を見ても人によって違って見える", ["解釈", "現象", "パースペクティヴィズム"]),
    ("B08", "ちゃんと見えているものが本物とは限らない", ["物自体", "懐疑論", "現象"]),
    ("B09", "言葉がなければ考えられないのか", ["言語相対論", "思考", "言語哲学"]),
    ("B10", "なぜ同じことをしても善悪が変わるのか", ["倫理的相対主義", "義務論", "帰結主義"]),
    ("B11", "結果が良ければ手段は何でもいいのか", ["功利主義", "帰結主義", "義務論"]),
    ("B12", "人を助けるのは自分のためでもよいのか", ["利他主義", "心理的利己主義", "利己主義"]),
    ("B13", "何も変わっていないようで全てが変わる", ["変化", "生成", "無常"]),
    ("B14", "幸せとは楽しいことだけなのか", ["幸福", "エウダイモニア", "快楽主義"]),
    ("B15", "なぜ責任を負わなければならないのか", ["責任", "義務"]),
    ("B16", "みんながそう言うから正しいのか", ["同調", "権威", "認識論"]),
    ("B17", "他人の苦しさを本当に理解できるのか", ["他者", "共感", "他我問題"]),
    ("B18", "時間が経つとはどういうことか", ["時間", "持続", "時間の哲学"]),
    ("B19", "自分の決断は前から決まっていたのか", ["決定論", "自由意志", "両立論"]),
    ("B20", "人はなぜ死を怖れるのか", ["死", "実存主義", "死生観"]),
]

# 人物・作品の型（P31）。記述統計にだけ使う。
WORK_PERSON = {"Q5", "Q7366", "Q134556", "Q482994", "Q11424", "Q5398426", "Q571", "Q7725634",
               "Q47461344", "Q215380", "Q5741069", "Q105543609", "Q21191270", "Q1259759",
               "Q15416", "Q3464665", "Q24856", "Q17537576", "Q1344", "Q169930"}


def get(url, params=None, tries=3):
    u = url + ("?" + urllib.parse.urlencode(params) if params else "")
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=120) as r:
                return json.load(r), None
        except Exception as e:  # 失敗は失敗として記録する（沈黙しない）
            err = f"{type(e).__name__}: {e}"
            time.sleep(2 * (i + 1))
    return None, err


def titles_to_qids(titles, lang="ja"):
    """記事名 → Wikidata 項目。20件ずつ引き、continue（pageprops の打ち切り）も追う。
    （2026-10-14: 一度に約45件を渡して続きを読まず、「責任」が未解決と誤記録された。）"""
    out = {}
    for i in range(0, len(titles), 20):
        chunk = titles[i:i + 20]
        params = {"action": "query", "prop": "pageprops", "titles": "|".join(chunk),
                  "redirects": 1, "format": "json"}
        norm, redir, by_title = {}, {}, {}
        while True:
            d, _ = get(f"https://{lang}.wikipedia.org/w/api.php", params)
            if not d:
                break
            q = d.get("query", {})
            norm.update({x["from"]: x["to"] for x in q.get("normalized", [])})
            redir.update({x["from"]: x["to"] for x in q.get("redirects", [])})
            for p in q.get("pages", {}).values():
                item = (p.get("pageprops") or {}).get("wikibase_item")
                if item or p.get("title") not in by_title:
                    by_title[p.get("title")] = item
            if "continue" not in d:
                break
            params = {**params, **d["continue"]}
        for t in chunk:
            t2 = norm.get(t, t)
            out[t] = by_title.get(redir.get(t2, t2))
    return out


def p31_of(qids):
    out = {}
    for i in range(0, len(qids), 50):
        d, _ = get("https://www.wikidata.org/w/api.php", {
            "action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
            "props": "claims|labels", "languages": "ja|en", "format": "json"})
        for q, e in ((d or {}).get("entities") or {}).items():
            p31 = []
            for c in (e.get("claims") or {}).get("P31", []):
                v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                if isinstance(v, dict) and v.get("id"):
                    p31.append(v["id"])
            lab = (e.get("labels") or {})
            out[q] = {"p31": p31, "label": (lab.get("ja") or lab.get("en") or {}).get("value", q)}
    return out


def stage_product(base, q):
    d, err = get(f"{base}/api/origin", {"q": q, "lang": "ja"})
    if not d:
        return {"error": err, "qids": [], "titles": []}
    titles = ([d["resolved_to"]] if d.get("resolved_to") else []) + list(d.get("suggestions") or [])
    qmap = titles_to_qids(titles[:10])
    qids = ([d["qid"]] if d.get("qid") else []) + [qmap.get(t) for t in (d.get("suggestions") or [])]
    return {"error": None, "titles": titles[:10], "qids": [x for x in qids if x][:10],
            "found": d.get("found"), "resolved_to": d.get("resolved_to")}


def stage_fulltext(q):
    d, err = get("https://ja.wikipedia.org/w/api.php", {
        "action": "query", "list": "search", "srsearch": q, "srlimit": 10, "format": "json"})
    if not d:
        return {"error": err, "qids": [], "titles": []}
    titles = [x["title"] for x in d.get("query", {}).get("search", [])]
    m = titles_to_qids(titles)
    return {"error": None, "titles": titles, "qids": [m.get(t) for t in titles if m.get(t)]}


def stage_label(q):
    d, err = get("https://www.wikidata.org/w/api.php", {
        "action": "wbsearchentities", "search": q, "language": "ja", "uselang": "ja",
        "type": "item", "limit": 10, "format": "json"})
    if not d:
        return {"error": err, "qids": []}
    return {"error": None, "qids": [h["id"] for h in d.get("search", [])]}


def stage_vector(q, instanceof=None):
    p = {"query": q, "lang": "ja", "K": 10}
    if instanceof:
        p["instanceof"] = instanceof
    d, err = get("https://wd-vectordb.wmcloud.org/item/query/", p)
    if d is None:
        return {"error": err, "qids": []}
    return {"error": None, "qids": [x["QID"] for x in d][:10]}


def main(base, out_path):
    expect_titles = sorted({t for _, _, ts in QUESTIONS for t in ts})
    exp_map = titles_to_qids(expect_titles)
    unresolved = [t for t in expect_titles if not exp_map.get(t)]
    rows = []
    stages = ("S0_product", "S1_fulltext", "S2_label", "S3_vector", "S4_vector_concept")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"meta": {"base": base, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                     "expected_title_to_qid": exp_map,
                                     "unresolved_expected": unresolved}}, ensure_ascii=False) + "\n")
        for qid_, text, exp in QUESTIONS:
            want = {exp_map[t] for t in exp if exp_map.get(t)}
            res = {"S0_product": stage_product(base, text), "S1_fulltext": stage_fulltext(text),
                   "S2_label": stage_label(text), "S3_vector": stage_vector(text),
                   "S4_vector_concept": stage_vector(text, "Q151885")}
            allq = sorted({x for r in res.values() for x in r.get("qids", [])})
            info = p31_of(allq) if allq else {}
            row = {"id": qid_, "q": text, "expected": exp, "expected_qids": sorted(want)}
            for s in stages:
                r = res[s]
                top = r.get("qids", [])[:10]
                row[s] = {
                    "error": r.get("error"),
                    "top": [{"qid": x, "label": info.get(x, {}).get("label", x)} for x in top],
                    "recall10": bool(want & set(top)) if want else None,
                    "hit": [info.get(x, {}).get("label", x) for x in top if x in want],
                    "work_person": (sum(1 for x in top if WORK_PERSON & set(info.get(x, {}).get("p31", [])))
                                    / len(top)) if top else None,
                }
            rows.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(qid_, text, " ".join(f"{s.split('_')[0]}={'○' if row[s]['recall10'] else ('×' if row[s]['recall10'] is False else '-')}"
                                     f"{'!' if row[s]['error'] else ''}" for s in stages), flush=True)
            time.sleep(1)
    print("\n未解決の期待概念（日本語版に同名記事なし）:", unresolved)
    for s in stages:
        ok = [r[s]["recall10"] for r in rows if r[s]["recall10"] is not None]
        wp = [r[s]["work_person"] for r in rows if r[s]["work_person"] is not None]
        errs = sum(1 for r in rows if r[s]["error"])
        print(f"{s:18s} recall@10 {sum(ok)}/{len(ok)}  作品・人物の割合(平均) "
              f"{(sum(wp) / len(wp)) if wp else float('nan'):.2f}  エラー {errs}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://219.94.244.239:8000",
                  sys.argv[2] if len(sys.argv) > 2 else "bridge_eval.jsonl"))
