from __future__ import annotations

import os
from typing import Protocol

from openai import OpenAI


class LLMProvider(Protocol):
    def extract(self, prompt: str) -> dict[str, object]:
        """Provider interface for extraction-style economic analysis."""


class DeepSeekProvider:
    """Thin provider wrapper that can be swapped with any OpenAI-compatible endpoint."""

    def __init__(self, api_key: str | None = None, base_url: str = "https://api.deepseek.com") -> None:
        self.client = OpenAI(api_key=api_key or os.getenv("DEEPSEEK_API_KEY", ""), base_url=base_url)

    def extract(self, prompt: str) -> dict[str, object]:
        response = self.client.responses.create(
            model="deepseek-reasoner",
            input=prompt,
        )
        output_text = getattr(response, "output_text", "") or ""
        if not output_text and hasattr(response, "output"):
            try:
                output_text = "\n".join(
                    str(part.text)
                    for item in response.output
                    for part in getattr(item, "content", [])
                    if getattr(part, "text", None)
                )
            except Exception:
                output_text = ""
        return {"raw_response": response, "output_text": output_text}
