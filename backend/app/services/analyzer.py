import logging
import time
import uuid

import httpx
from openai import BadRequestError
from sqlalchemy import select

from app.api.sse import publish
from app.config import get_settings
from app.database import SessionLocal
from app.models.db import Analysis, Package, Release
from app.services import embedder, github_fetcher, llm, npm_fetcher
from app.services.changelog_parser import ReleaseNote, split_release
from app.services.npm_fetcher import PackageNotFound, parse_version

log = logging.getLogger(__name__)


class StepError(Exception):
    def __init__(self, step: str, message: str):
        super().__init__(message)
        self.step, self.message = step, message


async def _progress(aid: str, step: str, message: str, progress: int) -> None:
    await publish(aid, "progress", {"step": step, "message": message, "progress": progress})


MAX_SPLIT_DEPTH = 3  # a batch whose response overflows max_tokens is halved up to this many times


def _split_text_in_half(text: str) -> tuple[str, str]:
    """Split text near its midpoint, preferring a paragraph/line boundary over a hard cut."""
    mid = len(text) // 2
    boundary = text.rfind("\n\n", 0, mid)
    if boundary == -1:
        boundary = text.rfind("\n", 0, mid)
    if boundary == -1:
        boundary = mid
    return text[:boundary].strip(), text[boundary:].strip()


async def _analyze_batch(name: str, batch: list[tuple[str, str]], depth: int = 0) -> list[llm.LLMOutput]:
    """Analyze a batch; if its response is too large to fit the output budget (a JSON-validation
    failure, not a content/correctness one), split it and retry each half instead of failing
    outright. A multi-item batch splits by item; a single item too dense to split that way (e.g.
    one release with many changes crammed under one heading) has its text itself split in half."""
    b_from, b_to = batch[0][0], batch[-1][0]
    try:
        return [await llm.analyze(name, b_from, b_to, batch)]
    except (llm.LLMError, BadRequestError):
        if depth >= MAX_SPLIT_DEPTH:
            raise
        if len(batch) > 1:
            mid = len(batch) // 2
            left, right = batch[:mid], batch[mid:]
        else:
            version, text = batch[0]
            half1, half2 = _split_text_in_half(text)
            if not half1 or not half2:
                raise
            left = [(f"{version} (split 1/2)", half1)]
            right = [(f"{version} (split 2/2)", half2)]
        return (await _analyze_batch(name, left, depth + 1)
                + await _analyze_batch(name, right, depth + 1))


