import uuid
from pathlib import Path

from cortex.bundle.local import RESERVED, LocalBundleStore
from cortex.bundle.parser import parse_concept
from cortex.embeddings.ollama import OllamaEmbeddings
from cortex.embeddings.provider import EmbeddingProvider
from cortex.embeddings.sentence import SentenceTransformersEmbeddings
from cortex.embeddings.vertex import VertexEmbeddings
from cortex.ingest import Ingester
from cortex.models import ConceptCard, ConceptResponse, ListingResponse
from cortex.prepare.llm import LLMProvider
from cortex.prepare.ollama import OllamaLLM
from cortex.prepare.pipeline import PrepareRunner
from cortex.prepare.queue import PrepareQueue
from cortex.prepare.vertex import VertexLLM
from cortex.settings import EmbeddingProviderKind, LLMProviderKind, Settings
from cortex.telemetry import (
    init_tracing,
    instrument_ollama,
    setup_logging,
    task_run,
    tracer,
)
from cortex.vector.store import VectorStore


class Cortex:
    def __init__(
        self,
        settings: Settings,
        embeddings: EmbeddingProvider | None = None,
        llm: LLMProvider | None = None,
        prepare_sync: bool = False,
    ) -> None:
        self._settings = settings
        self._bundles_root = settings.bundles_root
        self.traces_path = settings.traces_path
        setup_logging(settings.log_path, settings.log_level)
        init_tracing(settings.traces_path, settings.trace_retention_days)
        self.embeddings = embeddings or _build_embeddings(settings)
        self.vector = VectorStore(
            path=str(settings.chroma_path),
            collection=settings.chroma_collection,
            embeddings=self.embeddings,
        )
        self.bundles: dict[str, LocalBundleStore] = {}
        self._load_bundles()
        llm = llm or _build_llm(settings)
        if isinstance(llm, OllamaLLM):
            instrument_ollama()
        runner = PrepareRunner(
            llm=llm,
            bundles_root=settings.bundles_root,
            staging_root=settings.staging_path,
            manifest_factory=self.manifest,
        )
        self.prepare = PrepareQueue(runner=runner, sync=prepare_sync)

    def bundle_names(self) -> list[str]:
        return sorted(self.bundles)

    def manifest(self) -> list[dict]:
        self._load_bundles()
        entries: list[dict] = []
        for bundle in sorted(self.bundles):
            store = self.bundles[bundle]
            for rel_md in store.walk():
                if Path(rel_md).name in RESERVED or not rel_md.endswith(".md"):
                    continue
                rel = rel_md.removesuffix(".md")
                concept_path = f"{bundle}/{rel}"
                try:
                    parsed = parse_concept(store.read_text(rel_md), concept_path)
                    entries.append(
                        {
                            "concept_path": concept_path,
                            "type": parsed.frontmatter.get("type", ""),
                            "title": parsed.frontmatter.get("title"),
                            "description": parsed.frontmatter.get("description"),
                        }
                    )
                except Exception:  # noqa: BLE001 - lenient manifest: unparsable concepts carry their path
                    entries.append({"concept_path": concept_path, "type": ""})
        return entries

    def _load_bundles(self) -> None:
        if not self._bundles_root.is_dir():
            self.bundles = {}
            return
        self.bundles = {
            child.name: LocalBundleStore(child)
            for child in sorted(self._bundles_root.iterdir())
            if child.is_dir()
        }

    def _store(self, bundle: str) -> LocalBundleStore:
        store = self.bundles.get(bundle)
        if store is None:
            raise FileNotFoundError(f"unknown bundle: {bundle}")
        return store

    def ingest(self, bundle: str | None = None, path: str | None = None) -> dict:
        self._load_bundles()
        names = [bundle] if bundle else sorted(self.bundles)
        run_id = uuid.uuid4().hex[:12]
        with task_run("ingest", run_id, bundles=",".join(names), path=path or "") as span:
            response = {
                "run_id": run_id,
                "indexed": 0,
                "updated": 0,
                "deleted": 0,
                "index_files": 0,
                "errors": [],
            }
            for name in names:
                with tracer().start_as_current_span("ingest.bundle") as bundle_span:
                    bundle_span.set_attribute("cortex.bundle", name)
                    store = self._store(name)
                    ingester = Ingester(store, self.vector, name)
                    partial = ingester.ingest(path or "")
                    for key in ("indexed", "updated", "deleted", "index_files"):
                        response[key] += getattr(partial, key)
                    bundle_span.set_attribute("cortex.indexed", partial.indexed)
                    bundle_span.set_attribute("cortex.updated", partial.updated)
                    bundle_span.set_attribute("cortex.deleted", partial.deleted)
                    response["errors"].extend(error.model_dump() for error in partial.errors)
            span.set_attribute("cortex.status", "failed" if response["errors"] else "done")
            return response

    def search(self, request) -> dict:
        from cortex.search import search

        return [result.model_dump() for result in search(request, self.vector)]

    def _split_bundle(self, qualified_path: str) -> tuple[str, str]:
        bundle, _, rest = qualified_path.partition("/")
        return bundle, rest

    def read_concept(self, concept_path: str) -> ConceptResponse:
        concept_path = concept_path.strip("/")
        bundle, rel = self._split_bundle(concept_path)
        store = self._store(bundle)
        rel_file = f"{rel}.md" if rel else concept_path
        raw = store.read_text(rel_file)
        parsed = parse_concept(raw, f"{bundle}/{rel}")
        return ConceptResponse(
            concept_path=f"{bundle}/{rel}",
            frontmatter=parsed.frontmatter,
            body=parsed.body,
            links=parsed.links,
        )

    def list_dir(self, qualified_dir: str) -> ListingResponse:
        qualified_dir = qualified_dir.strip("/")
        bundle, rel_dir = self._split_bundle(qualified_dir)
        store = self._store(bundle)
        concepts = store.list_markdown(rel_dir)
        subdirs = store.list_subdirs(rel_dir)
        index_rel = f"{rel_dir}/index.md" if rel_dir else "index.md"
        if store.exists(index_rel):
            index_content = store.read_text(index_rel)
        else:
            index_content = None
        return ListingResponse(
            dir=f"{bundle}/{rel_dir}" if rel_dir else bundle,
            subdirs=subdirs,
            concepts=[self._card(bundle, rel_dir, name) for name in concepts],
            index_content=index_content,
        )

    def _card(self, bundle: str, rel_dir: str, name: str) -> ConceptCard:
        if not name.endswith(".md"):
            name = f"{name}.md"
        rel_path = f"{rel_dir}/{name}" if rel_dir else name
        path = rel_path[: -len(".md")]
        try:
            parsed = parse_concept(self._store(bundle).read_text(rel_path), path)
            return ConceptCard(
                concept_path=f"{bundle}/{path}",
                type=parsed.frontmatter.get("type", ""),
                title=parsed.frontmatter.get("title"),
                description=parsed.frontmatter.get("description"),
            )
        except Exception:  # noqa: BLE001 - lenient listing: unparsable concepts shown as bare paths
            return ConceptCard(concept_path=f"{bundle}/{path}", type="")


def _build_embeddings(settings: Settings) -> EmbeddingProvider:
    match settings.embedding_provider:
        case EmbeddingProviderKind.OLLAMA:
            return OllamaEmbeddings(
                settings.ollama_base_url, settings.ollama_embedding_model
            )
        case EmbeddingProviderKind.VERTEX:
            if not settings.vertex_project:
                raise ValueError(
                    "CORTEX_VERTEX_PROJECT is required when embedding_provider=vertex"
                )
            return VertexEmbeddings(
                settings.vertex_project,
                settings.vertex_location,
                settings.vertex_embedding_model,
            )
        case EmbeddingProviderKind.SENTENCE_TRANSFORMERS:
            return SentenceTransformersEmbeddings()


def _build_llm(settings: Settings) -> LLMProvider:
    match settings.llm_provider:
        case LLMProviderKind.OLLAMA:
            return OllamaLLM(settings.ollama_base_url, settings.ollama_llm_model)
        case LLMProviderKind.VERTEX:
            if not settings.vertex_project:
                raise ValueError(
                    "CORTEX_VERTEX_PROJECT is required when llm_provider=vertex"
                )
            return VertexLLM(
                settings.vertex_project,
                settings.vertex_location,
                settings.vertex_llm_model,
            )
