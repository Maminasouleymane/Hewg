"""In-process progress bus + SSE endpoint. Events are kept so late subscribers replay history."""
import asyncio
import json
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.db import Analysis

router = APIRouter()

_events: dict[str, list[tuple[str, dict]]] = defaultdict(list)
_conds: dict[str, asyncio.Condition] = defaultdict(asyncio.Condition)
TERMINAL = ("complete", "error")


async def publish(analysis_id: str, event: str, data: dict) -> None:
    _events[analysis_id].append((event, data))
    async with _conds[analysis_id]:
        _conds[analysis_id].notify_all()


def _format(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _stream(analysis_id: str) -> AsyncIterator[str]:
    i = 0
    while True:
        async with _conds[analysis_id]:
            await _conds[analysis_id].wait_for(lambda: len(_events[analysis_id]) > i)
        while i < len(_events[analysis_id]):
            event, data = _events[analysis_id][i]
            i += 1
            yield _format(event, data)
            if event in TERMINAL:
                return


@router.get("/analyze/{analysis_id}/status")
async def status_stream(analysis_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    key = str(analysis_id)
    if key not in _events:  # e.g. server restarted: answer from the DB
        analysis = await session.get(Analysis, analysis_id)
        if analysis is None:
            raise HTTPException(404, "Analysis not found")
        if analysis.status == "completed":
            _events[key].append(("complete", {"analysis_id": key, "status": "completed"}))
        elif analysis.status == "failed":
            _events[key].append(("error", {"message": analysis.error or "Analysis failed", "step": "unknown"}))
    return StreamingResponse(
        _stream(key), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
