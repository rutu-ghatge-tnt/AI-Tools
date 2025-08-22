# app/chatbot/llm_claude.py
"""Claude LLM integration via LangChain"""
try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    raise ImportError(
        "Claude Opus support requires `langchain-anthropic`. Install with:\n\npip install langchain-anthropic"
    )

from app.config import CLAUDE_API_KEY, CLAUDE_MODEL
from pydantic import SecretStr

def get_claude_llm():
    if CLAUDE_API_KEY is None:
        raise ValueError("CLAUDE_API_KEY must be set in your configuration.")
    return ChatAnthropic(
        api_key=SecretStr(CLAUDE_API_KEY),
        model_name=CLAUDE_MODEL,
        temperature=0.3,
        timeout=60,
        streaming=True,
        stop=None,  # Provide a suitable value or list of stop sequences if needed
    )
