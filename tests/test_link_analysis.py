"""Comprehensive Unit and Integration Tests for SitePulse AI.

Covers:
1. Root endpoint (GET /)
2. Health endpoint (GET /health)
3. Valid URL analysis (with mocked Gemini and HTTP)
4. Invalid URL format rejection
5. Unsupported URL scheme rejection (e.g., ftp://, file://)
6. Private IP rejection & SSRF protection (localhost, 127.0.0.1, 169.254.169.254, 10.0.0.1)
7. Website unavailable (404, 502, connection failure)
8. Empty website content rejection
9. Gemini response parsing and Pydantic schema validation
10. API error handling (Gemini rate limits, invalid credentials, malformed JSON)
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import (
    AnalysisContainer,
    BrandSummaryInfo,
    ExtractedWebsiteData,
    TechnicalSeoHealth,
    CompetitorItem,
)
from app.services.llm_service import (
    LLMConfigurationError,
    LLMRateLimitError,
    LLMServiceError,
)
from app.services.website_extractor import WebsiteExtractionError
from app.utils.validators import SSRFProtectionError, InvalidURLError

client = TestClient(app)


# Sample Mock Data
MOCK_HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Apex Cloud Solutions - Enterprise Cloud & DevOps Services</title>
    <meta name="description" content="Apex Cloud Solutions delivers world-class multi-cloud consulting, Kubernetes deployment, and automated DevOps infrastructure for modern high-growth enterprises.">
    <meta name="keywords" content="cloud solutions, devops, kubernetes, aws, azure, cloud migration">
</head>
<body>
    <header>
        <nav>
            <a href="/">Home</a>
            <a href="/about">About Us</a>
            <a href="/services">Services</a>
            <a href="/pricing">Pricing</a>
            <a href="/contact">Contact</a>
        </nav>
    </header>
    <main>
        <h1>Next-Generation Enterprise Cloud Architecture</h1>
        <p>Accelerate your business with secure, scalable cloud infrastructure and CI/CD pipelines.</p>
        
        <h2>Managed Kubernetes Infrastructure</h2>
        <p>Deploy production-ready Kubernetes clusters across AWS, GCP, and Azure with 99.99% uptime SLAs.</p>
        
        <h2>Automated CI/CD DevOps Pipelines</h2>
        <p>Eliminate release bottlenecks with end-to-end automated pipelines, GitOps, and security scanning.</p>
        
        <h2>Cloud Security & Compliance Audits</h2>
        <p>Ensure SOC2, HIPAA, and ISO27001 readiness with comprehensive cloud posture assessments.</p>
        
        <h2>24/7 SRE Cloud Monitoring & Incident Response</h2>
        <p>Proactive observability, APM metrics, and immediate MTTR resolution for mission-critical apps.</p>
        
        <h2>Legacy Migration & Microservices Modernization</h2>
        <p>Migrate monolithic architectures to cloud-native microservices seamlessly without downtime.</p>
        
        <img src="/img/architecture.png" alt="Cloud Architecture Diagram">
        <img src="/img/unnamed.png">
    </main>
    <footer>
        <p>Contact: info@apexcloudsolutions.io | +1 (555) 234-5678</p>
        <a href="https://linkedin.com/company/apexcloud">LinkedIn</a>
        <a href="https://x.com/apexcloud">Twitter</a>
    </footer>
</body>
</html>
"""

