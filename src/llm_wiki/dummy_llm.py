"""MockLLM wiring. LlamaIndex requires `Settings.llm`; we only use retrieval."""

from __future__ import annotations

from llama_index.core import Settings
from llama_index.core.llms import MockLLM

_INSTALLED = False


def install_dummy_llm() -> None:
    """Install a no-op LLM so retrieval paths never trigger OpenAI resolution."""
    global _INSTALLED
    if _INSTALLED:
        return
    # Assigning directly avoids reading Settings.llm, which would otherwise
    # trigger LlamaIndex's default resolver and pull in llama-index-llms-openai.
    Settings.llm = MockLLM(max_tokens=1)
    _INSTALLED = True
