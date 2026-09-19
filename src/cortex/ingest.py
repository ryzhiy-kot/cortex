from pathlib import PurePosixPath

from cortex.bundle.indexer import index_for
from cortex.bundle.local import RESERVED
from cortex.bundle.parser import parse_concept
from cortex.models import IngestError, IngestResponse
from cortex.vector.store import VectorStore


class Ingester:
    def __init__(self, store, vector: VectorStore, bundle: str) -> None:
        self._store = store
        self._vector = vector
        self._bundle = bundle

    def ingest(self, rel_dir: str) -> IngestResponse:
        response = IngestResponse()
        if rel_dir.startswith("/") or rel_dir == "..":
            response.errors.append(IngestError(path=rel_dir, reason="must be bundle-relative"))
            return response

        for root in sorted(self._affected_roots(rel_dir)):
            response.index_files += 1
            concepts = [(name, self._describe(root, name)) for name in self._store.list_markdown(root)]
            contents = index_for(root, concepts, self._store.list_subdirs(root))
            self._store.write_text(root, "index.md", contents)

        seen: set[str] = set()
        known = self._vector.concept_paths()
        for rel_path in sorted(self._walk_markdown(rel_dir)):
            concept_path = f"{self._bundle}/{rel_path[: -len('.md')]}"
            if concept_path in seen:
                continue
            seen.add(concept_path)
            try:
                raw = self._store.read_text(rel_path)
                parsed = parse_concept(raw, concept_path)
                text = self._embed_text(parsed)
                metadata = {**parsed.frontmatter, "bundle": self._bundle}
                self._vector.upsert_concept(concept_path, text, metadata)
                if concept_path in known:
                    response.updated += 1
                else:
                    response.indexed += 1
            except Exception as exc:  # noqa: BLE001 - lenient ingest: skip + report per-file
                response.errors.append(IngestError(path=f"{self._bundle}/{rel_path}", reason=str(exc)))

        if rel_dir:
            prefix = f"{self._bundle}/{rel_dir.strip('/')}".rstrip("/")
            present = self._vector.concept_paths()
            stale = [p for p in present if (p == prefix or p.startswith(prefix + "/")) and p not in seen]
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

    def _describe(self, rel_dir: str, name: str) -> str:
        rel_path = f"{rel_dir}/{name}" if rel_dir else name
        try:
            parsed = parse_concept(self._store.read_text(rel_path), name)
            return parsed.frontmatter.get("description") or ""
        except Exception:  # noqa: BLE001 - lenient ingest: index what reads
            return ""

    def _walk_markdown(self, rel_dir: str) -> list[str]:
        rel_dir = rel_dir.strip("/")
        return [rel for rel in self._store.walk(rel_dir) if rel.endswith(".md") and rel.rsplit("/", 1)[-1] not in RESERVED]

    def _affected_roots(self, rel_dir: str) -> set[str]:
        roots = {rel_dir}
        for rel in self._walk_markdown(rel_dir):
            parent = PurePosixPath(rel).parent
            roots.add(str(parent) if str(parent) != "." else "")
        return roots