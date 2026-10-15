#!/usr/bin/env python3
"""日常語 → 哲学概念：方式 A〜F の隔離比較（2026-10-15・製品は変えない）。

方式:
  A 現行          本番 /api/origin の着地と候補（読み取りだけ）
  B 鍵不要・語彙  文から漢字・カタカナの語を取り、ja.wikipedia opensearch と ja.wiktionary の
                  類義・関連語で広げる（LLM なし）
  C 鍵不要・接地  B ＋ ja 全文検索 ＋ Wikidata Vector DB（型なし・Q151885）の和集合を、
                  Wikidata の型と説明文で「概念らしいもの」に絞り、合意した源の数で並べる
  D BYO-LLM       利用者の LLM が文から概念名（ja.wikipedia の記事名）を挙げ、この system が
                  実在する項目に接地する。利用者の鍵の代わりに、試験では手元の CLI を使う
                  （D-claude = claude haiku、D-codex = codex。決裁 D36/D46: 評価用の model 利用）
  E handoff       既存の /api/handoff の文（app/handoff.build）を利用者の AI（codex）に渡し、
                  返った自由文から「」『』**…** の語を拾って接地する（利用者の貼り戻しを模す）
  F 組合せ        D-codex の接地済み候補を先に、C の候補で補う

採点（評価仕様の判定項目1を、意味の近さで誤判定しないよう段階に分ける）:
  strict   期待概念（暫定・複数可）の項目そのものが上位10件に在る
  near     期待概念の Wikidata 上の隣接項目（P279 上位／P361 全体／P527 部分／P460 同一視／
           P1269 側面 の、出る向き・入る向き）まで認める。隣接は Wikidata の言明で決め、AI は決めない
  grounded 候補のうち、実在の Wikidata 項目に接地できた割合（D・E では作り話の検出）
  precision は人の判断が要るので機械では採点しない（候補と理由を保存して人が見る）。

評価器の自己検査（--selftest）:
  正例（期待の項目そのもの）→ strict、近い例（物象化の P361＝マルクス主義における疎外）→ near、
  負例（曲・ドラマ）→ どちらも偽、無関係な概念（時間）→ どちらも偽、を確かめる。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import bridge_eval as be  # noqa: E402

REL_PROPS = ("P279", "P361", "P527", "P460", "P1269")
CONCEPT_CLASSES = {"Q151885", "Q33104279", "Q23847174", "Q17737", "Q12909644", "Q11862829",
                   "Q1047113", "Q7184903", "Q2915981", "Q5891", "Q60539481"}
CONCEPT_DESC = re.compile(r"哲学|概念|思想|倫理|主義|論|学説|心理|価値|philosoph|concept|ethic|theory|doctrine", re.I)
STOP = {"自分", "感じ", "ように", "何", "人", "ため", "こと", "もの", "とき", "よう", "全て", "前", "同じ"}


# ---------------------------------------------------------------- 採点
_NEIGH = {}


def neighbors(qid):
    """Wikidata の言明だけで決める隣接（出る向きと入る向き）。"""
    if qid in _NEIGH:
        return _NEIGH[qid]
    out = set()
    d, _ = be.get(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
    ent = ((d or {}).get("entities") or {}).get(qid, {})
    for p in REL_PROPS:
        for c in (ent.get("claims") or {}).get(p, []):
            v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            if isinstance(v, dict) and v.get("id"):
                out.add(v["id"])
    sr = " ".join(f"haswbstatement:{p}={qid}" for p in REL_PROPS[:1])
    for p in REL_PROPS:
        d, _ = be.get("https://www.wikidata.org/w/api.php", {
            "action": "query", "list": "search", "srsearch": f"haswbstatement:{p}={qid}",
            "srlimit": 50, "format": "json"})
        out |= {x["title"] for x in ((d or {}).get("query") or {}).get("search", [])}
    _NEIGH[qid] = out
    return out


def score(top, want):
    top = [q for q in top if q][:10]
    if not want:
        return {"strict": None, "near": None}
    strict = bool(set(top) & want)
    near_set = set(want)
    for w in want:
        near_set |= neighbors(w)
    return {"strict": strict, "near": bool(set(top) & near_set)}


def selftest():
    key = be.titles_to_qids(["物象化", "疎外", "物化"])
    want = {key["物象化"], key["疎外"]}
    cases = [("正例", [key["物象化"]], True, True),
             ("近い例 P361", ["Q13417770"], False, True),
             ("負例 曲・番組", ["Q45650", "Q11228384"], False, False),
             ("無関係な概念 時間", ["Q11471"], False, False)]
    ok = True
    for name, top, s, n in cases:
        r = score(top, want)
        good = (r["strict"] == s and r["near"] == n)
        ok &= good
        print(f"{'PASS' if good else 'FAIL'}  {name}: {r}")
    return 0 if ok else 1


# ---------------------------------------------------------------- 方式
def terms(q):
    t = re.findall(r"[一-龥々]{2,}|[ァ-ヶー]{2,}", q)
    return [x for x in dict.fromkeys(t) if x not in STOP]


def method_A(base, q):
    r = be.stage_product(base, q)
    return [{"qid": x, "src": "product"} for x in r.get("qids", [])], r.get("error")


def _opensearch(t, n=3):
    d, _ = be.get("https://ja.wikipedia.org/w/api.php", {
        "action": "opensearch", "search": t, "limit": n, "namespace": 0, "format": "json"})
    return (d[1] if isinstance(d, list) and len(d) > 1 else [])[:n]


def _wiktionary_related(t):
    d, _ = be.get("https://ja.wiktionary.org/w/api.php", {
        "action": "parse", "page": t, "prop": "wikitext", "format": "json", "redirects": 1})
    wt = ((d or {}).get("parse") or {}).get("wikitext", {}).get("*", "")
    if not wt:
        return []
    try:
        from app.connectors import ja_wiktionary
        rels = ja_wiktionary.relations(wt)
    except Exception:
        return []
    return [r.get("term") for r in rels if r.get("kind") in ("synonym", "related", "derived") and r.get("term")][:6]


def method_B(q):
    titles = []
    for t in terms(q):
        titles += _opensearch(t)
        for w in _wiktionary_related(t):
            titles += _opensearch(w, 1)
    titles = list(dict.fromkeys(titles))
    m = be.titles_to_qids(titles)
    return [{"qid": m[x], "title": x, "src": "B"} for x in titles if m.get(x)], None


def _info(qids):
    out = {}
    for i in range(0, len(qids), 50):
        d, _ = be.get("https://www.wikidata.org/w/api.php", {
            "action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
            "props": "claims|labels|descriptions|sitelinks", "languages": "ja|en", "format": "json"})
        for q, e in ((d or {}).get("entities") or {}).items():
            p31 = [((c.get("mainsnak") or {}).get("datavalue") or {}).get("value", {}).get("id")
                   for c in (e.get("claims") or {}).get("P31", [])]
            desc = " ".join(v.get("value", "") for v in (e.get("descriptions") or {}).values())
            lab = (e.get("labels") or {})
            out[q] = {"p31": [x for x in p31 if x], "desc": desc,
                      "label": (lab.get("ja") or lab.get("en") or {}).get("value", q),
                      "jawiki": "jawiki" in (e.get("sitelinks") or {})}
    return out


def conceptish(inf):
    if not inf:
        return False
    p31 = set(inf["p31"])
    if p31 & be.WORK_PERSON or "Q4167410" in p31:
        return False
    return bool(p31 & CONCEPT_CLASSES) or bool(CONCEPT_DESC.search(inf["desc"]))


def method_C(q, b_cands):
    pools = {"B": [c["qid"] for c in b_cands],
             "S1": be.stage_fulltext(q).get("qids", []),
             "S3": be.stage_vector(q).get("qids", []),
             "S4": be.stage_vector(q, "Q151885").get("qids", [])}
    allq = list(dict.fromkeys(x for v in pools.values() for x in v))
    inf = _info(allq) if allq else {}
    votes = {}
    for src, lst in pools.items():
        for rank, x in enumerate(lst):
            if conceptish(inf.get(x)):
                v = votes.setdefault(x, {"n": 0, "best": 99, "src": []})
                v["n"] += 1
                v["best"] = min(v["best"], rank)
                v["src"].append(src)
    order = sorted(votes, key=lambda x: (-votes[x]["n"], votes[x]["best"]))
    return [{"qid": x, "label": inf[x]["label"], "src": "+".join(votes[x]["src"])} for x in order], None


PROMPT_D = """次の日常的な問いに関係する哲学の概念を、日本語版ウィキペディアに実在する記事名そのもので最大8個挙げてください。
対立する立場や、別の文化圏の概念も含めてかまいません。出力は JSON の配列だけにしてください。
形式: [{{"title": "記事名", "reason": "問いとの関係を一文で"}}]
問い: {q}"""


def _llm(engine, prompt):
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        if engine == "claude":
            r = subprocess.run(["claude", "-p", "--restricted", "--strict-mcp-config",
                                "--no-session-persistence", "--tools", "",
                                "--model", "claude-haiku-5-5", "--output-format", "text"],
                               input=prompt, cwd=td, capture_output=True, text=True, timeout=300)
            out = r.stdout
        else:
            last = os.path.join(td, "last.txt")
            # 思考量は低にそろえる（既定の high では1問100〜400秒かかった・2026-10-15 実測）
            r = subprocess.run(["codex", "exec", "--skip-git-repo-check", "-s", "read-only",
                                "-c", 'model_reasoning_effort="low"',
                                "-o", last, "-"], input=prompt, cwd=td,
                               capture_output=True, text=True, timeout=400)
            out = open(last, encoding="utf-8").read() if os.path.exists(last) else r.stdout
    return out, round(time.time() - t0, 1)


def _parse_titles(text):
    m = re.search(r"\[[\s\S]*\]", text or "")
    if m:
        try:
            arr = json.loads(m.group(0))
            return [(str(x.get("title", "")).strip(), str(x.get("reason", ""))) for x in arr
                    if isinstance(x, dict) and x.get("title")]
        except Exception:
            pass
    return []


def _norm(t):
    import unicodedata
    t = unicodedata.normalize("NFKC", t or "")
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t)          # 末尾の括弧（仏教）を外す
    return re.sub(r"[\s・=＝\-－‐の]", "", t).lower()


def _close(a, b):
    import difflib
    na, nb = _norm(a), _norm(b)
    return na == nb or difflib.SequenceMatcher(None, na, nb).ratio() >= 0.85


def ground(names):
    """名前 → 実在する項目。記事名で引けなければ opensearch の1位で引き直す（ずれの吸収）。

    2026-10-15: 引き直し18件のうち6件が別物だった（カント倫理学→カントー大学・白い嘘→白い巨塔・
    持続（哲学）→持続可能な開発目標 など）。引き直しは、表記を正規化してほぼ一致し（類似度0.85以上）、
    かつ引き直した先が概念らしい（人物・作品・地名でない）ときだけ採る。それ以外は接地しない。"""
    m = be.titles_to_qids([n for n, _ in names])
    out, unground, rejected = [], [], []
    for n, why in names:
        q = m.get(n)
        via = "title"
        if not q:
            alt = _opensearch(n, 1)
            if alt and _close(n, alt[0]):
                q2 = be.titles_to_qids(alt).get(alt[0])
                if q2 and conceptish(_info([q2]).get(q2)):
                    q, via = q2, "opensearch:" + alt[0]
                elif q2:
                    rejected.append(f"{n}→{alt[0]}")
            elif alt:
                rejected.append(f"{n}→{alt[0]}")
        if q:
            out.append({"qid": q, "title": n, "via": via, "reason": why})
        else:
            unground.append(n)
    return out, unground + [f"(棄却) {x}" for x in rejected]


def method_D(q, engine):
    text, sec = _llm(engine, PROMPT_D.format(q=q))
    names = _parse_titles(text)
    cands, ung = ground(names)
    return cands, {"raw": text[:2000], "names": [n for n, _ in names], "ungrounded": ung, "sec": sec}


def method_E(q):
    from app import handoff
    h = handoff.build(text=q, lang="ja")
    text, sec = _llm("codex", h["prompt"])
    picked = re.findall(r"[「『]([^」』]{1,20})[」』]|\*\*([^*]{1,20})\*\*", text)
    names = [(a or b).strip() for a, b in picked]
    names = [(n, "") for n in dict.fromkeys(n for n in names if n and n != q)][:15]
    cands, ung = ground(names)
    return cands, {"raw": text[:3000], "names": [n for n, _ in names], "ungrounded": ung, "sec": sec}


# ---------------------------------------------------------------- 実行
def main(base, out_path, which):
    hold = json.load(open(os.path.join(HERE, "holdout_20261015.json"), encoding="utf-8"))
    qs = [("dev",) + tuple(x) for x in be.QUESTIONS] + [("holdout",) + tuple(x) for x in hold["questions"]]
    exp_titles = sorted({t for *_, ts in qs for t in ts})
    key = be.titles_to_qids(exp_titles)
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"meta": {"base": base, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                                     "methods": which, "key": key,
                                     "unresolved": [t for t in exp_titles if not key.get(t)]}},
                           ensure_ascii=False) + "\n")
        for split, qid_, text, exp in qs:
            want = {key[t] for t in exp if key.get(t)}
            row = {"split": split, "id": qid_, "q": text, "expected": exp, "want": sorted(want)}
            b_cands = None
            for mth in which:
                t0 = time.time()
                try:
                    if mth == "A":
                        c, extra = method_A(base, text)
                    elif mth == "B":
                        c, extra = method_B(text)
                        b_cands = c
                    elif mth == "C":
                        if b_cands is None:
                            b_cands, _ = method_B(text)
                        c, extra = method_C(text, b_cands)
                    elif mth in ("D-claude", "D-codex"):
                        c, extra = method_D(text, mth.split("-")[1])
                    elif mth == "E":
                        c, extra = method_E(text)
                    elif mth == "F":
                        d = row.get("D-codex", {}).get("cands") or method_D(text, "codex")[0]
                        cc = row.get("C", {}).get("cands") or method_C(text, b_cands or method_B(text)[0])[0]
                        seen, c = set(), []
                        for x in d + cc:
                            if x["qid"] not in seen:
                                seen.add(x["qid"])
                                c.append(x)
                        extra = None
                except Exception as e:
                    c, extra = [], {"error": f"{type(e).__name__}: {e}"}
                top = [x["qid"] for x in c][:10]
                row[mth] = {"cands": c[:15], "extra": extra, "sec": round(time.time() - t0, 1),
                            **score(top, want)}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(split, qid_, " ".join(f"{m}={'S' if row[m]['strict'] else ('n' if row[m]['near'] else '×')}"
                                        for m in which), flush=True)
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        sys.exit(selftest())
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3].split(",")))
