# Feature Idea: spaCy NLP Enhancement

## Overview

Integrate spaCy (or a similar advanced NLP library) to provide richer, more accurate content intelligence for the LinkedIn SSI Booster. This enhancement will enable deeper theme/claim extraction, semantic similarity, and advanced content analysis, improving both the learning system and user experience.

## Problem Statement (Project Context)

The current system uses basic tokenization and pattern matching for theme/claim extraction, repetition penalty, and content analysis. This approach:

- Misses nuanced or paraphrased repetitions
- Extracts noisy or overly broad themes
- Lacks semantic understanding for content moderation, reporting, and personalization

## Proposed Solution

Integrate spaCy to:

- Extract themes/claims using named entity recognition, noun chunking, and dependency parsing
- Compute semantic similarity between posts using vector embeddings
- Analyze sentiment, tone, passive voice, and jargon
- Detect entities, topics, and writing style for personalized prompt generation

## Expected Benefits (Project User Impact)

- Higher-quality narrative memory (less noise, more signal)
- Smarter repetition penalty (detects paraphrased repeats, not just exact matches)
- Enhanced moderation and reporting (detect sentiment, tone, and style)
- Ability to suggest new topics based on gaps in recent content
- More personalized and relevant post generation

## Technical Considerations (Project Integration)

- Add spaCy to requirements.txt and manage model downloads (e.g., en_core_web_sm)
- Update theme/claim extraction logic in services/selection_learning.py and related modules
- Use spaCy vectors for semantic similarity in repetition penalty and candidate matching
- Add content analysis hooks for moderation and reporting
- Ensure dry-run and testability (mock spaCy in tests)

## Project System Integration

- Narrative memory: Replace or augment current theme/claim extraction with spaCy-based methods
- Repetition penalty: Use semantic similarity to catch paraphrased or subtle repeats
- Content curation: Analyze sentiment, tone, and style for moderation and reporting
- Prompt generation: Personalize based on detected entities/topics

## Initial Scope

- Integrate spaCy and required models
- Refactor theme/claim extraction to use spaCy
- Add semantic similarity for repetition penalty
- Add basic sentiment/tone analysis for reporting
- Unit tests for new NLP logic

## Success Criteria

- spaCy-based extraction produces more meaningful themes/claims (qualitative review)
- Repetition penalty catches paraphrased repeats in test cases
- Sentiment/tone analysis available in candidate logs or reports
- No regression in performance or dry-run safety
- All new code is covered by unit tests
