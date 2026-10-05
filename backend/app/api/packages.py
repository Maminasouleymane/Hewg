from fastapi import APIRouter, HTTPException
from packaging.version import Version

import httpx

from app.models.schemas import VersionsResponse
from app.services.npm_fetcher import PackageNotFound, fetch_package, parse_version

router = APIRouter()


@router.get("/packages/{name:path}/versions", response_model=VersionsResponse)
async def package_versions(name: str):
    try:
        info = await fetch_package(name)
    except PackageNotFound:
        raise HTTPException(404, f"Package '{name}' not found on npm")
    except httpx.HTTPError as e:
        raise HTTPException(502, f"npm registry error: {e}")
    parsed = [(p, v) for v in info.versions if (p := parse_version(v))]
    parsed.sort(key=lambda t: t[0], reverse=True)  # newest first
    return VersionsResponse(package_name=name, versions=[v for _, v in parsed])
