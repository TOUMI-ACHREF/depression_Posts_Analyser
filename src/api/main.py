"""
API FastAPI — Depression Posts Analyser.

Lancer :
  uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

Docs : http://localhost:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes import analysis_router, clean_router, pipeline_router, posts_router
from src.api.schemas import HealthResponse
from src.config import API_HOST, API_PORT, load_dotenv
from src.db.mongo import close, ensure_indexes, ping

load_dotenv()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        ensure_indexes()
    except Exception:
        pass
    yield
    close()


app = FastAPI(
    title="Depression Posts Analyser API",
    version="0.4.0",
    description=(
        "Bronze → Silver → Gold. "
        "Sentiment: tabularisai/multilingual-sentiment-analysis. "
        "Thèmes: MoritzLaurer/mDeBERTa-v3-base-mnli-xnli (zero-shot)."
    ),
    lifespan=lifespan,
)

app.include_router(posts_router, prefix="/api/v1")
app.include_router(clean_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
app.include_router(pipeline_router, prefix="/api/v1")


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    from src.config import MONGO_DB, MONGO_URI
    from src.db.mongo import get_posts_collection

    try:
        mongo = ping()
        mongo["uri"] = MONGO_URI
        mongo["db"] = MONGO_DB
        mongo["posts_count"] = get_posts_collection().count_documents({})
        status = "ok" if mongo.get("ok") else "degraded"
    except Exception as exc:
        mongo = {"ok": False, "uri": MONGO_URI, "db": MONGO_DB, "error": str(exc)}
        status = "degraded"
    return HealthResponse(status=status, mongo=mongo)


@app.get("/", tags=["system"])
def root() -> dict:
    return {
        "service": "depression-posts-analyser",
        "docs": "/docs",
        "health": "/health",
        "bronze_posts": "/api/v1/posts",
        "silver_clean": {
            "preview": "POST /api/v1/clean/text",
            "batch": "POST /api/v1/clean/batch",
            "list": "GET /api/v1/clean/posts",
        },
        "gold_analysis": {
            "sentiment_preview": "POST /api/v1/analysis/sentiment",
            "themes_preview": "POST /api/v1/analysis/themes",
            "batch_silver_to_gold": "POST /api/v1/analysis/sentiment/batch",
            "list": "GET /api/v1/analysis/posts",
        },
        "pipelines": {
            "full_scrape_clean_ml": "POST /api/v1/pipeline/full",
            "from_bronze_clean_ml": "POST /api/v1/pipeline/from-bronze",
        },
    }


def run() -> None:
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
    )


if __name__ == "__main__":
    run()
