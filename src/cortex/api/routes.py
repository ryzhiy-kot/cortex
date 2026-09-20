from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request

from cortex.context import Cortex
from cortex.models import (
    ConceptResponse,
    IngestRequest,
    IngestResponse,
    ListingResponse,
    SearchRequest,
    SearchResult,
)

router = APIRouter()


def get_cortex(request: Request) -> Cortex:
    return request.app.state.cortex


CortexDep = Annotated[Cortex, Depends(get_cortex)]


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Rescan bundles: embed concepts and regenerate index.md",
    tags=["ingest"],
    responses={
        404: {"description": "Requested bundle does not exist under the bundles root."}
    },
)
def ingest(
    body: Annotated[
        IngestRequest,
        Body(
            openapi_examples={
                "Rescan all bundles": {
                    "summary": "Ingest every bundle under the bundles root.",
                    "value": {},
                },
                "Add or refresh one bundle": {
                    "summary": "Ingest a single bundle by name; creates and refreshes its index.",
                    "value": {"bundle": "retail"},
                },
                "Refresh part of a bundle": {
                    "summary": "Re-ingest one directory within a bundle.",
                    "value": {"bundle": "retail", "path": "tables"},
                },
            }
        ),
    ],
    cortex: CortexDep,
) -> IngestResponse:
    """Walk the bundle, embed concept bodies into the vector index, and
    regenerate `index.md` for every affected directory.

    Ingesting a new bundle and refreshing an existing one are the same
    operation: point `bundle` at a directory under the bundles root and Cortex
    picks it up. Omitting `bundle` rescans the whole bundles root (new bundles
    are auto-discovered).

    Returns counts instead of content: `indexed` (newly embedded concepts),
    `updated` (re-embedded because the file changed), `deleted` (concepts that
    disappeared from the bundle since the last ingest), `index_files`
    (regenerated `index.md` files), and per-file `errors` — malformed concepts
    are skipped, never fatal.
    """
    try:
        return cortex.ingest(bundle=body.bundle, path=body.path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/search",
    response_model=list[SearchResult],
    summary="Search for concept pointers",
    tags=["search"],
    responses={400: {"description": "Search failed (e.g. embedding provider unreachable)."}},
)
def search(
    body: Annotated[
        SearchRequest,
        Body(
            openapi_examples={
                "Hybrid search across all bundles": {
                    "summary": "Default: vector + lexical fused, every bundle.",
                    "value": {"query": "revenue"},
                },
                "Vector search within one bundle": {
                    "summary": "Semantic search narrowed to a single bundle.",
                    "value": {"query": "where are compute regions deployed", "bundle": "platform"},
                },
                "Lexical search by type": {
                    "summary": "Grep-like term match filtered by frontmatter type.",
                    "value": {"query": "orders", "mode": "lexical", "type": "reference"},
                },
            }
        ),
    ],
    cortex: CortexDep,
) -> list[SearchResult]:
    """Return concept pointers, not answers: what matched and where, with a
    score and a short snippet. Read full content from `GET /concepts/{path}`.

    Modes: `vector` (semantic), `lexical` (grep-like term match), `hybrid`
    (both fused by reciprocal rank — the default).

    Optional filters: `bundle` narrows to one bundle (all searched by default),
    `type` matches the concept's frontmatter `type`, `tags` matches frontmatter
    tags (concept must carry any of them). Results are scored 0-1.
    """
    try:
        return cortex.search(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"search failed: {exc}") from exc


@router.get(
    "/concepts/{path:path}",
    response_model=ConceptResponse | ListingResponse,
    summary="Read a concept body, or list a directory",
    tags=["read"],
    responses={
        404: {
            "description": "Unknown bundle, or no concept or index.md at the given path."
        }
    },
)
def read_concept(
    path: Annotated[
        str,
        Path(
            description="Bundle-qualified concept path (first segment names the bundle).",
            openapi_examples={
                "A concept": {
                    "summary": "Read the concepts of a specific file.",
                    "value": "retail/tables/orders",
                },
                "A directory": {
                    "summary": "List a directory within a bundle.",
                    "value": "retail/tables",
                },
            },
        ),
    ],
    cortex: CortexDep,
) -> ConceptResponse | ListingResponse:
    """Return the full concept (frontmatter, markdown body, extracted `.md`
    links) from the bundle's source markdown — answers stay grounded in the
    source files.

    Bundle-qualified path: the first segment names the bundle, the rest is the
    path within it (`retail/tables/orders`). When the path resolves to a
    directory rather than a concept, the response is the same listing shape as
    `GET /index/{dir}`.
    """
    path = path.strip("/")
    try:
        store, rel = _resolve_store(cortex, path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not store.exists(f"{rel}.md"):
        if store.exists(rel) and (store.list_subdirs(rel) or store.list_markdown(rel)):
            return cortex.list_dir(path)
        raise HTTPException(status_code=404, detail=f"concept not found: {path}")
    return cortex.read_concept(path)


@router.get(
    "/index/{dir:path}",
    response_model=ListingResponse,
    summary="List a directory with its generated index.md",
    tags=["read"],
    responses={
        404: {"description": "Unknown bundle, or directory does not exist within it."}
    },
)
def list_dir(
    dir: Annotated[
        str,
        Path(
            description="Bundle-qualified directory path (first segment names the bundle).",
            openapi_examples={
                "Bundle root": {"summary": "List a bundle's top level.", "value": "retail"},
                "Nested directory": {
                    "summary": "List a subdirectory within a bundle.",
                    "value": "retail/tables",
                },
            },
        ),
    ],
    cortex: CortexDep,
) -> ListingResponse:
    """Progressive-disclosure listing of a bundle directory: concept names with
    their frontmatter title/description, subdirectories, and the generated
    `index.md` content (regenerated by Cortex at ingest; never maintained by
    hand).
    """
    try:
        store, rel = _resolve_store(cortex, dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not store.exists(rel if rel else ""):
        raise HTTPException(status_code=404, detail=f"directory not found: {dir}")
    return cortex.list_dir(dir).model_dump()


def _resolve_store(cortex: Cortex, qualified_path: str) -> tuple:
    bundle, _, rest = qualified_path.strip("/").partition("/")
    store = cortex.bundles.get(bundle)
    if store is None:
        raise FileNotFoundError(f"unknown bundle: {bundle}")
    return store, rest