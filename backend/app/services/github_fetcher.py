import re
from datetime import datetime

import httpx

from app.config import get_settings
from app.services.changelog_parser import ReleaseNote, merge_sources, split_changelog, tag_to_version

API = "https://api.github.com"
GITHUB_RE = re.compile(r"github(?:\.com)?[:/]+([^/\s]+)/([^/\s#]+?)(?:\.git)?(?:[/#].*)?$")


class GitHubRateLimited(Exception):
    pass


def parse_repo(repo_url: str | None) -> tuple[str, str] | None:
    """'git+https://github.com/ReactiveX/rxjs.git' / 'github:o/r' -> ('ReactiveX', 'rxjs')."""
    if not repo_url:
        return None
    m = GITHUB_RE.search(repo_url.strip())
    return (m.group(1), m.group(2)) if m else None


def _headers(accept: str = "application/vnd.github+json") -> dict[str, str]:
    h = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    if token := get_settings().github_token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _check_rate_limit(resp: httpx.Response) -> None:
    if resp.status_code in (403, 429) and resp.headers.get("x-ratelimit-remaining") == "0":
        raise GitHubRateLimited("GitHub API rate limit exceeded; set GITHUB_TOKEN to raise it")


def parse_releases(releases: list[dict]) -> list[ReleaseNote]:
    notes = []
    for r in releases:
        version = tag_to_version(r.get("tag_name") or "")
        body = (r.get("body") or "").strip()
        if not version or not body:
            continue
        date = r.get("published_at")
        notes.append(ReleaseNote(
            version=version, content=body, source="github_release",
            date=datetime.fromisoformat(date.replace("Z", "+00:00")) if date else None,
        ))
    return notes


async def fetch_releases(client: httpx.AsyncClient, owner: str, repo: str, max_pages: int = 5) -> list[ReleaseNote]:
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        resp = await client.get(
            f"{API}/repos/{owner}/{repo}/releases",
            params={"per_page": 100, "page": page}, headers=_headers(),
        )
        _check_rate_limit(resp)
        if resp.status_code == 404:
            break
        resp.raise_for_status()
        batch = resp.json()
        out.extend(batch)
        if len(batch) < 100:
            break
    return parse_releases(out)


async def fetch_changelog_md(client: httpx.AsyncClient, owner: str, repo: str) -> list[ReleaseNote]:
    resp = await client.get(
        f"{API}/repos/{owner}/{repo}/contents/CHANGELOG.md",
        headers=_headers("application/vnd.github.raw+json"),
    )
    _check_rate_limit(resp)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return [
        ReleaseNote(version=v, content=body, source="changelog_md")
        for v, body in split_changelog(resp.text).items()
    ]


async def fetch_changelogs(repo_url: str | None, client: httpx.AsyncClient | None = None) -> dict[str, ReleaseNote]:
    """GitHub releases first, CHANGELOG.md fills the gaps. Empty dict if no GitHub repo."""
    repo = parse_repo(repo_url)
    if repo is None:
        return {}
    own = client is None
    client = client or httpx.AsyncClient(timeout=30, follow_redirects=True)
    try:
        releases = await fetch_releases(client, *repo)
        changelog = await fetch_changelog_md(client, *repo)
        return merge_sources(releases, changelog)
    finally:
        if own:
            await client.aclose()
