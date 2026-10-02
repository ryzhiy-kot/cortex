from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.settings import ModelSettings

from cortex.prepare.llm import LLMProvider


def _openai_compat_base(base_url: str) -> str:
    """Ollama's OpenAI-compatible chat endpoint lives under /v1.

    `CORTEX_OLLAMA_BASE_URL` is a plain host (embeddings hit the native
    `/api/embed`), so derive the OpenAI-compatible base by appending `/v1`,
    deduplicated for callers that already suffix it.
    """
    base = base_url.rstrip("/")
    return base if base.endswith("/v1") else f"{base}/v1"


class OllamaLLM(LLMProvider):
    """Ollama chat via pydantic-ai's native Ollama model and provider.

    Structured outputs are enforced by Ollama's grammar-constrained decoder
    (`response_format.json_schema`), so prose noise is impossible. Pydantic-ai's
    OpenTelemetry instrumentation emits `gen_ai.*` spans into the run's trace.
    """

    def __init__(self, base_url: str, model: str, timeout: float = 300.0) -> None:
        self._model = OllamaModel(
            model,
            provider=OllamaProvider(base_url=_openai_compat_base(base_url)),
            settings=ModelSettings(timeout=timeout),
        )

    def complete(
        self,
        system: str,
        user: str,
        output_type: type[BaseModel] | None = None,
    ) -> str | BaseModel:
        agent = Agent(
            model=self._model,
            system_prompt=system,
            output_type=str if output_type is None else output_type,
        )
        agent.instrument = True
        return agent.run_sync(user).output
