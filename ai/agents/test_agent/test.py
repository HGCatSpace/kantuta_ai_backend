from langgraph.graph import MessagesState, START, END, StateGraph
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
import os
from dotenv import load_dotenv
load_dotenv()

class Info(BaseModel):
    """Informacion del usaurio"""
    id: str = Field(description="id del usuario.")
    name: str = Field(description="nombre del usuario.")
    age: str = Field(description="edad del usuario.")

google_llm = ChatGoogleGenerativeAI(
    model="gemini-3-flash-preview",
    temperature=0,
)

google_llm_structured = google_llm.with_structured_output(schema=Info)

class State(MessagesState):
    user_id: str
    user_name: str
    user_age: int

def node_1(state: State):
    new_state: State = {}
    id: str = state.get("user_id", None)
    name: str = state.get("user_name", None)
    age: int = state.get("user_age", 0)

    if id is None or name is None or age == 0:
        history = state.get("messages",[])
        schema: Info = google_llm_structured.invoke(history)
        new_state["user_id"] = schema.id
        new_state["user_name"] = schema.name
        new_state["user_age"] = schema.age
    
    return new_state

builder = StateGraph(State)
builder.add_node("node_1", node_1)
builder.add_edge(START,"node_1")
builder.add_edge("node_1", END)

agent = builder.compile()

class StateMessage(MessagesState):
    id: str
        
async def node_model(state: StateMessage):
    history = state.get("messages", [])
    response = await google_llm.invoke(history)
    return 

builder_msg = StateGraph(StateMessage)
builder_msg.add_node("node_model",node_model)
builder_msg.add_edge(START, "node_model")
builder_msg.add_edge("node_model", END)

agent_msg = builder_msg.compile()