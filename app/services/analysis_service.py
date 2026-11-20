"""Analysis Service Orchestrator for SitePulse AI.

Coordinates URL validation, website extraction, competitor research,
LLM analysis, response construction, and TTL caching.
"""

import datetime
import logging
import time
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

from app.config import settings
from app.schemas import (
    AnalysisMetadata,
    LinkAnalysisResponse,
)
from app.services.competitor_service import CompetitorService
from app.services.llm_service import LLMService
from app.services.website_extractor import WebsiteExtractor
from app.utils.validators import validate_url_security

logger = logging.getLogger(__name__)


class TTLCache:
    """Simple in-memory thread-safe TTL cache for analyzed website responses."""

    def __init__(self, ttl_seconds: int = 3600):
        self.ttl = ttl_seconds
        self._store: Dict[str, Tuple[float, LinkAnalysisResponse]] = {}

    def get(self, key: str) -> Optional[LinkAnalysisResponse]:
        item = self._store.get(key)
        if not item:
            return None
        timestamp, response = item
        if time.time() - timestamp > self.ttl:
            del self._store[key]
            return None
        # Return a copy marked as cached
        cached_resp = response.model_copy(deep=True)
        cached_resp.metadata.cached = True
        return cached_resp

    def set(self, key: str, value: LinkAnalysisResponse) -> None:
        self._store[key] = (time.time(), value)

    def clear(self) -> None:
        self._store.clear()


class AnalysisService:
    """Master orchestrator for the SitePulse AI website intelligence pipeline."""

    def __init__(self):
        self.extractor = WebsiteExtractor()
        self.competitor_service = CompetitorService()
        self.llm_service = LLMService()
        self.cache = TTLCache(ttl_seconds=settings.CACHE_TTL_SECONDS)

    async def analyze_url(self, raw_url: str) -> LinkAnalysisResponse:
        """
        Executes the full intelligence pipeline:
        1. Validate URL & SSRF checks
        2. Check TTL cache
        3. Extract website HTML & calculate technical SEO signals
        4. Discover competitor context (verified external or labeled fallback)
        5. Generate Gemini business intelligence across 5 modules
        6. Construct and validate LinkAnalysisResponse
        7. Cache and return
        """
        # 1. URL validation & normalization
        validated_url = validate_url_security(raw_url)
        canonical_key = validated_url.rstrip("/").lower()

        # 2. Check TTL cache
        cached_result = self.cache.get(canonical_key)
        if cached_result:
            logger.info(f"Serving analysis from TTL cache for '{validated_url}'")
            return cached_result

        # 3. Extract website data
        logger.info(f"Extracting website content for '{validated_url}'")
        extracted_data, technical_health = await self.extractor.extract(validated_url)

        # 4. Search external competitors if search provider configured
        domain = urlparse(extracted_data.final_url).netloc
        external_competitors = await self.competitor_service.search_external_competitors(
            brand_name=extracted_data.business_name or domain,
            category=extracted_data.title or "Commercial Website",
            domain=domain,
        )

        # 5. Invoke LLM for the 5 intelligence modules
        logger.info(f"Invoking Gemini model '{settings.GEMINI_MODEL}' for '{validated_url}'")
        brand_info, analysis_container, metadata_stats = await self.llm_service.generate_analysis(
            extracted=extracted_data,
            technical_health=technical_health,
            external_competitors=external_competitors,
        )

        # 6. Assemble complete response
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        metadata = AnalysisMetadata(
            analyzed_at=now_iso,
            pages_analyzed=extracted_data.pages_crawled,
            ai_model=settings.GEMINI_MODEL,
            analysis_type="AI-powered website analysis",
            cached=False,
            estimated_tokens=metadata_stats.get("estimated_tokens"),
            estimated_cost_usd=metadata_stats.get("estimated_cost_usd"),
            execution_time_seconds=metadata_stats.get("execution_time_seconds"),
        )

        response = LinkAnalysisResponse(
            success=True,
            website=extracted_data.final_url,
            brand=brand_info,
            analysis=analysis_container,
            metadata=metadata,
        )

        # 7. Store in cache
        self.cache.set(canonical_key, response)

        return response
