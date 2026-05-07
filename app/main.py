"""
FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import keywords, scrape, trends
from app.scheduler import start_scheduler, stop_scheduler

# ------------------------------------------------------------------ #
#  Logging                                                             #
# ------------------------------------------------------------------ #
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
#  Lifespan (startup / shutdown)                                       #
# ------------------------------------------------------------------ #
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Trend Scraper API...")
    start_scheduler()
    yield
    logger.info("Shutting down Trend Scraper API...")
    stop_scheduler()


# ------------------------------------------------------------------ #
#  App                                                                 #
# ------------------------------------------------------------------ #
app = FastAPI(
    title="Trend Scraper API",
    description=(
        "Scrapes trending topics from X, Instagram, and Facebook by keyword. "
        "Results are stored in Supabase for search and analysis."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ #
#  Optional API key authentication middleware                          #
# ------------------------------------------------------------------ #
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    # Skip auth for health check and docs
    skip_paths = {"/", "/api/v1/health", "/docs", "/redoc", "/openapi.json"}
    if request.url.path in skip_paths:
        return await call_next(request)

    if settings.api_secret_key:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != settings.api_secret_key:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    return await call_next(request)


# ------------------------------------------------------------------ #
#  Routers                                                             #
# ------------------------------------------------------------------ #
app.include_router(keywords.router, prefix="/api/v1")
app.include_router(scrape.router, prefix="/api/v1")
app.include_router(trends.router, prefix="/api/v1")


# ------------------------------------------------------------------ #
#  Health & root                                                        #
# ------------------------------------------------------------------ #
@app.get("/")
async def root():
    return {"service": "Trend Scraper API", "version": "1.0.0", "status": "running"}


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
