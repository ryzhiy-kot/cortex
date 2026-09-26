from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
        output_type: type[BaseModel] | None = None,
    ) -> BaseModel | str:
        """Complete a chat turn.

        With `output_type` set, the provider returns structured output already
        validated into that pydantic model (schema enforced at generation time by
        the model provider); otherwise it returns the raw text (the OKF concept
        file authored for Prepare). Only the Prepare review step asks for a
        structured output.
        """
        ...