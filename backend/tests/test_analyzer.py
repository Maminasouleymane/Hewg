import httpx
import pytest
from openai import APIStatusError

from app.models.schemas import Change, LLMResult
from app.services import analyzer, llm


def _out(version):
    return llm.LLMOutput(
        LLMResult(summary=f"s{version}", changes=[Change(id=version, category="BUGFIX", severity="LOW", title="t")]),
        "m", "v1", 5,
    )


def _status_error(status_code: int) -> APIStatusError:
    resp = httpx.Response(status_code, request=httpx.Request("POST", "https://x.test"))
    return APIStatusError("boom", response=resp, body=None)


async def test_analyze_batch_splits_on_llm_error(monkeypatch):
    calls = []

    async def fake_analyze(name, b_from, b_to, batch, complete_fn=None):
        calls.append(len(batch))
        if len(batch) > 1:
            raise llm.LLMError("too big")
        return _out(batch[0][0])

    monkeypatch.setattr(llm, "analyze", fake_analyze)
    batch = [("1.0.0", "a"), ("1.1.0", "b"), ("1.2.0", "c"), ("1.3.0", "d")]
    outs = await analyzer._analyze_batch("pkg", batch)
    assert [o.result.summary for o in outs] == ["s1.0.0", "s1.1.0", "s1.2.0", "s1.3.0"]
    assert calls[0] == 4  # first attempt at full batch size fails
    assert calls.count(1) == 4  # eventually succeeds one version at a time


async def test_analyze_batch_gives_up_at_single_version_with_short_text(monkeypatch):
    async def fake_analyze(name, b_from, b_to, batch, complete_fn=None):
        raise llm.LLMError("always too big")

    monkeypatch.setattr(llm, "analyze", fake_analyze)
    with pytest.raises(llm.LLMError):
        await analyzer._analyze_batch("pkg", [("1.0.0", "a")])


async def test_analyze_batch_splits_text_when_single_item_too_dense(monkeypatch):
    calls = []

    async def fake_analyze(name, b_from, b_to, batch, complete_fn=None):
        text = batch[0][1]
        calls.append(text)
        if len(text) > 15:
            raise llm.LLMError("too dense")
        return _out(b_from)

    monkeypatch.setattr(llm, "analyze", fake_analyze)
    text = "\n\n".join(f"change {i}" for i in range(4))  # too long for one call, splittable
    outs = await analyzer._analyze_batch("pkg", [("1.0.0", text)])
    assert len(outs) > 1  # had to split at least once
    assert len(calls) > 1


async def test_analyze_batch_gives_up_when_always_too_dense(monkeypatch):
    async def fake_analyze(name, b_from, b_to, batch, complete_fn=None):
        raise llm.LLMError("always too dense")

    monkeypatch.setattr(llm, "analyze", fake_analyze)
    text = "\n\n".join(f"change {i}" for i in range(10))
    with pytest.raises(llm.LLMError):
        await analyzer._analyze_batch("pkg", [("1.0.0", text)])


async def test_analyze_batch_splits_on_413_request_too_large(monkeypatch):
    """Regression test: 413 (request too large for the provider's TPM limit) has no
    dedicated openai SDK subclass - it's the generic APIStatusError - so it used to slip
    past the except clause entirely instead of triggering a split, unlike the 400 case."""
    calls = []

    async def fake_analyze(name, b_from, b_to, batch, complete_fn=None):
        calls.append(len(batch))
        if len(batch) > 1:
            raise _status_error(413)
        return _out(batch[0][0])

    monkeypatch.setattr(llm, "analyze", fake_analyze)
    batch = [("1.0.0", "a"), ("1.1.0", "b"), ("1.2.0", "c"), ("1.3.0", "d")]
    outs = await analyzer._analyze_batch("pkg", batch)
    assert [o.result.summary for o in outs] == ["s1.0.0", "s1.1.0", "s1.2.0", "s1.3.0"]
    assert calls.count(1) == 4


async def test_analyze_batch_does_not_retry_unrelated_errors(monkeypatch):
    """A 401/403/etc isn't a size problem - splitting can't fix it, so it must re-raise
    immediately instead of burning through the split budget on something unsplittable."""
    calls = []

    async def fake_analyze(name, b_from, b_to, batch, complete_fn=None):
        calls.append(len(batch))
        raise _status_error(401)

    monkeypatch.setattr(llm, "analyze", fake_analyze)
    batch = [("1.0.0", "a"), ("1.1.0", "b")]
    with pytest.raises(APIStatusError):
        await analyzer._analyze_batch("pkg", batch)
    assert calls == [2]  # one attempt, no split attempted
