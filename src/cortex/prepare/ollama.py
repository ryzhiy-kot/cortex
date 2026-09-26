from ollama import Client

from cortex.prepare.llm import LLMProvider


class OllamaLLM(LLMProvider):
    """Ollama chat client via the official SDK, so the OTel GenAI
    instrumentor can trace calls ("chat <model>" spans with usage)."""

    def __init__(self, base_url: str, model: str, timeout: float = 300.0) -> None:
        self._client = Client(host=base_url.rstrip("/"), timeout=timeout)
        self._model = model

    def complete(self, system: str, user: str) -> str:
        response = self._client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.message.content