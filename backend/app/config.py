from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    anthropic_api_key: str = ""
    database_url: str = "postgresql+asyncpg://hewg:hewg@localhost:5432/hewg"
    github_token: str = ""
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    llm_provider: str = "anthropic"  # "anthropic" | "openai_compatible"
    llm_base_url: str = ""  # used only when llm_provider == "openai_compatible"
    llm_api_key: str = ""  # generic key for openai_compatible branch
    llm_max_output_tokens: int = 2048  # max_tokens for the openai_compatible branch only
    llm_reasoning_effort: str = ""  # "low"|"medium"|"high"; only sent if set (reasoning models, e.g. Groq gpt-oss)
    analysis_model: str = "claude-sonnet-4-6"
    max_output_tokens: int = 8192
    max_batch_tokens: int = 15_000  # per-LLM-call budget for concatenated release-notes text
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:4200"]
    prompt_version: str = "v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
