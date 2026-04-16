# Selection Learning

Adaptive selection learning is the mechanism that helps the curation pipeline prioritize sources and topics that are more likely to match actual publishing behavior. The system does this by logging candidates, reconciling them against published posts, and feeding acceptance rates back into future ranking.

## Candidate logging

Every generated article candidate and post is logged to `data/selection/generated_candidates.jsonl` together with metadata such as source, topic, SSI component, route, and run ID. This creates the training signal for later reconciliation and ranking.

## Reconciliation

Running `python main.py --reconcile` fetches published posts and matches them against logged candidates. The documented matching cascade is exact Buffer post ID first, then article URL, then Jaccard token similarity between generated and published text.

Candidates matched to published posts become `selected=True`, while candidates older than the 14-day acceptance window become `selected=False`; newer unmatched candidates stay pending as `selected=None`. These labels are then used to compute acceptance priors.

## Acceptance priors

The system computes a Beta-smoothed acceptance rate for each `(source, ssi_component)` bucket. On later curation runs, that prior becomes one of the ranking features alongside keyword relevance and freshness, helping preferred sources float upward over time.

## Local files

The README identifies `data/selection/generated_candidates.jsonl` and `data/selection/published_posts_cache.jsonl` as local, auto-created, gitignored files. It also notes a local ideas cache whose path can be overridden with `IDEAS_CACHE_PATH` in `.env`.

## Workflow

A typical loop is: run `--curate`, review or publish outputs, run `--reconcile`, and let later curation runs incorporate those choices automatically. This keeps the ranking system grounded in user behavior instead of one-time keyword matching alone.
