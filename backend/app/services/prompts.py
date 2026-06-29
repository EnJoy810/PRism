"""Langfuse prompt management with hardcoded fallback.

Usage in agents:
    langfuse_prompt_name = "prism-security-agent"   # class attribute

BaseAgent.__init__ calls get_prompt() automatically.
If Langfuse is not configured or the prompt doesn't exist yet,
the hardcoded SYSTEM_PROMPT in each agent file is used as-is.
"""

import logging
import os

logger = logging.getLogger(__name__)

_client = None


def _langfuse():
    global _client
    if _client is None and os.environ.get("LANGFUSE_PUBLIC_KEY"):
        try:
            from langfuse import Langfuse
            _client = Langfuse()
        except Exception as e:
            logger.debug("langfuse client init failed: %s", e)
    return _client


def get_prompt(name: str, fallback: str) -> str:
    """Return prompt text from Langfuse, falling back to `fallback` if unavailable."""
    lf = _langfuse()
    if lf is None:
        return fallback
    try:
        return lf.get_prompt(name).compile()
    except Exception as e:
        logger.debug("langfuse prompt '%s' not found, using fallback: %s", name, e)
        return fallback


def push_prompt(name: str, text: str, labels: list[str] | None = None) -> bool:
    """Create or update a prompt in Langfuse. Returns True on success."""
    lf = _langfuse()
    if lf is None:
        logger.warning("push_prompt: Langfuse not configured (LANGFUSE_PUBLIC_KEY missing)")
        return False
    try:
        lf.create_prompt(name=name, prompt=text, labels=labels or ["production"])
        logger.info("push_prompt: uploaded '%s'", name)
        return True
    except Exception as e:
        logger.warning("push_prompt: failed for '%s': %s", name, e)
        return False
