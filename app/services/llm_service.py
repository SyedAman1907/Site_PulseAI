"""Google Gemini AI Integration Service.

Generates structured business intelligence across the 5 required modules:
1. Competitor vs Brand Analysis
2. Top 5 Target Search Queries
3. SEO Improvement Recommendations
4. Top 5 Business Services
5. Target Audience Identification
"""

import json
import logging
import re
import time
from typing import Any, Dict, Optional, Tuple

from app.config import settings
from app.schemas import (
    AnalysisContainer,
    BrandSummaryInfo,
    ExtractedWebsiteData,
    TechnicalSeoHealth,
    CompetitorItem,
)

logger = logging.getLogger(__name__)

# Pricing per million tokens for Gemini Flash (Gemini 2.5 Flash / 1.5 Flash official rate <= 128k context)
GEMINI_FLASH_INPUT_PRICE_PER_M = 0.075
GEMINI_FLASH_OUTPUT_PRICE_PER_M = 0.30


class LLMServiceError(Exception):
    """Raised when LLM invocation or parsing encounters an error."""
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class LLMConfigurationError(LLMServiceError):
    """Raised when GEMINI_API_KEY is missing or invalid."""
    def __init__(self, message: str):
        super().__init__(message, status_code=500)


class LLMRateLimitError(LLMServiceError):
    """Raised when Gemini API rate limit or quota is exhausted."""
    def __init__(self, message: str):
        super().__init__(message, status_code=429)


