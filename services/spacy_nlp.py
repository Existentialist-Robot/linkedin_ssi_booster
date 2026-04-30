"""
spaCy NLP Engine — theme extraction, semantic similarity, and sentiment analysis.

This module provides advanced NLP capabilities for the LinkedIn SSI Booster:
- Theme/claim extraction using NER and noun chunking
- Semantic similarity using spaCy word vectors
- Sentiment/tone analysis for content moderation
- Fact suggestion for truth gate
- Contextual article summarization

The design ensures:
- Lazy model loading (on first use)
- Graceful fallbacks if spaCy unavailable
- Mockable interface for testing
- Minimal performance overhead (<1s per post)
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Global cache for the spaCy model to avoid reloading
_SPACY_NLP_MODEL: Any = None
_SPACY_AVAILABLE: bool | None = None


def _is_spacy_available() -> bool:
    """Check if spaCy is available and can be imported."""
    global _SPACY_AVAILABLE
    if _SPACY_AVAILABLE is not None:
        return _SPACY_AVAILABLE
    
    try:
        import spacy
        _SPACY_AVAILABLE = True
        return True
    except ImportError:
        logger.warning("spacy_nlp: spaCy not installed — NLP features disabled")
        _SPACY_AVAILABLE = False
        return False


def _load_model(model_name: str = "en_core_web_sm") -> Any:
    """Load spaCy model, caching it globally. Returns None if unavailable."""
    global _SPACY_NLP_MODEL
    
    if _SPACY_NLP_MODEL is not None:
        return _SPACY_NLP_MODEL
    
    if not _is_spacy_available():
        return None
    
    try:
        import spacy
        _SPACY_NLP_MODEL = spacy.load(model_name)
        logger.info("spacy_nlp: loaded model '%s'", model_name)
        return _SPACY_NLP_MODEL
    except OSError:
        logger.warning(
            "spacy_nlp: model '%s' not found — run 'python -m spacy download %s'",
            model_name,
            model_name,
        )
        return None
    except Exception as exc:
        logger.warning("spacy_nlp: failed to load model '%s': %s", model_name, exc)
        return None


class SpacyNLP:
    """
    spaCy NLP Engine for theme extraction, similarity, and sentiment analysis.
    
    All methods gracefully degrade if spaCy is unavailable, returning
    fallback values (empty lists, 0.0 similarity, neutral sentiment).
    """
    
    def __init__(self, model_name: str = "en_core_web_sm"):
        """Initialize the NLP engine with the specified spaCy model.
        
        Args:
            model_name: spaCy model to use (default: en_core_web_sm)
        """
        self.model_name = model_name
        self._nlp = None
    
    def _ensure_model(self) -> Any:
        """Lazy load the spaCy model on first use."""
        if self._nlp is None:
            self._nlp = _load_model(self.model_name)
        return self._nlp
    
    def extract_themes(self, text: str) -> list[str]:
        """Extract themes/topics from text using NER and noun chunks.
        
        Combines:
        - Named entities (PERSON, ORG, GPE, PRODUCT, etc.)
        - Noun chunks (meaningful noun phrases)
        
        Returns a deduplicated list of themes, normalized to lowercase.
        Falls back to empty list if spaCy unavailable.
        
        Args:
            text: Input text to analyze
            
        Returns:
            List of extracted theme strings
        """
        nlp = self._ensure_model()
        if nlp is None:
            logger.debug("spacy_nlp: extract_themes fallback (spaCy unavailable)")
            return []
        
        try:
            doc = nlp(text)
            themes: set[str] = set()
            
            # Extract named entities
            for ent in doc.ents:
                # Focus on meaningful entity types
                if ent.label_ in {
                    "PERSON", "ORG", "GPE", "PRODUCT", "EVENT",
                    "WORK_OF_ART", "LAW", "LANGUAGE", "NORP"
                }:
                    themes.add(ent.text.lower().strip())
            
            # Extract noun chunks (filter out very short or common ones)
            for chunk in doc.noun_chunks:
                chunk_text = chunk.text.lower().strip()
                # Only keep chunks with 2+ words or 5+ chars
                if len(chunk_text.split()) >= 2 or len(chunk_text) >= 5:
                    themes.add(chunk_text)
            
            return sorted(themes)
        
        except Exception as exc:
            logger.warning("spacy_nlp: extract_themes failed: %s", exc)
            return []
    
    def compute_similarity(self, text1: str, text2: str) -> float:
        """Compute semantic similarity between two texts using spaCy vectors.
        
        Returns cosine similarity (0.0–1.0) based on document vectors.
        Falls back to 0.0 if spaCy unavailable or vectors not present.
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            Similarity score (0.0 = dissimilar, 1.0 = identical)
        """
        nlp = self._ensure_model()
        if nlp is None:
            logger.debug("spacy_nlp: compute_similarity fallback (spaCy unavailable)")
            return 0.0
        
        try:
            doc1 = nlp(text1)
            doc2 = nlp(text2)
            
            # Check if vectors are available
            if not doc1.has_vector or not doc2.has_vector:
                logger.debug("spacy_nlp: compute_similarity fallback (no vectors)")
                return 0.0
            
            similarity = doc1.similarity(doc2)
            # Clamp to [0.0, 1.0] range
            return max(0.0, min(1.0, float(similarity)))
        
        except Exception as exc:
            logger.warning("spacy_nlp: compute_similarity failed: %s", exc)
            return 0.0
    
    def analyze_sentiment(self, text: str) -> dict[str, Any]:
        """Analyze sentiment and tone of text.
        
        Uses a simple heuristic based on:
        - Positive/negative keyword counting
        - Sentence structure (exclamation marks, questions)
        - Word choice patterns
        
        Note: en_core_web_sm doesn't include sentiment analysis,
        so this is a basic rule-based approach. For production,
        consider using a sentiment-specific model or API.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Dict with keys:
            - polarity: "positive", "negative", or "neutral"
            - confidence: 0.0–1.0 confidence score
            - tone: list of detected tones (e.g., ["professional", "enthusiastic"])
        """
        nlp = self._ensure_model()
        if nlp is None:
            logger.debug("spacy_nlp: analyze_sentiment fallback (spaCy unavailable)")
            return {"polarity": "neutral", "confidence": 0.0, "tone": []}
        
        try:
            doc = nlp(text)
            
            # Simple sentiment heuristic using keyword lists
            positive_words = {
                "great", "excellent", "amazing", "wonderful", "fantastic",
                "love", "best", "perfect", "awesome", "brilliant",
                "excited", "happy", "delighted", "thrilled", "proud"
            }
            negative_words = {
                "bad", "terrible", "awful", "horrible", "worst",
                "hate", "disappointed", "frustrated", "angry", "sad",
                "poor", "weak", "failed", "broken", "wrong"
            }
            
            # Use list(doc) to support both real spaCy docs and mocks
            tokens = list(doc)
            pos_count = sum(1 for token in tokens if token.text.lower() in positive_words)
            neg_count = sum(1 for token in tokens if token.text.lower() in negative_words)
            
            # Determine polarity
            if pos_count > neg_count:
                polarity = "positive"
                confidence = min(0.9, 0.5 + (pos_count - neg_count) * 0.1)
            elif neg_count > pos_count:
                polarity = "negative"
                confidence = min(0.9, 0.5 + (neg_count - pos_count) * 0.1)
            else:
                polarity = "neutral"
                confidence = 0.6
            
            # Detect tone characteristics
            tone: list[str] = []
            
            # Check for professional tone (longer sentences, formal words)
            avg_sent_len = sum(len(list(sent)) for sent in doc.sents) / max(1, len(list(doc.sents)))
            if avg_sent_len > 15:
                tone.append("professional")
            
            # Check for enthusiastic tone (exclamation marks)
            if "!" in text:
                tone.append("enthusiastic")
            
            # Check for questioning tone
            if "?" in text:
                tone.append("inquisitive")
            
            # Default to neutral if no tone detected
            if not tone:
                tone.append("neutral")
            
            return {
                "polarity": polarity,
                "confidence": confidence,
                "tone": tone,
            }
        
        except Exception as exc:
            logger.warning("spacy_nlp: analyze_sentiment failed: %s", exc)
            return {"polarity": "neutral", "confidence": 0.0, "tone": []}
    
    def suggest_matching_facts(
        self,
        dropped_sentence: str,
        available_facts: list[str],
        top_n: int = 3,
    ) -> list[dict[str, Any]]:
        """Suggest the closest matching facts for a dropped sentence.
        
        When the truth gate drops a sentence, this helps identify which facts
        from the persona graph might support it, or suggests how to rephrase.
        
        Args:
            dropped_sentence: The sentence that was dropped by truth gate
            available_facts: List of fact strings from persona graph
            top_n: Number of top suggestions to return
            
        Returns:
            List of dicts with 'fact', 'similarity', 'suggestion' keys
        """
        nlp = self._ensure_model()
        if nlp is None or not available_facts:
            logger.debug("spacy_nlp: suggest_matching_facts fallback (spaCy unavailable or no facts)")
            return []
        
        try:
            sent_doc = nlp(dropped_sentence)
            if not sent_doc.has_vector:
                logger.debug("spacy_nlp: suggest_matching_facts fallback (no vectors)")
                return []
            
            suggestions: list[tuple[float, str]] = []
            
            for fact in available_facts:
                fact_doc = nlp(fact)
                if not fact_doc.has_vector:
                    continue
                
                similarity = sent_doc.similarity(fact_doc)
                suggestions.append((similarity, fact))
            
            # Sort by similarity (highest first) and take top N
            suggestions.sort(key=lambda x: x[0], reverse=True)
            top_suggestions = suggestions[:top_n]
            
            # Format results with suggestions
            results: list[dict[str, Any]] = []
            for sim, fact in top_suggestions:
                suggestion_text = self._generate_rephrase_suggestion(
                    dropped_sentence, fact, sim
                )
                results.append({
                    "fact": fact,
                    "similarity": round(sim, 3),
                    "suggestion": suggestion_text,
                })
            
            return results
        
        except Exception as exc:
            logger.warning("spacy_nlp: suggest_matching_facts failed: %s", exc)
            return []
    
    def _generate_rephrase_suggestion(
        self,
        sentence: str,
        fact: str,
        similarity: float,
    ) -> str:
        """Generate a rephrase suggestion based on similarity score."""
        if similarity > 0.75:
            return f"High match — consider incorporating key terms from this fact"
        elif similarity > 0.5:
            return f"Moderate match — rephrase to align more closely with this evidence"
        else:
            return f"Low match — this fact may not support the claim; consider different evidence"
    
    def summarize_article(
        self,
        article_text: str,
        max_sentences: int = 3,
        focus_entities: bool = True,
    ) -> str:
        """Generate a concise, context-aware summary of an article.
        
        Uses spaCy's NER and dependency parsing to identify and extract
        the most important sentences from an article.
        
        Args:
            article_text: The full article text
            max_sentences: Maximum sentences in the summary
            focus_entities: Prioritize sentences with named entities
            
        Returns:
            Concise summary string
        """
        nlp = self._ensure_model()
        if nlp is None:
            logger.debug("spacy_nlp: summarize_article fallback (spaCy unavailable)")
            # Fallback: return first N sentences
            sentences = article_text.split(". ")[:max_sentences]
            return ". ".join(sentences) + "."
        
        try:
            doc = nlp(article_text)
            
            # Score each sentence based on importance signals
            sentence_scores: list[tuple[float, Any]] = []
            
            for sent in doc.sents:
                score = 0.0
                
                # Signal 1: Presence of named entities
                if focus_entities:
                    entity_count = len([ent for ent in sent.ents])
                    score += entity_count * 2.0
                
                # Signal 2: Sentence position (earlier sentences often more important)
                position_score = 1.0 / (1.0 + sentence_scores.__len__())
                score += position_score
                
                # Signal 3: Sentence length (prefer moderate-length sentences)
                length = len(list(sent))
                if 10 <= length <= 25:
                    score += 1.0
                elif length > 5:
                    score += 0.5
                
                # Signal 4: Presence of key linguistic markers
                text_lower = sent.text.lower()
                if any(marker in text_lower for marker in [
                    "new", "announce", "launch", "release", "breakthrough",
                    "significant", "important", "key", "major"
                ]):
                    score += 1.5
                
                sentence_scores.append((score, sent))
            
            # Sort by score and take top N
            sentence_scores.sort(key=lambda x: x[0], reverse=True)
            top_sentences = sentence_scores[:max_sentences]
            
            # Re-order by original position for coherent summary
            top_sentences.sort(key=lambda x: x[1].start)
            
            summary = " ".join(sent.text.strip() for _, sent in top_sentences)
            return summary
        
        except Exception as exc:
            logger.warning("spacy_nlp: summarize_article failed: %s", exc)
            # Fallback: return first N sentences
            sentences = article_text.split(". ")[:max_sentences]
            return ". ".join(sentences) + "."


# Singleton instance for convenience
_default_instance: SpacyNLP | None = None


def get_spacy_nlp() -> SpacyNLP:
    """Return the default singleton SpacyNLP instance.

    The model is selected via the ``SPACY_MODEL`` env var
    (default: ``en_core_web_md``).  Use ``en_core_web_sm`` for a smaller
    footprint when word vectors are not required.
    """
    global _default_instance
    if _default_instance is None:
        model_name = os.getenv("SPACY_MODEL", "en_core_web_md")
        _default_instance = SpacyNLP(model_name=model_name)
    return _default_instance
