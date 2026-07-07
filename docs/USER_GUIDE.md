# USER_GUIDE.md — User Manual (English)

For everyone using Dialexis. No philosophical background assumed. [日本語版](USER_GUIDE.ja.md)

## What Dialexis does for you

When a question strikes you — "what actually is freedom?", "can an AI be responsible?" — Dialexis does not hand you an answer. It **turns your question into an inquiry**: a keyless window onto the world's scholarly sources, plus a desk for organizing what you find. Free, no registration, no API key required.

## 1. Explore (front page)

Type a philosopher, work, or concept (`Karl Marx`, `freedom`, `Sein und Zeit`).

- For a person you get: dates, notable works, influences (Wikidata), a summary (Wikipedia), links to full primary texts (Wikisource / Project Gutenberg), and related scholarship (OpenAlex / Crossref) — on one page.
- Every item carries a badge saying **where it came from and when it was retrieved**. Information without that stamp does not exist in this system.
- A red badge means a source is currently not responding. That is shown deliberately, never hidden.

## 2. Research Desk

Start an inquiry with a title and an **initial question** (it becomes your first node). Then add nodes and connect them:

| Node | Use it for |
|---|---|
| Question | what you want to find out |
| Claim | what you want to assert |
| Evidence | material supporting a claim (always attach source URL + retrieval date) |
| Counterclaim | objections and counterexamples |
| Uncertainty | what you have NOT verified yet — honesty here is the quality of your research |
| Interpretation | your reading of a source |
| Decision | adopt / hold / reject |

Each node gets a **confidence class**: confirmed / highly probable / unverified / interpretive hypothesis / speculation. Admitting "this is still speculation" is a virtue here, not a weakness.

**Export**: your whole inquiry exports to Markdown (for humans) or JSON-LD (for machines) at any time — for essays, supervisors, or other tools. Your research never gets locked in.

## 3. Counterargument Engine

Enter a claim and six disciplinary perspectives interrogate it (philology, translation & conceptual history, analytic argument analysis, intellectual history, science & technology, sociology & institutions), plus a search for opposing literature.

- **Without a key (Level 0)**: checklists + literature search — already enough to find real holes in your claim.
- **With your own LLM key (Level 2)**: generated counterarguments per perspective, always labeled AI-generated and unverified.

## 4. Watches

Register "Karl Marx" and Dialexis will keep detecting new papers, works and materials. The idea: **even for the most classical authors, new discoveries happen.** A cron-driven harvester checks periodically; "Check now" works too.

## 5. Reading Levels

The same concept at seven depths, elementary school to expert. Try "freedom" at the elementary and the graduate level side by side — you will see that philosophy is not memorization. An API key extends this to any concept.

## 6. Settings (Key Switchboard)

Add an Anthropic / OpenAI / Gemini / Ollama (local, free) key to elevate AI features.

- Your key is stored **only in this browser** and relayed per-request; the server never persists or logs it.
- The AI Transparency Ledger on the same page shows everyone what AI did on this server, and when.

## 7. Example workflows

**A teenager**: explore "freedom" → read your level in Reading Levels → a doubt arises ("do I really choose?") → save it as a question on the Desk → test your idea against the Counterargument Engine.

**A graduate student**: explore the author → reach primary texts and scholarship → build the claim/evidence/counterclaim graph with provenance → register a Watch to monitor new scholarship automatically → export to Markdown for your supervisor.

## 8. When something breaks

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md), or open a GitHub Issue.
