"""LLM switchboard (GENESIS.md axiom 5: degradation ladder).

Every feature works at Level 0 without this module. A user-supplied API key
only ELEVATES a feature; it is never a requirement. Keys are passed per
request from the browser and are never persisted or logged server-side
(axiom 6: AI transparency — the ai_ledger records THAT a call happened and
what task it served, never the key or raw prompt).

Providers: anthropic | openai | gemini | ollama
"""
import httpx

from ..db import get_conn, now

TIMEOUT = 90


async def _anthropic(key: str, model: str, system: str, user: str) -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post("https://api.anthropic.com/v1/messages",
                         headers={"x-api-key": key,
                                  "anthropic-version": "2023-06-01"},
                         json={"model": model or "claude-sonnet-5",
                               "max_tokens": 2048, "system": system,
                               "messages": [{"role": "user", "content": user}]})
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", []))


async def _openai(key: str, model: str, system: str, user: str) -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post("https://api.openai.com/v1/chat/completions",
                         headers={"Authorization": f"Bearer {key}"},
                         json={"model": model or "gpt-4o-mini",
                               "messages": [{"role": "system", "content": system},
                                            {"role": "user", "content": user}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def _gemini(key: str, model: str, system: str, user: str) -> str:
    m = model or "gemini-2.0-flash"
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
            params={"key": key},
            json={"system_instruction": {"parts": [{"text": system}]},
                  "contents": [{"parts": [{"text": user}]}]})
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


async def _ollama(_key: str, model: str, system: str, user: str) -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post("http://localhost:11434/api/chat",
                         json={"model": model or "llama3.1", "stream": False,
                               "messages": [{"role": "system", "content": system},
                                            {"role": "user", "content": user}]})
        r.raise_for_status()
        return r.json()["message"]["content"]


PROVIDERS = {"anthropic": _anthropic, "openai": _openai,
             "gemini": _gemini, "ollama": _ollama}

GUARD = ("You are an assistant inside Dialexis, a reflexive philosophy research "
         "infrastructure. Hard rules: (1) never assert an unverified attribution "
         "as fact; (2) always separate: established scholarship / plausible "
         "interpretation / your own speculation, and label each part; (3) name "
         "primary sources the user should verify; (4) note translation risks when "
         "concepts cross languages; (5) if you do not know, say so.")


async def run(provider: str, model: str, key: str, task: str,
              system: str, user: str, project_id: int | None = None) -> dict:
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider}")
    text = await PROVIDERS[provider](key, model, GUARD + "\n\n" + system, user)
    conn = get_conn()
    conn.execute("INSERT INTO ai_ledger(ts, provider, model, task, project_id, summary)"
                 " VALUES(?,?,?,?,?,?)",
                 (now(), provider, model, task, project_id, user[:200]))
    conn.commit()
    conn.close()
    return {"text": text, "origin": "ai", "provider": provider,
            "model": model, "task": task, "generated_at": now(),
            "confidence": "unverified",
            "notice": "AI-generated. Unverified until a human checks the sources."}
