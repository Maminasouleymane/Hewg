import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.db import Analysis
from app.models.schemas import (
    AnalysisMetadata, AnalysisResponse, AnalyzeRequest, AnalyzeStartResponse,
)
from app.services.analyzer import run_analysis
from app.services.npm_fetcher import parse_version

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeStartResponse)
async def start_analysis(
    body: AnalyzeRequest, tasks: BackgroundTasks, session: AsyncSession = Depends(get_session),
):
    lo, hi = parse_version(body.from_version), parse_version(body.to_version)
    if lo is None or hi is None:
        raise HTTPException(422, "Versions must be valid semver, e.g. 6.5.0")
    if lo >= hi:
        raise HTTPException(422, "from_version must be lower than to_version")
    analysis = Analysis(
        package_name=body.package_name.strip(), from_version=body.from_version,
        to_version=body.to_version, status="processing",
    )
    session.add(analysis)
    await session.commit()
    tasks.add_task(run_analysis, analysis.id)
    return AnalyzeStartResponse(analysis_id=analysis.id, status="processing")


@router.get("/analyze/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(analysis_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    a = await session.get(Analysis, analysis_id)
    if a is None:
        raise HTTPException(404, "Analysis not found")
    result = a.result or {}
    return AnalysisResponse(
        id=a.id, package_name=a.package_name, from_version=a.from_version,
        to_version=a.to_version, status=a.status, error=a.error,
        summary=result.get("summary"),
        total_breaking=result.get("total_breaking", 0),
        total_deprecated=result.get("total_deprecated", 0),
        total_new_features=result.get("total_new_features", 0),
        versions_analyzed=result.get("versions_analyzed", 0),
        changes=result.get("changes", []),
        metadata=AnalysisMetadata(
            model=a.model, prompt_version=a.prompt_version,
            tokens_used=a.tokens_used, duration_ms=a.duration_ms,
        ) if a.status == "completed" else None,
    )
