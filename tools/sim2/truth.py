"""正解札（走行の前に一次資料から作る）: 語ごとに ja.wikipedia の実際の記事（転送・有無）と、その項目の P31。
AI の記憶では作らない。外部へは1秒1件・結果は truth.json に保存して再利用する。
usage: python3 truth.py <out.json> 語1 語2 ...
"""
import json, sys, time, urllib.error, urllib.parse, urllib.request
UA = {"User-Agent": "Dialexis-sim2/0.1 (verification harness; contact via repository)"}
def get(url, **p):
    for k in range(5):   # 利用上限（429）は待って再試行する。取れなければ札を作らない（推測で埋めない）
        time.sleep(1.5 + 8 * k)
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url + "?" + urllib.parse.urlencode(p), headers=UA), timeout=30))
        except urllib.error.HTTPError as e:
            if e.code != 429: raise
    raise RuntimeError("429 が続いたため取得を見送った")
out_path, words = sys.argv[1], sys.argv[2:]
try: out = json.load(open(out_path))
except Exception: out = {}
for w in words:
    if w in out: continue
    d = get("https://ja.wikipedia.org/w/api.php", action="query", titles=w, redirects=1, prop="pageprops", format="json", formatversion=2)
    q = d["query"]; pg = q["pages"][0]
    rec = {"word": w, "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "missing": bool(pg.get("missing")), "title": pg.get("title"),
           "redirected_to": (q.get("redirects") or [{}])[0].get("to"), "qid": (pg.get("pageprops") or {}).get("wikibase_item")}
    if rec["qid"]:
        e = get("https://www.wikidata.org/w/api.php", action="wbgetentities", ids=rec["qid"], props="claims|labels", languages="ja|en", format="json")
        ent = e["entities"][rec["qid"]]
        rec["p31"] = [c["mainsnak"].get("datavalue", {}).get("value", {}).get("id") for c in ent.get("claims", {}).get("P31", [])]
        rec["label_en"] = (ent.get("labels", {}).get("en") or {}).get("value")
    out[w] = rec
    print(json.dumps(rec, ensure_ascii=False))
    json.dump(out, open(out_path, "w"), ensure_ascii=False, indent=1)
json.dump(out, open(out_path, "w"), ensure_ascii=False, indent=1)
