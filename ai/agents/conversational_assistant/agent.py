from langgraph.graph import START, END, StateGraph
from ai.agents.conversational_assistant.nodes.retriever.node import retrieve_node
from ai.agents.conversational_assistant.nodes.generator.node import generate_node
from ai.agents.conversational_assistant.states import RetrievalState


builder = StateGraph(RetrievalState)

builder.add_sequence([retrieve_node, generate_node])
builder.add_edge(START, "retrieve_node")
builder.add_edge("generate_node", END)

agent = builder.compile()