async def run_analysis(analysis_id: uuid.UUID) -> None:
    """Background task: full pipeline. Never raises; failures become an `error` event + status."""
    aid, started, step = str(analysis_id), time.monotonic(), "fetching_registry"
    async with SessionLocal() as session:
        analysis = await session.get(Analysis, analysis_id)
        # plain copies: a rollback expires ORM objects, and lazy reloads fail under asyncio
        name, from_v, to_v = analysis.package_name, analysis.from_version, analysis.to_version
        try:
            analysis.status = "processing"
            await session.commit()

            # 1. npm registry
            await _progress(aid, step, "Fetching release notes from npm registry…", 10)
            try:
                info = await npm_fetcher.fetch_package(name)
            except PackageNotFound:
                raise StepError(step, f"Package '{name}' was not found on npm")
            try:
                versions = npm_fetcher.filter_versions(
                    list(info.versions), from_v, to_v)
            except ValueError as e:
                raise StepError(step, str(e))
            if not versions:
                raise StepError(step, "No published versions found in that range")
            pkg_id = (await npm_fetcher.cache_package(session, info)).id

            # 2. changelogs (skip versions already cached)
            step = "fetching_changelogs"
            cached = {r.version: r for r in (await session.execute(
                select(Release).where(Release.package_id == pkg_id, Release.version.in_(versions)))).scalars()
                if r.changelog_raw}
            missing = [v for v in versions if v not in cached]
            await _progress(aid, step, f"Reading {len(missing)} changelogs from GitHub…", 30)
            fetched: dict[str, ReleaseNote] = {}
            if missing:
                try:
                    fetched = await github_fetcher.fetch_changelogs(info.repo_url)
                except github_fetcher.GitHubRateLimited as e:
                    raise StepError(step, str(e))
                except httpx.HTTPError as e:
                    raise StepError(step, f"Failed to fetch changelogs from GitHub: {e}")

            # 3-4. chunk, store, embed
            step = "embedding"
            await _progress(aid, step, "Processing changelog data…", 50)
            for v in missing:
                note = fetched.get(v) or ReleaseNote(
                    v, "No release notes were published for this version.", "npm")
                row = (await session.execute(select(Release).where(
                    Release.package_id == pkg_id, Release.version == v))).scalar_one_or_none()
                row = row or Release(package_id=pkg_id, version=v)
                row.release_date = note.date or info.versions.get(v)
                row.changelog_raw = note.content  # stored in full; split into chunks at use time
                row.changelog_source = note.source
                session.add(row)
            await session.commit()
            try:
                # embeddings are a cache; a failure must not fail the analysis
                rows = (await session.execute(select(Release).where(
                    Release.package_id == pkg_id, Release.version.in_(versions)))).scalars().all()
                await embedder.embed_releases(session, list(rows))
            except Exception:
                log.warning("embedding failed; continuing without", exc_info=True)
                await session.rollback()

            # 5. retrieve in chronological order, splitting any oversized release into
            # multiple chunks (sized to the batch budget) instead of truncating it
            settings = get_settings()
            rows = (await session.execute(select(Release).where(
                Release.package_id == pkg_id, Release.version.in_(versions)))).scalars().all()
            rows = sorted(rows, key=lambda r: parse_version(r.version))
            notes: list[tuple[str, str]] = []
            for r in rows:
                chunks = split_release(r.changelog_raw or "", max_chars=settings.max_batch_tokens * 4)
                if len(chunks) == 1:
                    notes.append((r.version, chunks[0]))
                else:
                    notes.extend((f"{r.version} (part {i}/{len(chunks)})", c)
                                 for i, c in enumerate(chunks, start=1))

            # 6. LLM analysis, batched to stay under provider token-rate limits
            step = "analyzing"
            batches = llm.batch_notes(notes, settings.max_batch_tokens)
            outs = []
            for i, batch in enumerate(batches, start=1):
                pct = 75 + round(15 * (i - 1) / len(batches))
                b_from, b_to = batch[0][0], batch[-1][0]
                await _progress(aid, step, f"Analyzing versions {b_from}–{b_to} ({i}/{len(batches)})…", pct)
                try:
                    outs.extend(await _analyze_batch(name, batch))
                except (llm.LLMError, BadRequestError) as e:
                    raise StepError(step, f"batch {i}/{len(batches)} ({b_from}–{b_to}): {e}")
            out = llm.merge_results(outs)

            # 7. store
            step = "generating"
            await _progress(aid, step, "Shaping your migration guide…", 90)
            analysis.result = {**out.result.model_dump(), "versions_analyzed": len(rows)}
            analysis.model, analysis.prompt_version = out.model, out.prompt_version
            analysis.tokens_used = out.tokens_used
            analysis.duration_ms = int((time.monotonic() - started) * 1000)
            analysis.status = "completed"
            await session.commit()
            await publish(aid, "complete", {"analysis_id": aid, "status": "completed"})
        except StepError as e:
            await _fail(session, analysis, aid, e.step, e.message)
        except Exception as e:
            log.exception("analysis %s failed", aid)
            await _fail(session, analysis, aid, step, f"Unexpected error: {e}")


async def _fail(session, analysis: Analysis, aid: str, step: str, message: str) -> None:
    await session.rollback()
    analysis.status, analysis.error = "failed", message
    await session.commit()
    await publish(aid, "error", {"message": message, "step": step})
