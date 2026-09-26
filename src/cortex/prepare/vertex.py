from pydantic import BaseModel

from cortex.prepare.llm import LLMProvider


class VertexLLM(LLMProvider):
    """Gemini via pydantic-ai's native Google provider (API key auth).

    Structured output is enforced via the API's JSON response mime type, so prose
    noise is impossible. Pydantic-ai's OpenTelemetry instrumentation emits
    `gen_ai.*` spans into the run's trace. The API key comes from
    `CORTEX_VERTEX_API_KEY`, or from `GOOGLE_API_KEY` / `GEMINI_API_KEY` when none
    is passed.
    """

    def __init__(
        self, api_key: str | None = None, model: str = "gemini-2.0-flash-001"
    ) -> None:
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        self._model = GoogleModel(
            model,
            provider=GoogleProvider(api_key=api_key),
        )

    def complete(
        self,
        system: str,
        user: str,
        output_type: type[BaseModel] | None = None,
    ) -> BaseModel | str:
        from pydantic_ai import Agent

        agent = Agent(model=self._model, system_prompt=system, output_type=output_type)
        agent.instrument = True
        return agent.run_sync(user).output