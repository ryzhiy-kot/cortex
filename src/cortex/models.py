from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    bundle: str | None = Field(
        default=None,
        description=(
            "Bundle name to rescan (its directory under the bundles root). "
            "Defaults to all bundles; new bundles are auto-discovered."
        ),
        examples=["retail"],
    )
    path: str | None = Field(
        default=None,
        description=(
            "Bundle-relative directory to rescan. Defaults to the bundle root. "
            "Use to refresh only part of a bundle."
        ),
        examples=["tables"],
    )


class IngestError(BaseModel):
    path: str
    reason: str


class IngestResponse(BaseModel):
    indexed: int = Field(0, description="Concepts newly added to the index.")
    updated: int = Field(0, description="Concepts re-embedded because their file changed.")
    deleted: int = Field(
        0, description="Concepts removed from the index since the last ingest."
    )
    index_files: int = Field(0, description="Generated index.md files written.")
    errors: list[IngestError] = Field(
        default_factory=list,
        description="Per-file failures (malformed concepts are skipped, never fatal).",
    )


class SearchMode(str, Enum):
    VECTOR = "vector"
    LEXICAL = "lexical"
    HYBRID = "hybrid"


class SearchRequest(BaseModel):
    query: str = Field(description="Free-text query to match against concepts.")
    mode: SearchMode = Field(
        default=SearchMode.HYBRID,
        description="vector: semantic; lexical: grep-like term match; hybrid: both fused.",
        examples=["hybrid"],
    )
    top_k: int = Field(default=10, ge=1, le=100, description="Maximum results.")
    bundle: str | None = Field(
        default=None,
        description="Narrow search to one bundle. Defaults to all bundles.",
        examples=["retail"],
    )
    type: str | None = Field(
        default=None,
        description="Only concepts whose frontmatter `type` matches.",
        examples=["guide"],
    )
    tags: list[str] | None = Field(
        default=None,
        description="Only concepts whose frontmatter `tags` include any of these.",
        examples=[["sql"]],
    )


class SearchResult(BaseModel):
    bundle: str = Field("", description="Bundle the matching concept lives in.")
    concept_path: str = Field(
        ...,
        description="Bundle-qualified path to read the full concept: `GET /concepts/{concept_path}`.",
        examples=["retail/guides/revenue"],
    )
    type: str = Field(..., description="The concept's frontmatter `type`.")
    title: str | None = Field(default=None, description="Frontmatter title, if any.")
    description: str | None = Field(default=None, description="Frontmatter description, if any.")
    snippet: str = Field("", description="Leading text of the concept body for context.")
    score: float = Field(0.0, ge=0.0, le=1.0, description="Match score, 0-1.")


class ConceptResponse(BaseModel):
    concept_path: str = Field(
        ...,
        description="Bundle-qualified path of the returned concept.",
        examples=["retail/tables/orders"],
    )
    frontmatter: dict[str, Any] = Field(
        ..., description="Parsed YAML frontmatter of the concept file."
    )
    body: str = Field(..., description="Full markdown body from the source file.")
    links: list[str] = Field(
        ..., description="Concept paths extracted from links in the body."
    )


class ConceptCard(BaseModel):
    concept_path: str = Field(
        ..., description="Bundle-qualified path of the concept.",
        examples=["retail/tables/orders"],
    )
    type: str = Field(..., description="The concept's frontmatter `type`.")
    title: str | None = None
    description: str | None = None


class ListingResponse(BaseModel):
    dir: str = Field(
        ..., description="Bundle-qualified directory being listed.",
        examples=["retail/tables"],
    )
    subdirs: list[str] = Field(..., description="Immediate subdirectories.")
    concepts: list[ConceptCard] = Field(..., description="Concepts in this directory.")
    index_content: str | None = Field(
        default=None, description="Generated index.md content for the directory."
    )