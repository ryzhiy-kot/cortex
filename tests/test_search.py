from cortex.models import SearchMode, SearchRequest


def _search(cortex, query, mode, **kwargs):
    return cortex.search(SearchRequest(query=query, mode=SearchMode(mode), **kwargs))


def ingest_all(cortex):
    cortex.ingest()


def test_search_lexical_finds_body_term(cortex):
    ingest_all(cortex)
    results = _search(cortex, "revenue", "lexical")
    assert {"retail/guides/revenue"} & {r["concept_path"] for r in results}


def test_search_vector_returns_pointers(cortex):
    ingest_all(cortex)
    results = _search(cortex, "orders", "vector")
    assert results
    pointer = results[0]
    assert "bundle" in pointer
    assert "concept_path" in pointer
    assert "score" in pointer
    assert "snippet" in pointer


def test_search_hybrid_fuses_modes(cortex):
    ingest_all(cortex)
    results = _search(cortex, "customers email", "hybrid")
    assert results


def test_search_filters_by_bundle(cortex):
    ingest_all(cortex)
    results = _search(cortex, "pipeline", "lexical", bundle="platform")
    assert results
    assert all(r["bundle"] == "platform" for r in results)
    assert all(r["concept_path"].startswith("platform/") for r in results)


def test_search_filters_by_type(cortex):
    ingest_all(cortex)
    results = _search(cortex, "revenue", "lexical", type="guide")
    assert results
    assert all(r["type"] == "guide" for r in results)


def test_search_across_bundles_returns_mixed(cortex):
    ingest_all(cortex)
    results = _search(cortex, "reference", "hybrid")
    bundles = {r["bundle"] for r in results}
    assert bundles == {"retail", "platform"}


def test_search_top_k_limits_results(cortex):
    ingest_all(cortex)
    request = SearchRequest(query="table", mode=SearchMode.HYBRID, top_k=1)
    results = cortex.search(request)
    assert len(results) <= 1