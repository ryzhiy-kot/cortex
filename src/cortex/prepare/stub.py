import json

import yaml
from pydantic import BaseModel

from cortex.prepare.llm import LLMProvider


class StubLLM(LLMProvider):
    """Scriptable stand-in for the LLM used by tests and offline smoke runs.

    `review_plan(prompt) -> dict` returns the review plan; `author(prompt) -> str`
    returns the concept markdown. When not overridden, deterministic defaults apply.
    A structured `output_type` is fulfilled by validating the callback's dict into
    that model — the same shape a real provider's structured output takes.
    """

    def __init__(
        self,
        review_plan=None,
        author=None,
    ) -> None:
        self.review_plan = review_plan or self._default_review
        self.author = author or self._default_author
        self.calls: list[tuple[str, str]] = []

    def complete(
        self,
        system: str,
        user: str,
        output_type: type[BaseModel] | None = None,
    ) -> str | BaseModel:
        self.calls.append((system, user))
        prompt = json.loads(user)
        if prompt["task"] == "REVIEW":
            plan = self.review_plan(prompt)
            if output_type is not None:
                return output_type.model_validate(plan)
            return plan
        return self.author(prompt)

    @staticmethod
    def _default_review(prompt: dict) -> dict:
        bundle = prompt.get("forced_bundle") or "knowledge"
        return {
            "bundle": bundle,
            "decisions": {
                name: {"action": "create", "reason": "new knowledge"}
                for name in prompt["files"]
            },
        }

    @staticmethod
    def _default_author(prompt: dict) -> str:
        title = prompt["source"]
        body = prompt["content"]
        existing = prompt.get("existing_concept")
        if isinstance(existing, dict) and existing.get("body"):
            body = f"{existing['body']}\n\n{body}".strip("\n")
        frontmatter = {
            "type": "reference",
            "title": title,
            "description": "stub-authored concept",
        }
        header = yaml.safe_dump(
            frontmatter, sort_keys=False, allow_unicode=True
        ).strip()
        return f"---\n{header}\n---\n\n# {title}\n\n{body}\n"
