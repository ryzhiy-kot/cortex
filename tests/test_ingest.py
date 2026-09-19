def test_ingest_all_counts_union(cortex, bundles_root):
    result = cortex.ingest()

    assert result["indexed"] == 7
    assert result["errors"] == []
    assert (bundles_root / "retail" / "index.md").exists()
    assert (bundles_root / "retail" / "tables" / "index.md").exists()
    assert (bundles_root / "retail" / "guides" / "index.md").exists()
    assert (bundles_root / "platform" / "index.md").exists()
    assert "[orders](orders.md) - Columns and semantics of the orders table." in (bundles_root / "retail" / "tables" / "index.md").read_text()


def test_ingest_single_bundle(cortex, bundles_root):
    result = cortex.ingest("retail")

    assert result["indexed"] == 5
    assert result["errors"] == []
    assert (bundles_root / "retail" / "index.md").exists()
    assert not (bundles_root / "platform" / "index.md").exists()


def test_ingest_subpath_only_for_bundle(cortex, bundles_root):
    result = cortex.ingest("retail", "tables")

    assert result["indexed"] == 2
    assert result["errors"] == []
    assert (bundles_root / "retail" / "tables" / "index.md").exists()
    assert not (bundles_root / "retail" / "index.md").exists()


import pytest


def test_ingest_unknown_bundle_raises(cortex):
    with pytest.raises(FileNotFoundError):
        cortex.ingest("nope")


def test_ingest_reports_malformed_and_keeps_going(cortex, bundles_root):
    (bundles_root / "retail" / "tables" / "broken.md").write_text("no frontmatter here\n")

    result = cortex.ingest("retail", "tables")

    assert result["indexed"] == 2
    assert len(result["errors"]) == 1
    assert result["errors"][0]["path"] == "retail/tables/broken.md"


def test_ingest_rejects_absolute_path(cortex):
    result = cortex.ingest("retail", "/etc/passwd")

    assert result["indexed"] == 0
    assert result["errors"][0]["reason"] == "must be bundle-relative"


def test_ingest_deletes_removed_concepts(cortex, bundles_root):
    cortex.ingest("retail", "tables")
    assert cortex.vector.concept_paths() == {"retail/tables/orders", "retail/tables/customers"}

    (bundles_root / "retail" / "tables" / "customers.md").unlink()
    result = cortex.ingest("retail", "tables")

    assert result["deleted"] == 1
    assert cortex.vector.concept_paths() == {"retail/tables/orders"}


def test_ingest_updated_counts_existing(cortex):
    cortex.ingest("retail", "tables")

    result = cortex.ingest("retail", "tables")

    assert result["updated"] == 2
    assert result["indexed"] == 0
    assert result["errors"] == []


def test_ingest_auto_discovers_new_bundle(cortex, bundles_root):
    (bundles_root / "analytics").mkdir()
    (bundles_root / "analytics" / "funnel.md").write_text(
        "---\ntype: reference\ntitle: Funnel\ndescription: Conversion funnel.\n---\nStage drop-off docs.\n"
    )

    result = cortex.ingest()

    assert "analytics/funnel" in cortex.vector.concept_paths()
    assert result["indexed"] >= 1