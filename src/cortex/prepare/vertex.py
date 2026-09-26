from pydantic import BaseModel

from cortex.prepare.llm import LLMProvider


class VertexLLM(LLMProvider):
    """Gemini via Google Cloud (Vertex AI), driven through pydantic-ai.

    Structured outputs are enforced via the API's JSON response mime type, so
    prose noise is impossible. Pydantic-ai's OpenTelemetry instrumentation emits
    `gen_ai.*` spans into the run's trace. Requires Google Cloud application
    default credentials (`GOOGLE_APPLICATION_CREDENTIALS`) plus
    `CORTEX_VERTEX_PROJECT` / `CORTEX_VERTEX_LOCATION`.
    """

    def __init__(
        self, project: str, location: str, model: str = "gemini-2.0-flash-001"
    ) -> None:
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google_cloud import GoogleCloudProvider

        self._model = GoogleModel(
            model,
            provider=GoogleCloudProvider(project=project, location=location),
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