# 🚀 LinkedIn SSI Booster — Quickstart Cheatsheet

## 1. Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in PERSONA_SYSTEM_PROMPT, BUFFER_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODEL, etc.
cp data/avatar/persona_graph.example.json data/avatar/persona_graph.json
cp data/avatar/narrative_memory.example.json data/avatar/narrative_memory.json
cp content_calendar.example.py content_calendar.py
```

## 2. Generate & Schedule Posts

- **Preview week 1 posts (no Buffer calls):**
  ```bash
  python main.py --generate --week 1 --dry-run
  ```
- **Schedule week 1 posts to Buffer (LinkedIn):**
  ```bash
  python main.py --generate --schedule --week 1
  ```
- **Schedule to all channels:**
  ```bash
  python main.py --generate --schedule --week 1 --channel all
  ```

## 3. Curate AI News

- **Preview curation (no Buffer calls):**
  ```bash
  python main.py --curate --dry-run
  ```
- **Push curated ideas to Buffer (review before publishing):**
  ```bash
  python main.py --curate
  ```
- **Schedule curated posts directly:**
  ```bash
  python main.py --curate --type post --channel linkedin
  ```

## 4. Learning & Explainability

- **Reconcile published posts (improves future curation ranking):**
  ```bash
  python main.py --reconcile
  ```
- **Show grounding facts after each post:**
  ```bash
  python main.py --curate --avatar-explain
  ```
- **Print learning report from moderation events:**
  ```bash
  python main.py --avatar-learn-report
  ```

## 5. SSI Tracking

- **Record today's SSI scores:**
  ```bash
  python main.py --save-ssi 10.49 9.69 11.0 12.15
  ```
- **Print SSI report:**
  ```bash
  python main.py --report
  ```

## 6. Test Everything

```bash
pytest tests/ -v
```

---

**Pro tips:**
- Edit your persona in `data/avatar/persona_graph.json` for best results.
- Tweak keywords/feeds in `.env` (`CURATOR_KEYWORDS`, `CURATOR_RSS_FEEDS`).
- All generation is local — no cloud AI keys required.
- All learning data is stored locally and gitignored.
