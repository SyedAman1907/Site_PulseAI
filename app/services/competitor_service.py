"""Competitor Research Service for SitePulse AI.

Provides external search lookup if configured (e.g. Tavily API),
or properly labeled unverified fallback profiles when no external search provider is active.
"""

import logging
from typing import List, Optional, Dict, Any
import httpx
from app.config import settings
from app.schemas import CompetitorItem

logger = logging.getLogger(__name__)


class CompetitorService:
    """Handles external competitor discovery and evidence verification."""

    def __init__(self):
        self.tavily_key = settings.TAVILY_API_KEY
        self.search_key = settings.SEARCH_API_KEY

    async def search_external_competitors(self, brand_name: str, category: str, domain: str) -> List[CompetitorItem]:
        """
        Attempts to find verified competitors using external search APIs (e.g., Tavily API).
        Returns a list of CompetitorItem objects with verification_status='verified_external_search'.
        If external provider is not configured or query fails, returns empty list.
        """
        # If Tavily is configured
        if self.tavily_key:
            try:
                return await self._query_tavily(brand_name, category, domain)
            except Exception as e:
                logger.warning(f"External search via Tavily failed: {e}. Falling back to labeled AI suggestions.")

        return []

    async def _query_tavily(self, brand_name: str, category: str, domain: str) -> List[CompetitorItem]:
        """Query Tavily search API for real competitors in the industry."""
        query = f"top competitors and alternatives to {brand_name} {category} website"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.tavily_key,
                    "query": query,
                    "search_depth": "basic",
                    "include_answer": True,
                    "max_results": 5,
                }
            )
            if resp.status_code != 200:
                logger.warning(f"Tavily returned status {resp.status_code}")
                return []

            data = resp.json()
            results = data.get("results", [])
            competitors: List[CompetitorItem] = []

            for r in results:
                url = r.get("url", "")
                title = r.get("title", "")
                snippet = r.get("content", "")

                # Exclude self-domain
                if domain and domain.lower() in url.lower():
                    continue

                comp_name = title.split("-")[0].split("|")[0].strip() or "Market Alternative"
                competitors.append(
                    CompetitorItem(
                        name=comp_name,
                        website_url=url,
                        category=category or "Industry Peer",
                        main_services=["Discovered via web search indexing"],
                        strengths=["Active search presence and visibility"],
                        weaknesses=["May vary based on custom client requirements"],
                        comparison=f"Competes in {category} market space with public presence at {url}",
                        evidence_or_source=f"Tavily Search: {url} - {snippet[:150]}...",
                        verification_status="verified_external_search",
                        is_verified=True,
                    )
                )
                if len(competitors) >= 3:
                    break

            return competitors

    def format_unverified_competitor(
        self,
        name: str,
        website_url: Optional[str],
        category: str,
        main_services: List[str],
        strengths: List[str],
        weaknesses: List[str],
        comparison: str,
    ) -> CompetitorItem:
        """
        Creates a strictly labeled unverified competitor profile when external search is not used.
        """
        return CompetitorItem(
            name=name,
            website_url=website_url or None,
            category=category,
            main_services=main_services,
            strengths=strengths,
            weaknesses=weaknesses,
            comparison=comparison,
            evidence_or_source="AI-generated estimation based on industry domain; unverified by external search API.",
            verification_status="ai_generated_unverified",
            is_verified=False,
        )
