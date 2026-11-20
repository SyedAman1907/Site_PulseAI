"""Pydantic schemas for SitePulse AI request and response models."""

from typing import List, Optional, Literal, Dict, Any, Union
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator
from app.utils.validators import validate_url_security


def ensure_list_of_strings(v: Any) -> List[str]:
    """
    Robustly normalizes arbitrary input into a clean list of non-empty strings.
    Handles None, single strings, comma/newline-separated strings, numbers, and lists.
    """
    if v is None:
        return []
    if isinstance(v, str):
        v_stripped = v.strip()
        if not v_stripped:
            return []
        # Check for newline-delimited or comma-delimited strings
        if "\n" in v_stripped:
            return [line.strip().lstrip("•-*0123456789. ") for line in v_stripped.split("\n") if line.strip()]
        if "," in v_stripped and not v_stripped.startswith("http"):
            return [part.strip().lstrip("•-*0123456789. ") for part in v_stripped.split(",") if part.strip()]
        return [v_stripped]
    if isinstance(v, (list, tuple, set)):
        result = []
        for item in v:
            if item is None:
                continue
            if isinstance(item, str):
                s = item.strip().lstrip("•-*0123456789. ")
                if s:
                    result.append(s)
            elif isinstance(item, (int, float)):
                result.append(str(item))
            elif isinstance(item, dict):
                # If an item inside a string list is a dict, extract text value if possible
                val = next((str(val).strip() for val in item.values() if isinstance(val, str) and val.strip()), "")
                if val:
                    result.append(val)
        return result
    s = str(v).strip()
    return [s] if s else []


# ==========================================
# Request Schemas
# ==========================================

