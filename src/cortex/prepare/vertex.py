from cortex.prepare.llm import LLMProvider


class VertexLLM(LLMProvider):
    def __init__(
        self, project: str, location: str, model: str = "gemini-2.0-flash-001"
    ) -> None:
        import vertexai
        from vertexai.generative_models import GenerativeModel

        vertexai.init(project=project, location=location)
        self._model = GenerativeModel(model)

    def complete(self, system: str, user: str) -> str:
        response = self._model.generate_content([system, user])
        return response.text
