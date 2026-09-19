import re
from pathlib import PurePosixPath

from cortex.bundle.parser import concept_path_from

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _normalize(href: str) -> str:
    href = href.split("#")[0].split("?")[0].lstrip("/")
    if href.endswith(".md"):
        return concept_path_from(href)
    return href


def collect_links(body: str) -> list[str]:
    return [_normalize(href) for href in LINK_RE.findall(body)]


def index_for(dir_path: str, concepts: list[str], subdirs: list[str]) -> str:
    parts = [f"# {dir_path if dir_path else 'Bundle root'}"]
    if concepts:
        parts.append("")
        parts.append("## Concepts")
        for name in sorted(concepts):
            concept = name[: -len(".md")] if name.endswith(".md") else name
            parts.append(f"- [{concept}]({PurePosixPath(dir_path, concept) if dir_path else concept}.md)")
    if subdirs:
        parts.append("")
        parts.append("## Subdirectories")
        for subdir in sorted(subdirs):
            parts.append(f"- [{subdir}]({PurePosixPath(dir_path, subdir) if dir_path else subdir}/index.md)")
    return "\n".join(parts) + "\n"