import json
from zipfile import ZIP_DEFLATED, ZipFile

from cortex.prepare.pipeline import ReviewPlan


def _upload(client, source: bytes, filename: str, bundle: str | None = None):
    files = {"source": (filename, source, "application/octet-stream")}
    data = {"bundle": bundle} if bundle else None
    return client.post("/prepare", files=files, data=data)


def test_prepare_single_file_creates_concept_in_forced_bundle(client, cortex):
    source = b"# Cancellation policy\n\nRefunds are processed within 5 days."
    response = _upload(client, source, "policy.md", bundle="retail")

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "done"
    assert job["target_bundle"] == "retail"
    assert job["created_concepts"] == ["retail/policy"]
    assert job["errors"] == []

    concept = cortex.read_concept("retail/policy")
    assert "cancell" in concept.body.lower()
    assert concept.frontmatter.get("sources") == ["policy.md"]


def test_prepare_creates_new_bundle_on_demand(client, cortex):
    source = b"# New domain\n\nFresh knowledge with no home."
    response = _upload(client, source, "fresh.txt")

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "done"
    assert job["target_bundle"] == "knowledge"
    assert job["created_concepts"] == ["knowledge/fresh"]
    assert (cortex._bundles_root / "knowledge" / "fresh.md").exists()


def test_prepare_consolidates_into_existing_concept_preserving_path(
    client, cortex, stub_llm
):
    source = b"# Extra orders notes\n\nOrder IDs are stored as strings."

    def review_plan(prompt: dict) -> dict:
        return {
            "bundle": "retail",
            "decisions": {
                name: {
                    "action": "consolidate",
                    "into": "retail/tables/orders",
                    "reason": "extends orders",
                }
                for name in prompt["files"]
            },
        }

    def author(prompt: dict) -> str:
        existing = prompt["existing_concept"]["body"]
        frontmatter = (
            "---\n"
            "type: reference\n"
            "title: Orders\n"
            "description: stub merged concept\n"
            "---\n"
        )
        return (
            frontmatter + f"{existing}\n\n# Extra orders notes\n\n{prompt['content']}\n"
        )

    stub_llm.review_plan = review_plan
    stub_llm.author = author
    original = cortex.read_concept("retail/tables/orders")

    response = _upload(client, source, "orders-note.md", bundle="retail")

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "done"
    assert job["created_concepts"] == []
    assert job["updated_concepts"] == ["retail/tables/orders"]

    merged = cortex.read_concept("retail/tables/orders")
    assert merged.concept_path == "retail/tables/orders"
    assert merged.frontmatter.get("sources") == list(
        original.frontmatter.get("sources", [])
    ) + ["orders-note.md"]


def test_prepare_authoring_failure_is_atomic(client, cortex, stub_llm):
    stub_llm.author = lambda prompt: "not frontmatter, just broken body text"

    response = _upload(client, b"one", "a.md", bundle="retail")

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "failed"
    assert job["errors"]
    assert not (cortex._bundles_root / "retail" / "a.md").exists()


def test_prepare_reserved_name_fails_without_writing(client, cortex, stub_llm):
    stub_llm.review_plan = lambda prompt: {
        "bundle": "retail",
        "decisions": {
            name: {"action": "create", "reason": "new"} for name in prompt["files"]
        },
    }
    stub_llm.author = lambda prompt: (
        "---\ntype: x\ntitle: x\ndescription: x\n---\nBody."
    )

    response = _upload(client, b"index", "index.md", bundle="retail")

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "failed"
    assert not (cortex._bundles_root / "retail" / "index.md").exists()


def test_prepare_zip_creates_mirrored_concepts_and_skips_binary(client, cortex):
    import io

    buf = io.BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as archive:
        archive.writestr("docs/a.md", "# A\n\nContent A.")
        archive.writestr("docs/b.txt", "# B\n\nContent B.")
        archive.writestr("assets/logo.png", b"\x89PNG\r\n\x1a\n")
    buf.seek(0)

    response = _upload(client, buf.read(), "bundle.zip", bundle="retail")

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "done"
    assert sorted(job["created_concepts"]) == ["retail/docs/a", "retail/docs/b"]
    assert "assets/logo.png" in job["skipped_files"]
    assert (cortex._bundles_root / "retail" / "docs" / "a.md").exists()
    assert (cortex._bundles_root / "retail" / "assets" / "logo.png").exists() is False


