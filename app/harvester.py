"""Dialexis harvester — the external executor for dynamic freshness.

Run by cron / systemd timer, NOT by the AI and NOT by user action (the trigger
must live outside anyone's memory or goodwill). For every registered watch it
queries OpenAlex and Crossref for items newer than last_checked and records
hits. Always writes data/harvester_status.json — absence or staleness of that
file is itself the alarm (visibility over silence).

Usage:  python3 -m app.harvester
"""
import asyncio
import json
import os
import traceback

from .db import get_conn, init_db, now, rows, BASE_DIR
from .main import check_watch

STATUS_PATH = os.path.join(BASE_DIR, "data", "harvester_status.json")


async def run() -> dict:
    init_db()
    conn = get_conn()
    watches = rows(conn.execute("SELECT * FROM watches"))
    conn.close()
    results, errors = [], []
    for w in watches:
        try:
            results.append(await check_watch(w))
        except Exception:
            errors.append({"watch_id": w["id"], "label": w["label"],
                           "error": traceback.format_exc(limit=3)})
        await asyncio.sleep(1)  # politeness toward free APIs
    status = {"last_run": now(), "watch_count": len(watches),
              "new_hits": sum(r["new_count"] for r in results),
              "results": results, "errors": errors}
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    return status


if __name__ == "__main__":
    s = asyncio.run(run())
    print(json.dumps({k: s[k] for k in ("last_run", "watch_count", "new_hits")},
                     ensure_ascii=False))
    if s["errors"]:
        print(f"ERRORS: {len(s['errors'])} (see {STATUS_PATH})")
        raise SystemExit(1)
