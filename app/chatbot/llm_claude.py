# app/chatbot/llm_claude.py
"""Claude LLM integration via LangChain"""
try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    raise ImportError(
        "Claude Opus support requires `langchain-anthropic`. Install with:\n\npip install langchain-anthropic"
    )

from app.config import CLAUDE_API_KEY, CLAUDE_MODEL

def get_claude_llm():
    if CLAUDE_API_KEY is None:
        raise ValueError("CLAUDE_API_KEY must be set in your configuration.")
    try:
        return ChatAnthropic(
            api_key=CLAUDE_API_KEY,  # Use the string directly instead of SecretStr
            model_name=CLAUDE_MODEL,
            temperature=0.3,
            timeout=60,
            streaming=True,
        )
    except Exception as e:
        print(f"Warning: Could not initialize Claude client: {e}")
        print("Analysis will not be available without a valid API key.")
        return None
