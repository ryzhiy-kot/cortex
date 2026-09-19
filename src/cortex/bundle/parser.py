import re
from dataclasses import dataclass, field

import yaml

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+\.md)\)")


class ParseError(ValueError):
    pass


@dataclass
class ParsedConcept:
    path: str
    frontmatter: dict
    body: str
    links: list[str] = field(default_factory=list)


def concept_path_from(rel_path: str) -> str:
    rel_path = rel_path.removesuffix(".md")
    return rel_path


def parse_concept(text: str, path: str) -> ParsedConcept:
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ParseError(f"{path}: missing YAML frontmatter block")
    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise ParseError(f"{path}: unparseable YAML frontmatter: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise ParseError(f"{path}: frontmatter must be a YAML mapping")
    if not frontmatter.get("type"):
        raise ParseError(f"{path}: frontmatter missing required 'type' field")
    body = text[match.end() :]
    links = _extract_links(body)
    return ParsedConcept(path=concept_path_from(path), frontmatter=frontmatter, body=body, links=links)


def _extract_links(body: str) -> list[str]:
    links = []
    for href in LINK_RE.findall(body):
        href = href.split("#")[0].split("?")[0].lstrip("/")
        if not href.endswith(".md"):
            continue
        links.append(concept_path_from(href))
    return links