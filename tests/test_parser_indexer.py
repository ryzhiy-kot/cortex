import pytest

from cortex.bundle.indexer import index_for
from cortex.bundle.parser import ParseError, parse_concept

VALID = """---
type: reference
title: Orders
description: Columns of the orders table.
tags: [tables]
---

Body with [customers](customers.md).
"""


def test_parse_concept_extracts_frontmatter_body_and_links():
    parsed = parse_concept(VALID, "tables/orders")
    assert parsed.path == "tables/orders"
    assert parsed.frontmatter["type"] == "reference"
    assert parsed.frontmatter["title"] == "Orders"
    assert "Body with" in parsed.body
    assert parsed.links == ["customers"]


def test_parse_concept_requires_type():
    with pytest.raises(ParseError):
        parse_concept("---\ntitle: No type\n---\nBody", "x/foo")


def test_parse_concept_requires_frontmatter():
    with pytest.raises(ParseError):
        parse_concept("Just body text", "x/foo")


def test_parse_concept_requires_mapping():
    with pytest.raises(ParseError):
        parse_concept("---\n- a\n- b\n---\nBody", "x/foo")


def test_parse_concept_rejects_invalid_yaml():
    with pytest.raises(ParseError):
        parse_concept("---\ntype: [unclosed\n---\nBody", "x/foo")


def test_index_for_lists_concepts_and_subdirs():
    content = index_for("tables", [("orders.md", "Order rows.")], ["guides"])
    assert "- [orders](orders.md) - Order rows." in content
    assert "- [guides](guides/)" in content


def test_index_for_root():
    content = index_for("", [("glossary.md", "")], ["tables"])
    assert "- [glossary](glossary.md)" in content
    assert "- [tables](tables/)" in content