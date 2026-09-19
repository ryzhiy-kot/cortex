from enum import Enum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingProviderKind(str, Enum):
    SENTENCE_TRANSFORMERS = "sentence-transformers"
    OLLAMA = "ollama"
    VERTEX = "vertex"


class BundleStoreKind(str, Enum):
    LOCAL = "local"
    GCS = "gcs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORTEX_", env_file=".env", extra="ignore")

    bundle_root: Path = Field(default=Path("bundle"), description="Bundle root on the local filesystem.")
    bundle_store: BundleStoreKind = BundleStoreKind.LOCAL

    chroma_path: Path = Path(".cortex/chroma")
    chroma_collection: str = "concepts"

    embedding_provider: EmbeddingProviderKind = EmbeddingProviderKind.SENTENCE_TRANSFORMERS
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "nomic-embed-text"
    vertex_project: str | None = None
    vertex_location: str = "us-central1"
    vertex_embedding_model: str = "text-embedding-005"

    gcs_bucket: str | None = None
    gcs_prefix: str = ""