from typing import List, Tuple, Union, Optional
from langgraph.graph import MessagesState
from langchain_core.documents import Document

class RetrievalState(MessagesState):
    """
    Estado dinámico del agente RAG.
    Controla tanto los datos como la configuración de ejecución.
    """
    # --- DATOS ---
    context: List[Tuple[Document, float]] 
    # --- CONFIGURACIÓN DE RECUPERACIÓN (Retrieval) ---
    k_retrieval: Optional[int] 
    
    # Distancia máxima permitida. 
    score: Optional[float]

    # --- CONFIGURACIÓN DE GENERACIÓN (LLM) ---
    temperature: Optional[float] # Creatividad (0.0 a 1.0)
    top_p: Optional[float]       # Nucleus sampling (0.0 a 1.0)
    top_k: Optional[int]         # Token selection limit