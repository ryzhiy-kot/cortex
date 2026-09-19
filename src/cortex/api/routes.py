from typing import Union

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
    cortex: Cortex = request.app.state.cortex
    return cortex


@router.post("/ingest", response_model=IngestResponse)
def ingest(body: IngestRequest, cortex: Cortex = Depends(get_cortex)) -> dict:
    try:
        return cortex.ingest(body.path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="bundle path not found") from exc


@router.post("/search", response_model=list[SearchResult])
def search(body: SearchRequest, cortex: Cortex = Depends(get_cortex)) -> dict:
    try:
        return cortex.search(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"search failed: {exc}") from exc


@router.get("/concepts/{path:path}", response_model=Union[ConceptResponse, ListingResponse])
def read_concept(path: str, cortex: Cortex = Depends(get_cortex)):
    path = path.strip("/")
    if not cortex.store.exists(f"{path}.md"):
        if cortex.store.exists(path) and (cortex.store.list_subdirs(path) or cortex.store.list_markdown(path)):
            return cortex.list_dir(path)
        raise HTTPException(status_code=404, detail=f"concept not found: {path}")
    return cortex.read_concept(path)


@router.get("/index/{dir:path}", response_model=ListingResponse)
def list_dir(dir: str, cortex: Cortex = Depends(get_cortex)) -> dict:
    if not cortex.store.exists(dir if dir else ""):
        raise HTTPException(status_code=404, detail=f"directory not found: {dir}")
    return cortex.list_dir(dir).model_dump()