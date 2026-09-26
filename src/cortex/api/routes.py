from pathlib import Path as PPath
from typing import Annotated

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Request,
    Response,
    UploadFile,
)

from cortex.context import Cortex
from cortex.models import (
    ConceptResponse,
    IngestRequest,
    IngestResponse,
    ListingResponse,
    PrepareJob,
    SearchRequest,
    SearchResult,
)
from cortex.prepare.pipeline import SAFE_BUNDLE_RE

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
    responses={
        400: {"description": "Search failed (e.g. embedding provider unreachable)."}
    },
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
                    "value": {
                        "query": "where are compute regions deployed",
                        "bundle": "platform",
                    },
                },
                "Lexical search by type": {
                    "summary": "Grep-like term match filtered by frontmatter type.",
                    "value": {
                        "query": "orders",
                        "mode": "lexical",
                        "type": "reference",
                    },
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
                "Bundle root": {
                    "summary": "List a bundle's top level.",
                    "value": "retail",
                },
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


@router.post(
    "/prepare",
    response_model=PrepareJob,
    status_code=202,
    summary="Convert uploaded source material into OKF concepts",
    tags=["prepare"],
    responses={
        400: {
            "description": "Both a file and a zip were sent, or the upload was missing."
        }
    },
)
async def prepare(
    source: Annotated[
        UploadFile,
        File(
            description="Source material: one non-OKF file (`.md`/`.txt`) or one `.zip`."
        ),
    ],
    bundle: Annotated[
        str | None,
        Form(
            description="Target bundle name. Defaults to a name the review LLM picks.",
            openapi_examples={
                "Name an existing bundle": {
                    "summary": "Consolidate into or create under an existing bundle.",
                    "value": "retail",
                }
            },
        ),
    ] = None,
    cortex: CortexDep = None,
) -> PrepareJob:
    """Queue a Prepare job: an LLM reviews the uploaded source (single file or
    zip) against the current bundles and turns it into OKF concept files under
    the bundles root.

    Review decides per source file whether to `create` a new concept or
    `consolidate` into an existing one (in-place rewrite that preserves the
    concept path and appends to its `sources` frontmatter). Concept files are
    validated and written atomically — any invalid output fails the whole job
    and nothing is written. Non-text files (anything that is not `.md`/`.txt`)
    are skipped, never fatal.

    Prepare writes OKF only: it does not embed anything or regenerate
    `index.md`. Run `POST /ingest` afterwards to index what Prepare produced.
    Jobs run serialized, one at a time; poll `GET /prepare/{job_id}`.

    The result is the job object: status (`queued|reviewing|authoring|done|
    failed`), which concepts were created or updated in place, and which source
    files were skipped.
    """
    if bundle is not None and SAFE_BUNDLE_RE.match(bundle) is None:
        raise HTTPException(
            status_code=400,
            detail="bundle must start with a letter or digit and contain only [A-Za-z0-9._-]",
        )
    payload = await source.read()
    if not payload:
        raise HTTPException(status_code=400, detail="empty upload")
    return cortex.prepare.submit(
        payload=payload,
        filename=source.filename or "upload",
        bundle=bundle,
    )


@router.get(
    "/prepare/{job_id}",
    response_model=PrepareJob,
    summary="Poll a Prepare job",
    tags=["prepare"],
    responses={404: {"description": "Unknown job id (jobs live in memory only)."}},
)
def prepare_job(
    job_id: Annotated[
        str,
        Path(
            description="Job id returned by POST /prepare.",
            openapi_examples={
                "A job id": {
                    "summary": "As returned by POST /prepare.",
                    "value": "a1b2c3",
                }
            },
        ),
    ],
    cortex: CortexDep,
) -> PrepareJob:
    """Return a Prepare job in its current state. Poll until status is `done`
    or `failed`. Jobs are held in memory and do not survive a restart.
    """
    job = cortex.prepare.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown prepare job: {job_id}")
    return job


@router.get(
    "/prepare/{job_id}/trace",
    summary="Read a Prepare job's trace",
    tags=["prepare"],
    responses={
        200: {
            "content": {"application/x-ndjson": {}},
            "description": "One JSON object per line: the job's LLM interactions, steps, and failures.",
        },
        404: {"description": "Unknown job id, or the job's trace file no longer exists."},
    },
)
def prepare_trace(
    job_id: Annotated[
        str,
        Path(
            description="Job id returned by POST /prepare.",
            openapi_examples={
                "A job id": {
                    "summary": "As returned by POST /prepare.",
                    "value": "a1b2c3",
                }
            },
        ),
    ],
    cortex: CortexDep,
) -> Response:
    """Return the run's trace file as NDJSON. Every span of the run — the
    review/author/persist steps and each LLM interaction with its prompts,
    responses, and token usage — is one line. A failed run stays diagnosable
    here after a restart.
    """
    return _read_trace(cortex.traces_path / "prepare" / f"{job_id}.jsonl")


@router.get(
    "/ingest/{run_id}/trace",
    summary="Read an ingest run's trace",
    tags=["ingest"],
    responses={
        200: {
            "content": {"application/x-ndjson": {}},
            "description": "One JSON object per line: the run's steps and per-file failures.",
        },
        404: {"description": "Unknown run id, or the run's trace file no longer exists."},
    },
)
def ingest_trace(
    run_id: Annotated[
        str,
        Path(
            description="Run id returned in the POST /ingest response.",
            openapi_examples={
                "A run id": {
                    "summary": "As returned by POST /ingest.",
                    "value": "3f2a91cb",
                }
            },
        ),
    ],
    cortex: CortexDep,
) -> Response:
    """Return the run's trace file as NDJSON. The run span and one span per
    bundle are the lines; `exception` events record per-file ingest failures.
    """
    return _read_trace(cortex.traces_path / "ingest" / f"{run_id}.jsonl")


def _read_trace(trace_file: PPath) -> Response:
    if not trace_file.is_file():
        raise HTTPException(status_code=404, detail=f"trace file not found: {trace_file.stem}")
    return Response(
        content=trace_file.read_text(encoding="utf-8"),
        media_type="application/x-ndjson",
    )
