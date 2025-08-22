# app/chatbot/api.py
from fastapi import APIRouter
from pydantic import BaseModel
from app.chatbot.rag_pipeline import get_rag_chain
from fastapi.responses import JSONResponse, StreamingResponse
import asyncio
import json

router = APIRouter()
rag_chain = get_rag_chain()

OFFENSIVE_WORDS = {"stupid", "idiot", "dumb", "hate", "shut up"}

class ChatTurn(BaseModel):
    query: str
    response: str

class ChatRequest(BaseModel):
    query: str
    history: list[ChatTurn] = []

def is_offensive(text: str) -> bool:
    text_lower = text.lower()
    return any(word in text_lower for word in OFFENSIVE_WORDS)

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    user_query = request.query.strip()
    clean_query = user_query.rstrip("?!.").lower()

    identity_triggers = {
        "who are you", "what is your name", "tell me about yourself",
        "who is skinsage", "are you a bot", "your identity"
    }

    if clean_query in identity_triggers:
        return JSONResponse(content={
            "answer": "🌟 Welcome to SkinBB Metaverse! I'm SkinSage, your wise virtual skincare assistant. Ask me anything about skincare — ingredients, routines, or products!"
        })

    if is_offensive(user_query):
        return JSONResponse(content={
            "answer": "I'm here to help with skincare, not to battle words. Let's keep it friendly! 😊"
        })

    # Format frontend-passed history
    chat_context = "\n".join([
        f"User: {turn.query}\nAssistant: {turn.response}"
        for turn in request.history[-5:]
        if turn.query and turn.response
    ])

    rag_inputs = {
        "query": user_query,
        "history": chat_context
    }

    async def stream_response():
        try:
            rag_result = rag_chain.invoke(rag_inputs)
            answer = rag_result.get("result", "").strip()
            answer = answer.replace("\\n", "\n")  # Convert escaped backslash-n into real newline
        except Exception as e:
            print("RAG error:", e)
            answer = "Sorry, something went wrong while processing your question."

        for sentence in answer.split("\n"):
            if sentence.strip():
                yield json.dumps({"response": sentence + "\n", "done": False}) + "\n"
                await asyncio.sleep(0.05)

        yield json.dumps({"response": "", "done": True}) + "\n"

    return StreamingResponse(stream_response(), media_type="application/json")
