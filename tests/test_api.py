def test_ingest_endpoint_all(client):
    response = client.post("/ingest", json={"bundle": None})
    assert response.status_code == 200
    assert response.json()["indexed"] == 7


def test_ingest_endpoint_single_bundle(client):
    response = client.post("/ingest", json={"bundle": "retail"})
    assert response.status_code == 200
    assert response.json()["indexed"] == 5


def test_ingest_endpoint_unknown_bundle_is_404(client):
    response = client.post("/ingest", json={"bundle": "nope"})
    assert response.status_code == 404


def test_search_endpoint_via_http(client):
    client.post("/ingest", json={})
    response = client.post("/search", json={"query": "revenue", "mode": "lexical", "top_k": 5})
    assert response.status_code == 200
    body = response.json()
    assert body
    assert all("concept_path" in result and "bundle" in result for result in body)


def test_search_endpoint_bundle_filter(client):
    client.post("/ingest", json={})
    response = client.post("/search", json={"query": "pipeline", "mode": "lexical", "bundle": "platform"})
    assert response.status_code == 200
    assert all(result["bundle"] == "platform" for result in response.json())


def test_search_endpoint_rejects_bad_mode(client):
    response = client.post("/search", json={"query": "x", "mode": "bogus"})
    assert response.status_code == 422


def test_read_concept_via_http(client):
    client.post("/ingest", json={})
    response = client.get("/concepts/retail/tables/orders")
    assert response.status_code == 200
    body = response.json()
    assert body["concept_path"] == "retail/tables/orders"
    assert body["frontmatter"]["type"] == "reference"
    assert "order_id" in body["body"]


def test_read_concept_missing_is_404(client):
    response = client.get("/concepts/retail/tables/nope")
    assert response.status_code == 404


def test_read_concept_unknown_bundle_is_404(client):
    response = client.get("/concepts/nope/tables/orders")
    assert response.status_code == 404


def test_read_dir_falls_back_to_listing(client):
    response = client.get("/concepts/retail/tables")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"dir", "subdirs", "concepts", "index_content"}
    assert body["dir"] == "retail/tables"


def test_index_endpoint_returns_generated_index(client):
    client.post("/ingest", json={})
    response = client.get("/index/retail/tables")
    assert response.status_code == 200
    assert "- [orders](orders.md) - Columns and semantics of the orders table." in response.json()["index_content"]


def test_index_endpoint_bundle_root(client):
    client.post("/ingest", json={})
    response = client.get("/index/retail")
    assert response.status_code == 200
    assert "- [glossary](glossary.md)" in response.json()["index_content"]


def test_index_endpoint_missing_dir_is_404(client):
    response = client.get("/index/retail/nope")
    assert response.status_code == 404