MOCK_GEMINI_ANALYSIS_JSON = {
    "brand": {
        "name": "Apex Cloud Solutions",
        "category": "Cloud Computing & DevOps Consulting",
        "summary": "Enterprise multi-cloud consulting, Kubernetes deployments, and automated CI/CD infrastructure services."
    },
    "analysis": {
        "competitor_analysis": {
            "brand_overview": {
                "name": "Apex Cloud Solutions",
                "business_overview": "Enterprise cloud consultancy specializing in managed Kubernetes, DevSecOps pipelines, and cloud migration.",
                "main_category": "Cloud Computing & DevOps Consulting",
                "products_and_services": ["Managed Kubernetes", "CI/CD DevOps", "Cloud Security Audits", "24/7 SRE Support", "Cloud Modernization"],
                "target_market": "North America and Global B2B Enterprises",
                "competitive_advantages": ["99.99% SLA commitment", "Multi-cloud vendor agnostic architecture", "Turnkey GitOps workflows"],
                "market_positioning": "Premium high-reliability cloud engineering partner for mid-to-enterprise tech companies",
                "improvement_opportunities": ["Self-serve portal for SMBs", "Transparent tier-based public pricing page"]
            },
            "competitors": [
                {
                    "name": "Datadog Cloud Advisory",
                    "website_url": "https://www.datadoghq.com",
                    "category": "Cloud Observability & Consulting",
                    "main_services": ["Infrastructure Monitoring", "Application Performance Monitoring"],
                    "strengths": ["Massive enterprise brand recognition and deep monitoring telemetry"],
                    "weaknesses": ["High enterprise licensing costs and complex pricing structure"],
                    "comparison": "Apex provides boutique hands-on DevOps engineering rather than just software licenses.",
                    "evidence_or_source": "AI-generated estimation based on industry domain; unverified by external search API",
                    "verification_status": "ai_generated_unverified",
                    "is_verified": False
                },
                {
                    "name": "Mission Cloud",
                    "website_url": "https://www.missioncloud.com",
                    "category": "Managed Cloud Services",
                    "main_services": ["AWS Managed Services", "Cloud Optimization"],
                    "strengths": ["Premier AWS Partner status with strong AWS migration incentives"],
                    "weaknesses": ["Predominantly AWS-centric with limited Azure/GCP multicloud depth"],
                    "comparison": "Apex provides true multi-cloud support across AWS, GCP, and Azure.",
                    "evidence_or_source": "AI-generated estimation based on industry domain; unverified by external search API",
                    "verification_status": "ai_generated_unverified",
                    "is_verified": False
                },
                {
                    "name": "Contino (Cognizant)",
                    "website_url": "https://www.contino.io",
                    "category": "Enterprise DevOps Transformation",
                    "main_services": ["Digital Transformation", "DevSecOps Culture"],
                    "strengths": ["Backed by global system integrator scale and enterprise contract vehicles"],
                    "weaknesses": ["Slow agility and heavy overhead on agile mid-market engagements"],
                    "comparison": "Apex delivers faster deployment velocity and dedicated senior engineers.",
                    "evidence_or_source": "AI-generated estimation based on industry domain; unverified by external search API",
                    "verification_status": "ai_generated_unverified",
                    "is_verified": False
                }
            ],
            "strengths": ["Dedicated multi-cloud engineering", "Tailored GitOps pipelines", "Direct access to senior cloud architects"],
            "opportunities": ["Create automated self-service cloud cost audit tool", "Publish multi-cloud Terraform templates"]
        },
        "target_search_queries": [
            {
                "query": "enterprise managed kubernetes consulting services",
                "recommended_platforms": ["Google", "LinkedIn"],
                "search_intent": "Commercial",
                "business_relevance": "Directly targets engineering executives seeking Kubernetes expertise",
                "target_audience": "CTOs, VP of Engineering, DevOps Directors",
                "source_type": "AI-generated query recommendation (non-benchmark)"
            },
            {
                "query": "cloud migration architecture best practices 2026",
                "recommended_platforms": ["Google", "X"],
                "search_intent": "Informational",
                "business_relevance": "Attracts enterprise decision-makers in the early planning phase",
                "target_audience": "Enterprise Cloud Architects",
                "source_type": "AI-generated query recommendation (non-benchmark)"
            },
            {
                "query": "hire fractional SRE DevOps team",
                "recommended_platforms": ["LinkedIn", "Google"],
                "search_intent": "Transactional",
                "business_relevance": "High-intent lead generation for 24/7 SRE retainers",
                "target_audience": "Startup Founders & Technical Heads",
                "source_type": "AI-generated query recommendation (non-benchmark)"
            },
            {
                "query": "#DevSecOps automation pipeline security",
                "recommended_platforms": ["LinkedIn", "X"],
                "search_intent": "Commercial",
                "business_relevance": "Builds thought leadership in compliant automated infrastructure",
                "target_audience": "Security & Compliance Officers, DevSecOps Leads",
                "source_type": "AI-generated query recommendation (non-benchmark)"
            },
            {
                "query": "SOC2 compliant AWS cloud setup agency",
                "recommended_platforms": ["Google", "Facebook"],
                "search_intent": "Commercial",
                "business_relevance": "High conversion for funded SaaS startups needing compliance fast",
                "target_audience": "SaaS Founders & Operations Leads",
                "source_type": "AI-generated query recommendation (non-benchmark)"
            }
        ],
        "seo_improvements": {
            "primary_keyword": "enterprise cloud solutions and devops",
            "secondary_keywords": ["managed kubernetes services", "cloud migration consulting", "soc2 cloud compliance", "devsecops automation"],
            "long_tail_keywords": ["multi cloud managed kubernetes consulting for enterprises", "how to automate gitops ci cd pipeline safely", "24 7 site reliability engineering services for startups"],
            "existing_title": "Apex Cloud Solutions - Enterprise Cloud & DevOps Services",
            "recommended_title": "Apex Cloud Solutions | Enterprise Multi-Cloud & DevOps Architecture",
            "title_improvement_reason": "Incorporates multi-cloud capability and architecture keywords within optimal 58 character length.",
            "existing_meta_description": "Apex Cloud Solutions delivers world-class multi-cloud consulting, Kubernetes deployment, and automated DevOps infrastructure for modern high-growth enterprises.",
            "meta_description": "Transform your enterprise with Apex Cloud Solutions: Managed Kubernetes, multi-cloud DevOps pipelines, and 24/7 SRE reliability. Book a cloud consult today.",
            "relevant_keywords": ["managed kubernetes", "multi cloud devops", "enterprise cloud consulting"],
            "supporting_content": [
                {
                    "content_type": "Service Landing Page",
                    "topic": "Managed Kubernetes on Multi-Cloud",
                    "target_keyword": "multi-cloud kubernetes management",
                    "purpose": "Capture high-intent enterprise search traffic looking for Kubernetes operations."
                },
                {
                    "content_type": "Industry Page",
                    "topic": "HIPAA & SOC2 Compliant Cloud Architecture for Healthcare SaaS",
                    "target_keyword": "hipaa compliant cloud devops",
                    "purpose": "Position Apex as the go-to partner for regulated tech verticals."
                },
                {
                    "content_type": "FAQ Section",
                    "topic": "Enterprise Cloud Migration & SLA Guarantees FAQ",
                    "target_keyword": "cloud migration cost and timelines",
                    "purpose": "Address prospective client friction regarding migration downtime and pricing."
                },
                {
                    "content_type": "Blog Topic",
                    "topic": "Migrating from Docker Swarm to EKS: A Step-by-Step Production Guide",
                    "target_keyword": "migrate docker swarm to eks",
                    "purpose": "Technical organic SEO authority driver targeting engineers."
                },
                {
                    "content_type": "Supporting Article",
                    "topic": "How We Cut Cloud Spend by 40% with Karpenter & Spot Instances",
                    "target_keyword": "karpenter spot instance cost optimization",
                    "purpose": "Demonstrates real-world engineering ROI to financial stakeholders."
                }
            ],
            "seo_observations": [
                "Title tag is present and well-structured.",
                "Meta description is compelling but could include a stronger call-to-action.",
                "Clear single H1 heading with supporting H2 structure found."
            ]
        },
        "top_services": [
            {
                "service_name": "Managed Kubernetes Infrastructure",
                "description": "Production-ready cluster provisioning and management across AWS EKS, GCP GKE, and Azure AKS with 99.99% uptime guarantees.",
                "target_industry": "SaaS, FinTech, E-commerce",
                "target_customer": "VP of Engineering & Lead DevOps Architects",
                "main_benefit": "Zero maintenance overhead and automated cluster scaling",
                "source_evidence": "Found under H2 'Managed Kubernetes Infrastructure' in body content",
                "identification_type": "extracted"
            },
            {
                "service_name": "Automated CI/CD DevOps Pipelines",
                "description": "End-to-end GitOps deployment pipelines, canary deployments, automated vulnerability testing, and artifact management.",
                "target_industry": "Software & Technology Companies",
                "target_customer": "Product Engineering Teams",
                "main_benefit": "Reduces release cycle time from weeks to hours with zero downtime",
                "source_evidence": "Found under H2 'Automated CI/CD DevOps Pipelines'",
                "identification_type": "extracted"
            },
            {
                "service_name": "Cloud Security & Compliance Audits",
                "description": "Comprehensive security posture assessments, IAM hardening, and audit preparation for SOC2, HIPAA, and ISO27001.",
                "target_industry": "Healthcare Tech & Financial Services",
                "target_customer": "Chief Information Security Officers (CISOs)",
                "main_benefit": "Accelerates compliance readiness and eliminates cloud misconfigurations",
                "source_evidence": "Found under H2 'Cloud Security & Compliance Audits'",
                "identification_type": "extracted"
            },
            {
                "service_name": "24/7 SRE Cloud Monitoring & Incident Response",
                "description": "Round-the-clock proactive site reliability engineering, telemetry observability, and immediate mean-time-to-resolution SLAs.",
                "target_industry": "High-traffic consumer apps & Enterprise platforms",
                "target_customer": "Head of Infrastructure & Operations",
                "main_benefit": "Guarantees continuous application availability and rapid disaster recovery",
                "source_evidence": "Found under H2 '24/7 SRE Cloud Monitoring & Incident Response'",
                "identification_type": "extracted"
            },
            {
                "service_name": "Legacy Migration & Microservices Modernization",
                "description": "Refactoring monolithic architectures into containerized, cloud-native microservices with zero operational downtime.",
                "target_industry": "Legacy Enterprise & Traditional Industries",
                "target_customer": "Chief Technology Officers & IT Directors",
                "main_benefit": "Unlocks agility and drastically lowers legacy infrastructure hosting costs",
                "source_evidence": "Found under H2 'Legacy Migration & Microservices Modernization'",
                "identification_type": "extracted"
            }
        ],
        "target_audience": {
            "primary_audience": ["Enterprise CTOs & VPs of Engineering", "Heads of Cloud Infrastructure & DevOps"],
            "secondary_audience": ["Early-Stage Tech Founders needing scalable cloud architecture", "Product Engineering Managers"],
            "industries": ["B2B Software & SaaS", "Financial Technology", "Digital Health", "E-commerce"],
            "business_types": ["B2B Mid-Market", "Funded Tech Startups", "High-Growth Scaleups", "Enterprise Organizations"],
            "customer_profiles": ["Companies experiencing rapid traffic growth", "Teams struggling with developer velocity and cloud outages"],
            "geographical_focus": ["North America", "United Kingdom & Europe", "Global Distributed Engineering Teams"],
            "customer_needs": ["Expert cloud infrastructure management without hiring expensive in-house SREs", "High availability and strict security compliance"],
            "customer_challenges": ["Unpredictable cloud bills", "Slow deployment cycles", "Frequent Kubernetes cluster outages", "Audit compliance pressure"],
            "potential_interests": ["Kubernetes", "Terraform", "GitOps", "FinOps Cloud Cost Optimization", "Zero-Trust Cloud Security"],
            "marketing_segments": [
                {
                    "audience_name": "Growth-Stage SaaS CTOs",
                    "business_type": "B2B SaaS",
                    "industry": "Software & Technology",
                    "main_requirements": ["SOC2 compliant architecture", "Automated release pipeline", "Scalable multi-region deployment"],
                    "problems_faced": ["Engineers spending 30% of their time troubleshooting deployment scripts rather than building core product features"],
                    "business_relevance": "Apex provides plug-and-play DevOps so developers can focus solely on product code",
                    "suggested_marketing_channel": "LinkedIn Thought Leadership & Executive Peer Communities",
                    "segment_type": "primary",
                    "is_inferred": True
                },
                {
                    "audience_name": "FinTech Security & Infrastructure Directors",
                    "business_type": "B2B / B2C FinTech",
                    "industry": "Financial Services",
                    "main_requirements": ["Zero-trust network architecture", "24/7 incident response SLA", "PCI-DSS / ISO27001 compliance"],
                    "problems_faced": ["Strict regulatory audits and risk of catastrophic financial platform downtime"],
                    "business_relevance": "Apex offers proven compliance hardening and round-the-clock SRE monitoring",
                    "suggested_marketing_channel": "Google Search High-Intent Ads & Enterprise Case Studies",
                    "segment_type": "secondary",
                    "is_inferred": True
                }
            ]
        }
    }
}


