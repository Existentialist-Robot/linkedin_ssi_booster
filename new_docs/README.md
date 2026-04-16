# LinkedIn SSI Booster — Persona-Grounded Learning · Hybrid RAG Agent

Automates LinkedIn post generation and scheduling via local Ollama to systematically grow your LinkedIn Social Selling Index (SSI) score. The project combines persona grounding, hybrid retrieval, deterministic validation, and local learning loops so content stays on-brand, evidence-backed, and adaptive over time.

## What it is

LinkedIn SSI Booster is more than a prompt wrapper. It is a content automation system that combines spaCy-based NLP, a persona graph, BM25 retrieval, a truth gate, confidence scoring, and local memory to generate, curate, rank, and route posts with more control than a basic AI writer workflow.

Core capabilities include:

- Persona-grounded generation using structured profile facts from `data/avatar/persona_graph.json`.
- Hybrid RAG orchestration with BM25 retrieval, prompt constraints, and deterministic post-processing.
- Curation learning that updates acceptance priors from what actually gets published.
- Explainability features such as `--avatar-explain` and `--avatar-learn-report`.
- Local-first operation using Ollama, with persona and learning data stored on your own machine.

## Docs map

- [Setup guide](docs/setup.md) — environment, dependencies, persona graph, and calendar setup.
- [Architecture guide](docs/architecture.md) — learning pipeline, grounding flow, truth gate, and curation ranking.
- [Persona and Avatar Intelligence](docs/persona-and-avatar.md) — persona graph, system prompt, memory, confidence, and explainability.
- [Usage guide](docs/usage-schedule-curate-console.md) — scheduling, curation, console mode, channels, and CLI examples.
- [SSI strategy](docs/ssi-and-strategy.md) — SSI model, content mapping, scheduler behavior, and reporting.
- [AI backend](docs/ai-backend-and-models.md) — Ollama setup and model recommendations.
- [Testing and development](docs/testing-and-dev.md) — pytest coverage and project structure.
- [Selection learning](docs/selection-learning.md) — candidate logging, reconciliation, and acceptance priors.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
cp .env.example .env
cp data/avatar/persona_graph.example.json data/avatar/persona_graph.json
cp data/avatar/narrative_memory.example.json data/avatar/narrative_memory.json
cp content_calendar.example.py content_calendar.py
python main.py --schedule --week 1 --dry-run
```

The setup flow requires a configured `.env`, a filled-in persona graph, a narrative memory file, and a personalized content calendar before useful scheduling or curation runs begin.

## Existing docs

The repository already includes `docs/idea.md`, `docs/prd.md`, `docs/design.md`, and `docs/nlp-basics.md`, plus a feature-specific Avatar Intelligence documentation subtree under `docs/features/avatar-intelligence-learning/`.

## License

MIT — see `LICENSE` for details.
