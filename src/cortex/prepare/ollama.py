import httpx

from cortex.prepare.llm import LLMProvider


class OllamaLLM(LLMProvider):
    def __init__(self, base_url: str, model: str, timeout: float = 300.0) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self._model = model

    def complete(self, system: str, user: str) -> str:
        response = self._client.post(
            "/api/chat",
            json={
                "model": self._model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