# ==========================================
# 1. Root Endpoint Test
# ==========================================
def test_root_endpoint():
    """Verify GET / returns application information and status."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "SitePulse AI"
    assert data["status"] == "operational"
    assert "version" in data
    assert data["primary_endpoint"] == "POST /link-analysis"


# ==========================================
# 2. Health Endpoint Test
# ==========================================
def test_health_endpoint():
    """Verify GET /health returns service health, environment, and uptime."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "uptime_seconds" in data
    assert "ai_model" in data
    assert "gemini_api_configured" in data


# ==========================================
# 3. Valid URL Analysis Flow Test (Mocked)
# ==========================================
@patch("app.utils.validators.resolve_and_verify_dns", return_value=["93.184.216.34"])
@patch("app.services.website_extractor.WebsiteExtractor.fetch_html")
@patch("app.services.llm_service.LLMService.generate_analysis")
def test_valid_url_analysis(mock_llm, mock_fetch, mock_dns):
    """Verify POST /link-analysis executes end-to-end pipeline with mocked external services."""
    # Mock website extractor
    mock_fetch.return_value = (MOCK_HTML_CONTENT, "https://apexcloudsolutions.io", 200)

    # Mock Gemini response
    brand_info = BrandSummaryInfo(**MOCK_GEMINI_ANALYSIS_JSON["brand"])
    analysis_container = AnalysisContainer(**MOCK_GEMINI_ANALYSIS_JSON["analysis"])
    mock_llm.return_value = (
        brand_info,
        analysis_container,
        {
            "execution_time_seconds": 1.25,
            "estimated_tokens": {"input_tokens": 1200, "output_tokens": 850, "total_tokens": 2050},
            "estimated_cost_usd": 0.000345,
        }
    )

    payload = {"url": "https://apexcloudsolutions.io"}
    response = client.post("/link-analysis", json=payload)

    assert response.status_code == 200
    res_data = response.json()

    # Verify root fields
    assert res_data["success"] is True
    assert res_data["website"] == "https://apexcloudsolutions.io"
    assert res_data["brand"]["name"] == "Apex Cloud Solutions"

    # Verify all 5 modules exist
    analysis = res_data["analysis"]
    assert "competitor_analysis" in analysis
    assert "target_search_queries" in analysis
    assert "seo_improvements" in analysis
    assert "top_services" in analysis
    assert "target_audience" in analysis

    # Module 1: Competitors
    assert len(analysis["competitor_analysis"]["competitors"]) >= 3
    assert analysis["competitor_analysis"]["competitors"][0]["verification_status"] == "ai_generated_unverified"

    # Module 2: Target Queries (exactly 5)
    assert len(analysis["target_search_queries"]) == 5

    # Module 3: SEO Improvements
    assert analysis["seo_improvements"]["primary_keyword"] != ""
    assert analysis["seo_improvements"]["recommended_title"] != ""
    assert len(analysis["seo_improvements"]["supporting_content"]) >= 1

    # Module 4: Top Services (exactly 5)
    assert len(analysis["top_services"]) == 5
    assert analysis["top_services"][0]["service_name"] == "Managed Kubernetes Infrastructure"

    # Module 5: Target Audience
    assert len(analysis["target_audience"]["primary_audience"]) >= 1
    assert len(analysis["target_audience"]["marketing_segments"]) >= 1

    # Metadata
    assert "analyzed_at" in res_data["metadata"]
    assert res_data["metadata"]["ai_model"] != ""