def test_prepare_accepts_any_text_format(client, cortex):
    source = b"report,amount,note\n1,10,first-row\n2,20,second-row\n"
    response = _upload(client, source, "data.csv", bundle="retail")

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "done"
    assert job["created_concepts"] == ["retail/data"]
    assert job["skipped_files"] == []

    concept = cortex.read_concept("retail/data")
    assert concept.frontmatter.get("sources") == ["data.csv"]
    assert "first-row" in concept.body.lower()


def test_prepare_accepts_html_and_extensionless_text(client, cortex):
    html = b"<html><body><h1>Pricing</h1><p>Annual plans only.</p></body></html>"

    response = _upload(client, html, "pricing.html", bundle="retail")
    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "done"
    assert job["created_concepts"] == ["retail/pricing"]

    plain = b"README: point the CORTEX_BUNDLES_ROOT env at your bundles.\n"
    response = _upload(client, plain, "README", bundle="retail")
    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "done"
    assert job["created_concepts"] == ["retail/README"]


def test_prepare_single_binary_file_is_skipped(client, cortex):
    response = _upload(
        client,
        b"\x89PNG\r\n\x1a\n" + b"\0" * 64,
        "photo.png",
        bundle="retail",
    )

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "done"
    assert job["created_concepts"] == []
    assert job["skipped_files"] == ["photo.png"]
    assert not (cortex._bundles_root / "retail" / "photo.md").exists()


def test_prepare_zip_slip_extraction_fails_job(client, cortex):
    import io

    buf = io.BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as archive:
        archive.writestr("../evil.md", "# Evil\n\nBoom.")
    buf.seek(0)

    response = _upload(client, buf.read(), "bundle.zip", bundle="retail")

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "failed"
    assert not (cortex._bundles_root / "retail" / "evil.md").exists()


def test_prepare_empty_upload_rejected(client):
    response = _upload(client, b"", "empty.md", bundle="retail")
    assert response.status_code == 400


def test_prepare_invalid_bundle_name_rejected(client):
    response = _upload(client, b"x", "a.md", bundle="../escape")
    assert response.status_code == 400


def test_prepare_job_poll_unknown_id_404(client):
    assert client.get("/prepare/nope").status_code == 404


def test_prepare_invalid_review_plan_fails_cleanly(client, cortex, stub_llm):
    def prose_review(prompt):
        return "Based on the provided context, here is a review of the task..."

    stub_llm.review_plan = prose_review

    response = _upload(client, b"# New\n\nBody.", "new.md", bundle="retail")

    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "failed"
    assert "invalid review plan" in job["errors"][0]["reason"]
    assert not (cortex._bundles_root / "retail" / "new.md").exists()


def test_prepare_review_uses_structured_output(client, cortex, stub_llm):
    original = stub_llm.complete
    output_types: list[type[ReviewPlan] | None] = []

    def spying(
        system: str, user: str, output_type: type[ReviewPlan] | None = None
    ) -> str | ReviewPlan:
        prompt = json.loads(user)
        if prompt["task"] == "REVIEW":
            output_types.append(output_type)
        return original(system, user, output_type)

    stub_llm.complete = spying

    response = _upload(client, b"# New\n\nBody.", "new.md", bundle="retail")

    assert response.status_code == 202
    assert response.json()["status"] == "done"
    assert output_types == [ReviewPlan]


def test_prepare_then_ingest_indexes_created_concepts(client, cortex):
    source = b"# Prepared concept\n\nNow it can be searched."
    job = _upload(client, source, "prep.md", bundle="retail").json()
    assert job["status"] == "done"

    response = client.post("/ingest", json={"bundle": "retail"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["indexed"] >= 1
