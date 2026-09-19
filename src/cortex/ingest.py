from pathlib import PurePosixPath

from cortex.bundle.indexer import index_for
from cortex.bundle.local import RESERVED
from cortex.bundle.parser import parse_concept
from cortex.models import IngestError, IngestResponse
from cortex.vector.store import VectorStore


class Ingester:
    def __init__(self, store, vector: VectorStore, embedding_provider) -> None:
        self._store = store
        self._vector = vector
        self._embeddings = embedding_provider

    def ingest(self, rel_dir: str) -> IngestResponse:
        response = IngestResponse()
        if rel_dir.startswith("/") or rel_dir == "..":
            response.errors.append(IngestError(path=rel_dir, reason="must be bundle-relative"))
            return response

        roots = sorted(self._affected_roots(rel_dir))
        for root in roots:
            response.index_files += 1
            concepts = self._store.list_markdown(root)
            subdirs = self._store.list_subdirs(root)
            contents = index_for(root, concepts, subdirs)
            self._store.write_text(root, "index.md", contents)

        seen: set[str] = set()
        for rel_path in sorted(self._walk_markdown(rel_dir)):
            concept_path = rel_path[: -len(".md")]
            if concept_path in seen:
                continue
            seen.add(concept_path)
            try:
                raw = self._store.read_text(rel_path)
                parsed = parse_concept(raw, concept_path)
                text = self._embed_text(parsed)
                self._vector.upsert_concept(concept_path, text, parsed.frontmatter)
                response.indexed += 1
            except Exception as exc:
                response.errors.append(IngestError(path=rel_path, reason=str(exc)))

        present = self._vector.concept_paths()
        if rel_dir:
            prefix = rel_dir.strip("/")
            stale = [p for p in present if (p + "/").startswith(prefix + "/") or p == prefix]
            stale = [p for p in stale if p not in seen]
            if stale:
                self._vector.delete(stale)
                response.deleted = len(stale)
        return response

    def _embed_text(self, parsed) -> str:
        body = parsed.body.strip()
        snippet = body if len(body) <= 400 else body[:400]
        parts = [
            parsed.frontmatter.get("title", ""),
            parsed.frontmatter.get("description", ""),
            snippet,
        ]
        return "\n".join(p for p in parts if p)

    def _walk_markdown(self, rel_dir: str) -> list[str]:
        rel_dir = rel_dir.strip("/")
        walker = self._store.walk(rel_dir)
        return [rel for rel in walker if rel.endswith(".md") and rel.split("/")[-1] not in RESERVED]

    def _affected_roots(self, rel_dir: str) -> set[str]:
        roots = {rel_dir}
        for rel in self._walk_markdown(rel_dir):
            parent = PurePosixPath(rel).parent
            roots.add(str(parent) if str(parent) != "." else "")
        return roots