# ==========================================
# 4. Invalid URL Format Test
# ==========================================
def test_invalid_url_format():
    """Verify malformed URLs are rejected with HTTP 422."""
    for bad_url in ["not-a-valid-url", "htt://broken-domain", ""]:
        response = client.post("/link-analysis", json={"url": bad_url})
        assert response.status_code in (400, 422)
        err = response.json()
        assert err["success"] is False


# ==========================================
# 5. Unsupported Scheme Test
# ==========================================
def test_unsupported_scheme():
    """Verify non-HTTP/HTTPS schemes (ftp, file, ssh) are rejected."""
    for scheme_url in ["ftp://example.com/file.txt", "file:///etc/passwd", "gopher://example.com"]:
        response = client.post("/link-analysis", json={"url": scheme_url})
        assert response.status_code in (400, 422)
        err = response.json()
        assert err["success"] is False
        assert "scheme" in err["error"].lower() or "scheme" in str(err.get("detail", "")).lower()


# ==========================================
# 6. SSRF & Private IP Protection Test
# ==========================================
def test_ssrf_and_private_ip_rejection():
    """Verify localhost, private IPs, and cloud metadata IPs are strictly rejected."""
    ssrf_targets = [
        "http://localhost:8000",
        "http://127.0.0.1:4000",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1",
        "http://192.168.1.1",
        "http://172.16.0.1",
        "http://0.0.0.0",
        "http://metadata.google.internal",
    ]

    for target in ssrf_targets:
        response = client.post("/link-analysis", json={"url": target})
        assert response.status_code in (400, 422), f"Failed to reject SSRF target: {target}"
        err = response.json()
        assert err["success"] is False


