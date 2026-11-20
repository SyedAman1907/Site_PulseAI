"""SitePulse AI - FastAPI Application.

AI-Powered Website Intelligence & Business Growth Advisor.
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import settings
from app.schemas import (
    ErrorResponse,
    LinkAnalysisRequest,
    LinkAnalysisResponse,
)
from app.services.analysis_service import AnalysisService
from app.services.llm_service import (
    AIOutputValidationError,
    LLMConfigurationError,
    LLMRateLimitError,
    LLMServiceError,
)
from app.services.website_extractor import WebsiteExtractionError
from app.utils.validators import (
    DNSResolutionError,
    InvalidURLError,
    SSRFProtectionError,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("sitepulse")

# Global analysis service instance
analysis_service = AnalysisService()
start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info(
        f"Starting {settings.APP_NAME} v{settings.APP_VERSION} on {settings.HOST}:{settings.PORT} "
        f"[Model: {settings.GEMINI_MODEL}, Env: {settings.ENVIRONMENT}]"
    )
    yield
    logger.info(f"Shutting down {settings.APP_NAME}")


app = FastAPI(
    title="SitePulse AI",
    description=(
        "AI-Powered Website Intelligence & Business Growth Advisor REST API. "
        "Extracts live website content and applies Google Gemini LLM reasoning to generate "
        "Competitor vs Brand Analysis, Top 5 Target Search Queries, SEO Improvements, "
        "Top 5 Business Services, and Target Audience Profiles."
    ),
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Enable CORS for frontend/client integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# Exception Handlers
# ==========================================

@app.exception_handler(SSRFProtectionError)
async def ssrf_exception_handler(request: Request, exc: SSRFProtectionError):
    logger.warning(f"SSRF violation blocked from {request.client.host if request.client else 'unknown'}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(
            success=False,
            error=str(exc),
            error_code="SSRF_PROTECTION_VIOLATION",
            detail="The requested URL targets an internal, private, loopback, or cloud metadata network destination.",
        ).model_dump(),
    )


@app.exception_handler(InvalidURLError)
async def invalid_url_handler(request: Request, exc: InvalidURLError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=ErrorResponse(
            success=False,
            error=str(exc),
            error_code="INVALID_URL_FORMAT",
            detail="The URL provided is malformed or uses an unsupported scheme. Only HTTP and HTTPS are permitted.",
        ).model_dump(),
    )


@app.exception_handler(DNSResolutionError)
async def dns_resolution_handler(request: Request, exc: DNSResolutionError):
    logger.warning(f"DNS resolution failure for request: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(
            success=False,
            error=str(exc),
            error_code="DNS_RESOLUTION_ERROR",
            detail="Unable to resolve the provided hostname via DNS.",
        ).model_dump(),
    )


@app.exception_handler(WebsiteExtractionError)
async def website_extraction_handler(request: Request, exc: WebsiteExtractionError):
    error_code = getattr(exc, "error_code", "WEBSITE_EXTRACTION_ERROR")
    detail = getattr(exc, "detail", f"Failed to access or parse target website (HTTP {exc.status_code}).")
    logger.error(f"Website extraction error [{error_code}] (HTTP {exc.status_code}): {exc}")
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            success=False,
            error=str(exc),
            error_code=error_code,
            detail=detail,
        ).model_dump(),
    )


@app.exception_handler(LLMRateLimitError)
async def llm_rate_limit_handler(request: Request, exc: LLMRateLimitError):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=ErrorResponse(
            success=False,
            error=str(exc),
            error_code="LLM_RATE_LIMIT_EXCEEDED",
            detail="Google Gemini API quota or rate limit temporarily exceeded. Please retry shortly.",
        ).model_dump(),
    )


@app.exception_handler(LLMConfigurationError)
async def llm_config_handler(request: Request, exc: LLMConfigurationError):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            success=False,
            error=str(exc),
            error_code="LLM_CONFIGURATION_ERROR",
            detail="AI service configuration error. Please verify GEMINI_API_KEY.",
        ).model_dump(),
    )


@app.exception_handler(AIOutputValidationError)
async def ai_output_validation_handler(request: Request, exc: AIOutputValidationError):
    clean_error = str(exc).split("\n")[0]
    logger.error(f"AI output validation error: {clean_error}")
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            success=False,
            error=clean_error,
            error_code=exc.error_code,
            detail=exc.detail,
        ).model_dump(),
    )


@app.exception_handler(LLMServiceError)
async def llm_service_handler(request: Request, exc: LLMServiceError):
    clean_error = str(exc).split("\n")[0]
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            success=False,
            error=clean_error,
            error_code="AI_ANALYSIS_FAILED",
            detail="An error occurred during Gemini AI intelligence processing.",
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first_err = errors[0].get("msg", "Invalid input parameters") if errors else "Validation failed"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=ErrorResponse(
            success=False,
            error=first_err,
            error_code="VALIDATION_ERROR",
            detail=str(errors),
        ).model_dump(),
    )


# ==========================================
# API Endpoints
# ==========================================

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "index.html")


@app.get(
    "/",
    tags=["General"],
    summary="Application Root & Web Dashboard",
)
async def root(request: Request):
    """
    Returns application name, status, and version as JSON by default.
    If requested by a web browser expecting HTML, serves the interactive web dashboard.
    """
    accept = request.headers.get("accept", "").lower()
    # Serve visual dashboard if a web browser directly navigates to root expecting HTML
    if accept.startswith("text/html") and os.path.exists(TEMPLATE_PATH):
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())

    # Return standard JSON metadata
    return JSONResponse(content={
        "name": settings.APP_NAME,
        "status": "operational",
        "version": settings.APP_VERSION,
        "description": "AI-Powered Website Intelligence & Business Growth Advisor",
        "docs_url": "/docs",
        "primary_endpoint": "POST /link-analysis",
    })


@app.get(
    "/dashboard",
    response_class=HTMLResponse,
    tags=["General"],
    summary="Interactive Web Dashboard",
)
async def dashboard():
    """Visual interactive web dashboard for submitting URLs and viewing 5-module intelligence."""
    if os.path.exists(TEMPLATE_PATH):
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>SitePulse AI Dashboard</h1><p>Template not found.</p>")


@app.get(
    "/health",
    tags=["Monitoring"],
    summary="Service Health Status",
)
async def health_check() -> Dict[str, Any]:
    """Returns comprehensive service health, uptime, and configuration status."""
    uptime_seconds = round(time.time() - start_time, 2)
    api_key_configured = bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your_api_key_here")

    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "uptime_seconds": uptime_seconds,
        "environment": settings.ENVIRONMENT,
        "ai_model": settings.GEMINI_MODEL,
        "gemini_api_configured": api_key_configured,
        "cache_ttl_seconds": settings.CACHE_TTL_SECONDS,
    }


@app.post(
    "/link-analysis",
    response_model=LinkAnalysisResponse,
    status_code=status.HTTP_200_OK,
    tags=["Analysis"],
    summary="Analyze Website & Generate Business Intelligence",
    responses={
        200: {"description": "Successful 5-module intelligence analysis."},
        400: {"model": ErrorResponse, "description": "SSRF or DNS validation failure."},
        404: {"model": ErrorResponse, "description": "Target website was not found."},
        415: {"model": ErrorResponse, "description": "Target website does not return HTML content."},
        422: {"model": ErrorResponse, "description": "Malformed URL or validation failure."},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
        502: {"model": ErrorResponse, "description": "Extraction or AI parsing failure."},
    },
)
async def link_analysis(request: LinkAnalysisRequest) -> LinkAnalysisResponse:
    """
    Main Intelligence Endpoint:
    1. Validates and inspects URL for SSRF vulnerabilities
    2. Fetches website HTML & assesses technical SEO signals
    3. Crawls same-domain high-value subpages (if present)
    4. Checks external competitor providers
    5. Prompts Google Gemini Flash for deep 5-module business intelligence
    6. Returns structured, validated JSON
    """
    response = await analysis_service.analyze_url(request.url)
    return response


if __name__ == "__main__":
    import uvicorn
    # Support platform PORT environment variable, defaulting to 4000
    port = int(os.environ.get("PORT", settings.PORT))
    uvicorn.run("app.main:app", host=settings.HOST, port=port, reload=True)
