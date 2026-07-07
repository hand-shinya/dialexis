"""Standard-locator citation resolver.

Field research (docs/RESEARCH_REALITY.md) is emphatic: in philosophy the atomic
unit of reference is NOT a DOI or a PDF page — it is an edition-independent
standard locator that resolves the SAME passage across every edition and
translation:
  * Plato  -> Stephanus number   (e.g. Republic 514a)
  * Aristotle -> Bekker number   (e.g. Nicomachean Ethics 1094a1)
  * Kant   -> A/B pagination     (Critique of Pure Reason A51/B75)
A tool that cannot speak these cannot support how philosophers cite or locate.

This module parses such a locator and deep-links it to a free open edition
(Perseus for Greek/Latin) so a citation becomes a click to the passage —
mirroring what Oxford Scholarly Editions does commercially. It is intentionally
small and honest: it resolves what it can and says so when it cannot, rather
than pretending to cover the whole canon.
"""
import re

# Perseus canonical text ids for the works we can deep-link today.
_PLATO = {
    "republic": "1999.01.0168", "apology": "1999.01.0170",
    "phaedo": "1999.01.0170", "symposium": "1999.01.0174",
    "gorgias": "1999.01.0168", "meno": "1999.01.0178",
    "phaedrus": "1999.01.0174", "timaeus": "1999.01.0180",
}
_ARISTOTLE = {
    "nicomachean ethics": "1999.01.0054", "ethics": "1999.01.0054",
    "politics": "1999.01.0058", "metaphysics": "1999.01.0052",
    "physics": "1999.01.0050", "de anima": "1999.01.0050",
    "rhetoric": "1999.01.0060",
}


def resolve(author: str, work: str, locator: str) -> dict:
    """Return a best-effort deep link + citation guidance for a standard locator."""
    a, w, loc = author.strip().lower(), work.strip().lower(), locator.strip()
    out = {"author": author, "work": work, "locator": loc,
           "scheme": None, "deep_link": "", "note": "", "resolved": False}

    if a.startswith("plato") or w in _PLATO:
        out["scheme"] = "Stephanus"
        tid = _PLATO.get(w)
        m = re.match(r"(\d+)([a-e])", loc.replace(" ", "").lower())
        if tid and m:
            out["deep_link"] = (f"https://www.perseus.tufts.edu/hopper/text?doc=Perseus:"
                                f"text:{tid}:section={m.group(1)}{m.group(2)}")
            out["resolved"] = True
        out["note"] = ("Stephanus pagination (Estienne 1578): page+section a–e, "
                       "printed in the margins of every scholarly Plato edition "
                       "and translation. Cite as e.g. 'Republic 514a'.")
    elif a.startswith("aristotle") or w in _ARISTOTLE:
        out["scheme"] = "Bekker"
        tid = _ARISTOTLE.get(w)
        m = re.match(r"(\d+)([ab])(\d+)?", loc.replace(" ", "").lower())
        if tid and m:
            out["deep_link"] = (f"https://www.perseus.tufts.edu/hopper/text?doc=Perseus:"
                                f"text:{tid}:bekker page={m.group(1)}{m.group(2)}")
            out["resolved"] = True
        out["note"] = ("Bekker numbering (Prussian Academy 1831): page+column(a/b)+"
                       "line, printed in the margins of every scholarly Aristotle "
                       "edition. Cite as e.g. 'Nicomachean Ethics 1094a1'.")
    elif a.startswith("kant"):
        out["scheme"] = "A/B (Akademie)"
        out["note"] = ("Kant is cited by A/B pagination (A=1781 1st ed., B=1787 "
                       "2nd ed. of the Critique of Pure Reason), e.g. 'A51/B75'; "
                       "other works by Akademie-Ausgabe volume:page. These are "
                       "printed in the margins of every serious edition/translation.")
    else:
        out["note"] = ("No standard-locator scheme known for this author yet. "
                       "Major schemes: Plato=Stephanus, Aristotle=Bekker, "
                       "Kant=A/B, Wittgenstein=remark number, Aquinas=part/q/art.")
    return out


SCHEMES = [
    {"author": "Plato", "scheme": "Stephanus", "example": "Republic 514a"},
    {"author": "Aristotle", "scheme": "Bekker", "example": "Nicomachean Ethics 1094a1"},
    {"author": "Kant", "scheme": "A/B pagination", "example": "A51/B75"},
    {"author": "Wittgenstein", "scheme": "Remark number", "example": "Tractatus 5.6"},
    {"author": "Aquinas", "scheme": "Part/Question/Article", "example": "ST I q.2 a.3"},
]
