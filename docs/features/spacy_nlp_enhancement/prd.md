# Product Requirements Document: spaCy NLP Enhancement

## Executive Summary

This feature integrates spaCy, a state-of-the-art NLP library, into the LinkedIn SSI Booster to provide richer, more accurate content intelligence. The enhancement will enable deeper theme/claim extraction, semantic similarity, and advanced content analysis, improving both the learning system and user experience. It addresses current limitations in theme extraction, repetition detection, and content analysis, supporting smarter automation and higher-quality outputs.

## Project Context

- **Domain:** Automated LinkedIn content generation and scheduling to maximize Social Selling Index (SSI)
- **Current State:** Uses basic tokenization and pattern matching for theme/claim extraction and repetition penalty
- **Pain Points:**
  - Misses nuanced or paraphrased repetitions
  - Extracts noisy or overly broad themes
  - Lacks semantic understanding for moderation, reporting, and personalization
- **Tech Stack:** Python 3.11+, spaCy, Anthropic Claude, Buffer API, APScheduler, feedparser
- **Quality Standards:** Type-annotated, idiomatic Python; all new code covered by unit tests; dry-run/testable; logging via `logging.getLogger(__name__)`

## User Stories

1. **As a content creator**, I want the system to extract more meaningful themes and claims from my posts, so that my narrative memory is less noisy and more actionable.
2. **As a moderator**, I want the system to detect paraphrased repetitions, so that repeated ideas are penalized even if reworded.
3. **As a user**, I want sentiment and tone analysis in candidate logs/reports, so I can better understand and control my content's impact.
4. **As a developer**, I want spaCy integration to be testable and mockable, so that CI and dry-run modes remain robust.

## Functional Requirements

- Integrate spaCy and required models (e.g., en_core_web_sm)
- Refactor theme/claim extraction logic in `services/selection_learning.py` to use spaCy NER, noun chunking, and dependency parsing
- Compute semantic similarity between posts using spaCy vectors
- Add sentiment, tone, passive voice, and jargon analysis for moderation/reporting
- Detect entities, topics, and writing style for prompt personalization
- Ensure all new NLP logic is covered by unit tests and supports dry-run

## Non-Functional Requirements

- **Performance:** NLP analysis must not add more than 1s per post in typical runs
- **Security:** No external API calls for NLP; all processing is local
- **Usability:** No additional user configuration required; works out-of-the-box after install
- **Reliability:** spaCy integration must not break existing scheduling or post generation
- **Maintainability:** All new code is idiomatic, type-annotated, and tested
- **Compatibility:** Python 3.11+, spaCy >=3.x, works with existing Buffer/Claude integrations

## Project System Integration

- **Narrative memory:** Replace/augment current theme/claim extraction with spaCy-based methods
- **Repetition penalty:** Use semantic similarity to catch paraphrased or subtle repeats
- **Content curation:** Analyze sentiment, tone, and style for moderation and reporting
- **Prompt generation:** Personalize based on detected entities/topics
- **Testing:** Mock spaCy in unit tests; ensure dry-run mode does not require model downloads

## Dependencies

- spaCy (add to requirements.txt)
- spaCy model (e.g., en_core_web_sm, managed via install script or on first run)
- Update to `services/selection_learning.py` and related modules
- Unit tests in `tests/test_selection_learning.py`

## Success Metrics

- spaCy-based extraction produces more meaningful themes/claims (qualitative review)
- Repetition penalty catches paraphrased repeats in test cases
- Sentiment/tone analysis available in candidate logs or reports
- No regression in performance or dry-run safety
- 100% unit test coverage for new NLP logic

## Timeline & Milestones

- Week 1: Integrate spaCy, refactor extraction logic, add semantic similarity
- Week 2: Add sentiment/tone analysis, reporting hooks, and unit tests
- Week 3: Qualitative review, performance validation, documentation update
- Week 4: Final QA, merge, and release
