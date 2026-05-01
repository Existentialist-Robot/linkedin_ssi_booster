# LinkedIn SSI Booster

#### _<u> — Persona-Grounded Truth-Gated Adaptive-Continual-Learning Hybrid-RAG Agent with Domain-Knowledge-Graph</u>_

[![License MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)[![Version alpha-v0.0.2.4](https://img.shields.io/badge/version-alpha--v0.0.2.4-orange.svg)]()

**LinkedIn SSI Booster** isn't just a prompt wrapper — it's an adaptive continual learning automation system for content, curation, and persona growth. It combines spaCy-based NLP, a persona graph, BM25 retrieval, a truth gate, confidence scoring, a NetworkX-powered knowledge graph, and local memory to generate, curate, rank, and route posts with more control and explainability than a basic AI writer workflow.

## 🧠 Intelligence Stack — Why This Is Smarter Than Just 'AI Writes Posts'

- **Advanced NLP with spaCy** — Theme/claim extraction, semantic similarity, sentiment/tone analysis, and two advanced curation/grounding features:
  - **Fact Suggestion:** When the truth gate drops a sentence, spaCy suggests the closest matching fact or evidence from your persona graph, or recommends how to rephrase for grounding.
  - **Contextual Summarization:** spaCy generates concise, context-aware summaries of curated articles, improving the quality of commentary and learning signals.
- **Persona-grounded generation** — Every post is written in your real technical voice, with facts, projects, and outcomes pulled from your private persona graph and knowledge graph (not just keywords or a bio blurb).
- **Hybrid RAG + agent pipeline** — Combines BM25 retrieval, deterministic validation, multi-step agent orchestration, and a hybrid BM25+graph reranker for high factuality, persona-awareness, and variety.
- **Curation learning loop** — The system tracks every generated candidate, learns which ones you actually publish, and automatically floats the best sources/topics to the top in future runs (Beta-smoothed acceptance priors per source/SSI component).
- **Truth gate** — Post-generation filter removes unsupported claims (numbers, dates, company names, project-tech mismatches) for maximum credibility. Four validation layers run in sequence on every sentence:
  - **BM25 evidence scoring** — each sentence is ranked against article text and persona facts; sentences below the configurable threshold (`TRUTH_GATE_BM25_THRESHOLD`) are flagged as weakly supported.
  - **Derivative of Truth per-sentence scoring** — every sentence receives a composite truth gradient (evidence type × reasoning quality × source credibility × token overlap). Sentences that pass BM25 but score below `TRUTH_GRADIENT_FLAG_THRESHOLD` (0.35) are flagged `weak_dot_gradient` and auto-removed. The 4-term DoT formula is active — token overlap between the sentence and each evidence fact is computed (Jaccard) and included as a 25%-weight component.
  - **spaCy semantic similarity floor** — for sentences containing numeric claims, years, dollar amounts, or org names, `compute_similarity()` checks the sentence against the source article. Similarity below `TRUTH_GATE_SPACY_SIM_FLOOR` (default `0.10`, configurable) flags the sentence as `low_semantic_similarity`, catching paraphrased hallucinations BM25 misses.
  - **spaCy NER org-name validation** — org/company names are extracted via spaCy named entity recognition (`ORG` entities) and verified against the allowed evidence set. Falls back to the legacy regex when spaCy is unavailable.
  - **False-positive hardening for tech terms** — concept/service tokens and tech-version entities (for example `S3`, `AI Q&A`, `Java 21`) are filtered before ORG enforcement so technical references are not incorrectly blocked as `unsupported_org`.
  - **Expanded domain evidence via multi-file loading** — avatar state now auto-merges sibling `domain_knowledge_*.json` files (for example Java and Python packs), which broadens allowed evidence tokens and improves support checks.
  > **DoT gradient vs. spaCy sim — what's the difference?**
  > These are complementary, not overlapping:
  >
  > | | DoT gradient | spaCy sim |
  > |---|---|---|
  > | **What it measures** | Evidence quality + reasoning chain | Semantic meaning alignment |
  > | **Input** | Generated sentence vs. persona/domain fact pool | Generated sentence vs. source article text |
  > | **Method** | Weighted formula: `0.30×evidence + 0.25×reasoning + 0.20×credibility + 0.25×token_overlap` | spaCy `en_core_web_md` cosine similarity |
  > | **Catches** | Fabricated numbers, wrong org names, weak evidence chains | Paraphrased hallucinations that drift in meaning but share no tokens |
  > | **Threshold** | `TRUTH_GRADIENT_FLAG_THRESHOLD` = 0.35 | `TRUTH_GATE_SPACY_SIM_FLOOR` = 0.10 |
  >
  > DoT asks *"is this claim supported by credible, well-reasoned evidence?"*; spaCy sim asks *"does the generated text still mean the same thing as the source?"* — each catches a different failure mode.
- **Confidence scoring & policy routing** — Each post is scored for grounding, novelty, and repetition; you control what gets scheduled, sent to Ideas, or blocked entirely.
- **Memory & repetition penalty** — The system remembers recent themes and claims, penalizing repeated angles so your feed stays fresh.
- **Explainability & learning reports** — CLI flags let you see exactly which facts grounded each post, trace graph-based support, and generate advisory reports from moderation history.
- **Derivative of Truth (DoT) reporting** — Use `--dot-report` with either `--schedule` or `--curate` to print a detailed truth gradient, evidence, and uncertainty breakdown for every generated post or curated idea.
- **No cloud AI keys required** — All generation is local (Ollama), with persona and learning data stored only on your machine.

**Result:** You get a self-improving, persona-driven content engine that adapts to your taste, avoids repetition, and systematically grows your SSI — with full transparency, control, and explainability.

---

### 🏆 What is the LinkedIn SSI?

The [LinkedIn Social Selling Index](https://www.linkedin.com/sales/ssi) is a 0–100 score LinkedIn updates daily. It measures how effectively you build your personal brand, find the right people, engage with insights, and build relationships — the four pillars LinkedIn's algorithm uses to determine how widely your content and profile are surfaced to others.

A higher SSI directly correlates with more profile views, post reach, and inbound connection requests. LinkedIn's own data shows that professionals with an SSI above 70 get 45% more opportunities than those below 30.

The score breaks down into four components (25 points each):

| Component                             | What LinkedIn measures                                                            |
| ------------------------------------- | --------------------------------------------------------------------------------- |
| **Establish your professional brand** | Completeness of profile, consistency of posting, saves/shares on your content     |
| **Find the right people**             | Profile searches landing on you, connection acceptance rate, right-audience reach |
| **Engage with insights**              | Shares, comments, and reactions on industry content; thought leadership signals   |
| **Build relationships**               | Connection growth, message response rate, relationship depth                      |

### 🤖 Why automate it?

SSI decays if you go quiet — LinkedIn penalises inconsistency. Manually writing 3 posts per week, curating industry articles with original commentary, and maintaining an on-brand voice across hundreds of posts is simply not sustainable alongside a full-time engineering role.

This tool handles the repeatable parts:

- **Consistent cadence** — 3 posts/week scheduled to Buffer at proven engagement times (Tue/Wed/Fri 4 PM EST)
- **On-brand content** — every post is grounded in your real projects, real numbers, and real technical voice via a detailed persona prompt
- **All four SSI pillars** — the content calendar and curator rotate across all four components so no single pillar is neglected
- **Curation pipeline** — fetches today's AI/GovTech news, filters by your niche, and generates commentary that you can either:
  - push to Buffer Ideas for review and manual approval (default), or
  - schedule directly as posts to your Buffer queue (using `--type post`)

**Advanced Reporting CLI Flags:**

- `--dot-report` — Show a Derivative of Truth (truth gradient, evidence, uncertainty) report for every generated post (with `--schedule`) or curated idea (with `--curate`).
- `--avatar-explain` — Show evidence IDs and grounding summary after each generation.
- `--avatar-learn-report` — Print learning report from captured moderation events and exit.
- `--learn` — Extract and persist knowledge from curated articles into `extracted_knowledge.json`. By default this only runs on live (`--curate`) runs. Pass `--dry-run --learn` together to extract knowledge while still previewing posts without pushing to Buffer. When `--learn` is active, the normal 5-post cap is bypassed — every relevant article found across all feeds is processed, maximising knowledge extraction per run (e.g. `--curate --learn --dry-run` may process 60+ articles in one pass).

You control whether curated content is reviewed before publishing or scheduled directly. The tool removes the blank-page problem, but you decide what goes live.

---

## 🚀 Schedule Your Content with Buffer (Partner Link)

Want to automate your LinkedIn growth with the best scheduling tool? [Sign up for Buffer with our partner link](https://join.buffer.com/samjd42) and get started in minutes!

**Why Buffer?**

- Effortlessly schedule posts at optimal times for maximum reach
- Manage multiple channels and queues from one dashboard
- Integrates seamlessly with LinkedIn SSI Booster for hands-off publishing

**Support the project:** Using our [Buffer partner link](https://join.buffer.com/samjd42) helps fund ongoing development and keeps this tool open-source. Try Buffer today and see why top creators and engineers trust it for their content workflow!

---

## 🔍 Learning, Grounding, and Explainability Pipeline

**How the system learns and adapts:**

- **Candidate logging:** Every generated post and curated article candidate is logged, including source, topic, and all relevant metadata. This creates a full audit trail of what the system considered, not just what was published.
- **Reconciliation & learning:** When you publish or reject posts (via Buffer or moderation), the system reconciles what actually went live. It updates acceptance rates (priors) for each source, topic, and SSI component, so future curation floats the best-performing sources and topics to the top.
- **Ranking:** Article and post candidates are ranked using a combination of acceptance priors and BM25 retrieval scores, so the system learns your preferences over time and adapts what it suggests.

**How deterministic grounding and the truth gate work:**

- **Fact retrieval:** For every post or answer, the system retrieves relevant facts from your persona graph (projects, skills, outcomes) using BM25Okapi — a production-grade IR algorithm. This ensures rare, high-signal skills and projects are prioritized.
- **Prompt balance rules:** Prompts require every factual claim to be grounded in either the article or your persona facts. Personal references are capped, and invented stats/dates/companies are forbidden.
- **Truth gate:** After generation, a four-layer deterministic filter removes any sentence with unsupported numbers, dates, company names, or project-tech mismatches unless the claim is found in evidence. The layers are: BM25 evidence scoring → per-sentence Derivative of Truth gradient (4-term formula with token overlap) → spaCy semantic similarity floor for specific-claim sentences → spaCy NER org-name validation. ORG validation includes hardening against common technical false positives (for example `S3`, `AI Q&A`, `Java 21`) and is backed by an expanded evidence set from auto-merged `domain_knowledge_*.json` files. Each removed sentence is logged with a reason code (`weak_evidence_bm25`, `weak_dot_gradient`, `low_semantic_similarity`, `unsupported_org`, etc.) that feeds the confidence scoring pipeline.

---

## 🧮 Derivative of Truth (DoT) Framework - Next Generation Reasoning Layer

```mermaid
flowchart TD
  ClaimQuery(["Claim / Query"]) --> BM25Retriever[BM25 Retriever]
  ClaimQuery --> KnowledgeGraph[Knowledge Graph]
  BM25Retriever -- "Top Candidates" --> EvidencePaths((Evidence Paths))
  KnowledgeGraph -- "Proximity / Support" --> EvidencePaths
  EvidencePaths --> DoT["Derivative of Truth\n(Reasoning Layer)"]
  DoT -- "Truth Gradient, Reasoning, Uncertainty" --> Explainability["Explainability & Reporting"]
  DoT -- "Flag / Score" --> FinalOutput["Final Output\n(Accept / Reject / Flag)"]
  Explainability --> UserDisplay["User"]
  FinalOutput --> UserDisplay
```

**Explanation:**

- BM25 and the Knowledge Graph retrieve and rerank evidence for each claim.
- The Derivative of Truth (DoT) layer analyzes the quality of evidence, the type of reasoning, and uncertainty, **and how well the generated text aligns with that evidence**, producing a truth gradient score and a human-readable explanation.
- The system outputs both a decision (accept/reject/flag) and an explanation, closing the loop with the user.

#### How BM25, the Knowledge Graph, and DoT Work Together

The Derivative of Truth framework is powerful because it combines deterministic evidence retrieval (BM25), explicit knowledge graph reasoning, and a transparent reasoning layer:

- **BM25** is used to find the most relevant evidence for each claim, based on token overlap. This ensures that only facts with strong lexical support (matching numbers, names, technical terms) are considered. BM25’s scores are transparent and auditable.
- **The Knowledge Graph** encodes relationships between your persona, projects, facts, and evidence. It enables the system to compute proximity, support, and reasoning chains—so you can see exactly why a fact supports a claim, and trace the evidence path.
- **Hybrid Scoring** combines BM25’s lexical precision with graph-based proximity/support, giving both high recall (BM25 finds candidates) and high precision (the graph reranks by relevance to your persona/context).
- **The DoT Reasoning Layer** sits on top of retrieval. For each claim, DoT:
  - Annotates evidence by type (primary, secondary, derived, pattern), reasoning (logical, statistical, analogy, pattern), and credibility.
  - Computes **claim-evidence token overlap** — how much the generated text's language actually reflects the evidence it was grounded in.
  - Aggregates evidence quality, reasoning type, credibility, and overlap into a single composite score.
  - Tracks and penalizes uncertainty (weak evidence, long inference chains, conflicts, sparse support).
  - Composes a single, interpretable "truth gradient" score, and explains why a claim is strong or weak.

**In effect, DoT turns your system into not just a retriever, but a reasoner—able to justify, explain, and flag claims based on both the quality of their evidence _and_ how faithfully the LLM output reflects that evidence.**

> ### The Derivative of Truth: A New Mathematical Framework for AI Truthfulness
>
> **The Core Problem:**
> Current AI systems optimize for next token prediction, which can lead to reward hacking—models sound confident about memorized patterns, not about evidence.

> **Breakthrough Insight:**
> Truth is subjective and dynamic. Instead of solving for absolute truth T, we optimize for dT/dt—the derivative of truth, representing movement toward more reliable knowledge.
>
> **Key Mathematical Components:**
>
> - **Truth-Seeking Loss:**
>   L_current = -log P(next_token | context)
>   L_truth = -log P(truth_direction | evidence, reasoning, uncertainty)
> - **Derivative of Truth:**
>   dT/dt = ∂(Evidence Quality)/∂t + ∂(Reasoning Strength)/∂t - ∂(Uncertainty)/∂t
> - **Truth Gradient:**
>   ∇(Evidence × Reasoning × Consistency) - ∇(Uncertainty × Bias)
> - **Truth Score:**
>   T(statement) = Σ [E_i × R_i × C_i × U_i]
>   Where E_i is evidence strength, R_i is reasoning validity, C_i is source credibility, U_i is uncertainty penalty.
> - **Implemented base_gradient formula (with claim-evidence overlap O_i):**
>   With overlap: `0.30×E_i + 0.25×R_i + 0.20×C_i + 0.25×O_i`
>   Without overlap (KG-only paths): `0.40×E_i + 0.35×R_i + 0.25×C_i`
>   O_i ∈ [0,1] is the token overlap between the LLM output and the supporting evidence text, scaled to reward alignment.
>
> **The Key Insight:**
> Don't solve for truth directly—solve for the trajectory toward truth. This makes the model reward-seeking for reliable knowledge, not just confident pattern matching.

The Derivative of Truth framework augments the existing truth gate and confidence scoring pipeline with a new scoring subsystem that explicitly models evidence strength, reasoning validity, and uncertainty. It introduces a truth gradient metric for every generated claim/post, and integrates with the knowledge graph, hybrid retriever, continual learning, and explainability/reporting subsystems.

### 🚩 Why This Approach Is Revolutionary

Most AI content tools rely on black-box vector search or generic LLM outputs, which are hard to audit, explain, or trust. The LinkedIn SSI Booster’s Derivative of Truth framework is different:

- **Deterministic, auditable, and explainable:** BM25 and token matching provide transparent, reproducible evidence scoring, enabling precise truthfulness and uncertainty annotation.
- **Fine-grained control:** You can set exact thresholds for what counts as “supported,” especially for numbers, names, and facts—something vector search can’t reliably do.
- **Actionable feedback:** The system gives clear, actionable explanations for why claims are accepted or rejected, helping users and moderators improve content quality.
- **Bridges IR and AI:** By combining traditional information retrieval (BM25) with modern AI, the system is both robust and trustworthy—unlike most current AI automation tools.
- **Sets a new bar for trustworthy AI:** This approach is rare in today’s content automation landscape and is a strong step toward explainable, compliance-ready AI for real-world workflows.

In short, this framework brings a new level of transparency, reliability, and control to automated content generation—making it ideal for professional, compliance-sensitive, and high-stakes environments.

### 🔄 How Learning, Truth Gate, and Scoring Improve Future Generations

The system’s continual learning and truth gate scoring directly shape the quality of future content:

- **Curation Learning Loop:** Every generated post and curated article is logged with its truth gate score, evidence support, and publication outcome. Acceptance rates (priors) for sources, topics, and SSI components are updated based on what gets published or rejected. Over time, the system floats the best-performing patterns and demotes weak ones.

- **Adaptive Retrieval and Grounding:** The retrieval layer learns which facts, themes, and evidence types are most likely to pass the truth gate. Future generations are more likely to ground claims in high-confidence, well-supported facts, making outputs more credible and relevant.

- **Prompt and Policy Adaptation:** The LLM is guided by prompts that require factual grounding. As the system learns which claims are accepted, it adapts prompt constraints and retrieval strategies to favor those patterns. Confidence scoring and policy routing reinforce high-quality output.

- **Feedback to the LLM:** When a post is rejected by the truth gate, the system suggests the closest matching facts or evidence, helping you or the LLM rephrase or better ground the claim. Over time, the LLM “learns” (via prompt engineering, retrieval adaptation, and user feedback) to avoid unsupported patterns and generate more credible content.

- **Continual Learning:** As new facts and evidence are added (from curated articles, RSS feeds, etc.), the knowledge graph grows, providing richer grounding for future generations. Retrieval and scoring adapt to leverage this expanding evidence base.

**Bottom line:**
The system closes the loop between generation, evidence retrieval, truth gate scoring, and user feedback—so each new generation is smarter, more credible, and better aligned with your SSI goals.

Key benefits:

- **Explicit Truthfulness Scoring:** Every claim/post receives a "truth gradient" score reflecting evidence strength, reasoning validity, credibility, **and how well the LLM output aligns with the evidence it was given** — not just how good the evidence was.
- **Claim-Evidence Alignment:** Each evidence path now carries a token overlap score (weak / moderate / strong) shown in the CLI report, revealing when the LLM's language drifts from its grounding facts.
- **Evidence & Reasoning Annotation:** Each fact/claim is annotated with evidence type, reasoning type, and source credibility for transparency and explainability.
- **Uncertainty Handling:** Tracks and penalizes uncertainty (weak evidence, long chains, conflicts, sparse support), flagging overconfident or unsupported claims.
- **Improved Explainability:** CLI and reports show why claims are accepted/rejected, what evidence supports them, alignment strength per path, and how uncertainty affects scores.
- **Better Content Quality:** Filters out weak claims, prioritizes well-grounded ones, and ensures published content is credible and authoritative.
- **Adaptive Learning:** As more evidence and reasoning paths are accumulated, scoring and explanations improve, making automation smarter over time.
- **Alignment with Best Practices:** Follows trustworthy AI and explainable AI (XAI) principles for robust, future-proof automation.

#### 🛡️ Truth Gate & Confidence Scoring Pipeline

```mermaid
flowchart TD
  Subsystem["Content Generation / Curation"] -->|"Claims, Facts"| TruthGate["Truth Gate & Confidence Scoring"]
  TruthGate -->|"BM25, Graph, Claim Support"| HybridRetriever["Hybrid Retriever & Reranker"]
  HybridRetriever -->|"Candidate Claims"| DerivativeTruth["Derivative of Truth Scoring"]
  DerivativeTruth -->|"Truth Gradient, Evidence Path, Uncertainty"| Explainability["Explainability & Reporting"]
  DerivativeTruth -->|"Penalty/Flag"| Output["Final Output (Post/Claim)"]
  ContinualLearning["Continual Learning"] -->|"New Evidence, Reasoning"| KnowledgeGraph["Knowledge Graph"]
  KnowledgeGraph --> HybridRetriever
  KnowledgeGraph --> DerivativeTruth
```

See [docs/features/derivative-of-truth/](docs/features/derivative-of-truth/) for technical details, schema, and scoring examples.

---

## 🧩 Knowledge Graph Choice: NetworkX Core, Neo4j for Expansion

The core knowledge graph is implemented with NetworkX, an in-memory Python graph library. This choice is intentional:

- **Simplicity & Speed:** NetworkX is fast, pure Python, and ideal for small to medium graphs (well under 100k nodes/edges), which covers all core persona, domain, and learning knowledge for a single avatar.
- **Tight, Local Core:** By keeping the avatar's core knowledge graph tight and local, the system remains fast, debuggable, and easy to extend—no external dependencies or infrastructure required.
- **Scalability Policy:** If the knowledge graph ever needs to scale to millions of nodes/edges (e.g., for mass knowledge injection, multi-avatar, or enterprise use), the system is designed to support Neo4j as a drop-in backend. Neo4j provides persistent, disk-backed storage and a powerful query language (Cypher) for large-scale or multi-user scenarios.
- **Best of Both Worlds:** For most users, NetworkX is more than sufficient. Neo4j is reserved for future expansion, bulk import, or advanced analytics—keeping the core avatar experience lightweight and local-first.

**Current graph size:** The combined domain and learning knowledge graphs are well below 1,000 nodes—orders of magnitude under any practical NetworkX limit.

See the chart below for a summary of trade-offs:

| Feature/Constraint    | NetworkX (Current)                               | Neo4j (Future Option)                         |
| --------------------- | ------------------------------------------------ | --------------------------------------------- |
| Storage               | In-memory (RAM only)                             | On-disk, persistent                           |
| Scale                 | Best for small/medium graphs (<100k nodes/edges) | Scales to millions/billions of nodes/edges    |
| Query Language        | Python API, no query language                    | Cypher query language                         |
| Performance           | Fast for small graphs, slows with size           | Optimized for large, complex queries          |
| Persistence           | No built-in persistence                          | Full persistence, ACID compliance             |
| Integration           | Simple, pure Python                              | Requires running Neo4j server, extra setup    |
| Learning/Dev Overhead | Minimal, easy to use                             | Higher, requires Cypher and DB management     |
| Use Case Fit          | Prototyping, research, local automation          | Production, multi-user, large-scale analytics |
| Cost                  | Free, no infra                                   | Free (Community), but infra/ops required      |

**Bottom line:** The core of the avatar will remain in NetworkX for speed, simplicity, and local-first operation. Neo4j is available for future expansion, mass knowledge injection, or advanced analytics if needed.

---

The system now includes a NetworkX-powered knowledge graph for incremental learning, hybrid BM25+graph retrieval, and persona-aware reranking.

**Integration Philosophy:**

- BM25 (lexical retrieval) remains the primary candidate selector for claims, project details, facts, narrative memory, and learned article summaries.

- The NetworkX knowledge graph is used as a secondary, persona-aware reranker and explainer: it links persona ↔ skills ↔ projects ↔ claims ↔ domain facts.

- Final candidate scoring is a hybrid:

  $$
  ext{final} = 0.7 \times \text{bm25} + 0.2 \times \text{graph proximity} + 0.1 \times \text{claim support}
  $$

### 🧬 Hybrid Retrieval and Scoring Architecture

```mermaid
flowchart TD
    UserInput["User Interactions / Content Curation"] -->|"New Knowledge"| Learning["Avatar Learning Subsystem"]
    Learning -->|"Add/Update"| KnowledgeGraph["Knowledge Graph (networkx)"]
    UserQuery["User Query / Generation Request"] --> BM25["BM25 Lexical Retriever"]
    BM25 -->|"Top Candidates"| GraphRerank["Graph Proximity & Claim Support"]
    KnowledgeGraph -->|"Proximity/Support"| GraphRerank
    GraphRerank -->|"Hybrid Score"| Generation["Post Generation / Explanation"]
    Generation -->|"Citations/Explanations"| UserInput
```

## 🔄 Continual Learning (NLP-Extracted Knowledge)

> **Inspiration:** This subsystem is inspired by the work of Dr. Ben Goertzel (SingularityNET) and the OpenCog team on AtomSpace and MeTTa, bringing incremental, explainable cognition to practical automation. [Making AI learning AGI-capable: continual learning, transfer learning, lifelong learning - YouTube](https://youtu.be/n10J1OjmgLM)

The avatar supports fully automatic, incremental continual learning from new content streams (e.g., RSS feeds, curated articles) via an NLP-extracted knowledge graph. As new content is processed, spaCy is used to extract, structure, and normalize new facts, terms, and relationships. The system deduplicates and validates these facts, merging them into the knowledge graph alongside persona and domain knowledge.

- Extracted knowledge is stored in `data/avatar/extracted_knowledge.json` and is automatically merged into the knowledge graph and BM25 candidate pool.
- These new facts are used in both retrieval (BM25 and graph) and grounding, so your system's evidence base grows over time with no manual steps.
- Deduplication and normalization ensure that only novel, high-quality knowledge is added, and all learning is ongoing as new content is ingested.
- Modular, file-based design: easy to extend, debug, and test.
- **Console mode** (`--console`) includes extracted knowledge in the grounding pool alongside persona and domain facts, so the persona can answer questions using anything learned from `--learn` runs. Use `/reload` inside a running console session to re-read `extracted_knowledge.json` (and all other avatar files) without restarting — useful when running a `--learn` job concurrently in a second terminal.
- **Inline truth score** — after every AI-generated reply, console mode prints a minimal 1-line truthfulness indicator showing the aggregate DoT gradient and average spaCy semantic similarity for that reply. The indicator is dim and non-distracting:
  ```
  Sam> [reply text]
    ● DoT 0.82  spaCy sim 0.45
  ```
  The symbol colour reflects the DoT score: `●` green (≥ 0.75 — well-grounded), `◑` yellow (≥ 0.45 — moderate), `○` red (< 0.45 — weakly supported). Only AI-generated replies receive the indicator; deterministic grounded replies do not.

**Noise filtering pipeline** — before a sentence is stored, a multi-layer quality filter rejects low-signal content that would pollute the knowledge base:

| Filter                         | What it catches                                                                                                              |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| First-person narration         | Author asides ("As I write this…", "I sat down with…")                                                                       |
| Truncated RSS fragments        | Sentences ending in "… Read more"                                                                                            |
| Newsletter/podcast preambles   | Openers like "Welcome to…", "For this episode…", "In last week's…"                                                           |
| Navigation / contributor blobs | Sentences ≥12 words where >45% of tokens start with uppercase (HuggingFace menus, author lists, etc.)                        |
| Zero-signal sentences          | Sentences with no digit, no 2+-char acronym, and no consecutive title-case words (named entity / product name) — pure filler |

These filters run before spaCy NLP and deduplication, so only genuinely informative domain sentences reach the knowledge graph.

See [docs/features/continual-learning/idea.md](docs/features/continual-learning/idea.md) for technical details and schema.

- **Adaptive Curation Ranking:** The system tracks every generated and published post, learning which sources, topics, and themes you actually approve. Over time, it floats the best-performing sources and topics to the top using Beta-smoothed acceptance priors and theme-based ranking.
- **Semantic Repetition Detection:** Uses spaCy-powered semantic similarity to detect and penalize repeated or paraphrased content, keeping your feed fresh and non-redundant.
- **User Feedback Integration:** You can upvote, downvote, or override candidate posts, and this feedback is incorporated into future ranking and selection.
- **Fact Suggestion for Truth Gate:** When a sentence is dropped for lacking evidence, the system suggests the closest matching facts from your persona graph or extracted knowledge to help you rephrase or ground your claims.
- **Memory & Narrative Learning:** The system maintains a local memory of recent themes and claims, using this to diversify future outputs and avoid repetition.
- **Explainability & Learning Reports:** CLI flags like `--avatar-explain` and `--avatar-learn-report` let you see exactly what the system has learned, which facts grounded each post (including those from continual learning), and which sources or topics are most effective.

**Bottom line:** The more you use it, the smarter and more tailored your content pipeline becomes — adapting to your preferences, audience, and SSI goals. All new knowledge is immediately available for both retrieval and grounding, powering the hybrid pipeline.

---

Core capabilities include:

- Persona-grounded generation using structured profile facts from `data/avatar/persona_graph.json`.
- Hybrid RAG orchestration with BM25 retrieval, prompt constraints, and deterministic post-processing.
- Curation learning that updates acceptance priors from what actually gets published.
- Explainability features such as `--avatar-explain` and `--avatar-learn-report`.
- Local-first operation using Ollama, with persona and learning data stored on your own machine.

The writing rules draw on **Neuro-Linguistic Programming (NLP)** principles — specifically pattern interrupts (scroll-stopping first lines), presupposition (assuming the reader already cares), and anchoring (pairing your name with specific technical outcomes so readers associate _you_ with the domain). The forbidden-phrases list functions as a negative anchor removal layer: stripping hollow corporate phrases forces the model toward concrete, specific language that builds credibility. For the theoretical underpinning, see [_Monsters and Magical Sticks, There's no Such Thing as Hypnosis?_ by Steven Heller & Terry Steele](https://www.amazon.com/Monsters-Magical-Sticks-Theres-Hypnosis-ebook/dp/B007WMOMXU) — an accessible introduction to how language patterns shape perception.

Notes: https://richardstep.com/downloads/tools/Notes--Monsters-and-Magic-Sticks.pdf

NLP primer in this repo:

- [docs/nlp-basics.md](docs/nlp-basics.md)

The primer covers core NLP concepts, practical communication techniques, technical writing examples, and ethical usage guidelines.

## 🗺️ Docs map

- [Setup guide](docs/setup.md) — environment, dependencies, persona graph, and calendar setup.
- [Architecture guide](docs/architecture.md) — learning pipeline, grounding flow, truth gate, and curation ranking.
- [Persona and Avatar Intelligence](docs/persona-and-avatar.md) — persona graph, system prompt, memory, confidence, explainability, and continual learning.
- [Continual Learning (NLP-extracted knowledge)](docs/features/continual-learning/idea.md) — how the avatar accumulates new knowledge from external content.
- [Domain Knowledge Graph](docs/domain-knowledge.md) — domain-level expertise that isn't tied to specific projects.
- [Usage guide](docs/usage-schedule-curate-console.md) — scheduling, curation, console mode, channels, and CLI examples.
- [SSI strategy](docs/ssi-and-strategy.md) — SSI model, content mapping, scheduler behavior, and reporting.
- [AI backend](docs/ai-backend-and-models.md) — Ollama setup and model recommendations.
- [Testing and development](docs/testing-and-dev.md) — pytest coverage and project structure. All tests pass (337/337)
- [Selection learning](docs/selection-learning.md) — candidate logging, reconciliation, and acceptance priors.

## 🐳 Docker Compose (Recommended)

Run the full stack — Ollama LLM server + SSI Booster app — with a single command, no local Python environment required.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Docker Compose v2)
- A filled-in `.env` file (see below)

### 1. Configure your environment

```bash
cp .env.example .env
# Edit .env — set BUFFER_API_KEY, OLLAMA_MODEL, persona vars, etc.
# Leave OLLAMA_BASE_URL as http://localhost:11434 — docker-compose overrides it automatically.
```

Also copy the required data files (these are bind-mounted into the container at runtime):

```bash
cp data/avatar/persona_graph.example.json   data/avatar/persona_graph.json
cp data/avatar/domain_knowledge.example.json data/avatar/domain_knowledge.json
cp data/avatar/narrative_memory.example.json data/avatar/narrative_memory.json
cp content_calendar.example.py               content_calendar.py

# Optional extra packs: auto-discovered and merged when named domain_knowledge_*.json
cp data/avatar/domain_knowledge_java.json    data/avatar/domain_knowledge_java.json
cp data/avatar/domain_knowledge_python.json  data/avatar/domain_knowledge_python.json
```

Edit `data/avatar/persona_graph.json` with your real career facts before running.

### 2. Pull models and start Ollama

```bash
# Start Ollama in the background and pull the configured model (one-time)
docker compose up ollama ollama-init
```

`ollama-init` exits automatically once the model pull completes. Leave `ollama` running.

### 3. Build the app image (first time only)

```bash
docker compose build app
```

### 4. Run any command

```bash
# Dry-run post schedule (no Buffer calls)
docker compose run --rm app python main.py --schedule --week 1 --dry-run

# Curate AI news → Buffer Ideas (live)
docker compose run --rm app python main.py --curate

# Interactive persona console (TTY required)
docker compose run --rm -it app python main.py --console

# Record today's SSI scores
docker compose run --rm app python main.py --save-ssi 10.49 9.69 11.0 12.15
```

### Docker notes

| Topic                                  | Detail                                                                                                                                                                                      |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `OLLAMA_BASE_URL`                      | Overridden to `http://ollama:11434` in `docker-compose.yml` — do not change it in `.env` for Docker use                                                                                     |
| Ollama model storage                   | Persisted in the `ollama_data` Docker volume — survives container restarts                                                                                                                  |
| Runtime data (`data/`, `yt-vid-data/`) | Bind-mounted from the host — changes are visible immediately                                                                                                                                |
| GPU (NVIDIA)                           | Uncomment the `deploy:` block in `docker-compose.yml` after installing the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) |
| Rebuilding after code changes          | `docker compose build app`                                                                                                                                                                  |

---

## ⚡ Quickstart (local Python)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_md
cp .env.example .env
cp data/avatar/persona_graph.example.json data/avatar/persona_graph.json
cp data/avatar/domain_knowledge.example.json data/avatar/domain_knowledge.json
cp data/avatar/narrative_memory.example.json data/avatar/narrative_memory.json

# Optional extra packs: auto-discovered and merged when named domain_knowledge_*.json
cp data/avatar/domain_knowledge_java.json data/avatar/domain_knowledge_java.json
cp data/avatar/domain_knowledge_python.json data/avatar/domain_knowledge_python.json
cp content_calendar.example.py content_calendar.py
python main.py --schedule --week 1 --dry-run
```

### ⚙️ Environment Variables

Add these to your `.env` file:

```
BUFFER_API_KEY=...
OLLAMA_MODEL=gemma4:26b
OLLAMA_MODEL_FALLBACK=qwen2.5:14b  # fallback for ALL generation calls when primary model fails
OLLAMA_BASE_URL=http://localhost:11434
```

- `OLLAMA_MODEL` — Main Ollama model for all generations (e.g. `gemma4:26b`).
- `OLLAMA_MODEL_FALLBACK` — Fallback model auto-retried once on empty output or error for all generation calls (default: `qwen2.5:14b`).
- `OLLAMA_BASE_URL` — Ollama server URL (default: `http://localhost:11434`).
- `EXTRACTED_CONTEXT_LIMIT` — Max extracted facts injected into curation prompts (default: `10`).
- `EXTRACTED_EVIDENCE_COUNT` — Max extracted facts considered as evidence per article during grounding/DoT (default: `2`).
- `TOPIC_SIGNAL_WINDOW` — Number of most-recent extracted facts used to build adaptive topic signal (default: `50`).

The setup flow requires a configured `.env`, a filled-in persona graph, a narrative memory file, and a personalized content calendar before useful scheduling or curation runs begin.

## 📄 License

[MIT License](LICENSE) — see LICENSE for details.