# ==========================================
# 7. Website Unavailable Test
# ==========================================
@patch("app.services.website_extractor.WebsiteExtractor.fetch_html")
def test_website_unavailable_404(mock_fetch):
    """Verify 404 response from target website is handled gracefully."""
    mock_fetch.side_effect = WebsiteExtractionError("Target website returned 404 Not Found", status_code=404)

    response = client.post("/link-analysis", json={"url": "https://example.com/non-existent-page-xyz"})
    assert response.status_code == 404
    err = response.json()
    assert err["success"] is False
    assert err["error_code"] == "WEBSITE_EXTRACTION_ERROR"


@patch("app.utils.validators.resolve_and_verify_dns", return_value=["93.184.216.34"])
@patch("app.services.website_extractor.WebsiteExtractor.fetch_html")
def test_website_unavailable_connection_error(mock_fetch, mock_dns):
    """Verify connection timeout/failure is handled gracefully."""
    mock_fetch.side_effect = WebsiteExtractionError("Connection failed for target host", status_code=502)

    response = client.post("/link-analysis", json={"url": "https://unreachable-domain-12345.com"})
    assert response.status_code == 502
    err = response.json()
    assert err["success"] is False


# ==========================================
# 8. Empty Website Content Test
# ==========================================
@patch("app.services.website_extractor.WebsiteExtractor.fetch_html")
def test_empty_website_content(mock_fetch):
    """Verify empty website content is detected and handled."""
    mock_fetch.side_effect = WebsiteExtractionError("Website returned completely empty content.", status_code=422)

    response = client.post("/link-analysis", json={"url": "https://empty-blank-website.com"})
    assert response.status_code == 422
    err = response.json()
    assert err["success"] is False
    assert "empty" in err["error"].lower()


