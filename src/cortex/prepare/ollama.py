from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.settings import ModelSettings

from cortex.prepare.llm import LLMProvider


class OllamaLLM(LLMProvider):
    """Ollama chat via pydantic-ai's native Ollama model and provider.

    Structured outputs are enforced by Ollama's grammar-constrained decoder
    (`response_format.json_schema`), so prose noise is impossible. Pydantic-ai's
    OpenTelemetry instrumentation emits `gen_ai.*` spans into the run's trace.
    """

    def __init__(self, base_url: str, model: str, timeout: float = 300.0) -> None:
        self._model = OllamaModel(
            model,
            provider=OllamaProvider(base_url=base_url.rstrip("/")),
            settings=ModelSettings(timeout=timeout),
        )

    def complete(
        self,
        system: str,
        user: str,
        output_type: type[BaseModel] | None = None,
    ) -> BaseModel | str:
        agent = Agent(model=self._model, system_prompt=system, output_type=output_type)
        agent.instrument = True
        return agent.run_sync(user).output