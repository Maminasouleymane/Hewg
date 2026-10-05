"""Embeds release notes into pgvector. Anthropic has no embeddings endpoint, so this uses
OpenAI's; without OPENAI_API_KEY embedding is skipped and the analysis still works
(phase 1 retrieval is a metadata filter, not vector search)."""
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.db import EMBEDDING_DIM, Release

MAX_INPUT_CHARS = 24_000


async def embed_texts(texts: list[str]) -> list[list[float]] | None:
    settings = get_settings()
    if not settings.openai_api_key or not texts:
        return None
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.embedding_model,
                "input": [t[:MAX_INPUT_CHARS] for t in texts],
                "dimensions": EMBEDDING_DIM,
            },
        )
        resp.raise_for_status()
        return [d["embedding"] for d in sorted(resp.json()["data"], key=lambda d: d["index"])]


async def embed_releases(session: AsyncSession, releases: list[Release]) -> int:
    """Embed releases lacking an embedding (cache check). Returns number newly embedded."""
    todo = [r for r in releases if r.embedding is None and r.changelog_raw]
    if not todo:
        return 0
    vectors = await embed_texts([f"{r.version}\n{r.changelog_raw}" for r in todo])
    if vectors is None:
        return 0
    for r, v in zip(todo, vectors):
        r.embedding = v
    await session.commit()
    return len(todo)
