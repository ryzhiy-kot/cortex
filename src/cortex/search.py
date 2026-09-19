from cortex.models import SearchMode, SearchRequest, SearchResult
from cortex.vector.store import VectorStore

K = 60
RERANK_CONSTANT = 60


def search(request: SearchRequest, vector: VectorStore) -> list[SearchResult]:
    where = {}
    if request.type:
        where["type"] = request.type
    if request.tags:
        where["tags"] = {"$in": request.tags}

    if request.mode == SearchMode.VECTOR:
        hits = vector.query_vector(request.query, request.top_k, where or None)
        return [_to_result(hit, score=_distance_to_score(_d(hit))) for hit in hits]

    if request.mode == SearchMode.LEXICAL:
        hits = vector.query_lexical(request.query, request.top_k, where or None)
        return [_to_result(hit, score=1.0) for hit in hits]

    vector_hits = vector.query_vector(request.query, K, where or None)
    lexical_hits = vector.query_lexical(request.query, K, where or None)
    fused = _rrf_fuse(vector_hits, lexical_hits)
    return [_to_result(hit, score=score) for hit, score in fused[: request.top_k]]


def _rrf_fuse(vector_hits: list[dict], lexical_hits: list[dict]) -> list[tuple[dict, float]]:
    scores: dict[str, float] = {}
    explicit: dict[str, dict] = {}
    for list_of_hits in (vector_hits, lexical_hits):
        for rank, hit in enumerate(list_of_hits):
            path = hit["concept_path"]
            scores[path] = scores.get(path, 0.0) + 1.0 / (RERANK_CONSTANT + rank + 1)
            explicit.setdefault(path, hit)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [(explicit[path], score) for path, score in ranked]


def _distance_to_score(distance: float) -> float:
    return 1.0 / (1.0 + distance)


def _d(hit: dict) -> float:
    return hit.get("distance") or 0.0


def _to_result(hit: dict, score: float) -> SearchResult:
    metadata = hit.get("metadata") or {}
    return SearchResult(
        concept_path=hit["concept_path"],
        type=metadata.get("type", ""),
        title=metadata.get("title"),
        description=metadata.get("description"),
        snippet=(hit.get("body") or "")[:400],
        score=score,
    )