import json

import yaml

from cortex.prepare.llm import LLMProvider


class StubLLM(LLMProvider):
    """Scriptable stand-in for the LLM used by tests and offline smoke runs.

    `review_plan(prompt) -> dict` returns the review JSON object; `author(prompt) -> str`
    returns the concept markdown. When not overridden, deterministic defaults apply.
    """

    def __init__(
        self,
        review_plan=None,
        author=None,
    ) -> None:
        self.review_plan = review_plan or self._default_review
        self.author = author or self._default_author
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        prompt = json.loads(user)
        if prompt["task"] == "REVIEW":
            return json.dumps(self.review_plan(prompt))
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
