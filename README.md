# Dialexis — Reflexive Philosophy Infrastructure

*Make your question deeper, grounded, falsifiable and shareable.*
[日本語 README](README.ja.md) · **[GENESIS.md — the constitution](GENESIS.md)**

Dialexis is an open (AGPL-3.0) research infrastructure for anyone with a
philosophical question — from schoolchildren to specialists. It is **not** a
philosophy Wikipedia, a scholar search engine, or a chatbot. It offers:

1. **A lens** — a keyless, unified window onto the world's living free
   scholarly sources (Wikidata, OpenAlex, Crossref, OpenCitations,
   Wikipedia/Wikisource, Project Gutenberg). Every item is stamped with its
   source and retrieval time. Nothing encyclopedic is stored here.
2. **A research desk** — a research-process graph whose first-class citizens
   are *questions, claims, evidence, counterclaims, uncertainties and
   decisions*, with per-node provenance, a fixed confidence scale, and full
   export to Markdown / JSON-LD.
3. **A counterargument engine** — six disciplinary perspectives interrogate
   any claim, free and keyless (Level 0); your own LLM API key elevates it to
   generated counterarguments (Level 2).
4. **Watches** — a cron-fired harvester detects new works, papers and
   citations for targets you track. Even for Karl Marx, new material appears.
5. **Reading levels** — the same concept at seven depths, elementary school
   to expert.
6. **AI transparency** — every AI-touched output is labeled, ledgered, and
   "unverified" until a human checks the sources.

## Quick start

```bash
git clone https://github.com/hand-shinya/dialexis.git
cd dialexis
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000
# open http://localhost:8000
```

No API keys, no external database, no build step. An LLM key (Anthropic /
OpenAI / Gemini / local Ollama) is optional and stays in your browser.

## Documentation

| Doc | Purpose |
|---|---|
| [GENESIS.md](GENESIS.md) | The constitution: purpose, seven axioms, rebuild prompt |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System structure and data model |
| [docs/BUILD_FROM_ZERO.md](docs/BUILD_FROM_ZERO.md) | Rebuild everything from an empty machine |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Using Dialexis ([日本語](docs/USER_GUIDE.ja.md)) |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Running it in production |
| [docs/IMPROVEMENT_PROTOCOL.md](docs/IMPROVEMENT_PROTOCOL.md) | How the system improves itself |
| [docs/DEPLOY_SAKURA_VPS.md](docs/DEPLOY_SAKURA_VPS.md) | Deploying on a small VPS |
| [docs/COST_AND_API.md](docs/COST_AND_API.md) | Every external API, its cost and limits |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | When things break |
| [docs/ROADMAP.md](docs/ROADMAP.md) | From MVP to full Reflexive Philosophy Infrastructure |
| [docs/DONATIONS.md](docs/DONATIONS.md) | Funding model |

## License

Code: AGPL-3.0. Documentation: CC-BY-4.0. The commons cannot be enclosed.
