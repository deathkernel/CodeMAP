"""FastAPI application entry point for CodeMap."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.analysis import router as analysis_router
from app.routes.repository import router as repository_router

app = FastAPI(
    title="CodeMap API",
    description="Local-first codebase intelligence API.",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(repository_router)
app.include_router(analysis_router)


@app.get("/api/health", tags=["system"])
async def health() -> dict[str, str]:
    """Return API health without exposing local configuration or secrets."""
    return {"status": "ok", "service": "codemap-api"}
