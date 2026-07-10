"""BibTeX / CSL-JSON generation for a project's cited sources (G2 in
WORKFLOW_COVERAGE — "採用の必須条件": a tool that does not export to the citation
manager the researcher already uses gets abandoned, RESEARCH_REALITY §7).

Deliberately dependency-free (GENESIS axiom 7: no framework, no build step) — the
formats are simple enough to emit by hand. Citekeys are STABLE: derived from the
source name/title, disambiguated by a short hash of the URL, so the same project
always yields the same keys (RESEARCH_REALITY §7: "安定した citekey").

Input `refs` is a list of dicts collected in main.py from provenance rows and
argument-premise sources: {title, url, urldate, note, source_name}.
"""
import re
import hashlib


def _slug(s: str, n: int = 20) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", (s or "").strip()).strip("_").lower()
    return s[:n] or "ref"


def _citekey(ref: dict, used: set) -> str:
    base = _slug(ref.get("source_name") or ref.get("title") or "ref")
    key = base
    if key in used:
        h = hashlib.sha1((ref.get("url") or ref.get("title") or "").encode("utf-8")).hexdigest()[:4]
        key = f"{base}_{h}"
        i = 2
        while key in used:
            key = f"{base}_{h}_{i}"
            i += 1
    used.add(key)
    return key


def _clean(s: str) -> str:
    # braces would break BibTeX grouping; backslash would start a control seq.
    return (s or "").replace("{", "(").replace("}", ")").replace("\\", "/").strip()


def _note(ref: dict) -> str:
    src = ref.get("source_name") or ""
    return "; ".join(x for x in [f"source: {src}" if src else "", ref.get("note") or ""] if x)


def to_bibtex(refs: list, project: str = "") -> str:
    used, out = set(), []
    if project:
        out.append(f"% Dialexis bibliography — project: {_clean(project)}")
        out.append("% Generated from provenance (source + retrieved_at). Verify before use.")
    for r in refs:
        key = _citekey(r, used)
        lines = ["@misc{" + key + ",", f"  title = {{{_clean(r.get('title'))}}},"]
        if r.get("url"):
            lines.append(f"  howpublished = {{\\url{{{r['url']}}}}},")
        if r.get("urldate"):
            lines.append(f"  urldate = {{{_clean(r['urldate'])}}},")
        note = _note(r)
        if note:
            lines.append(f"  note = {{{_clean(note)}}},")
        lines.append("}")
        out.append("\n".join(lines))
    return "\n\n".join(out) + ("\n" if out else "")


def to_csl(refs: list) -> list:
    used, items = set(), []
    for r in refs:
        item = {"id": _citekey(r, used),
                "type": "webpage" if r.get("url") else "document",
                "title": r.get("title") or ""}
        if r.get("url"):
            item["URL"] = r["url"]
        parts = (r.get("urldate") or "").split("-")
        if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
            item["accessed"] = {"date-parts": [[int(parts[0]), int(parts[1]), int(parts[2])]]}
        note = _note(r)
        if note:
            item["note"] = note
        items.append(item)
    return items
