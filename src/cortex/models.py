from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    path: str | None = Field(
        default=None,
        description="Bundle-relative directory to rescan. Defaults to the bundle root.",
    )


class IngestError(BaseModel):
    path: str
    reason: str


class IngestResponse(BaseModel):
    indexed: int = 0
    updated: int = 0
    deleted: int = 0
    index_files: int = 0
    errors: list[IngestError] = Field(default_factory=list)


class SearchMode(str, Enum):
    VECTOR = "vector"
    LEXICAL = "lexical"
    HYBRID = "hybrid"


class SearchRequest(BaseModel):
    query: str
    mode: SearchMode = SearchMode.HYBRID
    top_k: int = Field(default=10, ge=1, le=100)
    type: str | None = None
    tags: list[str] | None = None


class SearchResult(BaseModel):
    concept_path: str
    type: str
    title: str | None = None
    description: str | None = None
    snippet: str = ""
    score: float = 0.0


class ConceptResponse(BaseModel):
    concept_path: str
    frontmatter: dict[str, Any]
    body: str
    links: list[str]


class ConceptCard(BaseModel):
    concept_path: str
    type: str
    title: str | None = None
    description: str | None = None


class ListingResponse(BaseModel):
    dir: str
    subdirs: list[str]
    concepts: list[ConceptCard]
    index_content: str | None = None