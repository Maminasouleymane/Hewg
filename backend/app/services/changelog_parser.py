import re
from dataclasses import dataclass
from datetime import datetime

VERSION_RE = re.compile(r"(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?)$")
# "## [7.8.0](url) (2022-01-01)", "# 7.0.0-beta.1 (2021-..)", "## v1.2.3", "## [1.2.3] - 2020-01-01"
HEADER_RE = re.compile(r"^#{1,3}\s*\[?v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?)\]?", re.MULTILINE)
SECTION_RE = re.compile(r"^#{2,4}\s+.+$", re.MULTILINE)

# ~3000 tokens
MAX_CHUNK_CHARS = 12_000
BREAKING_HINTS = ("break", "remov", "deprecat", "migrat", "chang")


@dataclass
class ReleaseNote:
    version: str
    content: str
    source: str  # 'github_release' | 'changelog_md' | 'npm'
    date: datetime | None = None


def tag_to_version(tag: str) -> str | None:
    """'v1.2.3', 'rxjs@7.0.0', '@angular/core@14.0.0' -> bare version."""
    m = VERSION_RE.search(tag.strip())
    return m.group(1) if m else None


def split_changelog(markdown: str) -> dict[str, str]:
    """Split a CHANGELOG.md into {version: notes} by version headers."""
    matches = list(HEADER_RE.finditer(markdown))
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[m.start():end].strip()
        out.setdefault(m.group(1), body)
    return out


def merge_sources(*sources: list[ReleaseNote]) -> dict[str, ReleaseNote]:
    """Merge by version; earlier sources win, later ones fill gaps (and missing dates)."""
    merged: dict[str, ReleaseNote] = {}
    for source in sources:
        for note in source:
            existing = merged.get(note.version)
            if existing is None:
                merged[note.version] = note
            elif existing.date is None and note.date:
                existing.date = note.date
    return merged


def split_release(content: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split a release's content into chunks under max_chars, breaking-relevant sections
    packed first. Unlike truncation, nothing is dropped - an oversized release becomes
    multiple chunks instead of losing whatever didn't fit."""
    if len(content) <= max_chars:
        return [content]
    parts = _split_sections(content)
    parts.sort(key=lambda p: 0 if any(h in p.splitlines()[0].lower() for h in BREAKING_HINTS) else 1)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for p in parts:
        if current and current_len + len(p) > max_chars:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0
        current.append(p)
        current_len += len(p)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _split_sections(text: str) -> list[str]:
    idx = [m.start() for m in SECTION_RE.finditer(text)]
    if not idx:
        return [text]
    bounds = [0, *idx] if idx[0] != 0 else idx
    return [text[a:b].strip() for a, b in zip(bounds, [*bounds[1:], len(text)]) if text[a:b].strip()]
