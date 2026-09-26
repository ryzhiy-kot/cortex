from pydantic import BaseModel

from cortex.prepare.llm import LLMProvider


class VertexLLM(LLMProvider):
    """Gemini via pydantic-ai's native Google model providers.

    The auth path is chosen at construction:
    - an API key (`CORTEX_VERTEX_API_KEY`, else `GOOGLE_API_KEY` / `GEMINI_API_KEY`)
      selects `GoogleProvider` (Gemini Developer API);
    - otherwise `GoogleCloudProvider` (Vertex AI) is used with application default
      credentials from the environment (`GOOGLE_APPLICATION_CREDENTIALS`,
      `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`).

    Structured output is enforced via the API's JSON response mime type, so prose
    noise is impossible. Pydantic-ai's OpenTelemetry instrumentation emits
    `gen_ai.*` spans into the run's trace.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.0-flash-001",
        project: str | None = None,
        location: str | None = None,
    ) -> None:
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        if api_key:
            provider = GoogleProvider(api_key=api_key)
        else:
            from pydantic_ai.providers.google_cloud import GoogleCloudProvider

            provider = GoogleCloudProvider(project=project, location=location)
        self._model = GoogleModel(model, provider=provider)

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