class LinkAnalysisRequest(BaseModel):
    """Incoming request model for website analysis."""
    url: str = Field(
        ...,
        description="Public website URL to analyze (must be HTTP or HTTPS)",
        examples=["https://example.com"]
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        # Validates format and checks for SSRF vulnerabilities
        return validate_url_security(v)


# ==========================================
# Extracted Raw Website Metadata (Internal)
# ==========================================

class ExtractedWebsiteData(BaseModel):
    """Raw structured data extracted from the target website."""
    url: str
    final_url: str
    title: str = ""
    meta_description: str = ""
    meta_keywords: List[str] = Field(default_factory=list)
    h1_headings: List[str] = Field(default_factory=list)
    h2_headings: List[str] = Field(default_factory=list)
    h3_headings: List[str] = Field(default_factory=list)
    main_text: str = ""
    navigation_labels: List[str] = Field(default_factory=list)
    internal_links: List[str] = Field(default_factory=list)
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    social_links: Dict[str, str] = Field(default_factory=dict)
    business_name: str = ""
    address_or_location: str = ""
    pages_crawled: int = 1
    total_images_found: int = 0
    images_missing_alt: int = 0
    subpage_summaries: List[Dict[str, str]] = Field(default_factory=list)


# ==========================================
# Module 1: Competitor vs Brand Analysis
# ==========================================

class BrandOverview(BaseModel):
    """In-depth brand positioning and profile."""
    name: str = Field(..., description="Identified brand name")
    business_overview: str = Field(..., description="Overview of company operations and purpose")
    main_category: str = Field(..., description="Primary industry or business category")
    products_and_services: List[str] = Field(default_factory=list, description="Core offerings detected")
    target_market: str = Field(..., description="Identified target geographic and demographic market")
    competitive_advantages: List[str] = Field(default_factory=list, description="Unique value propositions")
    market_positioning: str = Field(..., description="Current strategic positioning in the market")
    improvement_opportunities: List[str] = Field(default_factory=list, description="Immediate strategic growth areas")

    @model_validator(mode="before")
    @classmethod
    def normalize_brand_overview(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        normalized["name"] = normalized.get("name") or normalized.get("brand_name") or normalized.get("brand") or "Analyzed Brand"
        normalized["business_overview"] = (
            normalized.get("business_overview")
            or normalized.get("overview")
            or normalized.get("summary")
            or normalized.get("description")
            or "Business operations overview."
        )
        normalized["main_category"] = (
            normalized.get("main_category")
            or normalized.get("category")
            or normalized.get("industry")
            or "Commercial Enterprise"
        )
        normalized["target_market"] = (
            normalized.get("target_market")
            or normalized.get("market")
            or normalized.get("target_audience")
            or "Global & Regional Markets"
        )
        normalized["market_positioning"] = (
            normalized.get("market_positioning")
            or normalized.get("positioning")
            or normalized.get("market_position")
            or "Strategic Market Presence"
        )
        normalized["products_and_services"] = ensure_list_of_strings(normalized.get("products_and_services"))
        normalized["competitive_advantages"] = ensure_list_of_strings(normalized.get("competitive_advantages"))
        normalized["improvement_opportunities"] = ensure_list_of_strings(normalized.get("improvement_opportunities"))
        return normalized


class CompetitorItem(BaseModel):
    """Individual competitor profile with verification status."""
    name: str = Field(..., description="Competitor company or platform name")
    website_url: Optional[str] = Field(None, description="Competitor website URL (if verified)")
    category: str = Field(..., description="Competitor industry category")
    main_services: List[str] = Field(default_factory=list, description="Main services provided")
    strengths: List[str] = Field(default_factory=list, description="Key competitor advantages")
    weaknesses: List[str] = Field(default_factory=list, description="Weaknesses, gaps, or disadvantages")
    comparison: str = Field(..., description="Direct head-to-head comparison with submitted brand")
    evidence_or_source: str = Field(..., description="Source citation or AI inference note")
    verification_status: Literal["verified_external_search", "ai_generated_unverified"] = Field(
        ...,
        description="Whether competitor was verified via live search or AI suggested"
    )
    is_verified: bool = Field(..., description="True if verified via external search API")

    @model_validator(mode="before")
    @classmethod
    def normalize_competitor_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        normalized["name"] = normalized.get("name") or normalized.get("competitor_name") or normalized.get("company_name") or "Industry Peer"
        raw_url = normalized.get("website_url")
        if raw_url is not None:
            raw_url_str = str(raw_url).strip()
            if raw_url_str.lower() in ("none", "null", "n/a", "", "undefined"):
                normalized["website_url"] = None
            else:
                normalized["website_url"] = raw_url_str
        normalized["category"] = normalized.get("category") or normalized.get("industry") or "Industry Competitor"
        normalized["comparison"] = normalized.get("comparison") or normalized.get("details") or normalized.get("head_to_head") or "Direct industry competitor"
        normalized["evidence_or_source"] = normalized.get("evidence_or_source") or normalized.get("source") or normalized.get("evidence") or "AI inference"
        normalized["main_services"] = ensure_list_of_strings(normalized.get("main_services"))
        normalized["strengths"] = ensure_list_of_strings(normalized.get("strengths"))
        normalized["weaknesses"] = ensure_list_of_strings(normalized.get("weaknesses"))

        # Verification status normalization
        raw_status = str(normalized.get("verification_status", "")).lower()
        if "external" in raw_status or (raw_status.startswith("verified") and "unverified" not in raw_status):
            normalized["verification_status"] = "verified_external_search"
            normalized["is_verified"] = True
        else:
            normalized["verification_status"] = "ai_generated_unverified"
            normalized["is_verified"] = False
        return normalized


class CompetitorAnalysis(BaseModel):
    """Full Competitor vs Brand Analysis module output."""
    brand_overview: BrandOverview
    competitors: List[CompetitorItem] = Field(
        ...,
        description="At least three relevant competitors"
    )
    strengths: List[str] = Field(
        default_factory=list,
        description="Where the submitted brand outperforms competitors"
    )
    opportunities: List[str] = Field(
        default_factory=list,
        description="Market positioning opportunities where competitors are weak"
    )

    @field_validator("strengths", "opportunities", mode="before")
    @classmethod
    def normalize_lists(cls, v: Any) -> List[str]:
        return ensure_list_of_strings(v)


# ==========================================
# Module 2: Top 5 Target Search Queries
# ==========================================

class SearchQueryItem(BaseModel):
    """Target search query recommendation."""
    query: str = Field(..., description="Recommended customer search term or hashtag")
    recommended_platforms: List[str] = Field(
        ...,
        description="Supported platforms: Google, Facebook, Instagram, LinkedIn, X"
    )
    search_intent: str = Field(..., description="Informational, Commercial, Navigational, or Transactional")
    business_relevance: str = Field(..., description="Why this query drives qualified leads to this business")
    target_audience: str = Field(..., description="Specific audience segment using this query")
    source_type: str = Field(
        default="AI-generated query recommendation (non-benchmark)",
        description="Data provenance label"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_query_item(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        normalized["query"] = normalized.get("query") or normalized.get("search_query") or normalized.get("keyword") or normalized.get("term") or "High-intent search query"
        platforms = ensure_list_of_strings(normalized.get("recommended_platforms"))
        normalized["recommended_platforms"] = platforms if platforms else ["Google"]
        normalized["search_intent"] = normalized.get("search_intent") or normalized.get("intent") or "Commercial"
        normalized["business_relevance"] = (
            normalized.get("business_relevance")
            or normalized.get("relevance")
            or normalized.get("why")
            or "Targets prospective customers with high purchase or engagement intent."
        )
        normalized["target_audience"] = (
            normalized.get("target_audience")
            or normalized.get("audience")
            or "Target Prospects & Buyers"
        )
        normalized["source_type"] = (
            normalized.get("source_type")
            or "AI-generated query recommendation (non-benchmark)"
        )
        return normalized


# ==========================================
# Module 3: SEO Improvement Recommendations
# ==========================================

class SupportingContentItem(BaseModel):
    """Content strategy recommendation to improve search visibility."""
    content_type: str = Field(..., description="Service page, Industry page, FAQ, Blog, or Location page")
    topic: str = Field(..., description="Proposed page title or topic focus")
    target_keyword: str = Field(..., description="Primary target keyword for this content")
    purpose: str = Field(..., description="Strategic intent and conversion value")

    @model_validator(mode="before")
    @classmethod
    def normalize_content_item(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        normalized["content_type"] = normalized.get("content_type") or normalized.get("type") or "Service Landing Page"
        normalized["topic"] = normalized.get("topic") or normalized.get("title") or "High-Value Topic"
        normalized["target_keyword"] = normalized.get("target_keyword") or normalized.get("keyword") or normalized.get("primary_keyword") or "Target Keyword"
        normalized["purpose"] = normalized.get("purpose") or normalized.get("objective") or normalized.get("intent") or "Capture relevant search traffic."
        return normalized


class TechnicalSeoHealth(BaseModel):
    """Deterministic observations from the extracted HTML content."""
    missing_title: bool = False
    missing_meta_description: bool = False
    missing_h1: bool = False
    duplicate_or_empty_headings: List[str] = Field(default_factory=list)
    images_missing_alt: int = 0
    total_images_analyzed: int = 0
    internal_links_count: int = 0
    notes: List[str] = Field(default_factory=list)


class SeoImprovements(BaseModel):
    """Full SEO Improvement module output."""
    primary_keyword: str = Field(..., description="Primary high-intent keyword")
    secondary_keywords: List[str] = Field(default_factory=list, description="Secondary supporting keywords")
    long_tail_keywords: List[str] = Field(default_factory=list, description="High-conversion long tail phrases")
    existing_title: Optional[str] = Field(None, description="Current website title")
    recommended_title: str = Field(..., description="Optimized SEO title recommendation")
    title_improvement_reason: str = Field(..., description="Explanation of title changes and keyword targeting")
    existing_meta_description: Optional[str] = Field(None, description="Current meta description")
    meta_description: str = Field(..., description="Optimized meta description recommendation")
    relevant_keywords: List[str] = Field(default_factory=list, description="Target keywords used in recommendations")
    supporting_content: List[SupportingContentItem] = Field(
        default_factory=list,
        description="Recommended landing pages, FAQ sections, and articles"
    )
    seo_observations: List[str] = Field(
        default_factory=list,
        description="Key SEO health observations and actionable takeaways"
    )
    technical_health: Optional[TechnicalSeoHealth] = Field(
        None,
        description="Measured HTML technical signals from extraction"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_seo_improvements(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        normalized["primary_keyword"] = normalized.get("primary_keyword") or normalized.get("main_keyword") or "Primary Target Keyword"
        normalized["recommended_title"] = (
            normalized.get("recommended_title")
            or normalized.get("title_recommendation")
            or normalized.get("title")
            or "Optimized Brand SEO Title"
        )
        normalized["title_improvement_reason"] = (
            normalized.get("title_improvement_reason")
            or normalized.get("title_reason")
            or "Optimized keyword density and character length for search visibility."
        )
        normalized["meta_description"] = (
            normalized.get("meta_description")
            or normalized.get("recommended_meta_description")
            or "Optimized meta description highlighting core offerings and call to action."
        )
        normalized["secondary_keywords"] = ensure_list_of_strings(normalized.get("secondary_keywords"))
        normalized["long_tail_keywords"] = ensure_list_of_strings(normalized.get("long_tail_keywords"))
        normalized["relevant_keywords"] = ensure_list_of_strings(normalized.get("relevant_keywords"))
        normalized["seo_observations"] = ensure_list_of_strings(normalized.get("seo_observations"))
        return normalized


# ==========================================
# Module 4: Top 5 Business Services
# ==========================================

class BusinessServiceItem(BaseModel):
    """Identified core service or product."""
    service_name: str = Field(..., description="Name of the service or product")
    description: str = Field(..., description="Clear explanation of the offering")
    target_industry: str = Field(..., description="Industries best served")
    target_customer: str = Field(..., description="Ideal persona or department")
    main_benefit: str = Field(..., description="Primary value proposition or ROI")
    source_evidence: str = Field(..., description="Excerpt or section where this service was found")
    identification_type: Literal["extracted", "inferred"] = Field(
        ...,
        description="'extracted' if directly observed on website; 'inferred' if recommended by AI"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_service_item(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        normalized["service_name"] = (
            normalized.get("service_name")
            or normalized.get("name")
            or normalized.get("title")
            or normalized.get("service")
            or "Core Business Service"
        )
        normalized["description"] = (
            normalized.get("description")
            or normalized.get("details")
            or normalized.get("summary")
            or "Comprehensive offering tailored to client requirements."
        )
        normalized["target_industry"] = (
            normalized.get("target_industry")
            or normalized.get("industry")
            or "Relevant Commercial Sector"
        )
        normalized["target_customer"] = (
            normalized.get("target_customer")
            or normalized.get("customer")
            or normalized.get("target_audience")
            or "Key Decision Makers"
        )
        normalized["main_benefit"] = (
            normalized.get("main_benefit")
            or normalized.get("benefit")
            or normalized.get("value_prop")
            or "Improves operational performance and delivers measurable value."
        )
        normalized["source_evidence"] = (
            normalized.get("source_evidence")
            or normalized.get("evidence")
            or normalized.get("source")
            or "Identified from website content."
        )

        id_type = str(normalized.get("identification_type", "")).lower()
        normalized["identification_type"] = "extracted" if "extract" in id_type else "inferred"
        return normalized


# ==========================================
# Module 5: Target Audience Identification
# ==========================================

class MarketingSegmentItem(BaseModel):
    """Actionable marketing segment profile."""
    audience_name: str = Field(..., description="Name of the audience persona")
    business_type: str = Field(..., description="B2B, B2C, D2C, Enterprise, SMB, or Startup")
    industry: str = Field(..., description="Industry sector")
    main_requirements: List[str] = Field(default_factory=list, description="Key functional requirements")
    problems_faced: List[str] = Field(default_factory=list, description="Pain points and challenges")
    business_relevance: str = Field(..., description="Why the analyzed business solves their problem")
    suggested_marketing_channel: str = Field(
        ...,
        description="Best channel to acquire this audience (LinkedIn, Google Ads, SEO, Cold Outreach, Instagram, etc.)"
    )
    segment_type: Literal["primary", "secondary"] = Field(
        default="primary",
        description="Primary or secondary audience classification"
    )
    is_inferred: bool = Field(
        default=True,
        description="True if deduced via AI reasoning rather than explicit user survey data"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_marketing_segment(cls, data: Any) -> Any:
        """
        Accepts:
        - Plain string (Format A from Gemini) e.g. "Engineering Aspirants (B.Tech Applicants)"
        - Object with segment/description keys (Format B)
        - Full or partially formed dictionaries with alias keys
        """
        if isinstance(data, str):
            s = data.strip().lstrip("•-*0123456789. ")
            if not s:
                raise ValueError("Marketing segment string cannot be empty")
            return {
                "audience_name": s,
                "business_type": "B2B / B2C",
                "industry": "Target Industry",
                "main_requirements": [],
                "problems_faced": [],
                "business_relevance": f"Direct relevant audience segment for {s}.",
                "suggested_marketing_channel": "Digital Outreach, Search & Social Media",
                "segment_type": "primary",
                "is_inferred": True,
            }

        if not isinstance(data, dict):
            # If unexpected type (e.g. number), try converting to string if non-empty
            s = str(data).strip()
            if s and s != "None":
                return cls.normalize_marketing_segment(s)
            raise ValueError(f"Invalid input type for MarketingSegmentItem: {type(data)}")

        normalized = dict(data)
        # Handle aliases for audience_name
        name = (
            normalized.get("audience_name")
            or normalized.get("segment")
            or normalized.get("name")
            or normalized.get("title")
            or normalized.get("audience")
            or normalized.get("segment_name")
            or normalized.get("marketing_segment")
        )
        if isinstance(name, str):
            name = name.strip().lstrip("•-*0123456789. ")
        if not name:
            # Check if there is any string value in the dict
            fallback_val = next((str(v).strip() for v in normalized.values() if isinstance(v, str) and v.strip()), "")
            if fallback_val:
                name = fallback_val
            else:
                raise ValueError("Marketing segment object must have an audience or segment name")

        normalized["audience_name"] = name
        normalized["business_type"] = str(
            normalized.get("business_type")
            or normalized.get("type")
            or "B2B / B2C"
        )
        normalized["industry"] = str(
            normalized.get("industry")
            or normalized.get("sector")
            or "Target Industry"
        )
        normalized["business_relevance"] = str(
            normalized.get("business_relevance")
            or normalized.get("description")
            or normalized.get("details")
            or normalized.get("overview")
            or f"Direct relevant audience segment for {name}."
        )
        normalized["suggested_marketing_channel"] = str(
            normalized.get("suggested_marketing_channel")
            or normalized.get("marketing_channel")
            or normalized.get("channel")
            or "Digital Outreach, Search & Social Media"
        )
        raw_segment_type = str(normalized.get("segment_type", "")).lower()
        normalized["segment_type"] = "secondary" if "second" in raw_segment_type else "primary"
        normalized["is_inferred"] = bool(normalized.get("is_inferred", True))
        normalized["main_requirements"] = ensure_list_of_strings(normalized.get("main_requirements"))
        normalized["problems_faced"] = ensure_list_of_strings(normalized.get("problems_faced"))
        return normalized


class TargetAudience(BaseModel):
    """Full Target Audience Identification module output."""
    primary_audience: List[str] = Field(default_factory=list, description="Core target personas")
    secondary_audience: List[str] = Field(default_factory=list, description="Secondary or adjacent personas")
    industries: List[str] = Field(default_factory=list, description="Key target industries")
    business_types: List[str] = Field(default_factory=list, description="Target company models (e.g. B2B, SMB)")
    customer_profiles: List[str] = Field(default_factory=list, description="Demographic / firmographic attributes")
    geographical_focus: List[str] = Field(default_factory=list, description="Target locations or global presence")
    customer_needs: List[str] = Field(default_factory=list, description="Direct customer needs addressed")
    customer_challenges: List[str] = Field(default_factory=list, description="Critical pain points solved")
    potential_interests: List[str] = Field(default_factory=list, description="Key topics and interests")
    marketing_segments: List[MarketingSegmentItem] = Field(
        default_factory=list,
        description="Detailed segmented audience breakdowns"
    )

    @field_validator(
        "primary_audience",
        "secondary_audience",
        "industries",
        "business_types",
        "customer_profiles",
        "geographical_focus",
        "customer_needs",
        "customer_challenges",
        "potential_interests",
        mode="before"
    )
    @classmethod
    def normalize_string_lists(cls, v: Any) -> List[str]:
        return ensure_list_of_strings(v)

    @field_validator("marketing_segments", mode="before")
    @classmethod
    def normalize_marketing_segments(cls, v: Any) -> List[Any]:
        """
        Defensively normalizes marketing_segments before Pydantic model validation.
        Supports:
        - None or empty input -> []
        - Single string or comma/newline-separated strings
        - List of strings (Format A)
        - List of dicts (Format B or standard schema)
        - Mixed list containing strings and dicts
        - Drops None, whitespace-only, numbers, or unconvertible items safely
        """
        if v is None:
            return []

        # If a single string is passed
        if isinstance(v, str):
            v_stripped = v.strip()
            if not v_stripped:
                return []
            if "\n" in v_stripped:
                items = [line.strip().lstrip("•-*0123456789. ") for line in v_stripped.split("\n") if line.strip()]
            elif "," in v_stripped:
                items = [p.strip().lstrip("•-*0123456789. ") for p in v_stripped.split(",") if p.strip()]
            else:
                items = [v_stripped]
            return items

        if not isinstance(v, (list, tuple, set)):
            return []

        cleaned_items = []
        for item in v:
            if item is None:
                continue
            if isinstance(item, str):
                s = item.strip().lstrip("•-*0123456789. ")
                if s:
                    cleaned_items.append(s)
            elif isinstance(item, dict):
                # Ensure the dict has some meaningful content
                if any(v for v in item.values() if v is not None and str(v).strip()):
                    cleaned_items.append(item)
            elif isinstance(item, MarketingSegmentItem):
                cleaned_items.append(item)
            # Numbers, booleans, and nulls without context are safely skipped

        return cleaned_items


# ==========================================
# Aggregate API Response Schemas (Section 7)
# ==========================================

class BrandSummaryInfo(BaseModel):
    """High-level brand info matching required Section 7 output."""
    name: str = Field(..., description="Detected business or brand name")
    category: str = Field(..., description="Detected business category")
    summary: str = Field(..., description="Concise business overview")

    @model_validator(mode="before")
    @classmethod
    def normalize_brand_summary(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        normalized["name"] = normalized.get("name") or normalized.get("brand_name") or normalized.get("brand") or "Analyzed Business"
        normalized["category"] = (
            normalized.get("category")
            or normalized.get("main_category")
            or normalized.get("industry")
            or "Commercial Enterprise"
        )
        normalized["summary"] = (
            normalized.get("summary")
            or normalized.get("business_overview")
            or normalized.get("overview")
            or normalized.get("description")
            or "Business summary and positioning analysis."
        )
        return normalized


class AnalysisContainer(BaseModel):
    """Container grouping all 5 analysis modules."""
    competitor_analysis: CompetitorAnalysis
    target_search_queries: List[SearchQueryItem] = Field(..., max_length=5, min_length=5)
    seo_improvements: SeoImprovements
    top_services: List[BusinessServiceItem] = Field(..., max_length=5, min_length=5)
    target_audience: TargetAudience


class AnalysisMetadata(BaseModel):
    """Run metadata for the intelligence request."""
    analyzed_at: str = Field(..., description="ISO 8601 timestamp of analysis")
    pages_analyzed: int = Field(default=1, description="Number of site pages crawled")
    ai_model: str = Field(..., description="LLM model identifier used")
    analysis_type: str = "AI-powered website analysis"
    cached: bool = Field(default=False, description="Whether result was served from TTL cache")
    estimated_tokens: Optional[Dict[str, int]] = None
    estimated_cost_usd: Optional[float] = None
    execution_time_seconds: Optional[float] = None


class LinkAnalysisResponse(BaseModel):
    """Official Response structure adhering strictly to Section 7."""
    success: bool = True
    website: str = Field(..., description="Analyzed website URL")
    brand: BrandSummaryInfo
    analysis: AnalysisContainer
    metadata: AnalysisMetadata


# ==========================================
# Error Response Schema
# ==========================================

class ErrorResponse(BaseModel):
    """Standardized error response model."""
    success: bool = False
    error: str = Field(..., description="Human-readable error description")
    error_code: str = Field(..., description="Machine-readable error identifier")
    detail: Optional[Any] = None
