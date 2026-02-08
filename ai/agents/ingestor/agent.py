from langgraph.graph import START, END, StateGraph

from ai.agents.ingestor.states import IngestionState
from ai.agents.ingestor.nodes.loader.node import document_loader_node
from ai.agents.ingestor.nodes.splitter.node import text_splitter_node
from ai.agents.ingestor.nodes.ingestor_node.node import vector_store_node

builder = StateGraph(IngestionState)

builder.add_sequence([document_loader_node, text_splitter_node, vector_store_node])
builder.add_edge(START, "document_loader_node")
builder.add_edge("vector_store_node", END)

agent = builder.compile()