import json
from pathlib import Path

from app.services.changelog_parser import (
    ReleaseNote, merge_sources, split_changelog, split_release, tag_to_version,
)
from app.services.github_fetcher import parse_releases, parse_repo
from app.services.npm_fetcher import filter_versions, parse_registry_response

FIX = Path(__file__).parent / "fixtures"


def test_tag_to_version():
    assert tag_to_version("v1.2.3") == "1.2.3"
    assert tag_to_version("@angular/core@14.0.0") == "14.0.0"
    assert tag_to_version("nightly") is None


def test_split_changelog_variants():
    parts = split_changelog((FIX / "rxjs_changelog.md").read_text())
    assert set(parts) == {"7.0.0", "6.6.7", "6.6.0"}
    assert "toPromise" in parts["7.0.0"]
    assert "retryWhen" in parts["6.6.7"] and "toPromise" not in parts["6.6.7"]


def test_parse_repo():
    assert parse_repo("git+https://github.com/ReactiveX/rxjs.git") == ("ReactiveX", "rxjs")
    assert parse_repo("github:angular/angular") == ("angular", "angular")
    assert parse_repo("git@github.com:o/r.git") == ("o", "r")
    assert parse_repo("https://gitlab.com/o/r") is None


def test_releases_and_merge():
    releases = parse_releases(json.loads((FIX / "rxjs_releases.json").read_text()))
    assert [r.version for r in releases] == ["7.0.0", "6.6.7"]  # empty body dropped
    md = [ReleaseNote("7.0.0", "from md", "changelog_md"), ReleaseNote("6.6.0", "x", "changelog_md")]
    merged = merge_sources(releases, md)
    assert merged["7.0.0"].source == "github_release"
    assert "6.6.0" in merged


def test_registry_and_range():
    info = parse_registry_response("rxjs", json.loads((FIX / "npm_rxjs.json").read_text()))
    assert info.latest_version == "7.8.0" and info.repo_url.endswith("rxjs.git")
    # (from, to], stable only, junk ignored
    assert filter_versions(list(info.versions), "6.5.0", "7.8.0") == ["6.6.7", "7.0.0", "7.8.0"]


def test_split_release_packs_breaking_first_and_drops_nothing():
    text = "## Features\n" + "f" * 100 + "\n\n## Breaking Changes\n" + "b" * 100 + "\n\n## Docs\n" + "d" * 100
    chunks = split_release(text, max_chars=150)
    assert len(chunks) > 1
    assert "Breaking Changes" in chunks[0]
    joined = "".join(chunks)
    assert "f" * 100 in joined and "d" * 100 in joined  # nothing dropped, just split


def test_split_release_single_chunk_when_small():
    assert split_release("short content") == ["short content"]
