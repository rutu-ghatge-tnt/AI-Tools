# app/chatbot/memory.py
"""Session-based in-memory chat history management"""
from typing import Dict, List
from uuid import uuid4

# In-memory session history
SESSION_HISTORY: Dict[str, List[Dict[str, str]]] = {}

def get_or_create_session_id(request) -> str:
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid4())
    return session_id

def get_history(session_id: str) -> List[Dict[str, str]]:
    return SESSION_HISTORY.get(session_id, [])

def add_to_history(session_id: str, query: str, response: str):
    history = SESSION_HISTORY.get(session_id, [])
    history.append({"query": query, "response": response})
    SESSION_HISTORY[session_id] = history
