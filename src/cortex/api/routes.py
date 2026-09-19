from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

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


@router.post("/ingest", response_model=IngestResponse)
def ingest(body: IngestRequest, cortex: CortexDep) -> dict:
    try:
        return cortex.ingest(bundle=body.bundle, path=body.path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/search", response_model=list[SearchResult])
def search(body: SearchRequest, cortex: CortexDep) -> dict:
    try:
        return cortex.search(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"search failed: {exc}") from exc


@router.get("/concepts/{path:path}", response_model=ConceptResponse | ListingResponse)
def read_concept(path: str, cortex: CortexDep):
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


@router.get("/index/{dir:path}", response_model=ListingResponse)
def list_dir(dir: str, cortex: CortexDep) -> dict:
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