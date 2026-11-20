"""Pydantic schemas for SitePulse AI request and response models."""

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, field_validator
from app.utils.validators import validate_url_security


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

    @field_validator("verification_status", mode="before")
    @classmethod
    def normalize_verification_status(cls, v: Any) -> str:
        if isinstance(v, str):
            v_lower = v.lower()
            if "external" in v_lower or (v_lower.startswith("verified") and "unverified" not in v_lower):
                return "verified_external_search"
        return "ai_generated_unverified"


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


# ==========================================
# Module 3: SEO Improvement Recommendations
# ==========================================

class SupportingContentItem(BaseModel):
    """Content strategy recommendation to improve search visibility."""
    content_type: str = Field(..., description="Service page, Industry page, FAQ, Blog, or Location page")
    topic: str = Field(..., description="Proposed page title or topic focus")
    target_keyword: str = Field(..., description="Primary target keyword for this content")
    purpose: str = Field(..., description="Strategic intent and conversion value")


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

    @field_validator("identification_type", mode="before")
    @classmethod
    def normalize_identification_type(cls, v: Any) -> str:
        if isinstance(v, str) and "extract" in v.lower():
            return "extracted"
        return "inferred"


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

    @field_validator("segment_type", mode="before")
    @classmethod
    def normalize_segment_type(cls, v: Any) -> str:
        if isinstance(v, str) and "second" in v.lower():
            return "secondary"
        return "primary"


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


# ==========================================
# Aggregate API Response Schemas (Section 7)
# ==========================================

class BrandSummaryInfo(BaseModel):
    """High-level brand info matching required Section 7 output."""
    name: str = Field(..., description="Detected business or brand name")
    category: str = Field(..., description="Detected business category")
    summary: str = Field(..., description="Concise business overview")


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
    detail: Optional[str] = None
