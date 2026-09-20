import hashlib
from pathlib import Path

import pytest

from cortex.api.app import create_app
from cortex.context import Cortex
from cortex.embeddings.provider import EmbeddingProvider
from cortex.settings import Settings

BUNDLES_ROOT = Path(__file__).resolve().parent.parent / "examples" / "bundles"


class StubEmbeddings(EmbeddingProvider):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        digest = hashlib.sha256("\n".join(texts).encode()).hexdigest()
        return [[float(int(digest[i : i + 2], 16)) / 255.0 for i in range(0, 16, 2)]]


@pytest.fixture
def bundles_root(tmp_path: Path) -> Path:
    import shutil

    dest = tmp_path / "bundles"
    shutil.copytree(BUNDLES_ROOT, dest)
    for generated in dest.rglob("index.md"):
        generated.unlink()
    return dest


@pytest.fixture
def settings(tmp_path: Path, bundles_root: Path) -> Settings:
    return Settings(bundles_root=bundles_root, chroma_path=tmp_path / "chroma", chroma_collection="test_concepts")


@pytest.fixture
def cortex(settings: Settings) -> Cortex:
    return Cortex(settings, embeddings=StubEmbeddings())


@pytest.fixture
def client(cortex: Cortex, settings: Settings):
    from fastapi.testclient import TestClient

    app = create_app(settings, cortex=cortex)
    with TestClient(app) as test_client:
        yield test_client