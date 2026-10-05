import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analyze, packages, sse
from app.config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(title="Hewg", description="Your dependency blacksmith")
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins,
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(analyze.router, prefix="/api")
app.include_router(sse.router, prefix="/api")
app.include_router(packages.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
