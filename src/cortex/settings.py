from enum import Enum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingProviderKind(str, Enum):
    SENTENCE_TRANSFORMERS = "sentence-transformers"
    OLLAMA = "ollama"
    VERTEX = "vertex"


class LLMProviderKind(str, Enum):
    OLLAMA = "ollama"
    VERTEX = "vertex"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CORTEX_", env_file=".env", extra="ignore"
    )

    bundles_root: Path = Field(
        default=Path("bundles"),
        description="Directory whose immediate subdirectories are bundles, named by folder.",
    )

    chroma_path: Path = Path(".cortex/chroma")
    chroma_collection: str = "concepts"

    staging_path: Path = Field(
        default=Path(".cortex/staging"),
        description="Directory where uploaded source material is staged before Prepare.",
    )

    traces_path: Path = Field(
        default=Path(".cortex/traces"),
        description="Directory where per-run trace files are written, one JSON-lines file per prepare job or ingest run.",
    )
    trace_retention_days: int = Field(
        default=7,
        ge=1,
        description="Trace files older than this (by file mtime) are pruned at startup and after runs.",
    )

    log_path: Path = Field(
        default=Path(".cortex/logs/cortex.log"),
        description="JSON-lines log file for the cortex logger (size-rotating).",
    )
    log_level: str = Field(
        default="info",
        description="Log level for the cortex logger: debug | info | warning | error.",
    )

    embedding_provider: EmbeddingProviderKind = (
        EmbeddingProviderKind.SENTENCE_TRANSFORMERS
    )
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "nomic-embed-text"
    vertex_project: str | None = None
    vertex_location: str = "us-central1"
    vertex_embedding_model: str = "text-embedding-005"

    llm_provider: LLMProviderKind = LLMProviderKind.OLLAMA
    ollama_llm_model: str = "llama3.2"
    vertex_llm_model: str = "gemini-2.0-flash-001"
