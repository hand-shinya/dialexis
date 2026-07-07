"""Shared HTTP layer for all connectors.

GENESIS.md axiom 3 (lens principle): Dialexis stores provenance and traces,
not knowledge. Every fetch is stamped with retrieved_at (axiom 4) and cached
politely to respect free public APIs. Failures are returned as visible error
objects, never swallowed (visibility over silence).
"""
import datetime
import json
import os

import httpx

from ..db import get_conn, now

CONTACT = os.environ.get("DIALEXIS_CONTACT", "")
REPO = "https://github.com/hand-shinya/dialexis"
UA = f"Dialexis/0.1 (+{REPO}" + (f"; mailto:{CONTACT}" if CONTACT else "") + ")"
DEFAULT_TTL = 3600  # seconds


async def cached_get_json(url: str, params: dict | None = None,
                          ttl: int = DEFAULT_TTL, headers: dict | None = None):
    """Return (body, retrieved_at_iso, from_cache)."""
    key = url + ("?" + str(httpx.QueryParams(params)) if params else "")
    conn = get_conn()
    try:
        row = conn.execute("SELECT fetched_at, body FROM api_cache WHERE url=?",
                           (key,)).fetchone()
        if row:
            age = (datetime.datetime.now(datetime.timezone.utc)
                   - datetime.datetime.fromisoformat(row["fetched_at"])).total_seconds()
            if age < ttl:
                return json.loads(row["body"]), row["fetched_at"], True
        async with httpx.AsyncClient(timeout=25, follow_redirects=True,
                                     headers={"User-Agent": UA, **(headers or {})}) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            body = resp.json()
        ts = now()
        conn.execute("INSERT OR REPLACE INTO api_cache(url, fetched_at, body) VALUES(?,?,?)",
                     (key, ts, json.dumps(body)))
        conn.commit()
        return body, ts, False
    finally:
        conn.close()


def ok(source: str, retrieved_at: str, cached: bool, data) -> dict:
    return {"source": source, "retrieved_at": retrieved_at,
            "cached": cached, "error": None, "data": data}


def err(source: str, exc: Exception) -> dict:
    return {"source": source, "retrieved_at": now(), "cached": False,
            "error": f"{type(exc).__name__}: {exc}", "data": None}
