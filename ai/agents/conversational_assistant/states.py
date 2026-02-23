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
    # --- DATOS ---
    document_ids: Optional[List[int]] # Lista de IDs de documentos para filtrar 
    # --- CONFIGURACIÓN DE RECUPERACIÓN (Retrieval) ---
    k_retrieval: Optional[int] 
    
    # Distancia máxima permitida. 
    score: Optional[float]

    # --- CONFIGURACIÓN DE GENERACIÓN (LLM) ---
    temperature: Optional[float] # Creatividad (0.0 a 1.0)
    top_p: Optional[float]       # Nucleus sampling (0.0 a 1.0)
    top_k: Optional[int]         # Token selection limit
    
    # --- CONFIGURACIÓN DE SYSTEM PROMPT ---
    content_instruction: Optional[str] # Instrucción del sistema dinámica

    question: str      # Entrada del usuario
    documents: List    # Salida del retrieve_node
    generation: str    # Salida del generate_node (o 'answer')