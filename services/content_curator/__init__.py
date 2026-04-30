"""
services.content_curator — public API.

All external callers continue to use:
    from services.content_curator import ContentCurator, fetch_relevant_articles
"""

from services.content_curator.curator import ContentCurator
from services.content_curator._rss_fetcher import fetch_relevant_articles
from services.content_curator._config import (
    RSS_FEEDS,
    KEYWORDS,
    CURATOR_MAX_PER_FEED,
    IDEAS_CACHE_PATH,
    _SSI_WEIGHTS,
    _SSI_TOPIC_HINTS,
)
from services.content_curator._text_utils import (
    truncate_at_sentence,
    append_url_and_hashtags,
    extract_hashtags,
)
from services.content_curator._evidence_paths import (
    fact_to_evidence_path,
    article_to_evidence_path,
    extracted_fact_to_evidence_path,
)
from services.content_curator._ssi_picker import build_topic_signal, pick_ssi_component
from services.content_curator._grounding import (
    load_curation_grounding_keywords,
    load_curation_grounding_tag_expansions,
)

__all__ = [
    "ContentCurator",
    "fetch_relevant_articles",
    # config
    "RSS_FEEDS",
    "KEYWORDS",
    "CURATOR_MAX_PER_FEED",
    "IDEAS_CACHE_PATH",
    # text utils
    "truncate_at_sentence",
    "append_url_and_hashtags",
    "extract_hashtags",
    # evidence paths
    "fact_to_evidence_path",
    "article_to_evidence_path",
    "extracted_fact_to_evidence_path",
    # ssi picker
    "build_topic_signal",
    "pick_ssi_component",
    # grounding
    "load_curation_grounding_keywords",
    "load_curation_grounding_tag_expansions",
]
