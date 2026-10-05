import asyncio
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from anthropic import AsyncAnthropic
from openai import APIConnectionError, APIStatusError, AsyncOpenAI
from pydantic import ValidationError

from app.config import get_settings
from app.models.schemas import LLMResult

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class LLMError(Exception):
    pass


@dataclass
class LLMOutput:
    result: LLMResult
    model: str
    prompt_version: str
    tokens_used: int


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text()


def build_user_prompt(package: str, from_version: str, to_version: str, notes: list[tuple[str, str]]) -> str:
    sections = "\n\n".join(f"=== {package} {version} ===\n{text}" for version, text in notes)
    return load_prompt(f"analyze_{get_settings().prompt_version}.txt").format(
        package_name=package, from_version=from_version, to_version=to_version,
        release_notes_sections=sections,
    )


def parse_result(text: str) -> LLMResult:
    """Parse Claude's JSON, tolerating stray markdown fences."""
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip())
    return LLMResult.model_validate_json(text)


def _recount(result: LLMResult) -> LLMResult:
    """Derive totals from the changes rather than trusting the model's arithmetic."""
    result.total_breaking = sum(c.category == "BREAKING" for c in result.changes)
    result.total_deprecated = sum(c.category == "DEPRECATED" for c in result.changes)
    result.total_new_features = sum(c.category == "NEW_FEATURE" for c in result.changes)
    return result


CompleteFn = Callable[[str, str], Awaitable[tuple[str, int, int]]]  # (system, user) -> (text, in_tok, out_tok)


async def _complete_anthropic(system: str, user: str) -> tuple[str, int, int]:
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=settings.analysis_model, max_tokens=settings.max_output_tokens,
        system=system, messages=[{"role": "user", "content": user}],
        extra_body={"temperature": 0},  # SDK 1.x dropped the kwarg; the model still honours it
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return text, resp.usage.input_tokens, resp.usage.output_tokens


RETRYABLE_STATUSES = {429, 500, 502, 503, 504}  # rate limit / transient provider errors
MAX_PROVIDER_RETRIES = 3


async def _complete_openai_compatible(system: str, user: str) -> tuple[str, int, int]:
    settings = get_settings()
    # max_retries=0: we own retry/backoff below instead of the SDK's own, so they don't stack.
    client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url, max_retries=0)
    extra = {"reasoning_effort": settings.llm_reasoning_effort} if settings.llm_reasoning_effort else {}

    for attempt in range(MAX_PROVIDER_RETRIES + 1):
        try:
            resp = await client.chat.completions.create(
                model=settings.analysis_model, max_tokens=settings.llm_max_output_tokens, temperature=0,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                **extra,
            )
            usage = resp.usage
            return resp.choices[0].message.content, usage.prompt_tokens, usage.completion_tokens
        except (APIStatusError, APIConnectionError) as e:
            status = getattr(e, "status_code", None)
            if attempt == MAX_PROVIDER_RETRIES or (status is not None and status not in RETRYABLE_STATUSES):
                raise
            retry_after = getattr(getattr(e, "response", None), "headers", {}).get("retry-after")
            await asyncio.sleep(float(retry_after) if retry_after else 2 ** attempt + random.random())
    raise AssertionError("unreachable")


async def _dispatch(system: str, user: str) -> tuple[str, int, int]:
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        return await _complete_anthropic(system, user)
    return await _complete_openai_compatible(system, user)


async def analyze(
    package: str, from_version: str, to_version: str, notes: list[tuple[str, str]],
    complete_fn: CompleteFn | None = None,
) -> LLMOutput:
    settings = get_settings()
    complete_fn = complete_fn or _dispatch
    system = load_prompt(f"system_{settings.prompt_version}.txt")
    user = build_user_prompt(package, from_version, to_version, notes)
    tokens = 0

    for attempt in range(2):
        text, in_tok, out_tok = await complete_fn(system, user)
        tokens += in_tok + out_tok
        try:
            return LLMOutput(_recount(parse_result(text)), settings.analysis_model,
                             settings.prompt_version, tokens)
        except (ValidationError, ValueError) as e:
            if attempt == 1:
                raise LLMError(f"LLM returned invalid JSON twice: {e}") from e
            user = (
                f"{user}\n\n--- Your previous response ---\n{text}\n\n"
                f"--- That response failed validation ---\n{e}\n\n"
                "Respond again with ONLY the corrected JSON object matching the schema."
            )
    raise LLMError("unreachable")


def batch_notes(notes: list[tuple[str, str]], max_tokens: int) -> list[list[tuple[str, str]]]:
    """Group chronologically-sorted notes into batches, each under max_tokens (~chars/4)."""
    max_chars = max_tokens * 4
    batches: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    current_len = 0
    for version, text in notes:
        if current and current_len + len(text) > max_chars:
            batches.append(current)
            current, current_len = [], 0
        current.append((version, text))
        current_len += len(text)
    if current:
        batches.append(current)
    return batches


def merge_results(outputs: list[LLMOutput]) -> LLMOutput:
    """Combine per-batch LLMOutputs into one, recounting totals over the merged changes."""
    changes = [c for out in outputs for c in out.result.changes]
    summary = " ".join(out.result.summary for out in outputs)
    merged = _recount(LLMResult(summary=summary, total_breaking=0, total_deprecated=0,
                                 total_new_features=0, changes=changes))
    return LLMOutput(merged, outputs[0].model, outputs[0].prompt_version,
                      sum(o.tokens_used for o in outputs))