class LLMService:
    """Service wrapper for Google Gemini API."""

    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model_name = settings.GEMINI_MODEL

    def _get_client_or_model(self):
        """Initializes Gemini SDK using either modern google-genai or google-generativeai."""
        if not self.api_key:
            raise LLMConfigurationError(
                "GEMINI_API_KEY is not configured. Please set GEMINI_API_KEY in your .env file or environment variables."
            )

        # Attempt modern google-genai first
        try:
            from google import genai
            return "genai_client", genai.Client(api_key=self.api_key)
        except (ImportError, Exception):
            pass

        # Fallback to google-generativeai
        try:
            import google.generativeai as legacy_genai
            legacy_genai.configure(api_key=self.api_key)
            return "legacy_model", legacy_genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={"response_mime_type": "application/json"}
            )
        except Exception as e:
            raise LLMConfigurationError(f"Failed to initialize Gemini SDK: {str(e)}")

    def build_prompt(
        self,
        extracted: ExtractedWebsiteData,
        technical_health: TechnicalSeoHealth,
        external_competitors: Optional[list] = None,
    ) -> str:
        """Constructs an exhaustive system and analysis prompt for Google Gemini."""
        external_comp_note = ""
        if external_competitors:
            external_comp_note = f"\nExternal verified competitors found:\n" + "\n".join([
                f"- {c.name} ({c.website_url}): {c.comparison}" for c in external_competitors
            ])
        else:
            external_comp_note = (
                "\nNOTE: No external search API was used for competitors. "
                "Any competitors you identify must have 'verification_status': 'ai_generated_unverified' "
                "and 'is_verified': false."
            )

        subpages_text = ""
        if extracted.subpage_summaries:
            subpages_text = "\nAdditional Crawled Subpages:\n" + "\n".join([
                f"Page URL: {sp['url']}\nTitle: {sp['title']}\nExcerpt: {sp['excerpt']}\n---"
                for sp in extracted.subpage_summaries
            ])

        prompt = f"""You are SitePulse AI, a world-class senior digital strategist, SEO expert, and business intelligence analyst.
Analyze the following extracted website data and produce a comprehensive business growth report.

STRICT INSTRUCTIONS:
1. Return ONLY valid, well-formed JSON matching the required schema below. No conversational filler, no markdown fences.
2. Distinguish clearly between:
   - Information directly extracted from the website
   - Reasonable AI inferences
   - External competitor suggestions
   - Strategic recommendations
3. Do NOT fabricate information presented as verified facts. If any specific detail (e.g. location or phone) is unavailable, state 'unavailable' or use an empty array.
4. Exactly 5 items for 'target_search_queries' covering platforms: Google, Facebook, Instagram, LinkedIn, and X (Twitter).
5. Exactly 5 items for 'top_services'. Prioritize offerings explicitly mentioned on the website. If fewer than 5 exist, clearly label the remaining as identification_type='inferred'.
6. In 'competitors', provide at least 3 relevant competitors.{external_comp_note}

WEBSITE EXTRACTED DATA:
- Target URL: {extracted.url}
- Final Effective URL: {extracted.final_url}
- Page Title: {extracted.title}
- Meta Description: {extracted.meta_description}
- Meta Keywords: {", ".join(extracted.meta_keywords) if extracted.meta_keywords else "None detected"}
- H1 Headings: {json.dumps(extracted.h1_headings)}
- H2 Headings: {json.dumps(extracted.h2_headings[:10])}
- H3 Headings: {json.dumps(extracted.h3_headings[:10])}
- Navigation Labels: {json.dumps(extracted.navigation_labels)}
- Business Name Detected: {extracted.business_name or "Unknown"}
- Address / Location: {extracted.address_or_location or "None detected"}
- Emails Detected: {json.dumps(extracted.emails)}
- Phone Numbers: {json.dumps(extracted.phones)}
- Social Profiles: {json.dumps(extracted.social_links)}
- Measured Technical SEO Observations: {json.dumps(technical_health.notes)}
{subpages_text}

WEBSITE BODY CONTENT (SANITIZED EXCERPT):
\"\"\"
{extracted.main_text[:12000]}
\"\"\"

JSON SCHEMA REQUIREMENTS:
You must return a JSON object with this exact top-level structure:
{{
  "brand": {{
    "name": "Brand Name",
    "category": "Main Category",
    "summary": "Business overview"
  }},
  "analysis": {{
    "competitor_analysis": {{
      "brand_overview": {{
        "name": "Brand Name",
        "business_overview": "Detailed overview of what the company does",
        "main_category": "Industry category",
        "products_and_services": ["Service 1", "Service 2"],
        "target_market": "Target geography and sector",
        "competitive_advantages": ["Advantage 1", "Advantage 2"],
        "market_positioning": "Current strategic position",
        "improvement_opportunities": ["Opportunity 1", "Opportunity 2"]
      }},
      "competitors": [
        {{
          "name": "Competitor Name",
          "website_url": "https://competitor.com or null",
          "category": "Competitor Category",
          "main_services": ["Service A", "Service B"],
          "strengths": ["Strength 1"],
          "weaknesses": ["Weakness 1"],
          "comparison": "How submitted brand compares against this competitor",
          "evidence_or_source": "AI-generated estimation based on industry domain; unverified by external search API",
          "verification_status": "ai_generated_unverified",
          "is_verified": false
        }}
      ],
      "strengths": ["Where submitted brand outperforms competitors"],
      "opportunities": ["Market gaps and strategic advantages"]
    }},
    "target_search_queries": [
      {{
        "query": "High-intent search query",
        "recommended_platforms": ["Google", "LinkedIn"],
        "search_intent": "Commercial / Informational / Transactional",
        "business_relevance": "Why this query converts customers for this brand",
        "target_audience": "Specific audience segment",
        "source_type": "AI-generated query recommendation (non-benchmark)"
      }}
    ],
    "seo_improvements": {{
      "primary_keyword": "Best primary keyword",
      "secondary_keywords": ["keyword 1", "keyword 2", "keyword 3"],
      "long_tail_keywords": ["long-tail query 1", "long-tail query 2", "long-tail query 3"],
      "existing_title": "{extracted.title}",
      "recommended_title": "Optimized Brand SEO Title (50-60 chars)",
      "title_improvement_reason": "Detailed explanation of improvements",
      "existing_meta_description": "{extracted.meta_description}",
      "meta_description": "Optimized Meta Description (140-160 chars)",
      "relevant_keywords": ["keyword A", "keyword B"],
      "supporting_content": [
        {{
          "content_type": "Service Landing Page / Industry Page / FAQ / Blog Topic / Location Page",
          "topic": "Topic Title",
          "target_keyword": "Target Keyword",
          "purpose": "Strategic conversion objective"
        }}
      ],
      "seo_observations": ["Observation 1", "Observation 2", "Observation 3"]
    }},
    "top_services": [
      {{
        "service_name": "Service Name",
        "description": "Comprehensive description",
        "target_industry": "Industry targeted",
        "target_customer": "Target persona",
        "main_benefit": "Core value proposition",
        "source_evidence": "Text excerpt from website or AI-inferred note",
        "identification_type": "extracted"
      }}
    ],
    "target_audience": {{
      "primary_audience": ["Audience 1", "Audience 2"],
      "secondary_audience": ["Audience 3"],
      "industries": ["Industry 1", "Industry 2"],
      "business_types": ["B2B", "Enterprise"],
      "customer_profiles": ["Profile details"],
      "geographical_focus": ["Regions"],
      "customer_needs": ["Need 1", "Need 2"],
      "customer_challenges": ["Challenge 1", "Challenge 2"],
      "potential_interests": ["Interest 1", "Interest 2"],
      "marketing_segments": [
        {{
          "audience_name": "Segment Name",
          "business_type": "B2B or B2C",
          "industry": "Industry",
          "main_requirements": ["Requirement 1"],
          "problems_faced": ["Problem 1"],
          "business_relevance": "Why this business is ideal for them",
          "suggested_marketing_channel": "Recommended Acquisition Channel",
          "segment_type": "primary",
          "is_inferred": true
        }}
      ]
    }}
  }}
}}
"""
        return prompt

    async def generate_analysis(
        self,
        extracted: ExtractedWebsiteData,
        technical_health: TechnicalSeoHealth,
        external_competitors: Optional[list] = None,
    ) -> Tuple[BrandSummaryInfo, AnalysisContainer, Dict[str, Any]]:
        """
        Calls Google Gemini API, validates output against Pydantic schemas,
        and computes estimated token usage and costs.
        """
        sdk_type, handler = self._get_client_or_model()
        prompt = self.build_prompt(extracted, technical_health, external_competitors)

        start_time = time.time()
        response_text = ""

        try:
            if sdk_type == "genai_client":
                response = handler.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                response_text = response.text or ""
            else:
                response = handler.generate_content(prompt)
                response_text = response.text or ""

        except Exception as exc:
            err_msg = str(exc)
            if "429" in err_msg or "ResourceExhausted" in err_msg or "quota" in err_msg.lower():
                raise LLMRateLimitError(f"Gemini API rate limit or quota exceeded: {err_msg}")
            if "API_KEY_INVALID" in err_msg or "401" in err_msg or "403" in err_msg:
                raise LLMConfigurationError(f"Gemini API key is invalid or unauthorized: {err_msg}")
            raise LLMServiceError(f"Gemini generation error: {err_msg}")

        elapsed_time = round(time.time() - start_time, 2)

        # Clean JSON fences if model included them
        clean_json_str = response_text.strip()
        if clean_json_str.startswith("```"):
            clean_json_str = re.sub(r"^```(?:json)?\s*", "", clean_json_str)
            clean_json_str = re.sub(r"\s*```$", "", clean_json_str)

        try:
            parsed_json = json.loads(clean_json_str)
        except json.JSONDecodeError as jde:
            logger.error(f"Failed to parse Gemini output as JSON: {jde}. Raw text: {response_text[:300]}")
            raise LLMServiceError(
                f"Gemini returned invalid JSON structure: {str(jde)}",
                status_code=502
            )

        # Validate Brand info
        try:
            brand_info = BrandSummaryInfo(**parsed_json.get("brand", {}))
        except Exception as e:
            logger.warning(f"Failed to parse BrandSummaryInfo: {e}. Falling back to extracted data.")
            brand_info = BrandSummaryInfo(
                name=extracted.business_name or extracted.title[:30] or "Analyzed Website",
                category="Business & Professional Services",
                summary=extracted.meta_description or "Website analyzed by SitePulse AI",
            )

        # Validate Analysis container
        analysis_dict = parsed_json.get("analysis", {})

        # Ensure Technical SEO observations from extractor are merged into seo_improvements
        seo_dict = analysis_dict.get("seo_improvements", {})
        existing_obs = seo_dict.get("seo_observations", [])
        for note in technical_health.notes:
            if note not in existing_obs:
                existing_obs.append(note)
        seo_dict["seo_observations"] = existing_obs
        seo_dict["technical_health"] = technical_health.model_dump()
        analysis_dict["seo_improvements"] = seo_dict

        # If external competitors were verified, inject them
        if external_competitors:
            comp_analysis = analysis_dict.get("competitor_analysis", {})
            current_comps = comp_analysis.get("competitors", [])
            # Prepend verified competitors
            comp_analysis["competitors"] = [c.model_dump() for c in external_competitors] + current_comps[:2]
            analysis_dict["competitor_analysis"] = comp_analysis

        # Validate and defensively repair any minor schema discrepancies
        try:
            analysis_container = self._repair_and_validate(analysis_dict, extracted, technical_health)
        except Exception as val_err:
            logger.error(f"Pydantic validation failed for AnalysisContainer: {val_err}")
            raise LLMServiceError(f"Failed to validate AI analysis schema: {str(val_err)}", status_code=502)

        # Estimate tokens and cost
        # Gemini approximation: ~4 characters per token
        input_tokens = len(prompt) // 4
        output_tokens = len(response_text) // 4
        total_tokens = input_tokens + output_tokens

        cost_usd = (
            (input_tokens / 1_000_000) * GEMINI_FLASH_INPUT_PRICE_PER_M +
            (output_tokens / 1_000_000) * GEMINI_FLASH_OUTPUT_PRICE_PER_M
        )

        metadata_stats = {
            "execution_time_seconds": elapsed_time,
            "estimated_tokens": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
            "estimated_cost_usd": round(cost_usd, 6),
        }

        return brand_info, analysis_container, metadata_stats

    def _repair_and_validate(
        self,
        analysis_dict: Dict[str, Any],
        extracted: ExtractedWebsiteData,
        technical_health: TechnicalSeoHealth,
    ) -> AnalysisContainer:
        """
        Defensive fallback: Ensures exactly 5 search queries, 5 services,
        and at least 3 properly structured competitors are present so validation succeeds.
        """
        # Ensure competitor structure
        comp_analysis = analysis_dict.setdefault("competitor_analysis", {})
        competitors = comp_analysis.get("competitors", [])
        for comp in competitors:
            status = str(comp.get("verification_status", "")).lower()
            if "external" in status or (status.startswith("verified") and "unverified" not in status):
                comp["verification_status"] = "verified_external_search"
                comp["is_verified"] = True
            else:
                comp["verification_status"] = "ai_generated_unverified"
                comp["is_verified"] = False

        if len(competitors) < 3:
            for i in range(len(competitors), 3):
                competitors.append({
                    "name": f"Industry Peer #{i+1}",
                    "website_url": None,
                    "category": comp_analysis.get("brand_overview", {}).get("main_category", "Commercial Services"),
                    "main_services": ["Market competitive offerings"],
                    "strengths": ["Regional presence and visibility"],
                    "weaknesses": ["Custom solution flexibility"],
                    "comparison": "Competes in similar industry market space",
                    "evidence_or_source": "AI-generated estimation based on industry domain; unverified by external search API.",
                    "verification_status": "ai_generated_unverified",
                    "is_verified": False,
                })
        comp_analysis["competitors"] = competitors

        # Ensure 5 search queries
        queries = analysis_dict.get("target_search_queries", [])
        if len(queries) < 5:
            platforms = ["Google", "LinkedIn", "Facebook", "Instagram", "X"]
            for i in range(len(queries), 5):
                queries.append({
                    "query": f"{extracted.business_name or 'Business'} services near me",
                    "recommended_platforms": [platforms[i % len(platforms)]],
                    "search_intent": "Commercial",
                    "business_relevance": "Drives direct qualified customer inquiries",
                    "target_audience": "Prospective buyers and decision makers",
                    "source_type": "AI-generated query recommendation (non-benchmark)"
                })
        elif len(queries) > 5:
            queries = queries[:5]
        analysis_dict["target_search_queries"] = queries

        # Ensure 5 services
        services = analysis_dict.get("top_services", [])
        for s in services:
            id_type = str(s.get("identification_type", "")).lower()
            s["identification_type"] = "extracted" if "extract" in id_type else "inferred"

        if len(services) < 5:
            for i in range(len(services), 5):
                services.append({
                    "service_name": f"Core Business Solution #{i+1}",
                    "description": "Comprehensive professional service addressing client needs.",
                    "target_industry": "Commercial Enterprises",
                    "target_customer": "Operations & Business Leaders",
                    "main_benefit": "Enhanced efficiency and streamlined operations",
                    "source_evidence": "Inferred from company industry positioning",
                    "identification_type": "inferred"
                })
        elif len(services) > 5:
            services = services[:5]
        analysis_dict["top_services"] = services

        return AnalysisContainer(**analysis_dict)
