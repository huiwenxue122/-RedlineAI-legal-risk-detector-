"""
Central config: env vars for OpenAI, Neo4j, etc.
Use .env file or export in shell. Neo4j vars are required (no silent fallback).
"""
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM (OpenAI)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_max_output_tokens: int = 16384
    # 单次调用时发给 API 的合同文本最大字符数；snippet-only clause text 下用全文可跑完并得到约 40 clauses
    openai_max_input_chars: int = 120000

    # Neo4j (required: set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD in .env or environment)
    neo4j_uri: str = ""
    neo4j_user: str = ""
    neo4j_password: str = ""

    # App
    debug: bool = False

    @model_validator(mode="after")
    def require_neo4j_env(self) -> "Settings":
        missing = []
        if not (self.neo4j_uri or self.neo4j_uri.strip()):
            missing.append("NEO4J_URI")
        if not (self.neo4j_user or self.neo4j_user.strip()):
            missing.append("NEO4J_USER")
        if not (self.neo4j_password or self.neo4j_password.strip()):
            missing.append("NEO4J_PASSWORD")
        if missing:
            raise ValueError(
                "Missing required environment variable(s): "
                + ", ".join(missing)
                + ". Set them in .env (local) or in Render environment (deploy)."
            )
        return self


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
