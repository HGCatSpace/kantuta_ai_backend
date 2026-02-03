from typing import Union
from fastapi import FastAPI
from pydantic import BaseModel
from langchain.messages import HumanMessage

from ai.agents.test_agent.test import agent

app = FastAPI()

class Message(BaseModel):
    message: str

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.post("/chat/{chat_id}")
async def chat(chat_id: str, item: Message):
    human_message = HumanMessage(content=item.message)
    response = await agent.ainvoke({"messages": [human_message]})
    return {"chat_id": chat_id, "answer": response}

@app.post("/chat/{chat_id}/stream")
async def stream_chat(chat_id: str, message: Message):
    human_message = HumanMessage