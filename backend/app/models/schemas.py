import uuid
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["BREAKING", "DEPRECATED", "NEW_FEATURE", "BUGFIX", "INTERNAL"]
Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]


class AnalyzeRequest(BaseModel):
    package_name: str = Field(min_length=1, max_length=255)
    from_version: str = Field(min_length=1, max_length=50)
    to_version: str = Field(min_length=1, max_length=50)


class AnalyzeStartResponse(BaseModel):
    analysis_id: uuid.UUID
    status: str


class Change(BaseModel):
    id: str
    category: Category
    severity: Severity
    title: str
    affected_api: str = ""
    explanation: str = ""
    migration_action: str | None = None
    before_code: str | None = None
    after_code: str | None = None
    source_version: str = ""
    reasoning: str = ""
    doc_reference: str = ""


class LLMResult(BaseModel):
    """Schema Claude's JSON output is validated against."""

    summary: str
    total_breaking: int = 0
    total_deprecated: int = 0
    total_new_features: int = 0
    changes: list[Change]


class AnalysisMetadata(BaseModel):
    model: str | None
    prompt_version: str | None
    tokens_used: int | None
    duration_ms: int | None


class AnalysisResponse(BaseModel):
    id: uuid.UUID
    package_name: str
    from_version: str
    to_version: str
    status: str
    error: str | None = None
    summary: str | None = None
    total_breaking: int = 0
    total_deprecated: int = 0
    total_new_features: int = 0
    versions_analyzed: int = 0
    changes: list[Change] = []
    metadata: AnalysisMetadata | None = None


class VersionsResponse(BaseModel):
    package_name: str
    versions: list[str]
