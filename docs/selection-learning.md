# Selection Learning

Adaptive selection learning is the mechanism that helps the curation pipeline prioritize sources and topics that are more likely to match actual publishing behavior. The system does this by logging candidates, reconciling them against published posts, and feeding acceptance rates back into future ranking.

## Candidate logging

Every generated article candidate and post is logged to `data/selection/generated_candidates.jsonl` together with metadata such as source, topic, SSI component, route, and run ID. This creates the training signal for later reconciliation and ranking.

### Generated Candidates Schema (Mermaid)

Below is a class diagram of the generated candidates structure (`generated_candidates.jsonl`):

```mermaid
classDiagram
    class CandidateRecord {
        string candidate_id
        string timestamp
        string article_url
        string article_title
        string article_source
        string ssi_component
        string channel
        string text_hash
        string text_snippet
        string|None buffer_id
        string route
        bool|None selected
        string|None selected_at
        string run_id
        string[] themes
        dict sentiment
        dict user_feedback
    }
```

If your Markdown viewer does not support Mermaid, see the schema fields above or refer to the example JSONL for structure.

## Reconciliation

Running `python main.py --reconcile` fetches published posts and matches them against logged candidates. The documented matching cascade is exact Buffer post ID first, then article URL, then Jaccard token similarity between generated and published text.

Candidates matched to published posts become `selected=True`, while candidates older than the 14-day acceptance window become `selected=False`; newer unmatched candidates stay pending as `selected=None`. These labels are then used to compute acceptance priors.

## Acceptance priors

The system computes a Beta-smoothed acceptance rate for each `(source, ssi_component)` bucket. On later curation runs, that prior becomes one of the ranking features alongside keyword relevance and freshness, helping preferred sources float upward over time.

## Learning Signals and spaCy NLP

### Captured Attributes for Each Candidate

Each generated post candidate is logged with metadata such as:

- **Text snippet** (the generated post)
- **Candidate ID** (unique hash)
- **Article URL/source** (if curated from an article)
- **SSI component** (establish_brand, find_right_people, engage_with_insights, build_relationships)
- **Timestamp**
- **Selected status** (selected, rejected, or pending)
- **Buffer post ID** (if published)
- **Channel** (LinkedIn, X, Bluesky, etc.)
- **Route** (post, idea, block)
- **Run ID** (for tracking batch runs)
- **spaCy-extracted features** (see below)

### Signals Used for Learning and Ranking

The learning and ranking system uses a combination of:

- **SSI component** (which pillar the post targets)
- **Source** (where the article or idea came from)
- **spaCy NLP features:**
  - **Themes/topics** (extracted via NER and noun chunking)
  - **Sentiment/tone** (rule-based, using spaCy tokenization)
  - **Semantic similarity** (for repetition detection and matching)
  - **Fact grounding** (matching claims to persona graph facts)
  - **Repetition score** (semantic similarity to recent posts, penalizes repeated content)
  - **Confidence signals** (from the truth gate, spaCy, and other heuristics)
- **Acceptance priors** (Beta-smoothed rate of selection for each (source, ssi_component) bucket)
- **User feedback** (if you upvote/downvote or override a candidate)

### spaCy’s Role

spaCy is used for:

- **Theme extraction** (NER + noun chunks)
- **Sentiment/tone analysis** (rule-based, token-level)
- **Semantic similarity** (vector-based, for repetition and matching)
- **Fact suggestion** (when the truth gate drops a claim, spaCy finds the closest persona fact)
- **Summarization** (for curated articles)

### Summary Table

| Attribute           | Source/Method      | Used for...                     |
| ------------------- | ------------------ | ------------------------------- |
| Text snippet        | Generated          | Matching, learning, reporting   |
| SSI component       | Candidate metadata | Acceptance priors, allocation   |
| Source/article URL  | Candidate metadata | Acceptance priors, matching     |
| Channel             | Candidate metadata | Channel-specific reconciliation |
| spaCy themes        | spaCy NER/chunks   | Learning, repetition, priors    |
| Sentiment/tone      | spaCy (rule-based) | Confidence, learning            |
| Semantic similarity | spaCy vectors      | Repetition, matching, learning  |
| Fact suggestion     | spaCy + persona    | Truth gate, learning            |
| Confidence signals  | Heuristics + spaCy | Routing, learning               |
| User feedback       | Manual/CLI         | Learning, priors                |

In short:
spaCy powers most of the NLP signals (themes, sentiment, similarity, fact suggestion) that drive learning, ranking, and post selection in the system. All these signals are logged and used to adapt future content and curation.

## Local files

The README identifies `data/selection/generated_candidates.jsonl` and `data/selection/published_posts_cache.jsonl` as local, auto-created, gitignored files. It also notes a local ideas cache whose path can be overridden with `IDEAS_CACHE_PATH` in `.env`.

### Published Posts Cache Schema (Mermaid)

Below is a class diagram of the published posts cache structure (`published_posts_cache.jsonl`):

```mermaid
classDiagram
  class PublishedRecord {
    string buffer_id
    string channel
    string text_snippet
    string published_at
    string fetched_at
    string|None candidate_id
  }
```

If your Markdown viewer does not support Mermaid, see the schema fields above or refer to the example JSONL for structure.

## Workflow

A typical loop is: run `--curate`, review or publish outputs, run `--reconcile`, and let later curation runs incorporate those choices automatically. This keeps the ranking system grounded in user behavior instead of one-time keyword matching alone.
