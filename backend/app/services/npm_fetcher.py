from dataclasses import dataclass, field
from datetime import datetime

import httpx
from packaging.version import InvalidVersion, Version
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Package

REGISTRY_URL = "https://registry.npmjs.org"


class PackageNotFound(Exception):
    pass


@dataclass
class PackageInfo:
    name: str
    latest_version: str | None
    repo_url: str | None
    versions: dict[str, datetime | None] = field(default_factory=dict)


def parse_version(raw: str) -> Version | None:
    try:
        return Version(raw)
    except InvalidVersion:
        return None


def parse_registry_response(name: str, data: dict) -> PackageInfo:
    repo = data.get("repository")
    repo_url = repo.get("url") if isinstance(repo, dict) else repo
    times = data.get("time", {})
    versions: dict[str, datetime | None] = {}
    for v in data.get("versions", {}):
        ts = times.get(v)
        versions[v] = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
    return PackageInfo(
        name=name,
        latest_version=data.get("dist-tags", {}).get("latest"),
        repo_url=repo_url,
        versions=versions,
    )


def filter_versions(versions: list[str], from_version: str, to_version: str) -> list[str]:
    """Stable versions in (from, to], oldest first."""
    lo, hi = parse_version(from_version), parse_version(to_version)
    if lo is None or hi is None:
        raise ValueError("from_version and to_version must be valid semver versions")
    parsed = [(p, v) for v in versions if (p := parse_version(v)) and not p.is_prerelease]
    return [v for p, v in sorted(parsed) if lo < p <= hi]


async def fetch_package(name: str, client: httpx.AsyncClient | None = None) -> PackageInfo:
    own = client is None
    client = client or httpx.AsyncClient(timeout=30)
    try:
        # scoped names (@scope/pkg) need the slash encoded
        resp = await client.get(f"{REGISTRY_URL}/{name.replace('/', '%2F')}")
        if resp.status_code == 404:
            raise PackageNotFound(name)
        resp.raise_for_status()
        return parse_registry_response(name, resp.json())
    finally:
        if own:
            await client.aclose()


async def cache_package(session: AsyncSession, info: PackageInfo) -> Package:
    pkg = (await session.execute(select(Package).where(Package.name == info.name))).scalar_one_or_none()
    if pkg is None:
        pkg = Package(name=info.name)
        session.add(pkg)
    pkg.latest_version = info.latest_version
    pkg.repo_url = info.repo_url
    pkg.fetched_at = datetime.now().astimezone()
    await session.commit()
    return pkg
