from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.schemas import Change, LLMResult
from app.services import llm

FIX = Path(__file__).parent / "fixtures"


def fake_complete(*texts):
    calls = iter(texts)

    async def complete(system: str, user: str) -> tuple[str, int, int]:
        return next(calls), 10, 5
    return complete


NOTES = [("7.0.0", "removed toPromise")]


async def test_valid_response_recounts_totals():
    out = await llm.analyze("rxjs", "6.5.0", "7.0.0", NOTES,
                             complete_fn=fake_complete((FIX / "llm_response.json").read_text()))
    assert out.result.total_breaking == 1  # model said 99
    assert out.tokens_used == 15


async def test_retries_once_then_succeeds():
    good = "```json\n" + (FIX / "llm_response.json").read_text() + "\n```"
    out = await llm.analyze("rxjs", "6.5.0", "7.0.0", NOTES,
                             complete_fn=fake_complete("not json", good))
    assert out.tokens_used == 30


async def test_fails_after_second_bad_response():
    with pytest.raises(llm.LLMError):
        await llm.analyze("rxjs", "6.5.0", "7.0.0", NOTES,
                           complete_fn=fake_complete("nope", "still nope"))


def test_prompt_renders():
    p = llm.build_user_prompt("rxjs", "6.5.0", "7.0.0", NOTES)
    assert '"rxjs"' in p and "=== rxjs 7.0.0 ===" in p and '"summary"' in p


async def test_complete_openai_compatible_extracts_text_and_tokens(monkeypatch):
    class FakeClient:
        def __init__(self, **kw):
            pass

        class chat:
            class completions:
                @staticmethod
                async def create(**kw):
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content="hello"))],
                        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
                    )

    monkeypatch.setattr(llm, "AsyncOpenAI", FakeClient)
    text, in_tok, out_tok = await llm._complete_openai_compatible("sys", "usr")
    assert (text, in_tok, out_tok) == ("hello", 7, 3)


def _status_error(status_code: int):
    import httpx
    from openai import APIStatusError
    resp = httpx.Response(status_code, request=httpx.Request("POST", "https://x.test"))
    return APIStatusError("boom", response=resp, body=None)


async def test_complete_openai_compatible_retries_on_503_then_succeeds(monkeypatch):
    calls = {"n": 0}

    class FakeClient:
        def __init__(self, **kw):
            pass

        class chat:
            class completions:
                @staticmethod
                async def create(**kw):
                    calls["n"] += 1
                    if calls["n"] == 1:
                        raise _status_error(503)
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
                    )

    async def no_sleep(*a, **kw):
        return None

    monkeypatch.setattr(llm, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)
    text, in_tok, out_tok = await llm._complete_openai_compatible("sys", "usr")
    assert (text, in_tok, out_tok) == ("ok", 1, 1)
    assert calls["n"] == 2


async def test_complete_openai_compatible_does_not_retry_non_transient_error(monkeypatch):
    calls = {"n": 0}

    class FakeClient:
        def __init__(self, **kw):
            pass

        class chat:
            class completions:
                @staticmethod
                async def create(**kw):
                    calls["n"] += 1
                    raise _status_error(400)

    monkeypatch.setattr(llm, "AsyncOpenAI", FakeClient)
    with pytest.raises(Exception):
        await llm._complete_openai_compatible("sys", "usr")
    assert calls["n"] == 1


def test_batch_notes_splits_on_budget():
    notes = [("1.0.0", "x" * 50), ("1.1.0", "x" * 50), ("1.2.0", "x" * 50)]
    batches = llm.batch_notes(notes, max_tokens=30)  # 120 chars/batch budget
    assert batches == [[notes[0], notes[1]], [notes[2]]]


def test_batch_notes_oversized_entry_gets_its_own_batch():
    notes = [("1.0.0", "x" * 500), ("1.1.0", "y" * 10)]
    batches = llm.batch_notes(notes, max_tokens=30)  # 120 chars/batch budget
    assert batches == [[notes[0]], [notes[1]]]
    assert sum(len(b) for b in batches) == len(notes)  # nothing dropped


def _change(id_, category, severity="HIGH", title="t"):
    return Change(id=id_, category=category, severity=severity, title=title)


def test_merge_results_combines_changes_and_recounts():
    out1 = llm.LLMOutput(
        LLMResult(summary="first half.", changes=[_change("a", "BREAKING", severity="LOW")]),
        "m", "v1", 10,
    )
    out2 = llm.LLMOutput(
        LLMResult(summary="second half.", changes=[_change("b", "DEPRECATED", severity="LOW"),
                                                     _change("c", "BREAKING", severity="LOW")]),
        "m", "v1", 20,
    )
    merged = llm.merge_results([out1, out2])
    assert [c.id for c in merged.result.changes] == ["a", "b", "c"]
    assert merged.result.total_breaking == 2
    assert merged.result.total_deprecated == 1
    assert merged.tokens_used == 30
    assert merged.model == "m" and merged.prompt_version == "v1"
    # multi-batch: deterministic overview, not the two summaries concatenated
    assert merged.result.summary == (
        "3 changes across 2 version batches — 2 breaking (0 critical), "
        "1 deprecation, 0 new features, 0 bug fixes."
    )


def test_merge_results_keeps_single_batch_summary_unchanged():
    out = llm.LLMOutput(
        LLMResult(summary="Hand-written, full-context summary.", changes=[_change("a", "BREAKING")]),
        "m", "v1", 10,
    )
    merged = llm.merge_results([out])
    assert merged.result.summary == "Hand-written, full-context summary."


def test_merge_results_overview_highlights_critical_and_high_by_title():
    out1 = llm.LLMOutput(
        LLMResult(summary="a", changes=[
            _change("a", "BREAKING", severity="CRITICAL", title="Removed ComponentFactoryResolver"),
            _change("b", "NEW_FEATURE", severity="LOW", title="New signal API"),
        ]),
        "m", "v1", 5,
    )
    out2 = llm.LLMOutput(
        LLMResult(summary="b", changes=[
            _change("c", "BREAKING", severity="HIGH", title="Hammer.js integration removed"),
        ]),
        "m", "v1", 5,
    )
    merged = llm.merge_results([out1, out2])
    assert "2 breaking (1 critical)" in merged.result.summary
    assert "Highest risk: Removed ComponentFactoryResolver, Hammer.js integration removed." \
        in merged.result.summary
    assert "New signal API" not in merged.result.summary  # low severity, not a highlight


def test_merge_results_overview_caps_highlights_at_three_with_many_criticals():
    """Regression test: with 4+ CRITICAL items already, `3 - len(highlights)` goes negative -
    a plain slice with a negative stop would wrongly pull in extra HIGH items instead of none."""
    criticals = [_change(f"c{i}", "BREAKING", severity="CRITICAL", title=f"fatal-{i}")
                 for i in range(4)]
    highs = [_change("h1", "BREAKING", severity="HIGH", title="should-not-appear")]
    out = llm.LLMOutput(LLMResult(summary="a", changes=criticals + highs), "m", "v1", 5)
    merged = llm.merge_results([out, out])  # 2 outputs so the overview path is used

    highlights_line = merged.result.summary.split("Highest risk: ")[1]
    shown_titles = highlights_line.rstrip(".").split(", ")
    assert "should-not-appear" not in shown_titles
    assert len(shown_titles) == 3