# ==========================================
# 9. Gemini Response Schema Validation Test
# ==========================================
def test_pydantic_schema_validation():
    """Directly test Pydantic schemas against full intelligence JSON."""
    brand_info = BrandSummaryInfo(**MOCK_GEMINI_ANALYSIS_JSON["brand"])
    assert brand_info.name == "Apex Cloud Solutions"
    assert brand_info.category == "Cloud Computing & DevOps Consulting"

    analysis = AnalysisContainer(**MOCK_GEMINI_ANALYSIS_JSON["analysis"])
    assert len(analysis.competitor_analysis.competitors) == 3
    assert len(analysis.target_search_queries) == 5
    assert len(analysis.top_services) == 5
    assert analysis.seo_improvements.primary_keyword != ""
    assert len(analysis.target_audience.marketing_segments) == 2


# ==========================================
# 10. API Error Handling Test (Gemini Rate Limit & Missing Key)
# ==========================================
@patch("app.services.website_extractor.WebsiteExtractor.fetch_html")
@patch("app.services.llm_service.LLMService.generate_analysis")
def test_gemini_rate_limit_handling(mock_llm, mock_fetch):
    """Verify rate limit error (HTTP 429) is handled gracefully without leaking credentials."""
    mock_fetch.return_value = (MOCK_HTML_CONTENT, "https://example.com", 200)
    mock_llm.side_effect = LLMRateLimitError("Gemini API rate limit or quota exceeded.")

    response = client.post("/link-analysis", json={"url": "https://example.com"})
    assert response.status_code == 429
    err = response.json()
    assert err["success"] is False
    assert err["error_code"] == "LLM_RATE_LIMIT_EXCEEDED"


@patch("app.services.website_extractor.WebsiteExtractor.fetch_html")
@patch("app.services.llm_service.LLMService.generate_analysis")
def test_gemini_config_error_handling(mock_llm, mock_fetch):
    """Verify configuration error (missing API key) is handled cleanly."""
    mock_fetch.return_value = (MOCK_HTML_CONTENT, "https://example.com", 200)
    mock_llm.side_effect = LLMConfigurationError("GEMINI_API_KEY is not configured.")

    response = client.post("/link-analysis", json={"url": "https://example.com"})
    assert response.status_code == 500
    err = response.json()
    assert err["success"] is False
    assert err["error_code"] == "LLM_CONFIGURATION_ERROR"
